#!/usr/bin/env python3
"""
generate_slides.py — Academic paper slide-plan.json → .pptx

Usage:
    python3 generate_slides.py <paper-dir> [--template <template.pptx>]

paper-dir must contain:
    slide-plan.json    (written by Claude / paper-analyzer skill)
    figures/           (optional, from extract_assets.py)
    tables/            (optional)

Output:
    <paper-dir>/<output_filename>.pptx
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE as SHP
except ImportError:
    sys.exit("ERROR: python-pptx not installed.  Run: pip3 install python-pptx")

# ── Palette ────────────────────────────────────────────────────────────────
NAVY  = RGBColor(0x1B, 0x3A, 0x6B)
TEAL  = RGBColor(0x2E, 0x86, 0xAB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK  = RGBColor(0x2C, 0x3E, 0x50)
GRAY  = RGBColor(0x95, 0xA5, 0xA6)
LBLUE = RGBColor(0xB0, 0xC8, 0xE8)

# ── 16:9 dimensions ────────────────────────────────────────────────────────
SW, SH  = Inches(13.33), Inches(7.5)
HDR_H   = Inches(1.0)           # header bar height
PAD     = Inches(0.4)           # slide padding
BODY_Y  = HDR_H + PAD           # body area top
BODY_H  = SH - BODY_Y - PAD    # body area height
BODY_W  = SW - PAD * 2         # body area width


# ── Low-level helpers ──────────────────────────────────────────────────────

def _solid(shape, color: RGBColor):
    """Apply solid fill to a shape."""
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _textbox(slide, left, top, width, height, text="",
             size=18, bold=False, italic=False,
             color=DARK, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return tb


def _bullets(slide, left, top, width, height, items, size=19, color=DARK):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = p.add_run()
        run.text = "• " + str(item)
        run.font.size = Pt(size)
        run.font.color.rgb = color
        p.space_after = Pt(6)
    return tb


def _picture(slide, img_path, left, top, width, height):
    try:
        slide.shapes.add_picture(str(img_path), left, top, width, height)
        return True
    except Exception as e:
        print(f"  [warn] Cannot embed {img_path}: {e}", file=sys.stderr)
        return False


def _render_latex(latex: str):
    """Render LaTeX math to a temp PNG using matplotlib. Returns path or None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        expr = latex.strip()
        if not expr.startswith("$"):
            expr = f"${expr}$"
        fig = plt.figure(figsize=(11, 1.8), facecolor="none")
        fig.text(0.5, 0.5, expr, ha="center", va="center",
                 fontsize=26, color="#2C3E50")
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        fig.savefig(tmp.name, bbox_inches="tight", transparent=True, dpi=150)
        plt.close(fig)
        return tmp.name
    except Exception:
        return None


# ── Slide scaffolding ──────────────────────────────────────────────────────

def _blank(prs: Presentation, use_template: bool):
    """Return a new blank slide using the most appropriate layout."""
    if use_template:
        # Prefer a layout named 'blank'; fall back to last layout
        blank_layout = prs.slide_layouts[-1]
        for lay in prs.slide_layouts:
            if "blank" in lay.name.lower():
                blank_layout = lay
                break
        return prs.slides.add_slide(blank_layout)
    return prs.slides.add_slide(prs.slide_layouts[6])


def _header(slide, title: str, use_template: bool):
    """Add title header: navy bar (default) or plain text (template mode)."""
    if not use_template:
        bar = slide.shapes.add_shape(SHP.RECTANGLE, 0, 0, SW, HDR_H)
        _solid(bar, NAVY)
        _textbox(slide, PAD, Inches(0.1), SW - PAD * 2, HDR_H - Inches(0.1),
                 title, size=28, bold=True, color=WHITE)
    else:
        _textbox(slide, PAD, Inches(0.12), SW - PAD * 2, HDR_H - Inches(0.15),
                 title, size=28, bold=True, color=DARK)


# ── Slide type builders ────────────────────────────────────────────────────

def _title_slide(prs, s, use_template):
    slide = _blank(prs, use_template)
    if not use_template:
        bg = slide.shapes.add_shape(SHP.RECTANGLE, 0, 0, SW, SH)
        _solid(bg, NAVY)
    txt_color  = WHITE if not use_template else DARK
    sub_color  = LBLUE if not use_template else GRAY
    _textbox(slide, PAD, Inches(1.6), SW - PAD * 2, Inches(2.4),
             s.get("title", ""), size=32, bold=True,
             color=txt_color, align=PP_ALIGN.CENTER)
    byline = "\n".join(filter(None, [
        s.get("authors", ""),
        " · ".join(filter(None, [s.get("venue", ""), str(s.get("year", ""))])),
    ]))
    _textbox(slide, PAD, Inches(4.3), SW - PAD * 2, Inches(1.4),
             byline, size=18, color=sub_color, align=PP_ALIGN.CENTER)
    return slide


def _section_slide(prs, s, use_template):
    slide = _blank(prs, use_template)
    if not use_template:
        accent = slide.shapes.add_shape(SHP.RECTANGLE, 0, 0, Inches(4.5), SH)
        _solid(accent, NAVY)
    left = Inches(5.0) if not use_template else PAD
    _textbox(slide, left, Inches(2.7), SW - left - PAD, Inches(2.1),
             s.get("title", ""), size=36, bold=True, color=DARK)
    return slide


def _bullets_slide(prs, s, paper_dir: Path, use_template):
    slide = _blank(prs, use_template)
    _header(slide, s.get("title", ""), use_template)

    items    = s.get("bullets", [])
    fig_rel  = s.get("figure")
    fig_path = (paper_dir / fig_rel) if fig_rel else None

    if fig_path and fig_path.exists():
        bw = Inches(7.0)
        _bullets(slide, PAD, BODY_Y, bw, BODY_H, items)
        _picture(slide, fig_path, Inches(7.6), BODY_Y, Inches(5.3), BODY_H)
    else:
        _bullets(slide, PAD, BODY_Y, BODY_W, BODY_H, items)
    return slide


def _image_slide(prs, s, paper_dir: Path, use_template):
    slide = _blank(prs, use_template)
    _header(slide, s.get("title", ""), use_template)

    caption  = s.get("caption", "")
    cap_h    = Inches(0.42) if caption else Inches(0)
    body_h   = BODY_H - cap_h
    img_rel  = s.get("image")
    img_path = (paper_dir / img_rel) if img_rel else None

    if img_path and img_path.exists():
        _picture(slide, img_path, PAD, BODY_Y, BODY_W, body_h)
    else:
        _textbox(slide, PAD, BODY_Y, BODY_W, body_h,
                 f"[图像未找到: {img_rel}]", size=16, color=GRAY)
    if caption:
        _textbox(slide, PAD, BODY_Y + body_h + Inches(0.05), BODY_W, cap_h,
                 caption, size=13, italic=True, color=GRAY, align=PP_ALIGN.CENTER)
    return slide


def _formula_slide(prs, s, paper_dir: Path, use_template):
    slide = _blank(prs, use_template)
    _header(slide, s.get("title", ""), use_template)

    latex   = s.get("latex", "")
    caption = s.get("caption", "")
    y = BODY_Y

    formula_img = _render_latex(latex)
    if formula_img:
        ok = _picture(slide, formula_img, PAD, y, BODY_W, Inches(2.4))
        y += Inches(2.7) if ok else Inches(0)
    if not formula_img or not _picture:
        _textbox(slide, PAD, y, BODY_W, Inches(1.6),
                 latex, size=20, color=DARK, align=PP_ALIGN.CENTER)
        y += Inches(1.9)

    if caption:
        _textbox(slide, PAD, y, BODY_W, SH - y - PAD,
                 caption, size=17, color=DARK)
    return slide


def _closing_slide(prs, s, use_template):
    slide = _blank(prs, use_template)
    if not use_template:
        bg = slide.shapes.add_shape(SHP.RECTANGLE, 0, 0, SW, SH)
        _solid(bg, NAVY)
    txt_color = WHITE if not use_template else DARK
    sub_color = LBLUE if not use_template else GRAY
    _textbox(slide, PAD, Inches(2.4), SW - PAD * 2, Inches(1.8),
             s.get("title", "Thank You"),
             size=42, bold=True, color=txt_color, align=PP_ALIGN.CENTER)
    if s.get("subtitle"):
        _textbox(slide, PAD, Inches(4.4), SW - PAD * 2, Inches(1.2),
                 s["subtitle"], size=26, color=sub_color, align=PP_ALIGN.CENTER)
    return slide


# ── Dispatch table ─────────────────────────────────────────────────────────

BUILDERS = {
    "title":   (_title_slide,   False),  # (fn, needs_paper_dir)
    "section": (_section_slide, False),
    "bullets": (_bullets_slide, True),
    "image":   (_image_slide,   True),
    "formula": (_formula_slide, True),
    "closing": (_closing_slide, False),
}


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paper_dir", help="Directory with slide-plan.json and figures/")
    ap.add_argument("--template", default=None,
                    help="User-provided .pptx template (borrows master style)")
    args = ap.parse_args()

    paper_dir = Path(args.paper_dir).resolve()
    plan_path = paper_dir / "slide-plan.json"
    if not plan_path.exists():
        sys.exit(f"ERROR: slide-plan.json not found in {paper_dir}")

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    use_template = bool(args.template)
    if use_template:
        tpl = Path(args.template).resolve()
        if not tpl.exists():
            sys.exit(f"ERROR: Template file not found: {tpl}")
        prs = Presentation(str(tpl))
        # Remove existing slides while keeping master/layouts
        sld_lst = prs.slides._sldIdLst
        for el in list(sld_lst):
            sld_lst.remove(el)
        print(f"Using template: {tpl.name}")
    else:
        prs = Presentation()
        prs.slide_width  = SW
        prs.slide_height = SH
        print("Using default academic theme (navy / teal)")

    slides = plan.get("slides", [])
    print(f"Generating {len(slides)} slides …")

    for i, s in enumerate(slides):
        stype = s.get("type", "bullets")
        entry = BUILDERS.get(stype)
        if entry is None:
            print(f"  [warn] Unknown slide type '{stype}' — skipped", file=sys.stderr)
            continue
        fn, needs_dir = entry
        if needs_dir:
            fn(prs, s, paper_dir, use_template)
        else:
            fn(prs, s, use_template)
        print(f"  [{i+1}/{len(slides)}] {stype}: {s.get('title', '')[:60]}")

    out_stem = plan.get("output_filename", "slides")
    out_path = paper_dir / (out_stem + ".pptx")
    prs.save(str(out_path))
    print(f"\n✓ Saved: {out_path}  ({len(slides)} slides)")


if __name__ == "__main__":
    main()
