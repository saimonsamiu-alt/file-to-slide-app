"""
Vision-based content extraction for uploaded photos. Plain Tesseract
OCR (ocr.py) cannot read mathematical notation — it garbles fractions,
roots, super/subscripts into meaningless character soup. This module
uses Gemini's multimodal (vision) understanding instead: it reads the
image and returns text with any equations marked as $...$ mathtext
expressions, which render.py can then draw as actual typeset math via
math_render.py instead of plain (broken) text.

Falls back to None if GEMINI_API_KEY isn't set or the call fails —
callers should fall back to plain OCR in that case.
"""

import os


VISION_PROMPT = """Read this image of exam/study notes (Bangla and/or English).
Transcribe all the text exactly as it would be typed, preserving structure
(question numbers, line breaks between distinct questions/notes).

IMPORTANT: If the image contains a mathematical equation or expression
(fractions, square roots, trigonometric functions, exponents, etc.),
do NOT try to write it as plain text (which cannot represent it
correctly). Instead, write it as a matplotlib "mathtext" expression
wrapped in single dollar signs, for example:
$\\sqrt{\\frac{\\sec A+1}{\\sec A-1}}=\\cot A+\\operatorname{cosec}A$

Use \\frac{}{} for fractions, \\sqrt{} for roots, \\sec \\cos \\sin \\tan
\\cot \\csc for trig functions (use \\operatorname{cosec} for cosec
specifically, matplotlib doesn't have a built-in cosec macro), ^{} for
exponents, _{} for subscripts. Keep all non-equation text as plain text
around the $...$ expression.

Return ONLY the transcribed text (with $...$ for equations embedded
inline where they appear) — no extra commentary."""


def extract_content_from_image(image_bytes: bytes, mime_type: str = "image/png"):
    """
    Returns the transcribed text (str) with equations as $...$ mathtext
    markers, or None if unavailable (no API key, or the call failed) —
    callers should fall back to plain Tesseract OCR in that case.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        import gemini_client
        resp = gemini_client.generate_content(
            client,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                VISION_PROMPT,
            ],
        )
        text = (resp.text or "").strip()
        return text if text else None
    except Exception:
        return None
