"""
OCR for uploaded photos. Supports Bangla + English (code-switched content
is common in this market, so we run both language packs together).
"""

import io
import pytesseract
from PIL import Image


def extract_text_from_image(file_path: str) -> str:
    img = Image.open(file_path)
    # 'ben+eng' runs both Bangla and English language models together,
    # which handles mixed-language documents (common case here).
    text = pytesseract.image_to_string(img, lang="ben+eng")
    return text.strip()


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    img = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img, lang="ben+eng")
    return text.strip()
