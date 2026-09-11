"""
OCR for uploaded photos. Supports Bangla + English (code-switched content
is common in this market, so we run both language packs together).
"""

import pytesseract
from PIL import Image


def extract_text_from_image(file_path: str) -> str:
    img = Image.open(file_path)
    # 'ben+eng' runs both Bangla and English language models together,
    # which handles mixed-language documents (common case here).
    text = pytesseract.image_to_string(img, lang="ben+eng")
    return text.strip()
