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
CAPTION_PATTERNS = [
    ("algorithm", re.compile(r"^\s*(?:Algorithm|Alg\.?)\s*(\d+)[\.:\s]", re.IGNORECASE)),
    ("listing",   re.compile(r"^\s*Listing\s*(\d+)[\.:\s]", re.IGNORECASE)),
    ("table",     re.compile(r"^\s*Table\s*(\d+)[\.:\s]", re.IGNORECASE)),
    ("figure",    re.compile(r"^\s*(?:Figure|Fig\.?)\s*(\d+)[\.:\s]", re.IGNORECASE)),
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

# Anything within this many points from the top of the page is assumed to be
# the page header (conference info, paper title, page number, etc.) and acts
# as a hard upper bound on the asset region.
PAGE_HEADER_BAND = 80.0


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

    Boundary detection — only these four kinds of regions fence in the
    asset region; everything else (narrow labels, math/pseudocode lines,
    chart annotations) is assumed to be part of the asset itself:

      1. **Other captions** in the same column (Figure 9 caption above
         Figure 10's region, etc.)
      2. **Real body-text paragraphs** — wide (>=75% of column) AND long
         (>=100 chars) AND paragraph-like (avg line >= 40 chars). These
         are clearly prose, not figure content.
      3. **Page header band** — top PAGE_HEADER_BAND points of the page,
         used as a hard upper bound for figures.
      4. **Other pdfplumber tables** on the page — their bboxes mark
         regions claimed by other captions, so a figure above them
         shouldn't extend into that data, and vice versa.

    For figures we walk up; for algorithm/listing we walk down; for tables
    we extend in whichever direction has the larger natural gap.
    """
    page_h = page.rect.height
    page_w = page.rect.width
    x0, y0, x1, y1 = caption.bbox
    cap_x_range = (x0, x1)
    cap_w = x1 - x0

    # Column layout detection — by inspecting paragraph blocks, NOT caption width.
    column_width = _detect_column_width(all_blocks, page_w)
    two_column = column_width < page_w * 0.65
    spans_columns = cap_w > column_width * 1.1
    if two_column and not spans_columns:
        # Single-column-wide caption on a 2-column page → asset is in one column.
        left = max(0, x0 - 6)
        right = min(page_w, x1 + 6)
    elif two_column and spans_columns:
        # Caption is wider than one column on a 2-column page → asset is a
        # full-width float (typical for big tables and wide figures).
        left = 0
        right = page_w
    else:
        # Single-column page — center on the caption but use the dominant
        # content width as the horizontal extent.
        cap_center = (x0 + x1) / 2
        half = max(column_width / 2 + 10, cap_w / 2 + 10)
        left = max(0, cap_center - half)
        right = min(page_w, cap_center + half)

    # Collect candidate boundaries (their y_bottom values for "above the asset"
    # and y_top values for "below the asset").
    boundaries_above: list[float] = []  # y_bottom of blocks above the caption
    boundaries_below: list[float] = []  # y_top of blocks below the caption

    def consider_boundary(by0: float, by1: float, bx0: float, bx1: float) -> None:
        # Only counts if it overlaps the caption's column horizontally.
        if _overlap_fraction_of(cap_x_range, (bx0, bx1)) < 0.3:
            return
        if by1 <= y0 - GAP_THRESHOLD:
            boundaries_above.append(by1)
        elif by0 >= y1 + GAP_THRESHOLD:
            boundaries_below.append(by0)

    # (1) Other captions on this page
    for other in captions_on_page:
        if other is caption:
            continue
        if other.kind == caption.kind and other.number == caption.number:
            continue
        consider_boundary(other.bbox[1], other.bbox[3], other.bbox[0], other.bbox[2])

    # (2) Real body-text paragraphs
    for bx0, by0, bx1, by1, btext, *_ in all_blocks:
        stripped = (btext or "").strip()
        if len(stripped) < BODY_TEXT_MIN_CHARS:
            continue
        if (bx1 - bx0) < column_width * BODY_TEXT_MIN_WIDTH_FRAC:
            continue
        if _looks_like_caption(stripped):
            continue  # captions are handled in step (1); don't double-count
        if not _is_paragraph_like(stripped):
            continue  # table rows / pseudocode blocks of stacked cells
        consider_boundary(by0, by1, bx0, bx1)

    # (3) Page header band — hard upper bound (only as "above" boundary).
    boundaries_above.append(PAGE_HEADER_BAND)

    # (4) Other pdfplumber tables on this page (regions claimed by other captions).
    for tb in other_table_bboxes:
        tb_x0, tb_y0, tb_x1, tb_y1 = tb
        consider_boundary(tb_y0, tb_y1, tb_x0, tb_x1)

    max_span = page_h * LOOKUP_FRACTION

    def resolve_top() -> float:
        if not boundaries_above:
            return max(0, y0 - max_span)
        nearest = max(boundaries_above)
        return min(y0, nearest + GAP_THRESHOLD / 2)

    def resolve_bot() -> float:
        if not boundaries_below:
            return min(page_h, y1 + max_span)
        nearest = min(boundaries_below)
        return max(y1, nearest - GAP_THRESHOLD / 2)

    if caption.kind == "figure":
        top = resolve_top()
        bot = y1 + 4
    elif caption.kind in ("algorithm", "listing"):
        top = max(0, y0 - 4)
        bot = resolve_bot()
    else:  # table — pick the side with the larger gap
        top_candidate = resolve_top()
        bot_candidate = resolve_bot()
        gap_above = y0 - top_candidate
        gap_below = bot_candidate - y1
        if gap_above >= gap_below:
            top = top_candidate
            bot = y1 + 4
        else:
            top = max(0, y0 - 4)
            bot = bot_candidate

    # For figures (and algorithm/listing code blocks) the caption can be
    # narrower than the asset itself — e.g. a centered "Figure N: …" caption
    # under a wide protocol diagram, or a short "Algorithm N" caption above a
    # full-column pseudocode block. After the vertical range is settled, sweep
    # the page for non-prose content that sits inside that range and widen the
    # horizontal extent. Two safety nets keep this from leaking sideways:
    #   * **column limit** — the asset stays inside the column its caption
    #     sits in, unless the caption itself is wider than the column (then
    #     it's a full-width float and we allow the full page).
    #   * **forbidden body strips** — if a drawing or label still extends
    #     into a vertically-overlapping body-text column (e.g. a cloud-shaped
    #     figure on page 3 that crosses into prose), clip back to the strip's
    #     edge so the crop doesn't render partial letters of the prose.
    if caption.kind in ("figure", "algorithm", "listing"):
        columns = _detect_text_columns(all_blocks, page_w)
        cap_center = (x0 + x1) / 2
        cap_w_local = x1 - x0
        caption_col: tuple[float, float] | None = None
        for cl, cr in columns:
            if cl <= cap_center <= cr:
                caption_col = (cl, cr)
                break
        if caption_col is not None:
            col_w = caption_col[1] - caption_col[0]
            if cap_w_local > col_w * 0.9:
                caption_col = (0.0, page_w)

        forbidden_strips: list[tuple[float, float]] = []
        for bx0, by0, bx1, by1_, btext, *_ in all_blocks:
            stripped = (btext or "").strip()
            if not stripped:
                continue
            if (
                len(stripped) >= BODY_TEXT_MIN_CHARS
                and (bx1 - bx0) >= column_width * BODY_TEXT_MIN_WIDTH_FRAC
                and _is_paragraph_like(stripped)
                and not _looks_like_caption(stripped)
                and by1_ > top
                and by0 < bot
            ):
                forbidden_strips.append((bx0, bx1))

        for bx0, by0, bx1, by1_, btext, *_ in all_blocks:
            stripped = (btext or "").strip()
            if not stripped:
                continue
            bcy = (by0 + by1_) / 2
            if not (top - 2 <= bcy <= bot + 2):
                continue
            if (
                len(stripped) >= BODY_TEXT_MIN_CHARS
                and (bx1 - bx0) >= column_width * BODY_TEXT_MIN_WIDTH_FRAC
                and _is_paragraph_like(stripped)
                and not _looks_like_caption(stripped)
            ):
                continue
            left = min(left, bx0)
            right = max(right, bx1)

        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
        for d in drawings:
            r = d.get("rect") if isinstance(d, dict) else None
            if r is None:
                continue
            dx0, dy0, dx1, dy1 = r.x0, r.y0, r.x1, r.y1
            if dx1 - dx0 <= 0 or dy1 - dy0 <= 0:
                continue
            bcy = (dy0 + dy1) / 2
            if not (top - 2 <= bcy <= bot + 2):
                continue
            left = min(left, dx0)
            right = max(right, dx1)

        if caption_col is not None:
            left = max(left, caption_col[0])
            right = min(right, caption_col[1])

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
    labels and x-tick values get clustered into "cells" with many `\\n`s in
    one cell ("0.200 stsoc Git-crypt\\n0.175 Trivial-enc-sign\\n…"). It can
    also report bboxes with negative / off-page coordinates.

    Filter rules:
      * bbox must be within the page
      * bbox must be at least 30x10
      * at least 2 non-empty cells (data, not just whitespace)
      * non-empty cell fraction >= 20% (real tables have most cells filled)
      * no cell has >= 4 newlines (chart-label stacks)
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
    return True


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
            # Then widen horizontally via text-block heuristic to recover
            # right-edge columns pdfplumber sometimes misses.
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
                for bx0, by0, bx1, by1, btext, *_ in blocks:
                    if not (btext or "").strip():
                        continue
                    bcy = (by0 + by1) / 2
                    if rect.y0 - 2 <= bcy <= rect.y1 + 2:
                        rect = fitz.Rect(min(rect.x0, bx0), rect.y0,
                                         max(rect.x1, bx1), rect.y1)
            else:
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
