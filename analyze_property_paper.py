"""
analyze_property_paper.py
--------------------------
Multi-page extraction for PROPERTY PAPER.pdf (10 pages).
Renders ALL pages as images and sends them together to Gemini 2.5 Flash.
"""

import fitz
from PIL import Image
from google import genai

# ── Configuration ─────────────────────────────────────────────────────────────
PDF_PATH = "PROPERTY PAPER.pdf"
API_KEY = "REDACTED"
MODEL = "gemini-2.5-flash"

PROMPT = (
    "You are an expert Indian real estate data extractor. "
    "I am sending you ALL pages of an Indian property title deed. "
    "It contains printed and handwritten Hindi. "
    "Carefully read EVERY page and extract every possible data point useful "
    "for a real estate valuation. "
    "Return ONLY a valid JSON object (no markdown fences) with exactly these keys:\n"
    '{\n'
    '  "Buyer": { "Name": "", "Age": "", "Address": "" },\n'
    '  "Seller": { "Name": "", "Age": "", "Address": "" },\n'
    '  "Property_Identifiers": { "Property_Type": "", "Plot_or_House_Number": "", "Locality_or_Scheme": "" },\n'
    '  "Total_Area": { "Area_Sq_Meters": "", "Area_Sq_Feet": "", "Construction_Details": "" },\n'
    '  "Boundaries": {\n'
    '    "North": { "Dimension": "", "Neighbour": "" },\n'
    '    "South": { "Dimension": "", "Neighbour": "" },\n'
    '    "East":  { "Dimension": "", "Neighbour": "" },\n'
    '    "West":  { "Dimension": "", "Neighbour": "" }\n'
    '  },\n'
    '  "Transaction": { "Sale_Price": "", "Stamp_Duty": "" },\n'
    '  "Registration": { "Registration_Date": "", "Registration_Number": "", "Sub_Registrar_Office": "" },\n'
    '  "Witnesses": []\n'
    '}\n'
    "IMPORTANT: For the Name field of Buyer and Seller, format it as: "
    "'Sh./Smt. [First Name] S/O or W/O or D/O [Father/Husband Name]'. "
    "For example: 'Smt. Madhu Mali W/O Shri Hiralal Ji Mali'. "
    "Do NOT put father/husband name in a separate field. "
    "Translate all Hindi values to English. "
    "If a field is not found on any page, set its value to 'N/A'."
)


def pdf_all_pages_to_images(pdf_path: str, dpi: int = 200) -> list:
    """Render ALL pages of a PDF as PIL Images."""
    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    for i in range(len(doc)):
        pixmap = doc[i].get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        images.append(img)
        print(f"  Page {i+1}: {img.size[0]}×{img.size[1]} px")
    doc.close()
    return images


def main():
    # Step 1 — Render all pages
    print("=" * 70)
    print(f"Rendering ALL pages of '{PDF_PATH}' at 200 DPI...")
    print("=" * 70)
    images = pdf_all_pages_to_images(PDF_PATH, dpi=200)
    print(f"\n✅ {len(images)} pages rendered\n")

    # Step 2 — Send ALL page images + prompt to Gemini
    print("=" * 70)
    print(f"Sending {len(images)} pages to {MODEL} Vision...")
    print("=" * 70)
    client = genai.Client(api_key=API_KEY)

    # Build contents: prompt first, then all images
    contents = [PROMPT] + images

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
    )

    # Step 3 — Print response
    print("\n" + "=" * 70)
    print("GEMINI VISION RESPONSE")
    print("=" * 70)
    print(response.text)
    print("=" * 70)


if __name__ == "__main__":
    main()
