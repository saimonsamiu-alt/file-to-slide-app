"""
Renders parsed slide data + a template choice into an actual .pptx file.
Pure code, no AI call.
"""

import os
from io import BytesIO
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from math_render import render_math_to_png_bytes
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


def render_pptx_tuition(slides, topic_label, title, subtitle, whatsapp, out_path="output.pptx"):
    """
    Samiu's Tuition's own polished practice-slide design (ported from
    the Node/pptxgenjs script the user already had) — dark header bar
    with topic label + page counter, right-aligned italic board-
    reference tag, and the same diagonal watermark style.

    slides: list of {"question": str, "tag": str (optional)}
    """
    DARK = "17324D"
    MID = "2E6F9E"
    ACCENT = "4C9AC9"
    LIGHT_BG = "EEF5FA"
    BG = "FFFFFF"
    INK = "1B1B1B"
    MUTED = "5C6B77"

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    total = len(slides)

    def add_watermark(slide):
        box = slide.shapes.add_textbox(Inches(0), Inches(3.35), Inches(13.333), Inches(0.8))
        tf = box.text_frame
        tf.text = "Samiu's Tuition"
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(30)
        p.font.bold = True
        p.font.italic = True
        p.font.name = "Georgia"
        mid_rgb = _hex_to_rgb(MID)
        lighten = lambda c: int(c + (255 - c) * 0.84)
        p.font.color.rgb = RGBColor(lighten(mid_rgb[0]), lighten(mid_rgb[1]), lighten(mid_rgb[2]))
        box.rotation = -18

    def add_header(slide, label, n):
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.05))  # 1 = rectangle
        bar.fill.solid()
        bar.fill.fore_color.rgb = _hex_to_rgb(DARK)
        bar.line.fill.background()
        label_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.24), Inches(8), Inches(0.6))
        ltf = label_box.text_frame
        ltf.text = label
        ltf.paragraphs[0].font.size = Pt(20)
        ltf.paragraphs[0].font.bold = True
        ltf.paragraphs[0].font.color.rgb = RGBColor(255, 255, 255)
        if n:
            counter_box = slide.shapes.add_textbox(Inches(12.0), Inches(6.9), Inches(1.1), Inches(0.4))
            ctf = counter_box.text_frame
            ctf.text = f"{n} / {total}"
            ctf.paragraphs[0].alignment = PP_ALIGN.RIGHT
            ctf.paragraphs[0].font.size = Pt(11)
            ctf.paragraphs[0].font.color.rgb = _hex_to_rgb(MUTED)

    def add_question_text(slide, text, y=1.35, h=2.0):
        """
        Splits the text on $...$ math segments and renders plain text
        via normal text boxes, math segments via math_render.py so
        fractions/roots/trig actually display correctly instead of as
        broken plain-text characters.
        """
        import re
        parts = re.split(r'(\$[^$]+\$)', text)
        cursor_y = y
        for part in parts:
            if not part.strip():
                continue
            if part.startswith("$") and part.endswith("$"):
                try:
                    png_bytes = render_math_to_png_bytes(part, color=INK, fontsize=26)
                    img_stream = BytesIO(png_bytes)
                    pic = slide.shapes.add_picture(img_stream, Inches(1.5), Inches(cursor_y), height=Inches(0.9))
                    cursor_y += 1.1
                except Exception:
                    # if math rendering fails for any reason, fall back
                    # to plain text rather than dropping the content
                    box = slide.shapes.add_textbox(Inches(0.7), Inches(cursor_y), Inches(12.0), Inches(0.6))
                    box.text_frame.text = part
                    box.text_frame.paragraphs[0].font.size = Pt(18)
                    box.text_frame.paragraphs[0].font.color.rgb = _hex_to_rgb(INK)
                    cursor_y += 0.7
            else:
                box = slide.shapes.add_textbox(Inches(0.7), Inches(cursor_y), Inches(12.0), Inches(0.8))
                tf = box.text_frame
                tf.word_wrap = True
                tf.text = part.strip()
                tf.paragraphs[0].font.size = Pt(18)
                tf.paragraphs[0].font.color.rgb = _hex_to_rgb(INK)
                cursor_y += 0.7

    def add_tag(slide, text, y=3.1):
        box = slide.shapes.add_textbox(Inches(1.5), Inches(y), Inches(11.1), Inches(0.7))
        tf = box.text_frame
        tf.word_wrap = True
        tf.text = text
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        p.font.size = Pt(12)
        p.font.italic = True
        p.font.bold = True
        p.font.color.rgb = _hex_to_rgb(MID)

    # Title slide
    t = prs.slides.add_slide(blank)
    t.background.fill.solid()
    t.background.fill.fore_color.rgb = _hex_to_rgb(BG)
    bg_rect = t.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
    bg_rect.fill.solid()
    bg_rect.fill.fore_color.rgb = _hex_to_rgb(LIGHT_BG)
    bg_rect.line.fill.background()
    title_box = t.shapes.add_textbox(Inches(0.8), Inches(2.5), Inches(11.7), Inches(1.2))
    title_box.text_frame.text = title
    title_box.text_frame.paragraphs[0].font.size = Pt(38)
    title_box.text_frame.paragraphs[0].font.bold = True
    title_box.text_frame.paragraphs[0].font.name = "Georgia"
    title_box.text_frame.paragraphs[0].font.color.rgb = _hex_to_rgb(DARK)
    if subtitle:
        sub_box = t.shapes.add_textbox(Inches(0.8), Inches(3.6), Inches(11.7), Inches(0.7))
        sub_box.text_frame.text = subtitle
        sub_box.text_frame.paragraphs[0].font.size = Pt(20)
        sub_box.text_frame.paragraphs[0].font.color.rgb = _hex_to_rgb(MUTED)
    accent_line = t.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(4.45), Inches(1.4), Inches(0.06))
    accent_line.fill.solid()
    accent_line.fill.fore_color.rgb = _hex_to_rgb(ACCENT)
    accent_line.line.fill.background()
    contact_box = t.shapes.add_textbox(Inches(0.8), Inches(4.7), Inches(10), Inches(0.5))
    contact_text = "Samiu's Tuition"
    if whatsapp:
        contact_text += f"  \u2022  WhatsApp: {whatsapp}"
    contact_box.text_frame.text = contact_text
    contact_box.text_frame.paragraphs[0].font.size = Pt(15)
    contact_box.text_frame.paragraphs[0].font.italic = True
    contact_box.text_frame.paragraphs[0].font.color.rgb = _hex_to_rgb(MUTED)
    add_watermark(t)

    # Question slides
    for i, slide_data in enumerate(slides, start=1):
        s = prs.slides.add_slide(blank)
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = _hex_to_rgb(BG)
        add_header(s, topic_label, i)
        add_question_text(s, slide_data.get("question", ""))
        if slide_data.get("tag"):
            add_tag(s, slide_data["tag"])
        add_watermark(s)

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
