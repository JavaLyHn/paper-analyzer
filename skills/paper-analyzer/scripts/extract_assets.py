#!/usr/bin/env python3
"""Extract figures, tables and code/algorithm blocks from a PDF paper.

Usage:
    python extract_assets.py <pdf-path> <output-dir>

Layout produced under <output-dir>:
    figures/figure-<n>.png
    tables/table-<n>.png
    tables/table-<n>.md          (best-effort markdown via pdfplumber)
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

# Render resolution for PNG snapshots.
RENDER_DPI = 200


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


def _detect_column_width(page: fitz.Page, all_blocks: list[tuple]) -> float:
    """Return the dominant content width on the page in points.

    Looks at text blocks with paragraph-length content (>= 80 chars) and
    returns the maximum width among them. Falls back to page width if no
    paragraph blocks are found.
    """
    page_w = page.rect.width
    widths = []
    for bx0, _, bx1, _, btext, *_ in all_blocks:
        if not (btext or "").strip():
            continue
        if len(btext.strip()) < 80:
            continue
        widths.append(bx1 - bx0)
    if not widths:
        return page_w * 0.9
    return max(widths)


def asset_region(page: fitz.Page, caption: Caption, all_blocks: list[tuple]) -> fitz.Rect:
    """Compute the page region that likely contains the asset.

    Strategy: figures are above the caption; algorithm/listing below; tables
    can be either way, so we probe both directions and use the side with the
    larger contiguous "non-body" region.

    "Probing" walks outward from the caption and stops at the nearest text
    block whose horizontal range overlaps the caption column. That block is
    presumed to be unrelated body text; the asset lives between the caption
    and that block.

    Falls back to a generous LOOKUP_FRACTION window if no boundary is found.
    """
    page_h = page.rect.height
    page_w = page.rect.width
    x0, y0, x1, y1 = caption.bbox
    cap_w = x1 - x0

    # Detect column layout by looking at paragraph-length text blocks, not at
    # the caption width — captions can be narrower than the asset (centered
    # caption under a full-width figure) or wider than the asset.
    column_width = _detect_column_width(page, all_blocks)
    two_column = column_width < page_w * 0.65
    if two_column:
        left = max(0, x0 - 6)
        right = min(page_w, x1 + 6)
    else:
        # Single-column page → use the dominant content band, but extend to
        # at least cover the caption.
        cap_center = (x0 + x1) / 2
        half = max(column_width / 2 + 10, cap_w / 2 + 10)
        left = max(0, cap_center - half)
        right = min(page_w, cap_center + half)

    # Filter blocks to those that look like body text in the caption's column.
    # A block is "body text" if it spans most of the caption's horizontal range.
    # Narrow blocks (figure labels, math symbols, page numbers) are excluded
    # so they don't fence in the asset region.
    cap_h_range = (x0, x1)
    relevant_blocks = []
    for bx0, by0, bx1, by1, btext, *_ in all_blocks:
        if abs(by0 - y0) < 1 and abs(by1 - y1) < 1:
            continue  # itself
        stripped = (btext or "").strip()
        if not stripped:
            continue
        # Block must cover at least 70% of the caption's width to count as
        # a "body text" boundary. This filters out figure-internal labels.
        if _overlap_fraction_of(cap_h_range, (bx0, bx1)) < 0.7:
            continue
        # Also skip very short text (single short line) — likely a label,
        # not real body paragraph. 25 chars is a generous cutoff.
        if len(stripped) < 25:
            continue
        relevant_blocks.append((bx0, by0, bx1, by1))

    max_span = page_h * LOOKUP_FRACTION

    def boundary_above(reference_top: float) -> float:
        """Find the bottom edge of the nearest text block strictly above the reference."""
        candidates = [b for b in relevant_blocks if b[3] <= reference_top - GAP_THRESHOLD]
        if not candidates:
            return max(0, reference_top - max_span)
        nearest = max(candidates, key=lambda b: b[3])
        # +small margin so we don't include the bottom pixel row of that text
        return min(reference_top, nearest[3] + GAP_THRESHOLD / 2)

    def boundary_below(reference_bot: float) -> float:
        """Find the top edge of the nearest text block strictly below the reference."""
        candidates = [b for b in relevant_blocks if b[1] >= reference_bot + GAP_THRESHOLD]
        if not candidates:
            return min(page_h, reference_bot + max_span)
        nearest = min(candidates, key=lambda b: b[1])
        return max(reference_bot, nearest[1] - GAP_THRESHOLD / 2)

    if caption.kind == "figure":
        top = boundary_above(y0)
        bot = y1 + 4
    elif caption.kind in ("algorithm", "listing"):
        top = max(0, y0 - 4)
        bot = boundary_below(y1)
    else:  # table — pick the side with the larger gap
        top_candidate = boundary_above(y0)
        bot_candidate = boundary_below(y1)
        gap_above = y0 - top_candidate
        gap_below = bot_candidate - y1
        if gap_above >= gap_below:
            top = top_candidate
            bot = y1 + 4
        else:
            top = max(0, y0 - 4)
            bot = bot_candidate

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


def table_to_markdown(data: list[list[str | None]]) -> str:
    """Best-effort 2D list -> markdown table."""
    if not data:
        return ""
    # Normalize: replace None with "", strip newlines inside cells
    norm = [[(c or "").strip().replace("\n", " ") for c in row] for row in data]
    # Pad rows to max width
    width = max(len(row) for row in norm)
    norm = [row + [""] * (width - len(row)) for row in norm]
    header = norm[0]
    body = norm[1:] if len(norm) > 1 else []
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


def extract_text_in_rect(page: fitz.Page, rect: fitz.Rect) -> str:
    """Get the plain text inside a rectangular region."""
    return page.get_text("text", clip=rect)


def match_table_to_caption(captions: list[Caption], pdfplumber_tables: list[dict]) -> dict[int, dict]:
    """For each table caption, find the pdfplumber table on the same page whose
    bounding box vertically overlaps the asset region. Returns {caption_number: table_record}.
    """
    matches: dict[int, dict] = {}
    for cap in captions:
        if cap.kind != "table":
            continue
        candidates = [t for t in pdfplumber_tables if t["page"] == cap.page]
        if not candidates:
            continue
        cap_top = cap.bbox[1]
        # pdfplumber bbox is (x0, top, x1, bottom). Find the table whose center
        # is closest (vertically) to the caption, and ideally above it.
        def distance(t):
            t_top, t_bot = t["bbox"][1], t["bbox"][3]
            t_center = (t_top + t_bot) / 2
            # Prefer tables above the caption (table_center < cap_top)
            above_bonus = 0 if t_center < cap_top else 30
            return abs(t_center - cap_top) + above_bonus
        best = min(candidates, key=distance)
        matches[cap.number] = best
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
    table_match = match_table_to_caption(captions, pdfplumber_tables)

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

    # Cache per-page text blocks (used by the smart cropper).
    page_blocks_cache: dict[int, list[tuple]] = {}
    for cap in captions:
        if cap.number in produced[cap.kind]:
            continue
        page = doc[cap.page]
        if cap.page not in page_blocks_cache:
            page_blocks_cache[cap.page] = page.get_text("blocks")

        # Tables: prefer pdfplumber's detected bbox, then union with the
        # horizontal range of every text block on the same page that falls
        # within the table's vertical span — pdfplumber often underestimates
        # the table's right edge when right-side columns lack visible borders.
        if cap.kind == "table" and cap.number in table_match:
            t = table_match[cap.number]
            tb = t["bbox"]  # (x0, top, x1, bottom)
            cx0, cy0, cx1, cy1 = cap.bbox
            page_w = page.rect.width
            top = min(cy0, tb[1]) - 4
            bot = max(cy1, tb[3]) + 4
            left = min(cx0, tb[0])
            right = max(cx1, tb[2])
            # Widen using text blocks that sit inside the table's vertical band.
            for bx0, by0, bx1, by1, btext, *_ in page_blocks_cache[cap.page]:
                if not (btext or "").strip():
                    continue
                # Block's vertical center is inside the table band
                bcy = (by0 + by1) / 2
                if tb[1] - 2 <= bcy <= tb[3] + 2:
                    left = min(left, bx0)
                    right = max(right, bx1)
            rect = fitz.Rect(
                max(0, left - 8),
                top,
                min(page_w, right + 8),
                bot,
            )
        else:
            rect = asset_region(page, cap, page_blocks_cache[cap.page])

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
            md_path = out_dir / "tables" / f"table-{cap.number}.md"
            render_region(page, rect, png_path)
            md_content = ""
            if cap.number in table_match:
                md_content = table_to_markdown(table_match[cap.number]["data"])
            if not md_content:
                md_content = f"<!-- pdfplumber could not parse Table {cap.number}; see {png_path.name} -->\n"
                manifest["warnings"].append(f"Table {cap.number}: structure not parsed; PNG only")
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(f"# Table {cap.number}\n\n> {cap.text}\n\n{md_content}", encoding="utf-8")
            manifest["tables"].append({
                "number": cap.number,
                "page": cap.page + 1,
                "caption": cap.text,
                "image": str(png_path.relative_to(out_dir)),
                "markdown": str(md_path.relative_to(out_dir)),
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
