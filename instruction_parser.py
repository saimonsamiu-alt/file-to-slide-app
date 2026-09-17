"""
Turns a free-text instruction like "add a light watermark for Samiu's
Tuition in blue" into structured params: {text, opacity, color, position}.

Two modes:
1. If GEMINI_API_KEY is set in the environment, use a real (free-tier-friendly,
   small) Claude API call for robust parsing of arbitrary phrasing.
2. Otherwise, fall back to a simple regex/keyword parser that covers the
   common cases for free — this is what runs by default in this MVP so
   it works out of the box with zero AI cost.
"""

import os
import re
import json

COLOR_WORDS = {
    "red": "C00000", "blue": "1F4E79", "green": "2E7D32", "black": "000000",
    "gray": "808080", "grey": "808080", "orange": "C55A11", "purple": "6A1B9A",
    "yellow": "BF9000",
}

OPACITY_WORDS = {
    "light": "light", "faint": "light", "subtle": "light",
    "dark": "dark", "strong": "dark", "bold": "dark",
}


def _regex_parse(instruction: str) -> dict:
    result = {"text": None, "opacity": None, "color": None, "position": "diagonal-center"}

    # text in quotes, or after "for" if no quotes
    quoted = re.search(r'["\u2018\u2019\u201c\u201d]([^"\u2018\u2019\u201c\u201d]+)["\u2018\u2019\u201c\u201d]', instruction)
    if quoted:
        result["text"] = quoted.group(1)
    else:
        m = re.search(r"for\s+([A-Za-z0-9'\u2019\s]+?)(?:\s+in\s|\s+with\s|$)", instruction, re.IGNORECASE)
        if m:
            result["text"] = m.group(1).strip()

    lower = instruction.lower()
    for word, hexcode in COLOR_WORDS.items():
        if word in lower:
            result["color"] = hexcode
            break
    for word, level in OPACITY_WORDS.items():
        if word in lower:
            result["opacity"] = level
            break

    return result


def _ai_parse(instruction: str) -> dict:
    """Optional real AI parse — only runs if a Gemini API key is configured."""
    from google import genai
    from google.genai import types
    import gemini_client

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        "Parse this watermark instruction into JSON with keys "
        "text, opacity ('light' or 'dark' or null), color (hex code or null), "
        "position (default 'diagonal-center' if not specified). "
        "Return ONLY the JSON, nothing else.\n\n"
        f"Instruction: {instruction}"
    )
    resp = gemini_client.generate_content(
        client,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    text = resp.text.strip()
    text = re.sub(r"^```json|```$", "", text).strip()
    import safe_json
    return safe_json.loads(text)


def parse_instruction(instruction: str) -> dict:
    if not instruction or not instruction.strip():
        return {"text": None, "opacity": None, "color": None, "position": "diagonal-center"}

    if os.environ.get("GEMINI_API_KEY"):
        try:
            return _ai_parse(instruction)
        except Exception:
            # fall back gracefully rather than breaking the request
            return _regex_parse(instruction)

    return _regex_parse(instruction)
