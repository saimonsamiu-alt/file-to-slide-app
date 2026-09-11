"""
Renders parsed slide data + a template choice into an actual .pptx file.
Pure code, no AI call.
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import re


def _hex_to_rgb(hex_color: str) -> RGBColor:
    hex_color = hex_color.strip().lstrip("#")
    return RGBColor(int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def render_pptx(slides, template: dict, watermark: dict = None, out_path: str = "output.pptx",
                 title_page: dict = None):
    """
    title_page (optional): {"heading": "Samiu's Tuition", "subtitle": "topic name",
    "contact": "WhatsApp: 01577477346"} — rendered as slide 0 when provided.
    """
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]  # fully blank layout, we control everything

    bg_rgb = _hex_to_rgb(template["bg_color"])
    title_rgb = _hex_to_rgb(template["title_color"])
    bullet_rgb = _hex_to_rgb(template["bullet_color"])

    if title_page:
        cover = prs.slides.add_slide(blank_layout)
        cover.background.fill.solid()
        cover.background.fill.fore_color.rgb = bg_rgb
        h_box = cover.shapes.add_textbox(Inches(0.6), Inches(2.2), Inches(9), Inches(1.2))
        h_tf = h_box.text_frame
        h_tf.text = title_page.get("heading", "")
        h_tf.paragraphs[0].font.size = Pt(40)
        h_tf.paragraphs[0].font.bold = True
        h_tf.paragraphs[0].font.color.rgb = title_rgb
        h_tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        if title_page.get("subtitle"):
            s_box = cover.shapes.add_textbox(Inches(0.6), Inches(3.4), Inches(9), Inches(0.8))
            s_tf = s_box.text_frame
            s_tf.text = title_page["subtitle"]
            s_tf.paragraphs[0].font.size = Pt(22)
            s_tf.paragraphs[0].font.color.rgb = bullet_rgb
            s_tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        if title_page.get("contact"):
            c_box = cover.shapes.add_textbox(Inches(0.6), Inches(4.6), Inches(9), Inches(0.6))
            c_tf = c_box.text_frame
            c_tf.text = title_page["contact"]
            c_tf.paragraphs[0].font.size = Pt(16)
            c_tf.paragraphs[0].font.color.rgb = bullet_rgb
            c_tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    for slide_data in slides:
        slide = prs.slides.add_slide(blank_layout)

        # background
        bg = slide.background
        bg.fill.solid()
        bg.fill.fore_color.rgb = bg_rgb

        # title box
        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.4), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = slide_data["title"]
        tf.paragraphs[0].font.size = Pt(32)
        tf.paragraphs[0].font.bold = True
        tf.paragraphs[0].font.color.rgb = title_rgb

        # bullets box
        if slide_data["bullets"]:
            body_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(8.5), Inches(5))
            btf = body_box.text_frame
            btf.word_wrap = True
            for i, bullet in enumerate(slide_data["bullets"]):
                p = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
                p.text = f"\u2022 {bullet}"
                p.font.size = Pt(20)
                p.font.color.rgb = bullet_rgb
                p.space_after = Pt(10)

        # watermark (rule-based, no AI)
        if watermark and watermark.get("text"):
            wm_box = slide.shapes.add_textbox(Inches(1.5), Inches(3.2), Inches(7), Inches(1.5))
            wtf = wm_box.text_frame
            wtf.text = watermark["text"]
            wp = wtf.paragraphs[0]
            wp.alignment = PP_ALIGN.CENTER
            wp.font.size = Pt(40)
            wp.font.bold = True
            wm_color = _hex_to_rgb(watermark.get("color", "808080"))
            wp.font.color.rgb = wm_color
            # rotate the shape to fake a diagonal watermark
            if watermark.get("position", "").startswith("diagonal"):
                wm_box.rotation = -30
            # opacity isn't directly settable via python-pptx on text fill;
            # a lighter shade of the chosen color approximates "light" opacity.
            if watermark.get("opacity") == "light":
                r, g, b = wm_color[0], wm_color[1], wm_color[2]
                lighten = lambda c: int(c + (255 - c) * 0.6)
                wp.font.color.rgb = RGBColor(lighten(r), lighten(g), lighten(b))

    prs.save(out_path)
    return out_path


def convert_pptx_to_pdf(pptx_path: str, out_dir: str) -> str:
    """
    Uses headless LibreOffice to convert a .pptx to .pdf (same filename,
    .pdf extension). Requires libreoffice-impress installed on the
    system (see Dockerfile). Raises RuntimeError with the captured
    output if conversion fails, so the caller can show/log a clear
    error instead of a bare crash.
    """
    import subprocess
    result = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, pptx_path],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PDF conversion failed: {result.stderr or result.stdout}")
    pdf_path = os.path.join(out_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if not os.path.exists(pdf_path):
        raise RuntimeError(f"PDF conversion did not produce an output file. Log: {result.stdout} {result.stderr}")
    return pdf_path
