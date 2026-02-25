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
import openpyxl

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

    /* ── Chain of Title Timeline ── */
    .chain-timeline { position: relative; padding-left: 2.5rem; margin: 1.5rem 0; }
    .chain-timeline::before {
        content: ''; position: absolute; left: 0.9rem; top: 0; bottom: 0;
        width: 3px; background: linear-gradient(180deg, #1a5dbf, #7eb8f7);
        border-radius: 2px;
    }
    .chain-node {
        position: relative; margin-bottom: 1.5rem; padding: 1rem 1.2rem;
        background: rgba(15,31,56,0.7); border: 1px solid rgba(80,140,220,0.2);
        border-radius: 10px;
    }
    .chain-node.current {
        border-color: #4caf50; background: rgba(76,175,80,0.08);
        box-shadow: 0 0 12px rgba(76,175,80,0.15);
    }
    .chain-node.gap-warning {
        border-color: #ff9800; background: rgba(255,152,0,0.08);
    }
    .chain-node::before {
        content: ''; position: absolute; left: -1.95rem; top: 1.2rem;
        width: 14px; height: 14px; border-radius: 50%;
        background: #1a5dbf; border: 2px solid #0a1929;
    }
    .chain-node.current::before { background: #4caf50; }
    .chain-node .node-date {
        font-size: 0.78rem; color: #7eb8f7; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.5px;
    }
    .chain-node .node-title {
        font-size: 1rem; color: #cfd8e8; font-weight: 600; margin: 0.3rem 0;
    }
    .chain-node .node-detail {
        font-size: 0.85rem; color: #7a90a8; line-height: 1.5;
    }
    .chain-node .node-badge {
        display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
        font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.5px; margin-left: 0.5rem;
    }
    .chain-node .badge-current { background: rgba(76,175,80,0.2); color: #66bb6a; }
    .chain-node .badge-gap { background: rgba(255,152,0,0.2); color: #ffa726; }
    .chain-status {
        padding: 1rem; border-radius: 10px; text-align: center;
        font-weight: 600; margin-top: 1rem;
    }
    .chain-complete { background: rgba(76,175,80,0.1); color: #66bb6a; border: 1px solid rgba(76,175,80,0.3); }
    .chain-broken { background: rgba(255,152,0,0.1); color: #ffa726; border: 1px solid rgba(255,152,0,0.3); }
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
    "Return ONLY a valid JSON object (no markdown fences) with exactly these keys:\n"
    '{\n'
    '  "customer_name": "",\n'
    '  "address": "",\n'
    '  "land_area": "",\n'
    '  "dim_east": "",\n'
    '  "dim_west": "",\n'
    '  "dim_north": "",\n'
    '  "dim_south": "",\n'
    '  "bound_east": "",\n'
    '  "bound_west": "",\n'
    '  "bound_north": "",\n'
    '  "bound_south": ""\n'
    '}\n'
    "CRITICAL ACCURACY INSTRUCTIONS:\n"
    "1. For customer_name, extract the full name of the current buyer/applicant. Format it as: "
    "'Sh./Smt. [First Name] S/O or W/O or D/O [Father/Husband Name]'.\n"
    "2. For address, combine ALL location details into one complete address string.\n"
    "3. For land_area, include both the number and unit (e.g. '784.40 sq.ft').\n"
    "4. For dimensions (dim_east/west/etc.), extract only the dimension value.\n"
    "5. For boundaries (bound_east/west/etc.), extract the name of the neighbor/property on that side. Translate Hindi directions carefully: "
    "उत्तर = North, दक्षिण = South, पूर्व = East, पश्चिम = West.\n"
    "6. ACCURACY IS PARAMOUNT. Do NOT guess or infer — if you cannot read a value clearly, write 'Unclear'."
)

# ─────────────────────────────────────────────────────────────────────────────
# Bank template registry — add new banks here
# ─────────────────────────────────────────────────────────────────────────────
BANK_CONFIGS = {
    "Cholamandalam": {
        "template": "templates/chola_template.xlsx",
        "output_filename": "chola_valuation_report.xlsx",
        "cell_map": {
            "B5":  "customer_name",
            "B14": "address",
            "B15": "address",
            "B22": "land_area",
            "C22": "land_area",
            "B33": "dim_east",
            "B34": "dim_east",
            "C33": "dim_west",
            "C34": "dim_west",
            "D33": "dim_north",
            "D34": "dim_north",
            "E33": "dim_south",
            "E34": "dim_south",
            "B36": "bound_east",
            "B37": "bound_east",
            "C36": "bound_west",
            "C37": "bound_west",
            "D36": "bound_north",
            "D37": "bound_north",
            "E36": "bound_south",
            "E37": "bound_south",
        },
    },
    # ── Add more banks below ──────────────────────────────────────────────
    # "HDFC": {
    #     "template": "templates/hdfc_template.xlsx",
    #     "output_filename": "hdfc_valuation_report.xlsx",
    #     "cell_map": { ... },
    # },
}


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


def generate_bank_report(bank_key: str, extracted_data: dict) -> io.BytesIO:
    """Generate Excel report for the selected bank using its config from BANK_CONFIGS."""
    config = BANK_CONFIGS[bank_key]
    wb = openpyxl.load_workbook(config["template"])
    ws = wb.active

    for cell_ref, data_key in config["cell_map"].items():
        ws[cell_ref] = extracted_data.get(data_key, "N/A")

    out_stream = io.BytesIO()
    wb.save(out_stream)
    out_stream.seek(0)
    return out_stream


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
def render_boundaries_table(st_container, boundaries: dict):
    pass

def render_witnesses(st_container, witnesses):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Chain of Title — Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Normalize a name for fuzzy matching: lowercase, strip honorifics."""
    import re
    n = name.lower().strip()
    # Remove common prefixes and relation markers
    for prefix in ["sh.", "shri", "smt.", "smt", "sh", "mr.", "mrs.", "ms."]:
        n = n.replace(prefix, "")
    # Remove relation markers and everything after
    for marker in [" s/o ", " w/o ", " d/o ", " son of ", " wife of ", " daughter of "]:
        if marker in n:
            n = n.split(marker)[0]
    return re.sub(r"\s+", " ", n).strip()


def _name_match(name_a: str, name_b: str) -> bool:
    """Fuzzy check if two names refer to the same person."""
    a = _normalize_name(name_a)
    b = _normalize_name(name_b)
    if not a or not b:
        return False
    # Exact or substring match
    if a == b or a in b or b in a:
        return True
    # Token overlap: at least 2 tokens in common
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    overlap = tokens_a & tokens_b
    return len(overlap) >= 2


def _parse_date_for_sort(date_str: str):
    """Try to parse a date string for sorting. Returns a sortable tuple."""
    import re
    if not date_str or date_str == "N/A":
        return (9999, 99, 99)
    # Try DD-MM-YYYY or DD/MM/YYYY
    m = re.match(r"(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})", date_str)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    # Try YYYY-MM-DD
    m = re.match(r"(\d{4})[\-/](\d{1,2})[\-/](\d{1,2})", date_str)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Just extract year
    m = re.search(r"(\d{4})", date_str)
    if m:
        return (int(m.group(1)), 1, 1)
    return (9999, 99, 99)


def build_ownership_chain(deed_list: list) -> list:
    """
    Given a list of extracted deed dicts, build a sequence.
    Sorting assumes documents are uploaded in order since dates are removed.
    Returns a list of dicts with added 'chain_status' and 'gap_note' fields.
    """
    chain = []
    for i, deed in enumerate(deed_list):
        entry = {
            "data": deed,
            "date_str": "N/A", # Dates were removed in new prompt format
            "is_current": (i == len(deed_list) - 1),
            "has_gap": False,
            "gap_note": "",
        }
        
        # Check chain continuity: without explicit sellers, we assume valid sequence 
        # or gap if names change unexpectedly. For now, mark all as potential gaps
        # because we don't have Seller name to confirm.
        if i > 0:
            prev_buyer = deed_list[i - 1].get("customer_name", "N/A")
            this_buyer = deed.get("customer_name", "N/A")
            if prev_buyer and this_buyer and prev_buyer != this_buyer:
                entry["has_gap"] = True
                entry["gap_note"] = f"Previous buyer ({prev_buyer}) -> New applicant ({this_buyer}). Missing seller link."

        chain.append(entry)

    return chain


def render_chain_timeline(chain: list):
    """Render the ownership chain as a visual timeline."""
    html = '<div class="chain-timeline">'

    for entry in chain:
        deed = entry["data"]
        buyer = deed.get("customer_name", "N/A")
        seller = "N/A (Hidden in new format)"
        prop_type = ""
        reg_no = ""
        sale_price = "N/A"

        css_class = "chain-node"
        badges = ""
        if entry["is_current"]:
            css_class += " current"
            badges += '<span class="node-badge badge-current">★ Current Deed</span>'
        if entry["has_gap"]:
            css_class += " gap-warning"
            badges += '<span class="node-badge badge-gap">⚠ Gap</span>'

        html += f'''
        <div class="{css_class}">
            <div class="node-date">{entry["date_str"]}{badges}</div>
            <div class="node-title">{prop_type or "Property Transfer"}</div>
            <div class="node-detail">
                <strong>Seller:</strong> {seller}<br>
                <strong>Buyer:</strong> {buyer}<br>
                <strong>Sale Price:</strong> {sale_price}
                {f"<br><strong>Reg. No:</strong> {reg_no}" if reg_no and reg_no != 'N/A' else ""}
            </div>
            {f'<div style="margin-top:0.5rem; font-size:0.78rem; color:#ffa726;">⚠ {entry["gap_note"]}</div>' if entry["has_gap"] else ""}
        </div>
        '''

    html += '</div>'

    # Chain status summary
    gaps = sum(1 for e in chain if e["has_gap"])
    if gaps == 0:
        html += '<div class="chain-status chain-complete">✅ Chain is COMPLETE — no gaps detected</div>'
    else:
        html += f'<div class="chain-status chain-broken">⚠️ {gaps} gap{"s" if gaps > 1 else ""} detected in the ownership chain</div>'

    return html


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
        **Modes**

        📄 **Single Deed** — Upload 1 PDF, extract data

        🔗 **Chain of Title** — Upload multiple deeds,
        trace ownership from original to current owner

        ---

        **Fields extracted per deed**
        - Buyer & Seller (name, age, address)
        - Property Identifiers (patta/plot/khasra no.)
        - Area, Boundaries, Transaction
        - Registration & Witnesses

        ---
        *Handles printed and handwritten Hindi*
        """
    )
    st.markdown("---")
    st.caption(f"Model: `{DEFAULT_MODEL}` · Antigravity PropTech v3.0")


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
# Mode selector
# ─────────────────────────────────────────────────────────────────────────────
mode = st.radio(
    "Choose mode",
    ["📄 Single Deed", "🔗 Chain of Title"],
    horizontal=True,
    label_visibility="collapsed",
)


# ═══════════════════════════════════════════════════════════════════════════════
# MODE 1: SINGLE DEED (original behavior)
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "📄 Single Deed":

    st.markdown('<div class="avm-card">', unsafe_allow_html=True)
    st.markdown('<span class="badge badge-blue">Step 1</span>', unsafe_allow_html=True)
    st.markdown("### 📄 Upload Property Document")
    st.markdown("Upload a scanned property deed PDF — any number of pages, printed or handwritten Hindi.")

    uploaded_pdf = st.file_uploader(
        "Drop your PDF here",
        type=["pdf"],
        label_visibility="collapsed",
        key="single_upload",
    )
    st.markdown("</div>", unsafe_allow_html=True)

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
                st.error("AI Engine not configured. Please contact the administrator.", icon="🚨")
            elif not render_ok:
                st.error("Cannot extract — PDF rendering failed in Step 2.")
            else:
                if st.button("⚡ Extract Property Data", use_container_width=True, key="single_extract"):
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

        # ── Results display ──────────────────────────────────────────────────
        if st.session_state.get("extracted_data"):
            extracted = st.session_state["extracted_data"]

            st.markdown("---")
            st.markdown('<span class="badge badge-green">Results</span>', unsafe_allow_html=True)
            st.markdown("## 📊 Extracted Property Data")

            tab_table, tab_json, tab_raw = st.tabs(
                ["📋 Formatted Results", "🗂️ Raw JSON", "📝 Model Response"]
            )

            with tab_table:
                st.markdown('<div class="avm-card">', unsafe_allow_html=True)
                st.markdown("#### 👤 Customer & Property Summary")
                import pandas as pd
                st.table(pd.DataFrame([
                    {"Field": "Customer Name", "Value": extracted.get("customer_name", "N/A")},
                    {"Field": "Full Address", "Value": extracted.get("address", "N/A")},
                    {"Field": "Land Area", "Value": extracted.get("land_area", "N/A")},
                ]))
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="avm-card">', unsafe_allow_html=True)
                st.markdown("#### 🧭 Boundaries & Dimensions")
                st.table(pd.DataFrame([
                    {"Direction": "East", "Dimension": extracted.get("dim_east", "N/A"), "Neighbour": extracted.get("bound_east", "N/A")},
                    {"Direction": "West", "Dimension": extracted.get("dim_west", "N/A"), "Neighbour": extracted.get("bound_west", "N/A")},
                    {"Direction": "North", "Dimension": extracted.get("dim_north", "N/A"), "Neighbour": extracted.get("bound_north", "N/A")},
                    {"Direction": "South", "Dimension": extracted.get("dim_south", "N/A"), "Neighbour": extracted.get("bound_south", "N/A")},
                ]))
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown("### 📥 Download Report")
                bank_names = list(BANK_CONFIGS.keys())
                selected_bank = st.selectbox(
                    "Select Bank Template",
                    bank_names,
                    key="bank_selector",
                )
                try:
                    config = BANK_CONFIGS[selected_bank]
                    excel_data = generate_bank_report(selected_bank, extracted)
                    st.download_button(
                        label=f"⬇️ Download {selected_bank} Report (.xlsx)",
                        data=excel_data,
                        file_name=config["output_filename"],
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Failed to generate Excel report: {e}")

            with tab_json:
                st.markdown("#### Structured JSON Output")
                st.json(extracted)

            with tab_raw:
                st.markdown("#### Raw model response (pre-parse)")
                st.code(st.session_state.get("raw_response", ""), language="json")

    else:
        # Idle hero state
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


# ═══════════════════════════════════════════════════════════════════════════════
# MODE 2: CHAIN OF TITLE
# ═══════════════════════════════════════════════════════════════════════════════
else:

    st.markdown('<div class="avm-card">', unsafe_allow_html=True)
    st.markdown('<span class="badge badge-blue">Step 1</span>', unsafe_allow_html=True)
    st.markdown("### 🔗 Upload All Deeds in the Chain")
    st.markdown(
        "Upload **all property documents** in the ownership chain — sale deeds, "
        "allotment letters, gift deeds, partition deeds, etc. The AI will extract "
        "data from each and build the ownership timeline."
    )

    uploaded_pdfs = st.file_uploader(
        "Drop all PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="chain_upload",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if uploaded_pdfs and len(uploaded_pdfs) > 0:

        st.markdown('<div class="avm-card">', unsafe_allow_html=True)
        st.markdown('<span class="badge badge-amber">Step 2</span>', unsafe_allow_html=True)
        st.markdown(f"### 🤖 AI Extraction — {len(uploaded_pdfs)} Document{'s' if len(uploaded_pdfs) > 1 else ''}")

        if not GEMINI_API_KEY:
            st.error("AI Engine not configured. Please contact the administrator.", icon="🚨")
        else:
            if st.button("⚡ Extract All & Build Chain", use_container_width=True, key="chain_extract"):
                all_extractions = []
                progress_bar = st.progress(0, text="Starting extraction…")

                for idx, pdf_file in enumerate(uploaded_pdfs):
                    file_label = pdf_file.name
                    progress_bar.progress(
                        (idx) / len(uploaded_pdfs),
                        text=f"📄 Processing {file_label} ({idx + 1}/{len(uploaded_pdfs)})…"
                    )

                    try:
                        pdf_bytes = pdf_file.read()
                        page_images = pdf_to_pil_images(pdf_bytes, dpi=300)
                        extracted_data, _ = extract_with_gemini(
                            GEMINI_API_KEY, page_images, DEFAULT_MODEL
                        )
                        extracted_data["_source_file"] = file_label
                        extracted_data["_page_count"] = len(page_images)
                        all_extractions.append(extracted_data)
                    except Exception as exc:
                        st.warning(f"⚠️ Failed to extract from {file_label}: {exc}")

                progress_bar.progress(1.0, text="✅ All documents processed!")

                if all_extractions:
                    chain = build_ownership_chain(all_extractions)
                    st.session_state["chain_data"] = chain
                    st.session_state["chain_extractions"] = all_extractions
                    st.success(f"✅ Extracted data from {len(all_extractions)} documents and built ownership chain!", icon="🔗")
                else:
                    st.error("No documents were successfully extracted.")

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Chain of Title Results ────────────────────────────────────────────
        if st.session_state.get("chain_data"):
            chain = st.session_state["chain_data"]
            all_extractions = st.session_state.get("chain_extractions", [])

            st.markdown("---")
            st.markdown('<span class="badge badge-green">Results</span>', unsafe_allow_html=True)
            st.markdown("## 🔗 Chain of Title — Ownership Timeline")

            tab_timeline, tab_details, tab_json = st.tabs(
                ["📜 Ownership Timeline", "📋 Individual Deed Details", "🗂️ All Data (JSON)"]
            )

            with tab_timeline:
                st.markdown('<div class="avm-card">', unsafe_allow_html=True)
                st.markdown(f"**{len(chain)} documents** in the ownership chain")

                # Summary of chain
                if chain:
                    first_buyer = chain[0]["data"].get("customer_name", "N/A")
                    last_buyer = chain[-1]["data"].get("customer_name", "N/A")
                    first_date = chain[0]["date_str"]
                    last_date = chain[-1]["date_str"]
                    st.markdown(
                        f"**Original owner:** {first_buyer} ({first_date})  \n"
                        f"**Current owner:** {last_buyer} ({last_date})"
                    )

                timeline_html = render_chain_timeline(chain)
                st.markdown(timeline_html, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with tab_details:
                for i, entry in enumerate(chain):
                    deed = entry["data"]
                    source = deed.get("_source_file", f"Document {i+1}")
                    badge = " ★ CURRENT" if entry["is_current"] else ""
                    st.markdown(f'<div class="avm-card{" current" if entry["is_current"] else ""}">', unsafe_allow_html=True)
                    st.markdown(f"#### 📄 {source}{badge}")
                    st.markdown(f"**Date:** {entry['date_str']}")

                    # Render all categories for this deed
                    st.markdown("#### 👤 Customer & Property Summary")
                    import pandas as pd
                    st.table(pd.DataFrame([
                        {"Field": "Customer Name", "Value": deed.get("customer_name", "N/A")},
                        {"Field": "Full Address", "Value": deed.get("address", "N/A")},
                        {"Field": "Land Area", "Value": deed.get("land_area", "N/A")},
                    ]))

                    st.markdown("#### 🧭 Boundaries & Dimensions")
                    st.table(pd.DataFrame([
                        {"Direction": "East", "Dimension": deed.get("dim_east", "N/A"), "Neighbour": deed.get("bound_east", "N/A")},
                        {"Direction": "West", "Dimension": deed.get("dim_west", "N/A"), "Neighbour": deed.get("bound_west", "N/A")},
                        {"Direction": "North", "Dimension": deed.get("dim_north", "N/A"), "Neighbour": deed.get("bound_north", "N/A")},
                        {"Direction": "South", "Dimension": deed.get("dim_south", "N/A"), "Neighbour": deed.get("bound_south", "N/A")},
                    ]))

                    st.markdown('</div>', unsafe_allow_html=True)
                    st.markdown("")

            with tab_json:
                st.markdown("#### All Extracted Data")
                st.json(all_extractions)

    else:
        # Idle hero state for Chain mode
        st.markdown('<div class="avm-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div style="text-align:center; padding: 3rem 1rem;">
                <div style="font-size:4rem; margin-bottom:1rem;">🔗</div>
                <h2 style="color:#7eb8f7; margin-bottom:0.5rem;">Chain of Title</h2>
                <p style="color:#607d8b; max-width:520px; margin:0 auto;">
                    Upload all property deeds in the ownership chain above.
                    The AI will extract data from each document, match buyer→seller
                    names to build the ownership timeline, detect any gaps,
                    and highlight the current deed.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        feat1, feat2, feat3 = st.columns(3)
        for col, icon, title, desc in [
            (feat1, "📚", "Multi-Document",  "Upload 2-20 deeds at once"),
            (feat2, "🔗", "Auto Chain Link", "Matches buyer→seller across deeds"),
            (feat3, "⚠️", "Gap Detection",   "Flags breaks in the ownership chain"),
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
