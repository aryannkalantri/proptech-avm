"""
extractor.py
------------
Handles text extraction from uploaded PDF or image files.
- PDF  → PyMuPDF (fitz)
- Image → pytesseract OCR
"""

import io
import fitz  # PyMuPDF
import pytesseract
from PIL import Image


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from a PDF file given its raw bytes."""
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts)


def extract_text_from_image(file_bytes: bytes) -> str:
    """Run OCR on an image file given its raw bytes."""
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image)


def auto_extract(file_bytes: bytes, filename: str) -> str:
    """
    Automatically choose extraction method based on file extension.
    Supports .pdf, .png, .jpg, .jpeg, .tiff, .bmp, .webp.
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in {"png", "jpg", "jpeg", "tiff", "bmp", "webp"}:
        return extract_text_from_image(file_bytes)
    else:
        raise ValueError(
            f"Unsupported file type '.{ext}'. "
            "Please upload a PDF or image (PNG, JPG, TIFF)."
        )
