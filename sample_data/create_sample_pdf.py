"""
sample_data/create_sample_pdf.py
---------------------------------
Generates a realistic sample property PDF for demo and testing.
Run once with:
    python sample_data/create_sample_pdf.py
"""

import os
import fitz  # PyMuPDF


SAMPLE_TEXT = """\
PROPERTY INFORMATION SHEET
===========================

Property Address: 4821 Oakwood Drive
City: Austin
State: TX
ZIP: 78745
Year Built: 2003
Square Feet: 2,150
Bedrooms: 4
Bathrooms: 2.5
Lot Size: 0.22 acres

List Price: $485,000

COMPARABLE SALES
----------------
Comp 1: 4705 Maple Lane | $472,000 | 2,080 sqft
Comp 2: 4930 Cedar Ridge Blvd | $495,500 | 2,240 sqft
Comp 3: 4612 Birchwood Court | $468,000 | 2,010 sqft

NOTES
-----
Property is in excellent condition. Recent updates include new HVAC (2021),
updated kitchen countertops, and fresh exterior paint. Located in a
high-demand neighborhood with strong school ratings.
"""


def create_sample_pdf():
    os.makedirs("sample_data", exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # Letter size

    page.insert_text(
        point=(60, 72),
        text=SAMPLE_TEXT,
        fontsize=11,
        fontname="helv",
        color=(0.1, 0.1, 0.1),
    )

    out_path = os.path.join("sample_data", "sample_property.pdf")
    doc.save(out_path)
    doc.close()
    print(f"✅ Sample PDF saved to {out_path}")


if __name__ == "__main__":
    create_sample_pdf()
