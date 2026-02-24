"""
app.py — PropTech AVM: Vision Extractor (Production)
-----------------------------------------------------
A Streamlit dashboard that ingests scanned Indian property documents (PDFs
with printed + handwritten Hindi), renders ALL pages as high-resolution
images via PyMuPDF, and sends them to Google Gemini Vision to extract
structured property data.

API key is loaded from .env file — end users never touch it.
"""

import io
import json
import os
import traceback

import fitz  # PyMuPDF
from dotenv import load_dotenv
from google import genai
import streamlit as st
from PIL import Image

# ── Load configuration ────────────────────────────────────────────────────────
# Priority: st.secrets (Streamlit Cloud) > .env file (local) > empty
load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Read from Streamlit secrets first, then environment variables."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.getenv(key, default)


GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
DEFAULT_MODEL = _get_secret("GEMINI_MODEL", "gemini-2.5-flash")

# ─────────────────────────────────────────────────────────────────────────────
# Page configuration
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PropTech AVM: Vision Extractor",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — dark, premium PropTech aesthetic
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Deep navy gradient background */
    .stApp {
        background: linear-gradient(145deg, #080e1a 0%, #0f1f38 55%, #071625 100%);
        color: #cfd8e8;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #080e1a 0%, #0c1a30 100%);
        border-right: 1px solid rgba(50, 120, 220, 0.2);
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #7eb8f7 !important; }

    /* Glassmorphism cards */
    .avm-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(80,150,240,0.2);
        border-radius: 16px;
        padding: 1.8rem 2.2rem;
        margin-bottom: 1.6rem;
        backdrop-filter: blur(10px);
    }

    /* Status badge */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.85rem;
        border-radius: 20px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
    }
    .badge-blue  { background: rgba(30,100,220,0.25); color: #7eb8f7; border: 1px solid rgba(100,160,255,0.35); }
    .badge-green { background: rgba(20,160,80,0.2);  color: #6ddba3; border: 1px solid rgba(60,200,100,0.35); }
    .badge-amber { background: rgba(200,120,0,0.2);  color: #ffc96b; border: 1px solid rgba(240,160,20,0.35); }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #1a5dbf, #0b3d82);
        color: white; border: none; border-radius: 10px;
        padding: 0.55rem 1.5rem; font-weight: 600;
        transition: opacity 0.18s, transform 0.12s;
    }
    .stButton > button:hover { opacity: 0.85; transform: translateY(-1px); }

    /* Headings */
    h1 { color: #7eb8f7 !important; font-weight: 700 !important; }
    h2 { color: #aecff7 !important; font-weight: 600 !important; }
    h3 { color: #cde0fb !important; }

    /* JSON viewer */
    [data-testid="stJson"] {
        background: rgba(0,0,0,0.35) !important;
        border: 1px solid rgba(80,140,220,0.25) !important;
        border-radius: 10px !important;
        font-size: 0.88rem !important;
    }

    /* Table */
    [data-testid="stTable"] table {
        background: rgba(255,255,255,0.03);
        border-radius: 10px;
        border: 1px solid rgba(80,140,220,0.2);
    }
    [data-testid="stTable"] th {
        background: rgba(30,80,180,0.2) !important;
        color: #7eb8f7 !important;
        font-weight: 600 !important;
    }
    [data-testid="stTable"] td { color: #cfd8e8 !important; }

    /* Alerts */
    .stSuccess { background: rgba(20,160,80,0.15) !important; border-radius: 8px; }
    .stWarning { background: rgba(200,120,0,0.15) !important; border-radius: 8px; }
    .stError   { background: rgba(180,30,30,0.15) !important; border-radius: 8px; }
    .stInfo    { background: rgba(30,80,180,0.15) !important; border-radius: 8px; }

    /* File uploader */
    [data-testid="stFileUploader"] {
        border: 2px dashed rgba(80,150,240,0.4);
        border-radius: 14px;
        background: rgba(255,255,255,0.02);
        transition: border-color 0.2s;
    }
    [data-testid="stFileUploader"]:hover { border-color: rgba(100,180,255,0.75); }

    /* Divider */
    hr { border-color: rgba(80,140,220,0.15) !important; }

    /* Image caption */
    .stImage figcaption { color: #7eb8f7 !important; font-size: 0.8rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Extraction prompt
# ─────────────────────────────────────────────────────────────────────────────
EXTRACTION_PROMPT = (
    "You are an expert Indian real estate data extractor. "
    "I am sending you ALL pages of an Indian property title deed. "
    "It contains printed and handwritten Hindi. "
    "Carefully read EVERY page and extract every possible data point useful "
    "for a real estate valuation. "
    "Return ONLY a valid JSON object (no markdown fences) with exactly these keys:\n"
    '{\n'
    '  "Buyer": { "Name": "", "Age": "", "Address": "" },\n'
    '  "Seller": { "Name": "", "Age": "", "Address": "" },\n'
    '  "Property_Identifiers": {\n'
    '    "Property_Type": "",\n'
    '    "Patta_No": "",\n'
    '    "Book_No": "",\n'
    '    "Plot_No": "",\n'
    '    "Khasra_No": "",\n'
    '    "House_No": "",\n'
    '    "Survey_No": "",\n'
    '    "Locality_or_Scheme": "",\n'
    '    "Full_Address": ""\n'
    '  },\n'
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
    "CRITICAL ACCURACY INSTRUCTIONS:\n"
    "1. For the Name field of Buyer and Seller, format it as: "
    "'Sh./Smt. [First Name] S/O or W/O or D/O [Father/Husband Name]'. "
    "For example: 'Smt. Madhu Mali W/O Shri Hiralal Ji Mali'. "
    "Do NOT put father/husband name in a separate field.\n"
    "2. EACH identifier must go in its EXACT matching field. "
    "Patta number goes ONLY in Patta_No. Book number goes ONLY in Book_No. "
    "Plot number goes ONLY in Plot_No. Khasra number goes ONLY in Khasra_No. "
    "House number goes ONLY in House_No. Survey number goes ONLY in Survey_No. "
    "Do NOT confuse one type with another. Read the Hindi labels carefully: "
    "पट्टा = Patta, बही = Book, प्लॉट/भूखंड = Plot, खसरा = Khasra, मकान = House. "
    "If a particular identifier type is not present in the deed, set it to 'N/A'.\n"
    "3. For Full_Address, combine ALL location details into one complete address string "
    "(all identifier numbers, locality, gram panchayat, tehsil, district, state) — "
    "so it can be directly copy-pasted.\n"
    "4. ACCURACY IS PARAMOUNT. Copy numbers exactly as written in the document. "
    "Double-check every number you extract against the original text. "
    "Do NOT guess or infer — if you cannot read a value clearly, write 'Unclear'.\n"
    "Translate all Hindi values to English. "
    "If a field is not found on any page, set its value to 'N/A'."
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def pdf_to_pil_images(pdf_bytes: bytes, dpi: int = 200) -> list:
    """Render ALL pages of a PDF into PIL Images using PyMuPDF (fitz)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    for i in range(len(doc)):
        pixmap = doc[i].get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        images.append(img)
    doc.close()
    return images


def extract_with_gemini(api_key: str, images: list, model_name: str = "gemini-2.5-flash"):
    """
    Send ALL page images to Gemini Vision with the extraction prompt.
    Returns (parsed_dict, raw_text).
    """
    client = genai.Client(api_key=api_key)
    contents = [EXTRACTION_PROMPT] + images
    response = client.models.generate_content(
        model=model_name,
        contents=contents,
    )
    raw_text = response.text.strip()

    # Strip any accidental markdown fences
    clean = raw_text
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
    if clean.endswith("```"):
        clean = clean[: clean.rfind("```")]
    clean = clean.strip()

    try:
        return json.loads(clean), raw_text
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned non-JSON output: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Display configuration — categories, order, and labels
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_CONFIG = [
    ("Buyer",    "👤 Buyer / Purchaser (क्रेता)",  [
        ("Name", "Name"), ("Age", "Age"), ("Address", "Address"),
    ]),
    ("Seller",   "👤 Seller / Vendor (विक्रेता)",   [
        ("Name", "Name"), ("Age", "Age"), ("Address", "Address"),
    ]),
    ("Property_Identifiers", "📍 Property Identifiers", None),  # special rendering
    ("Total_Area", "📐 Total Area", [
        ("Area_Sq_Meters", "Area (sq. meters)"), ("Area_Sq_Feet", "Area (sq. feet)"), ("Construction_Details", "Construction Details"),
    ]),
    ("Transaction", "💰 Transaction / Stamp Details", [
        ("Sale_Price", "Sale Price"), ("Stamp_Duty", "Stamp Duty"),
    ]),
    ("Registration", "📋 Registration Details", [
        ("Registration_Date", "Registration Date"), ("Registration_Number", "Registration Number"), ("Sub_Registrar_Office", "Sub-Registrar Office"),
    ]),
]

BOUNDARY_DIRECTIONS = ["North", "South", "East", "West"]
BOUNDARY_HINDI = {"North": "उत्तर", "South": "दक्षिण", "East": "पूर्व", "West": "पश्चिम"}


def render_category_table(st_container, data: dict, fields: list):
    """Render a category as a styled table."""
    import pandas as pd
    rows = []
    for key, label in fields:
        val = data.get(key, "N/A")
        if isinstance(val, dict):
            val = ", ".join(f"{k}: {v}" for k, v in val.items())
        rows.append({"Field": label, "Value": str(val)})
    st_container.table(pd.DataFrame(rows))


def render_boundaries_table(st_container, boundaries: dict):
    """Render boundaries with Direction / Dimension / Neighbour columns."""
    import pandas as pd
    rows = []
    for direction in BOUNDARY_DIRECTIONS:
        info = boundaries.get(direction, {})
        if isinstance(info, dict):
            dim = info.get("Dimension", "N/A")
            nbr = info.get("Neighbour", "N/A")
        else:
            dim = "N/A"
            nbr = str(info)
        hindi = BOUNDARY_HINDI.get(direction, "")
        rows.append({"Direction": f"{direction} ({hindi})", "Dimension": str(dim), "Neighbour": str(nbr)})
    st_container.table(pd.DataFrame(rows))


def render_witnesses(st_container, witnesses):
    """Render witnesses list."""
    if isinstance(witnesses, list) and witnesses:
        for i, w in enumerate(witnesses, 1):
            st_container.markdown(f"**{i}.** {w}")
    else:
        st_container.markdown("*No witnesses found*")


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏗️ PropTech AVM")
    st.markdown("**Vision Extractor** — Production")
    st.markdown("---")

    # API status indicator (no input needed from user)
    if GEMINI_API_KEY:
        st.success("AI Engine: Connected ✓", icon="🤖")
    else:
        st.error("AI Engine: Not configured", icon="🚨")
        st.caption("Admin: add `GEMINI_API_KEY` to `.env` file")

    st.markdown("---")
    st.markdown(
        """
        **How it works**

        1. 📄 Upload a scanned property PDF
        2. 🖼️ All pages rendered as high-res images
        3. 🤖 Gemini Vision reads every page
        4. 🗂️ Structured data returned in English

        **Fields extracted**
        - Buyer & Seller (name, age, address)
        - Property Identifiers (plot no., locality)
        - Total Area (sq.m, sq.ft, construction)
        - Boundaries (dimension + neighbour per side)
        - Transaction Value & Stamp Duty
        - Registration Date & Number
        - Witnesses

        ---
        *Handles printed and handwritten Hindi*
        """
    )
    st.markdown("---")
    st.caption(f"Model: `{DEFAULT_MODEL}` · Antigravity PropTech v2.0")


# ─────────────────────────────────────────────────────────────────────────────
# Main header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='text-align:center;'>🏗️ PropTech AVM: Vision Extractor</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:#7eb8f7; margin-top:-0.5rem;'>"
    "Upload any Indian property deed · AI reads every page · Structured data in seconds"
    "</p>",
    unsafe_allow_html=True,
)
st.markdown("---")


# ─────────────────────────────────────────────────────────────────────────────
# Upload section
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="avm-card">', unsafe_allow_html=True)
st.markdown('<span class="badge badge-blue">Step 1</span>', unsafe_allow_html=True)
st.markdown("### 📄 Upload Property Document")
st.markdown("Upload a scanned property deed PDF — any number of pages, printed or handwritten Hindi.")

uploaded_pdf = st.file_uploader(
    "Drop your PDF here",
    type=["pdf"],
    label_visibility="collapsed",
)
st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction & Results
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_pdf is not None:

    col_img, col_results = st.columns([1, 1.4], gap="large")

    with col_img:
        st.markdown('<div class="avm-card">', unsafe_allow_html=True)
        st.markdown('<span class="badge badge-blue">Step 2</span>', unsafe_allow_html=True)
        st.markdown("### 🖼️ Document Preview")

        with st.spinner("Rendering all pages…"):
            try:
                pdf_bytes = uploaded_pdf.read()
                page_images = pdf_to_pil_images(pdf_bytes, dpi=300)
                num_pages = len(page_images)

                # Show first page as preview with page count
                st.image(
                    page_images[0],
                    use_container_width=True,
                    caption=f"Page 1 of {num_pages} · All pages will be analyzed"
                )
                if num_pages > 1:
                    st.info(f"📄 {num_pages} pages detected — AI will read all of them.", icon="📄")
                render_ok = True
            except Exception as exc:
                st.error(f"Failed to render PDF: {exc}")
                render_ok = False

        st.markdown("</div>", unsafe_allow_html=True)

    with col_results:
        st.markdown('<div class="avm-card">', unsafe_allow_html=True)
        st.markdown('<span class="badge badge-amber">Step 3</span>', unsafe_allow_html=True)
        st.markdown("### 🤖 AI Extraction")

        if not GEMINI_API_KEY:
            st.error(
                "AI Engine not configured. Please contact the administrator.",
                icon="🚨",
            )
        elif not render_ok:
            st.error("Cannot extract — PDF rendering failed in Step 2.")
        else:
            if st.button("⚡ Extract Property Data", use_container_width=True):
                spinner_msg = f"Analyzing {num_pages} page{'s' if num_pages > 1 else ''} with Gemini Vision…"
                with st.spinner(spinner_msg):
                    try:
                        extracted_data, raw_response = extract_with_gemini(
                            GEMINI_API_KEY, page_images, DEFAULT_MODEL
                        )
                        st.session_state["extracted_data"] = extracted_data
                        st.session_state["raw_response"]   = raw_response
                        st.success(f"Extraction complete! ({num_pages} pages analyzed)", icon="✅")
                    except ValueError as exc:
                        st.error(str(exc), icon="⚠️")
                        st.session_state["extracted_data"] = None
                        st.session_state["raw_response"]   = str(exc)
                    except Exception as exc:
                        st.error(f"AI Engine error: {exc}", icon="🚨")
                        with st.expander("Technical details"):
                            st.code(traceback.format_exc())
                        st.session_state["extracted_data"] = None
                        st.session_state["raw_response"]   = None

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Results display ──────────────────────────────────────────────────────
    if st.session_state.get("extracted_data"):

        extracted = st.session_state["extracted_data"]

        st.markdown("---")
        st.markdown('<span class="badge badge-green">Results</span>', unsafe_allow_html=True)
        st.markdown("## 📊 Extracted Property Data")

        tab_table, tab_json, tab_raw = st.tabs(
            ["📋 Formatted Results", "🗂️ Raw JSON", "📝 Model Response"]
        )

        with tab_table:
            # Render each category as a separate labelled card
            for cat_key, cat_title, cat_fields in CATEGORY_CONFIG:
                cat_data = extracted.get(cat_key, {})
                if not isinstance(cat_data, dict):
                    cat_data = {"Value": cat_data}
                st.markdown(f'<div class="avm-card">', unsafe_allow_html=True)
                st.markdown(f"#### {cat_title}")

                if cat_fields is None and cat_key == "Property_Identifiers":
                    # Special rendering: show each identifier type that has a value
                    import pandas as pd
                    rows = [
                        {"Field": "Property Type", "Value": str(cat_data.get("Property_Type", "N/A"))},
                    ]
                    # Add each identifier only if it has a real value
                    ID_FIELDS = [
                        ("Patta_No", "Patta No."),
                        ("Book_No", "Book No."),
                        ("Plot_No", "Plot No."),
                        ("Khasra_No", "Khasra No."),
                        ("House_No", "House No."),
                        ("Survey_No", "Survey No."),
                    ]
                    for field_key, field_label in ID_FIELDS:
                        val = str(cat_data.get(field_key, "N/A"))
                        if val and val != "N/A":
                            rows.append({"Field": field_label, "Value": val})
                    rows.append({"Field": "Locality / Scheme", "Value": str(cat_data.get("Locality_or_Scheme", "N/A"))})
                    rows.append({"Field": "Full Address", "Value": str(cat_data.get("Full_Address", "N/A"))})
                    st.table(pd.DataFrame(rows))
                else:
                    render_category_table(st, cat_data, cat_fields)

                st.markdown('</div>', unsafe_allow_html=True)

            # Boundaries — special 3-column table
            boundaries = extracted.get("Boundaries", {})
            st.markdown(f'<div class="avm-card">', unsafe_allow_html=True)
            st.markdown("#### 🧭 Boundaries — Per-Side Dimensions & Neighbours")
            render_boundaries_table(st, boundaries)
            st.markdown('</div>', unsafe_allow_html=True)

            # Witnesses
            witnesses = extracted.get("Witnesses", [])
            st.markdown(f'<div class="avm-card">', unsafe_allow_html=True)
            st.markdown("#### 👥 Witnesses")
            render_witnesses(st, witnesses)
            st.markdown('</div>', unsafe_allow_html=True)

        with tab_json:
            st.markdown("#### Structured JSON Output")
            st.json(extracted)

        with tab_raw:
            st.markdown("#### Raw model response (pre-parse)")
            st.code(st.session_state.get("raw_response", ""), language="json")

else:
    # ── Idle hero state ──────────────────────────────────────────────────────
    st.markdown('<div class="avm-card">', unsafe_allow_html=True)
    st.markdown(
        """
        <div style="text-align:center; padding: 3rem 1rem;">
            <div style="font-size:4rem; margin-bottom:1rem;">🏗️</div>
            <h2 style="color:#7eb8f7; margin-bottom:0.5rem;">Ready to Extract</h2>
            <p style="color:#607d8b; max-width:480px; margin:0 auto;">
                Upload a scanned Indian property document PDF above.
                The AI will read every page and extract Buyer, Seller,
                Property details, Area, Boundaries, Transaction value,
                and Registration information — even from handwritten Hindi.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # Feature highlights
    feat1, feat2, feat3, feat4 = st.columns(4)
    for col, icon, title, desc in [
        (feat1, "🔍", "Vision AI",      "Gemini 2.5 Flash reads printed & handwritten Hindi"),
        (feat2, "📄", "Multi-Page",     "Reads every page of the document, not just page 1"),
        (feat3, "🧭", "Full Extraction", "Buyer, Seller, Area, Boundaries, Transaction, Registration"),
        (feat4, "⚡", "Fast & Accurate", "Structured JSON in seconds, translated to English"),
    ]:
        with col:
            st.markdown(
                f"""
                <div class="avm-card" style="text-align:center; padding:1.2rem;">
                    <div style="font-size:2rem;">{icon}</div>
                    <div style="font-weight:600; color:#7eb8f7; margin:0.4rem 0 0.2rem;">{title}</div>
                    <div style="font-size:0.82rem; color:#7a90a8;">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
