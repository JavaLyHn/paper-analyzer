#!/usr/bin/env python3
"""Extract figures, tables and code/algorithm blocks from a PDF paper.

Usage:
    python extract_assets.py <pdf-path> <output-dir>

Layout produced under <output-dir>:
    figures/figure-<n>.png
    tables/table-<n>.png
    code/algorithm-<n>.md        (text wrapped in ```)
    code/listing-<n>.md
    manifest.json                (list of everything extracted)

Numbering follows the paper's own numbering (Figure 1 -> figure-1.png).
Items without a clear caption are silently skipped; the manifest tells the
caller what was actually produced.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from itertools import permutations
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF
import pdfplumber

# Caption patterns. Order matters: more specific first.
#
# A real caption MUST be one of:
#   "Figure 1: Title"   (ACM/IEEE convention — colon)
#   "Figure 1. Title"   (Springer/Elsevier convention — period)
#   "Algorithm 1 Title" (no separator, but next token is capitalized)
#
# We MUST NOT match body-text references like:
#   "Fig. 7 provides the full protocol..."  (lowercase after the number)
#   "as shown in Figure 3 the result..."    (block doesn't start with Figure)
#
# The `^\s*` anchor handles the second case; the post-digit `(?:\s*[:.]|\s+[A-Z])`
# rejects body text where a lowercase word follows the number.
#
# IGNORECASE is dropped on purpose: real captions in academic PDFs always use
# canonical capitalization ("Figure", "Fig.", "Table"). Lowercased "figure 1:"
# inside body text is almost never a caption.
CAPTION_PATTERNS = [
    ("algorithm", re.compile(r"^\s*(?:Algorithm|Alg\.?)\s+(\d+)(?:\s*[:.]|\s+[A-Z])")),
    ("listing",   re.compile(r"^\s*Listing\s+(\d+)(?:\s*[:.]|\s+[A-Z])")),
    ("table",     re.compile(r"^\s*Table\s+(\d+)(?:\s*[:.]|\s+[A-Z])")),
    ("figure",    re.compile(r"^\s*(?:Figure|Fig\.?)\s+(\d+)(?:\s*[:.]|\s+[A-Z])")),
]

# Maximum fraction of page height to look above/below a caption for the asset.
# This is only a safety cap; the smart algorithm in asset_region() normally
# stops earlier when it hits an unrelated text block.
LOOKUP_FRACTION = 0.7

# Minimum visual gap (in points) between a text block and the asset block.
# Used to detect "this text block is just adjacent body text, not part of the
# figure/table/algorithm region".
GAP_THRESHOLD = 6

# Render resolution for PNG snapshots. 300 DPI is the sweet spot between
# legibility (math symbols, small chart labels) and file size for academic PDFs.
RENDER_DPI = 300

# A body-text paragraph must be at least this many characters to count as a
# region boundary above/below a figure. Shorter blocks (pseudocode lines,
# math expressions, figure labels) are NOT boundaries — they're likely the
# figure's own content.
BODY_TEXT_MIN_CHARS = 100

# A body-text paragraph must span at least this fraction of the column width
# to count as a boundary. Narrow blocks (e.g. labels inside a figure) are
# excluded.
BODY_TEXT_MIN_WIDTH_FRAC = 0.75

# A conservative minimum upper bound (in points from page top) — used when
# we cannot detect any obvious page header on the current page. We intentionally
# keep this small so it doesn't eat the first row of an asset that starts very
# near the top of the page; the actual header band is detected per-page by
# `_page_header_y` below.
PAGE_HEADER_BAND_MIN = 30.0

# Any text block whose bottom y is below this threshold is considered a
# candidate for being part of the page header (running title, page number,
# conference info). This is well above the typical page-header band of
# ~20-40pt but below where the first real body content typically begins
# (~70-85pt in most templates).
PAGE_HEADER_CANDIDATE_MAX_Y = 75.0

# When looking above a figure caption for the figure's body via vector
# drawings (protocol boxes, chart frames, etc.), how far up to scan. Beyond
# this the drawing is likely from a different figure or page artifact.
DRAWING_LOOKUP_MAX_GAP = 350.0

# Minimum width/height of a drawing rect for it to count as "the figure"
# (filters out single lines, axis ticks, tiny markers).
MIN_DRAWING_W = 40.0
MIN_DRAWING_H = 20.0


@dataclass
class Caption:
    kind: str            # figure / table / algorithm / listing
    number: int          # paper's own numbering
    page: int            # 0-indexed
    bbox: tuple          # (x0, y0, x1, y1) of the caption text block
    text: str            # caption snippet, truncated


def find_captions(doc: fitz.Document) -> list[Caption]:
    """Scan every page, return all captions in paper order."""
    captions: list[Caption] = []
    for page_idx, page in enumerate(doc):
        blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        for bx0, by0, bx1, by1, text, *_ in blocks:
            stripped = (text or "").strip()
            if not stripped:
                continue
            for kind, pattern in CAPTION_PATTERNS:
                m = pattern.match(stripped)
                if m:
                    captions.append(Caption(
                        kind=kind,
                        number=int(m.group(1)),
                        page=page_idx,
                        bbox=(bx0, by0, bx1, by1),
                        text=stripped[:200].replace("\n", " "),
                    ))
                    break
    # Deduplicate: a caption can sometimes appear in both a text block and a span.
    seen = set()
    deduped = []
    for cap in captions:
        key = (cap.kind, cap.number, cap.page)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cap)
    return deduped


def _overlap_fraction_of(target: tuple, other: tuple) -> float:
    """How much does `other` cover `target` horizontally, as a fraction of target width?

    Asymmetric on purpose: we want to know if `other` spans the column that
    `target` lives in. Narrow labels (e.g. text inside a figure) score low
    even if they sit horizontally within the caption, because they don't
    span the column.
    """
    t_left, t_right = target
    o_left, o_right = other
    overlap = max(0.0, min(t_right, o_right) - max(t_left, o_left))
    target_w = max(1.0, t_right - t_left)
    return overlap / target_w


def _detect_text_columns(all_blocks: list[tuple], page_w: float) -> list[tuple[float, float]]:
    """Detect column ranges on a page by inspecting text block left-edges.

    Returns a list of (col_left, col_right) tuples. If only one column is
    detected (e.g. a single-column page or one with too few text blocks),
    returns ``[(0, page_w)]``.

    Why this exists: column-width detection via paragraph-block width fails
    on pages where the only blocks are pseudocode or table cells — those
    blocks aren't paragraph-like and the column-width fallback collapses to
    `page_w * 0.9`, which then mis-classifies a 2-column page as single-col
    and lets horizontal expansion swallow the neighbour column's content.
    Left-edge clustering, in contrast, works whatever the blocks contain.
    """
    left_edges: list[float] = []
    for bx0, _, _, _, btext, *_ in all_blocks:
        s = (btext or "").strip()
        if len(s) < 5:
            continue
        left_edges.append(bx0)
    if len(left_edges) < 5:
        return [(0.0, page_w)]
    mid = page_w / 2
    left_half = [x for x in left_edges if x < mid]
    right_half = [x for x in left_edges if x >= mid]
    if len(left_half) >= 3 and len(right_half) >= 3:
        l_start = min(left_half)
        r_start = min(right_half)
        return [
            (max(0.0, l_start - 4), r_start - 4),
            (max(0.0, r_start - 4), page_w),
        ]
    return [(0.0, page_w)]


def _is_paragraph_like(text: str) -> bool:
    """True if the text reads like prose, not a stacked column of short labels.

    PyMuPDF's `blocks` extractor can join cells of a wide table row into one
    block (e.g. `"Initialization (KB)\\nOne Version Update/Recovery (KB)\\nGit\\n…"`)
    or stack pseudocode/chart labels the same way. Such blocks meet the
    100-char length threshold but they're table content, not body prose, and
    must NOT be treated as a section boundary — otherwise the table's own
    header row fences off the table from its caption.

    Heuristic: real prose lines average ~80-110 chars (typical column width);
    stacked labels average <20. 40 is a conservative cutoff.
    """
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    avg_len = sum(len(l) for l in lines) / len(lines)
    return avg_len >= 40


def _detect_column_width(all_blocks: list[tuple], page_w: float) -> float:
    """Return the dominant column width on the page in points.

    Looks at paragraph-like text blocks with paragraph-length content
    (>= BODY_TEXT_MIN_CHARS) and returns the median width among them. Median
    is more robust than max against outliers like full-width table rows on a
    2-column page. Stacked-cell blocks are filtered via `_is_paragraph_like`
    so they don't pull the median up to full-page width.
    """
    widths = []
    for bx0, _, bx1, _, btext, *_ in all_blocks:
        stripped = (btext or "").strip()
        if len(stripped) < BODY_TEXT_MIN_CHARS:
            continue
        if not _is_paragraph_like(stripped):
            continue
        widths.append(bx1 - bx0)
    if not widths:
        return page_w * 0.9
    widths.sort()
    return widths[len(widths) // 2]


def _page_header_y(all_blocks: list[tuple]) -> float:
    """Return the y at which body content begins (below any page header).

    A page header is the running-title / page-number / venue band at the very
    top of every page (e.g. "CCS '25, October 13-17, 2025, Taipei", "USENIX
    Association ... 2043"). We must NOT extend an asset region into that band.

    Heuristic: any text block whose *bottom* sits within
    PAGE_HEADER_CANDIDATE_MAX_Y of the page top is part of the page header.
    Real body content (tables, figure boxes, prose) typically begins at
    y >= 75 in single-column layouts and y >= 85 in two-column ones. If no
    such block exists, return PAGE_HEADER_BAND_MIN so we don't crop the
    first row of an asset that starts very near the top.
    """
    bottom = 0.0
    for b in all_blocks:
        _, by0, _, by1, text, *_ = b
        if not (text or "").strip():
            continue
        if by1 < PAGE_HEADER_CANDIDATE_MAX_Y:
            bottom = max(bottom, by1)
    if bottom > 0:
        return bottom + GAP_THRESHOLD
    return PAGE_HEADER_BAND_MIN


def _drawings_in_column_near_caption(
    page: fitz.Page,
    cap_bbox: tuple,
    column: tuple[float, float] | None,
    direction: str,
    y_limit: float | None = None,
) -> fitz.Rect | None:
    """Return the bounding rect of all vector drawings that form the figure body.

    Many figures in academic PDFs have a vector-drawn border or frame:
    protocol pseudocode boxes have a rectangle border, charts have an axis
    frame, system diagrams have boxes connected by arrows. PyMuPDF's
    `page.get_drawings()` exposes these directly — and they are far more
    reliable for figure-extent detection than text-block boundary heuristics,
    which mistake the figure's own pseudocode lines for body prose.

    Strategy:
      * Look at drawings on the same side (above for caption-below figures,
        below for caption-above figures).
      * Drawing must overlap caption's column horizontally — this prevents
        the right-column figure from grabbing the left-column figure's box.
      * Drawing must be within DRAWING_LOOKUP_MAX_GAP of the caption — beyond
        that it likely belongs to a different figure.
      * Drawing must be at least MIN_DRAWING_W × MIN_DRAWING_H — filters out
        thin underlines, single-line strokes, axis ticks.
      * Union all qualifying drawings into one rect.

    Returns None if no qualifying drawings are found (e.g. a photo-only
    figure with no vector content, or a stub figure).
    """
    try:
        drawings = page.get_drawings()
    except Exception:
        return None

    cx0, cy0, cx1, cy1 = cap_bbox
    cap_cx = (cx0 + cx1) / 2

    rects: list[fitz.Rect] = []
    for d in drawings:
        r = d.get("rect") if isinstance(d, dict) else None
        if r is None:
            continue
        w = r.x1 - r.x0
        h = r.y1 - r.y0
        if w < MIN_DRAWING_W or h < MIN_DRAWING_H:
            continue

        if direction == "above":
            # caption is below the figure — drawing must end above caption top
            if r.y1 > cy0 + 1:
                continue
            if r.y1 < cy0 - DRAWING_LOOKUP_MAX_GAP:
                continue
            # y_limit (if given) bounds how far up we look — e.g. another
            # caption above this one fences off its own figure's drawings.
            # If the drawing crosses that limit, skip it entirely.
            if y_limit is not None and r.y0 < y_limit:
                continue
        else:  # "below"
            # caption is above the figure — drawing must start below caption bottom
            if r.y0 < cy1 - 1:
                continue
            if r.y0 > cy1 + DRAWING_LOOKUP_MAX_GAP:
                continue
            if y_limit is not None and r.y1 > y_limit:
                continue

        # Column constraint: the drawing must overlap the caption's column.
        # We accept either "caption center is inside drawing" OR "drawing
        # significantly overlaps caption width" — the first handles cases
        # where the figure is wider than the caption, the second handles
        # narrow figures.
        if column is not None:
            col_l, col_r = column
            if r.x0 >= col_r - 5 or r.x1 <= col_l + 5:
                continue
        else:
            if r.x1 < cap_cx - 200 or r.x0 > cap_cx + 200:
                continue

        rects.append(r)

    if not rects:
        return None

    x0 = min(r.x0 for r in rects)
    y0 = min(r.y0 for r in rects)
    x1 = max(r.x1 for r in rects)
    y1 = max(r.y1 for r in rects)
    return fitz.Rect(x0, y0, x1, y1)


def _looks_like_caption(text: str) -> bool:
    """Return True if a text block starts with a Figure/Table/Algorithm/Listing N caption."""
    stripped = (text or "").strip()
    for _, pat in CAPTION_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def asset_region(
    page: fitz.Page,
    caption: Caption,
    all_blocks: list[tuple],
    captions_on_page: list[Caption],
    other_table_bboxes: list[tuple] = (),
) -> fitz.Rect:
    """Compute the page region that likely contains the asset.

    Strategy by kind:

    * **figure** — caption is typically *below* the figure. We try to find
      the figure body via `page.get_drawings()` first (protocol boxes,
      chart frames, diagram lines). If a drawing in the caption's column
      sits just above the caption, its top is the figure top.
    * **algorithm/listing** — caption typically *above* the pseudocode.
      Same drawing-based detection but looking *below* the caption.
    * **table** — caption can be above (Springer/ACM newer) or below
      (ACM older / Springer). Pick whichever side has the larger gap to
      non-table content.

    Boundary detection — these mark where a non-asset region ends or begins:
      1. **Other captions** in the same column.
      2. **Real body-text paragraphs** — wide (>=75% of column) AND long
         (>=100 chars) AND paragraph-like (avg line >= 40 chars). But
         blocks that lie *inside* a large vector-drawing rect are figure
         content, NOT body prose — they're skipped.
      3. **Page header band** — top PAGE_HEADER_BAND points of the page.
      4. **Other pdfplumber tables** on the page.

    Drawings dominate boundary detection for figures because the figure's
    own pseudocode/text lines used to be incorrectly classified as body
    prose, fencing the figure off from its caption.
    """
    page_h = page.rect.height
    page_w = page.rect.width
    x0, y0, x1, y1 = caption.bbox
    cap_x_range = (x0, x1)
    cap_w = x1 - x0
    cap_center = (x0 + x1) / 2

    # Column layout detection.
    column_width = _detect_column_width(all_blocks, page_w)
    columns = _detect_text_columns(all_blocks, page_w)
    two_column = column_width < page_w * 0.65
    spans_columns = cap_w > column_width * 1.1

    # The column containing this caption (used as horizontal clipping bound).
    caption_col: tuple[float, float] | None = None
    for cl, cr in columns:
        if cl <= cap_center <= cr:
            caption_col = (cl, cr)
            break
    if caption_col is not None:
        col_w = caption_col[1] - caption_col[0]
        if cap_w > col_w * 0.9:
            # Wide caption — figure is a full-width float across both columns.
            caption_col = (0.0, page_w)

    # Initial horizontal extent.
    if two_column and not spans_columns:
        left = max(0, x0 - 6)
        right = min(page_w, x1 + 6)
    elif two_column and spans_columns:
        left = 0
        right = page_w
    else:
        half = max(column_width / 2 + 10, cap_w / 2 + 10)
        left = max(0, cap_center - half)
        right = min(page_w, cap_center + half)

    # Cache all drawings on the page (used for both vertical extent and
    # "is this block inside a figure" check).
    try:
        all_drawings_raw = page.get_drawings()
    except Exception:
        all_drawings_raw = []
    big_drawings: list[fitz.Rect] = []
    for d in all_drawings_raw:
        r = d.get("rect") if isinstance(d, dict) else None
        if r is None:
            continue
        if (r.x1 - r.x0) < MIN_DRAWING_W or (r.y1 - r.y0) < MIN_DRAWING_H:
            continue
        big_drawings.append(r)

    def block_inside_drawing(bx0_: float, by0_: float, bx1_: float, by1_: float) -> bool:
        """True if the block's center sits inside any large vector-drawn rect.

        Such blocks are figure content (pseudocode steps, chart annotations,
        diagram labels) and must NOT count as body-text boundaries.
        """
        bcx = (bx0_ + bx1_) / 2
        bcy = (by0_ + by1_) / 2
        for r in big_drawings:
            if r.x0 - 2 <= bcx <= r.x1 + 2 and r.y0 - 2 <= bcy <= r.y1 + 2:
                return True
        return False

    # Drawing-based vertical extent — strong signal for figures with a frame.
    # We bound the drawing search by the nearest other caption on the same
    # column: if another figure's caption sits above ours, its body fills the
    # space between the two captions and must not be swallowed.
    nearest_caption_above_y: float | None = None
    nearest_caption_below_y: float | None = None
    for other in captions_on_page:
        if other is caption:
            continue
        if other.kind == caption.kind and other.number == caption.number:
            continue
        # Only consider captions whose horizontal extent overlaps this caption's
        # column — captions in the other column don't fence us off.
        if _overlap_fraction_of(cap_x_range, (other.bbox[0], other.bbox[2])) < 0.3:
            continue
        if other.bbox[3] < y0 - GAP_THRESHOLD:
            if nearest_caption_above_y is None or other.bbox[3] > nearest_caption_above_y:
                nearest_caption_above_y = other.bbox[3]
        elif other.bbox[1] > y1 + GAP_THRESHOLD:
            if nearest_caption_below_y is None or other.bbox[1] < nearest_caption_below_y:
                nearest_caption_below_y = other.bbox[1]

    drawing_above = None
    drawing_below = None
    if caption.kind == "figure":
        drawing_above = _drawings_in_column_near_caption(
            page, caption.bbox, caption_col, "above",
            y_limit=nearest_caption_above_y,
        )
    elif caption.kind in ("algorithm", "listing"):
        drawing_below = _drawings_in_column_near_caption(
            page, caption.bbox, caption_col, "below",
            y_limit=nearest_caption_below_y,
        )

    # Standard boundary detection (for cases without a drawing frame).
    boundaries_above: list[float] = []
    boundaries_below: list[float] = []

    def consider_boundary(by0_: float, by1_: float, bx0_: float, bx1_: float) -> None:
        if _overlap_fraction_of(cap_x_range, (bx0_, bx1_)) < 0.3:
            return
        if by1_ <= y0 - GAP_THRESHOLD:
            boundaries_above.append(by1_)
        elif by0_ >= y1 + GAP_THRESHOLD:
            boundaries_below.append(by0_)

    # (1) Other captions
    for other in captions_on_page:
        if other is caption:
            continue
        if other.kind == caption.kind and other.number == caption.number:
            continue
        consider_boundary(other.bbox[1], other.bbox[3], other.bbox[0], other.bbox[2])

    # (2) Real body-text paragraphs (skip blocks inside drawings)
    for bx0_, by0_, bx1_, by1_, btext, *_ in all_blocks:
        stripped = (btext or "").strip()
        if len(stripped) < BODY_TEXT_MIN_CHARS:
            continue
        if (bx1_ - bx0_) < column_width * BODY_TEXT_MIN_WIDTH_FRAC:
            continue
        if _looks_like_caption(stripped):
            continue
        if not _is_paragraph_like(stripped):
            continue
        if block_inside_drawing(bx0_, by0_, bx1_, by1_):
            continue
        consider_boundary(by0_, by1_, bx0_, bx1_)

    # (3) Page header band (dynamic — depends on whether this page has a
    # running-title band at the very top).
    header_y = _page_header_y(all_blocks)
    boundaries_above.append(header_y)

    # (4) Other pdfplumber tables
    for tb in other_table_bboxes:
        consider_boundary(tb[1], tb[3], tb[0], tb[2])

    max_span = page_h * LOOKUP_FRACTION

    def resolve_top() -> float:
        if not boundaries_above:
            return max(0, y0 - max_span)
        return min(y0, max(boundaries_above) + GAP_THRESHOLD / 2)

    def resolve_bot() -> float:
        if not boundaries_below:
            return min(page_h, y1 + max_span)
        return max(y1, min(boundaries_below) - GAP_THRESHOLD / 2)

    # Settle vertical extent.
    if caption.kind == "figure":
        if drawing_above is not None:
            # Drawings win — they directly bound the figure's body.
            top = max(header_y, drawing_above.y0 - 4)
            # Respect boundary blocks that sit in the GAP between the drawing
            # and the caption (e.g. a section header in the gap). Boundaries
            # whose y is INSIDE the drawing's vertical span belong to the
            # figure itself (pseudocode steps, axis labels, pdfplumber
            # mis-detecting the chart as a table) and must be ignored.
            for b in boundaries_above:
                if drawing_above.y1 < b < y0:
                    top = max(top, b + GAP_THRESHOLD / 2)
        else:
            top = resolve_top()
        bot = y1 + 4
    elif caption.kind in ("algorithm", "listing"):
        if drawing_below is not None:
            bot = min(page_h, drawing_below.y1 + 4)
            for b in boundaries_below:
                if y1 < b < drawing_below.y0:
                    bot = min(bot, b - GAP_THRESHOLD / 2)
        else:
            bot = resolve_bot()
        top = max(0, y0 - 4)
    else:  # table — pick the side with the larger gap to non-table content
        top_c = resolve_top()
        bot_c = resolve_bot()
        if (y0 - top_c) >= (bot_c - y1):
            top = top_c
            bot = y1 + 4
        else:
            top = max(0, y0 - 4)
            bot = bot_c

    # Horizontal expansion (figures + algorithm + listing): a narrow caption
    # under a wide protocol diagram is common. Sweep non-prose content within
    # (top, bot) and widen, with column-clipping and forbidden-strip safety.
    if caption.kind in ("figure", "algorithm", "listing"):
        # Seed from the dominant drawing if we have one (gives a tight start).
        if drawing_above is not None:
            left = min(left, drawing_above.x0)
            right = max(right, drawing_above.x1)
        if drawing_below is not None:
            left = min(left, drawing_below.x0)
            right = max(right, drawing_below.x1)

        # Forbidden strips: prose columns vertically overlapping (top, bot).
        forbidden_strips: list[tuple[float, float]] = []
        for bx0_, by0_, bx1_, by1_, btext, *_ in all_blocks:
            stripped = (btext or "").strip()
            if not stripped:
                continue
            if (
                len(stripped) >= BODY_TEXT_MIN_CHARS
                and (bx1_ - bx0_) >= column_width * BODY_TEXT_MIN_WIDTH_FRAC
                and _is_paragraph_like(stripped)
                and not _looks_like_caption(stripped)
                and not block_inside_drawing(bx0_, by0_, bx1_, by1_)
                and by1_ > top
                and by0_ < bot
            ):
                forbidden_strips.append((bx0_, bx1_))

        # Expand to non-prose blocks within the vertical range.
        for bx0_, by0_, bx1_, by1_, btext, *_ in all_blocks:
            stripped = (btext or "").strip()
            if not stripped:
                continue
            bcy = (by0_ + by1_) / 2
            if not (top - 2 <= bcy <= bot + 2):
                continue
            if (
                len(stripped) >= BODY_TEXT_MIN_CHARS
                and (bx1_ - bx0_) >= column_width * BODY_TEXT_MIN_WIDTH_FRAC
                and _is_paragraph_like(stripped)
                and not _looks_like_caption(stripped)
                and not block_inside_drawing(bx0_, by0_, bx1_, by1_)
            ):
                continue
            left = min(left, bx0_)
            right = max(right, bx1_)

        # Expand to drawings within the vertical range.
        for r in big_drawings:
            bcy = (r.y0 + r.y1) / 2
            if not (top - 2 <= bcy <= bot + 2):
                continue
            left = min(left, r.x0)
            right = max(right, r.x1)

        # Clip to caption's column.
        if caption_col is not None:
            left = max(left, caption_col[0])
            right = min(right, caption_col[1])

        # Clip out of forbidden strips.
        left_clipped = False
        right_clipped = False
        for fx0, fx1 in forbidden_strips:
            if fx0 <= left <= fx1:
                left = fx1 + 4
                left_clipped = True
            if fx0 <= right <= fx1:
                right = fx0 - 4
                right_clipped = True
        if not left_clipped:
            left = max(0, left - 4)
        if not right_clipped:
            right = min(page_w, right + 4)
        if right <= left:
            left = max(0, x0 - 6)
            right = min(page_w, x1 + 6)

    return fitz.Rect(left, top, right, bot)


def render_region(page: fitz.Page, rect: fitz.Rect, out_path: Path) -> None:
    """Render a clipped region of a page to PNG."""
    zoom = RENDER_DPI / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, clip=rect, alpha=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(out_path)


def extract_tables_with_pdfplumber(pdf_path: Path) -> list[dict]:
    """Return all tables found by pdfplumber, with page index and bbox info.

    We use this to render markdown for each table; matching to captions is
    done later by page + vertical proximity.
    """
    results = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            tables = page.find_tables()
            for t in tables:
                try:
                    data = t.extract()
                except Exception:
                    data = None
                if not data:
                    continue
                results.append({
                    "page": page_idx,
                    "bbox": tuple(t.bbox),  # (x0, top, x1, bottom)
                    "data": data,
                })
    return results


def extract_text_in_rect(page: fitz.Page, rect: fitz.Rect) -> str:
    """Get the plain text inside a rectangular region."""
    return page.get_text("text", clip=rect)


def _is_real_table(t: dict, page_h: float, page_w: float) -> bool:
    """Reject pdfplumber `tables` that are noise (chart axes, off-page boxes).

    pdfplumber can mistake chart axis labels for tables — the rotated y-axis
    labels and x-tick values get clustered into "cells" with many `\\n`s, or
    fragmented across columns ("Lo\\nC", "cal\\nollabor", …). It can also
    report bboxes with negative / off-page coordinates, or detect a faintly-
    gridded chart background as a 7-row table where only the legend area
    (rows 0-2) has any content and rows 3-6 are blank.

    Filter rules:
      * bbox must be within the page.
      * bbox must be at least 30 × 10 points.
      * at least 2 non-empty cells (data, not just whitespace).
      * non-empty cell fraction >= 20% (real tables have most cells filled).
      * no cell has >= 4 newlines (chart-label stacks).
      * for tables with > 2 rows, at most half the rows can be completely
        empty (charts have a sparse legend area + many empty grid rows).
      * word-fragment heuristic: real tables don't split words across cells,
        so reject if many cells END or START mid-word (e.g. "Lo", "cal").
    """
    x0, y0, x1, y1 = t["bbox"]
    if y1 <= 0 or y0 >= page_h or x1 <= 0 or x0 >= page_w:
        return False
    if (x1 - x0) < 30 or (y1 - y0) < 10:
        return False
    data = t.get("data") or []
    if not data:
        return False
    total_cells = sum(len(row) for row in data)
    non_empty = sum(1 for row in data for c in row if c and c.strip())
    if non_empty < 2:
        return False
    if total_cells > 0 and non_empty / total_cells < 0.2:
        return False
    for row in data:
        for c in row:
            if c and c.count("\n") >= 4:
                return False

    if len(data) > 2:
        empty_rows = sum(1 for row in data if all(not (c and c.strip()) for c in row))
        if empty_rows / len(data) > 0.5:
            return False

    # Word-fragment check: in a chart-mistaken-as-table, cells often contain
    # word fragments like "Lo\nC" or "cal\nollabor" where a word ("Local",
    # "Collaborative") got split across columns. Heuristic: lowercase-starting
    # short cells next to a previous cell on the same row are suspicious.
    fragment_hits = 0
    for row in data:
        prev_nonempty = False
        for c in row:
            if not c:
                prev_nonempty = False
                continue
            s = c.strip()
            if not s:
                prev_nonempty = False
                continue
            if prev_nonempty and len(s) <= 8 and s[0].islower() and s[0].isalpha():
                fragment_hits += 1
            prev_nonempty = True
    if fragment_hits >= 2:
        return False

    return True


# A pdfplumber-detected table is only a valid match for a caption if its
# vertical distance to the caption is at most this many points. Real
# captions-table pairs are usually within ~30pt; 100pt covers margins and
# the rare case of caption-above-table-with-some-blank-space.
MAX_TABLE_CAPTION_GAP = 100.0


def match_table_to_caption(
    captions: list[Caption],
    pdfplumber_tables: list[dict],
    doc: fitz.Document,
) -> dict[int, dict]:
    """Match each table caption to a pdfplumber table via optimal (minimum
    total cost) assignment, per page.

    Distance between caption C and table T is the smaller of:
      - |C.bottom - T.top|   (caption above table — ACM/IEEE convention)
      - |T.bottom - C.top|   (caption below table — Springer/Elsevier convention)

    Greedy minimum-edge assignment fails when one table sits between two
    captions: the inner caption is close to BOTH the table above (via
    gap_above) and the table below (via gap_below), and greedy can lock the
    wrong pair first. Brute-force enumeration over permutations finds the
    assignment that minimizes total distance — n is small (per-page), so cost
    is negligible.
    """
    matches: dict[int, dict] = {}

    # Group by page so different pages don't compete.
    pages: dict[int, dict] = {}
    for cap in captions:
        if cap.kind == "table":
            pages.setdefault(cap.page, {"caps": [], "tables": []})["caps"].append(cap)
    for t in pdfplumber_tables:
        if t["page"] in pages:
            pages[t["page"]]["tables"].append(t)

    def cost(cap: Caption, t: dict) -> float:
        c_top, c_bot = cap.bbox[1], cap.bbox[3]
        t_top, t_bot = t["bbox"][1], t["bbox"][3]
        return min(abs(c_bot - t_top), abs(t_bot - c_top))

    for page_idx, group in pages.items():
        caps = group["caps"]
        page = doc[page_idx]
        page_h = page.rect.height
        page_w = page.rect.width
        tables = [t for t in group["tables"] if _is_real_table(t, page_h, page_w)]
        if not caps or not tables:
            continue

        n_caps = len(caps)
        n_tabs = len(tables)
        best: tuple | None = None  # (total_cost, [(cap_idx, tab_idx), ...])

        if n_caps <= n_tabs:
            for perm in permutations(range(n_tabs), n_caps):
                total = sum(cost(caps[i], tables[perm[i]]) for i in range(n_caps))
                if best is None or total < best[0]:
                    best = (total, [(i, perm[i]) for i in range(n_caps)])
        else:
            for perm in permutations(range(n_caps), n_tabs):
                total = sum(cost(caps[perm[j]], tables[j]) for j in range(n_tabs))
                if best is None or total < best[0]:
                    best = (total, [(perm[j], j) for j in range(n_tabs)])

        if best is not None:
            for cap_idx, tab_idx in best[1]:
                # Sanity check: reject matches where the table is implausibly
                # far from the caption. A 200pt gap means we're matching across
                # an unrelated figure or body section.
                if cost(caps[cap_idx], tables[tab_idx]) <= MAX_TABLE_CAPTION_GAP:
                    matches[caps[cap_idx].number] = tables[tab_idx]

    return matches


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract figures/tables/code from a PDF paper.")
    ap.add_argument("pdf", help="Path to the input PDF.")
    ap.add_argument("output_dir", help="Directory to write extracted assets into.")
    ap.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    args = ap.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    out_dir = Path(args.output_dir).expanduser().resolve()
    if not pdf_path.is_file():
        print(f"error: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    log(f"opened {pdf_path.name}: {len(doc)} pages")

    captions = find_captions(doc)
    log(f"found {len(captions)} captions")

    # Get tables via pdfplumber once (matched per caption below)
    pdfplumber_tables = extract_tables_with_pdfplumber(pdf_path)
    log(f"pdfplumber found {len(pdfplumber_tables)} raw tables")
    table_match = match_table_to_caption(captions, pdfplumber_tables, doc)

    manifest: dict = {
        "pdf": str(pdf_path),
        "total_captions": len(captions),
        "figures": [],
        "tables": [],
        "algorithms": [],
        "listings": [],
        "warnings": [],
    }

    # Track which numbers we've already produced, so a duplicate caption (e.g.
    # mention of "Figure 1" in body text) doesn't overwrite the real one.
    produced: dict[str, set[int]] = {"figure": set(), "table": set(), "algorithm": set(), "listing": set()}

    # Cache per-page text blocks and the captions on each page (used by the
    # smart cropper).
    page_blocks_cache: dict[int, list[tuple]] = {}
    captions_by_page: dict[int, list[Caption]] = {}
    for c in captions:
        captions_by_page.setdefault(c.page, []).append(c)

    # Index pdfplumber tables by page for boundary-detection in asset_region.
    tables_by_page: dict[int, list[dict]] = {}
    for t in pdfplumber_tables:
        page_h = doc[t["page"]].rect.height
        page_w_t = doc[t["page"]].rect.width
        if _is_real_table(t, page_h, page_w_t):
            tables_by_page.setdefault(t["page"], []).append(t)

    for cap in captions:
        if cap.number in produced[cap.kind]:
            continue
        page = doc[cap.page]
        if cap.page not in page_blocks_cache:
            page_blocks_cache[cap.page] = page.get_text("blocks")
        blocks = page_blocks_cache[cap.page]
        page_w = page.rect.width

        # Other tables on this page act as boundaries — but don't count THIS
        # caption's matched table against itself.
        matched_id = id(table_match[cap.number]) if cap.number in table_match else None
        other_table_bboxes = [
            tuple(t["bbox"]) for t in tables_by_page.get(cap.page, [])
            if id(t) != matched_id
        ]

        # For every kind, get the natural region using caption-aware boundaries.
        natural_rect = asset_region(
            page, cap, blocks, captions_by_page[cap.page], other_table_bboxes
        )

        if cap.kind == "table":
            # When pdfplumber found the table, trust its bbox for the table's
            # vertical extent. Earlier we unioned with natural_rect to recover
            # under-detection, but natural_rect can also LEAK into a neighbor
            # table or a figure on the same page — making one PNG swallow two
            # assets. Instead:
            #   - default: caption bbox ∪ pdfplumber table bbox (tight)
            #   - if pdfplumber clearly under-detected (its bbox is much
            #     shorter than natural_rect), fall back to the natural region
            #     so the user still gets the full picture.
            # Horizontal widening (recover right-edge columns pdfplumber
            # sometimes misses) is column-aware: we only union with blocks
            # whose center sits inside the table's current x-range OR within
            # ~30pt of an edge. This stops a left-column body paragraph from
            # being sucked into a right-column table.
            if cap.number in table_match:
                tb = table_match[cap.number]["bbox"]
                cap_bbox = cap.bbox
                rect = fitz.Rect(
                    min(cap_bbox[0], tb[0]),
                    min(cap_bbox[1], tb[1]),
                    max(cap_bbox[2], tb[2]),
                    max(cap_bbox[3], tb[3]),
                )
                pdfplumber_h = tb[3] - tb[1]
                natural_h = natural_rect.y1 - natural_rect.y0
                if natural_h > 0 and pdfplumber_h < natural_h * 0.35:
                    # pdfplumber under-detected — expand to natural region.
                    rect = fitz.Rect(
                        min(rect.x0, natural_rect.x0),
                        min(rect.y0, natural_rect.y0),
                        max(rect.x1, natural_rect.x1),
                        max(rect.y1, natural_rect.y1),
                    )
                # Column-aware horizontal widening.
                for bx0, by0, bx1, by1, btext, *_ in blocks:
                    if not (btext or "").strip():
                        continue
                    bcy = (by0 + by1) / 2
                    bcx = (bx0 + bx1) / 2
                    if not (rect.y0 - 2 <= bcy <= rect.y1 + 2):
                        continue
                    # Same-column test: block center within current rect's
                    # x-range (with a small margin) — keeps left-column body
                    # text out of a right-column table.
                    if not (rect.x0 - 30 <= bcx <= rect.x1 + 30):
                        continue
                    rect = fitz.Rect(min(rect.x0, bx0), rect.y0,
                                     max(rect.x1, bx1), rect.y1)
            else:
                # No pdfplumber match — natural_rect drives everything. Don't
                # widen further: natural_rect already accounts for column
                # boundaries via asset_region's logic.
                rect = fitz.Rect(natural_rect)
            rect = fitz.Rect(
                max(0, rect.x0 - 6),
                rect.y0,
                min(page_w, rect.x1 + 6),
                rect.y1,
            )
        else:
            rect = natural_rect

        if cap.kind == "figure":
            png_path = out_dir / "figures" / f"figure-{cap.number}.png"
            render_region(page, rect, png_path)
            manifest["figures"].append({
                "number": cap.number,
                "page": cap.page + 1,
                "caption": cap.text,
                "image": str(png_path.relative_to(out_dir)),
            })

        elif cap.kind == "table":
            png_path = out_dir / "tables" / f"table-{cap.number}.png"
            render_region(page, rect, png_path)
            manifest["tables"].append({
                "number": cap.number,
                "page": cap.page + 1,
                "caption": cap.text,
                "image": str(png_path.relative_to(out_dir)),
            })

        elif cap.kind in ("algorithm", "listing"):
            folder = "code"
            md_path = out_dir / folder / f"{cap.kind}-{cap.number}.md"
            text = extract_text_in_rect(page, rect).strip()
            # Drop the caption line itself (first matching pattern in the text)
            for _, pat in CAPTION_PATTERNS:
                text = pat.sub("", text, count=1).lstrip()
                break
            png_path = out_dir / folder / f"{cap.kind}-{cap.number}.png"
            render_region(page, rect, png_path)  # also keep an image fallback
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(
                f"# {cap.kind.capitalize()} {cap.number}\n\n"
                f"> {cap.text}\n\n"
                f"```\n{text}\n```\n\n"
                f"*Image fallback: {png_path.name}*\n",
                encoding="utf-8",
            )
            key = "algorithms" if cap.kind == "algorithm" else "listings"
            manifest[key].append({
                "number": cap.number,
                "page": cap.page + 1,
                "caption": cap.text,
                "markdown": str(md_path.relative_to(out_dir)),
                "image": str(png_path.relative_to(out_dir)),
            })

        produced[cap.kind].add(cap.number)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"manifest -> {manifest_path}")

    # Compact summary to stdout
    print(json.dumps({
        "figures": len(manifest["figures"]),
        "tables": len(manifest["tables"]),
        "algorithms": len(manifest["algorithms"]),
        "listings": len(manifest["listings"]),
        "warnings": len(manifest["warnings"]),
        "manifest": str(manifest_path),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
