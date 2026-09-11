"""
Rule-based content -> slide engine (Tier 1 from the product spec).
No AI call happens here — this is pure deterministic logic that should
handle the large majority (90-95% target) of uploads.
"""

import re


def parse_content_to_slides(raw_text: str):
    """
    Turn raw uploaded text into a list of slide dicts:
    [{"title": str, "bullets": [str, ...]}, ...]

    Rules (deterministic, no AI):
    - Blank-line-separated blocks become separate slides.
    - Within a block, the first non-empty line becomes the title.
    - Lines starting with '-', '*', or a number+'.' become bullets.
    - Any other lines are treated as plain bullets (whole line = one bullet).
    """
    raw_text = raw_text.strip().replace("\r\n", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw_text) if b.strip()]

    slides = []
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        title = lines[0]
        bullet_lines = lines[1:]
        bullets = []
        for line in bullet_lines:
            cleaned = re.sub(r"^[\-\*\u2022]\s*", "", line)
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
            bullets.append(cleaned)
        slides.append({"title": title, "bullets": bullets})

    # Fallback: if nothing parsed (e.g. one giant paragraph with no blank
    # lines), split into a single title-less content slide.
    if not slides and raw_text:
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        slides.append({"title": "Untitled", "bullets": lines})

    return slides


TEMPLATES = {
    "classic": {
        "name": "Classic Title + Bullets",
        "title_color": "1F3864",
        "bullet_color": "333333",
        "bg_color": "FFFFFF",
    },
    "dark": {
        "name": "Dark Mode",
        "title_color": "FFFFFF",
        "bullet_color": "DDDDDD",
        "bg_color": "1B1B1B",
    },
    "warm": {
        "name": "Warm / Education",
        "title_color": "8A3B00",
        "bullet_color": "3A2A1A",
        "bg_color": "FFF8F0",
    },
}


def apply_watermark_instruction(parsed: dict):
    """
    Given structured watermark params (already parsed from a natural-
    language instruction upstream, e.g. by a small AI call or explicit
    UI form), fill in sensible defaults for anything missing.
    This function itself does not call any AI - pure rule-based defaults.
    """
    defaults = {
        "text": parsed.get("text") or "",
        "opacity": parsed.get("opacity") or "light",
        "color": parsed.get("color") or "808080",  # default gray
        "position": parsed.get("position") or "diagonal-center",
    }
    return defaults
