"""
analyze_deed.py
---------------
Standalone script to extract property data from 'suresh proparty pepar 3.pdf'
using PyMuPDF (fitz) for rendering and Gemini 2.5 Flash Vision for extraction.
"""

import os

import fitz  # PyMuPDF
from PIL import Image
from google import genai
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
PDF_PATH = "suresh proparty pepar 3.pdf"
API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"

PROMPT = (
    "You are an expert Indian real estate data extractor. "
    "Read this Rajasthan property title deed. "
    "It contains printed and handwritten Hindi. "
    "Extract every possible data point useful for a real estate valuation, "
    "specifically looking for: Buyer Name, Seller Name, Khasra/Plot No., "
    "Total Area, Boundaries (North, South, East, West) — for each boundary "
    "provide BOTH the dimension/length of that side AND the neighbour description, "
    "and Stamp Duty/Transaction Value. "
    "Translate your findings into English and format it clearly."
)


def pdf_page_to_image(pdf_path: str, page_index: int = 0, dpi: int = 300) -> Image.Image:
    """Render one PDF page as a PIL Image using PyMuPDF (no poppler/pdf2image)."""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=mat, alpha=False)
    doc.close()
    return Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)


def main():
    # Step 1 — Render first page
    print("=" * 70)
    print(f"Rendering page 1 of '{PDF_PATH}' at 300 DPI...")
    print("=" * 70)
    image = pdf_page_to_image(PDF_PATH, page_index=0, dpi=300)
    print(f"✅ Image size: {image.size[0]}×{image.size[1]} px\n")

    # Step 2 — Send to Gemini Vision
    print("=" * 70)
    print(f"Sending to {MODEL} Vision...")
    print("=" * 70)
    client = genai.Client(api_key=API_KEY)
    response = client.models.generate_content(
        model=MODEL,
        contents=[PROMPT, image],
    )

    # Step 3 — Print response
    print("\n" + "=" * 70)
    print("GEMINI VISION RESPONSE")
    print("=" * 70)
    print(response.text)
    print("=" * 70)


if __name__ == "__main__":
    main()
