"""
Renders parsed slide data + a template choice into an actual .pptx file.
Pure code, no AI call.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import re


def _hex_to_rgb(hex_color: str) -> RGBColor:
    hex_color = hex_color.strip().lstrip("#")
    return RGBColor(int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def render_pptx(slides, template: dict, watermark: dict = None, out_path: str = "output.pptx"):
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]  # fully blank layout, we control everything

    bg_rgb = _hex_to_rgb(template["bg_color"])
    title_rgb = _hex_to_rgb(template["title_color"])
    bullet_rgb = _hex_to_rgb(template["bullet_color"])

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
