"""
app_v2_test.py — Satellite Discrepancy Engine (PoC)
Run: streamlit run app_v2_test.py --server.port 8502
"""

import io
import json
import os
import re
import traceback

import fitz  # PyMuPDF
from dotenv import load_dotenv
from google import genai
import streamlit as st
from PIL import Image
import openpyxl
import requests
import folium
from streamlit_folium import st_folium

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PropTech AVM: Satellite Risk Engine",
    page_icon="🛰️",
    layout="wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS (dark premium theme)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }
.avm-card {
    background: linear-gradient(135deg, rgba(30,41,59,0.85), rgba(15,23,42,0.95));
    border: 1px solid rgba(126,184,247,0.15);
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    backdrop-filter: blur(12px);
}
.badge {
    display: inline-block; padding: 0.2rem 0.7rem; border-radius: 999px;
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.05em; margin-bottom: 0.5rem;
}
.badge-blue   { background: rgba(59,130,246,0.2); color: #60a5fa; }
.badge-amber  { background: rgba(245,158,11,0.2); color: #fbbf24; }
.badge-green  { background: rgba(34,197,94,0.2);  color: #4ade80; }
.badge-red    { background: rgba(239,68,68,0.2);  color: #f87171; }
.risk-high    { border-left: 4px solid #ef4444; padding-left: 1rem; }
.risk-medium  { border-left: 4px solid #f59e0b; padding-left: 1rem; }
.risk-low     { border-left: 4px solid #22c55e; padding-left: 1rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────────────────────────────────────
try:
    GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
except Exception:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Sidebar — API keys
st.sidebar.markdown("### 🔑 API Configuration")
gmaps_key = st.sidebar.text_input(
    "Google Maps API Key",
    value=os.getenv("GMAPS_API_KEY", ""),
    type="password",
    help="Used for satellite image download via Static Maps API",
)

# ─────────────────────────────────────────────────────────────────────────────
# Extraction prompt (with confidence scoring)
# ─────────────────────────────────────────────────────────────────────────────
EXTRACTION_PROMPT = (
    "You are an expert Indian real estate data extractor. "
    "I am sending you ALL pages of an Indian property title deed. "
    "Return ONLY a valid JSON object (no markdown fences). "
    "IMPORTANT: Every field must be a nested object with exactly two keys: "
    "'value' (the extracted text) and 'confidence' (strictly 'High', 'Medium', or 'Low').\n"
    "Use 'Low' if the handwriting is messy, smudged, or barely legible. "
    "Use 'Medium' if you can read it but are not 100% certain. "
    "Use 'High' only when the text is clearly readable.\n\n"
    "Return exactly these keys:\n"
    '{\n'
    '  "customer_name": {"value": "", "confidence": "High"},\n'
    '  "address": {"value": "", "confidence": "High"},\n'
    '  "land_area": {"value": "", "confidence": "High"},\n'
    '  "dim_east": {"value": "", "confidence": "High"},\n'
    '  "dim_west": {"value": "", "confidence": "High"},\n'
    '  "dim_north": {"value": "", "confidence": "High"},\n'
    '  "dim_south": {"value": "", "confidence": "High"},\n'
    '  "bound_east": {"value": "", "confidence": "High"},\n'
    '  "bound_west": {"value": "", "confidence": "High"},\n'
    '  "bound_north": {"value": "", "confidence": "High"},\n'
    '  "bound_south": {"value": "", "confidence": "High"}\n'
    '}\n'
    "CRITICAL ACCURACY INSTRUCTIONS:\n"
    "1. For customer_name, extract the full name of the current buyer/applicant.\n"
    "2. For address, combine ALL location details into one complete address string.\n"
    "3. For land_area, include both the number and unit (e.g. '784.40 sq.ft').\n"
    "4. For dimensions (dim_east/west/etc.), extract only the dimension value.\n"
    "5. For boundaries (bound_east/west/etc.), extract the name of the neighbor/property on that side.\n"
    "6. ACCURACY IS PARAMOUNT. If you cannot read a value clearly, "
    "set value to 'Unclear' and confidence to 'Low'."
)

DISCREPANCY_PROMPT = (
    "You are a PropTech Risk Officer. I am giving you:\n"
    "1. The extracted details of a property deed (JSON below)\n"
    "2. A current satellite image of the property coordinates\n\n"
    "DEED DATA:\n{deed_json}\n\n"
    "Compare them and produce a DISCREPANCY REPORT. Analyze carefully:\n"
    "- Does the deed describe empty/vacant land while the satellite shows a built structure (or vice versa)?\n"
    "- Are there obvious boundary discrepancies or encroachments visible?\n"
    "- Any signs of unauthorized construction, environmental risk, or flood-prone terrain?\n"
    "- Does the visible plot size roughly match the deed's land area?\n\n"
    "Output EXACTLY in this format:\n"
    "RISK LEVEL: [HIGH / MEDIUM / LOW / NONE]\n"
    "FINDINGS:\n"
    "- [finding 1]\n"
    "- [finding 2]\n"
    "- ...\n"
    "RECOMMENDATION: [one-line action item for the bank valuer]"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def get_val(data: dict, key: str, default: str = "N/A") -> str:
    field = data.get(key, default)
    if isinstance(field, dict):
        return field.get("value", default)
    return field if field else default


def get_conf(data: dict, key: str) -> str:
    field = data.get(key)
    if isinstance(field, dict):
        return field.get("confidence", "High")
    return "High"


def conf_badge(level: str) -> str:
    badges = {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"}
    return badges.get(level, "⚪ Unknown")


def pdf_to_pil_images(pdf_bytes: bytes, dpi: int = 200) -> list:
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
    client = genai.Client(api_key=api_key)
    contents = [EXTRACTION_PROMPT] + images
    response = client.models.generate_content(model=model_name, contents=contents)
    raw_text = response.text.strip()
    try:
        clean = raw_text
        if clean.startswith("```"):
            clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        return json.loads(clean), raw_text
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned non-JSON output: {exc}") from exc


def download_satellite_image(lat: float, lon: float, api_key: str, zoom: int = 20) -> Image.Image:
    """Download satellite image from Google Maps Static API."""
    url = (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat},{lon}"
        f"&zoom={zoom}"
        f"&size=600x600"
        f"&maptype=satellite"
        f"&key={api_key}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content))


def run_discrepancy_check(api_key: str, satellite_img: Image.Image, deed_data: dict) -> str:
    """Send satellite image + deed JSON to Gemini for risk analysis."""
    client = genai.Client(api_key=api_key)

    # Build clean JSON of just the values for the prompt
    clean_data = {}
    for key in ["customer_name", "address", "land_area",
                 "dim_east", "dim_west", "dim_north", "dim_south",
                 "bound_east", "bound_west", "bound_north", "bound_south"]:
        clean_data[key] = get_val(deed_data, key)

    prompt = DISCREPANCY_PROMPT.format(deed_json=json.dumps(clean_data, indent=2))

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, satellite_img],
    )
    return response.text.strip()


def parse_risk_level(report: str) -> str:
    """Extract risk level from the discrepancy report."""
    report_upper = report.upper()
    if "RISK LEVEL: HIGH" in report_upper or "RISK LEVEL:HIGH" in report_upper:
        return "HIGH"
    elif "RISK LEVEL: MEDIUM" in report_upper or "RISK LEVEL:MEDIUM" in report_upper:
        return "MEDIUM"
    elif "RISK LEVEL: LOW" in report_upper or "RISK LEVEL:LOW" in report_upper:
        return "LOW"
    return "NONE"


# ─────────────────────────────────────────────────────────────────────────────
# Main UI
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    "<h1 style='text-align:center;'>🛰️ PropTech AVM: Satellite Risk Engine</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:#7eb8f7; margin-top:-0.5rem;'>"
    "Upload a deed · AI extracts data · Compare against satellite imagery · Detect discrepancies"
    "</p>",
    unsafe_allow_html=True,
)
st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Upload PDF
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="avm-card">', unsafe_allow_html=True)
st.markdown('<span class="badge badge-blue">Step 1</span>', unsafe_allow_html=True)
st.markdown("### 📄 Upload Property Document")

uploaded_pdf = st.file_uploader(
    "Drop your PDF here",
    type=["pdf"],
    label_visibility="collapsed",
    key="v2_upload",
)
st.markdown("</div>", unsafe_allow_html=True)

if uploaded_pdf is not None:

    # ── Step 2: Preview + Extract ────────────────────────────────────────────
    col_img, col_results = st.columns([1, 1.4], gap="large")

    with col_img:
        st.markdown('<div class="avm-card">', unsafe_allow_html=True)
        st.markdown('<span class="badge badge-blue">Step 2</span>', unsafe_allow_html=True)
        st.markdown("### 🖼️ Document Preview")

        with st.spinner("Rendering…"):
            try:
                pdf_bytes = uploaded_pdf.read()
                page_images = pdf_to_pil_images(pdf_bytes, dpi=300)
                st.image(page_images[0], use_container_width=True,
                         caption=f"Page 1 of {len(page_images)}")
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
            st.error("Gemini API key not configured.", icon="🚨")
        elif not render_ok:
            st.error("Cannot extract — PDF rendering failed.")
        else:
            if st.button("⚡ Extract Property Data", use_container_width=True, key="v2_extract"):
                with st.spinner(f"Analyzing {len(page_images)} pages with Gemini…"):
                    try:
                        extracted_data, raw_response = extract_with_gemini(
                            GEMINI_API_KEY, page_images, DEFAULT_MODEL
                        )
                        st.session_state["v2_extracted"] = extracted_data
                        st.session_state["v2_raw"] = raw_response
                        st.success("Extraction complete!", icon="✅")
                    except Exception as exc:
                        st.error(f"AI Engine error: {exc}", icon="🚨")
                        with st.expander("Details"):
                            st.code(traceback.format_exc())

        st.markdown("</div>", unsafe_allow_html=True)

    # ── Step 4: Results + Risk Analysis ──────────────────────────────────────
    if st.session_state.get("v2_extracted"):
        extracted = st.session_state["v2_extracted"]

        st.markdown("---")
        st.markdown('<span class="badge badge-green">Results</span>', unsafe_allow_html=True)
        st.markdown("## 📊 Extracted Property Data")

        import pandas as pd

        col_summary, col_boundaries = st.columns(2)
        with col_summary:
            st.markdown('<div class="avm-card">', unsafe_allow_html=True)
            st.markdown("#### 👤 Customer & Property")
            st.table(pd.DataFrame([
                {"Field": "Customer Name", "Value": get_val(extracted, "customer_name"), "Conf.": conf_badge(get_conf(extracted, "customer_name"))},
                {"Field": "Address", "Value": get_val(extracted, "address"), "Conf.": conf_badge(get_conf(extracted, "address"))},
                {"Field": "Land Area", "Value": get_val(extracted, "land_area"), "Conf.": conf_badge(get_conf(extracted, "land_area"))},
            ]))
            st.markdown("</div>", unsafe_allow_html=True)

        with col_boundaries:
            st.markdown('<div class="avm-card">', unsafe_allow_html=True)
            st.markdown("#### 🧭 Boundaries & Dimensions")
            st.table(pd.DataFrame([
                {"Dir.": "East", "Dim.": get_val(extracted, "dim_east"), "Boundary": get_val(extracted, "bound_east"), "Conf.": conf_badge(get_conf(extracted, "dim_east"))},
                {"Dir.": "West", "Dim.": get_val(extracted, "dim_west"), "Boundary": get_val(extracted, "bound_west"), "Conf.": conf_badge(get_conf(extracted, "dim_west"))},
                {"Dir.": "North", "Dim.": get_val(extracted, "dim_north"), "Boundary": get_val(extracted, "bound_north"), "Conf.": conf_badge(get_conf(extracted, "dim_north"))},
                {"Dir.": "South", "Dim.": get_val(extracted, "dim_south"), "Boundary": get_val(extracted, "bound_south"), "Conf.": conf_badge(get_conf(extracted, "dim_south"))},
            ]))
            st.markdown("</div>", unsafe_allow_html=True)

        # ── RISK ANALYSIS SECTION ────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<span class="badge badge-red">Risk Engine</span>', unsafe_allow_html=True)
        st.markdown("## 🛰️ Risk Analysis: Satellite vs. Deed")

        st.markdown('<div class="avm-card">', unsafe_allow_html=True)
        st.markdown("### 📍 Property Coordinates")
        st.markdown("Enter the latitude and longitude of the property to view satellite imagery and run risk analysis.")

        coord_col1, coord_col2 = st.columns(2)
        with coord_col1:
            lat = st.number_input("Latitude", value=26.9124, format="%.6f", key="v2_lat")
        with coord_col2:
            lon = st.number_input("Longitude", value=75.7873, format="%.6f", key="v2_lon")

        st.markdown("</div>", unsafe_allow_html=True)

        # ── Satellite Map ────────────────────────────────────────────────────
        map_col, action_col = st.columns([1.5, 1])

        with map_col:
            st.markdown('<div class="avm-card">', unsafe_allow_html=True)
            st.markdown("### 🗺️ Satellite Map Preview")

            m = folium.Map(location=[lat, lon], zoom_start=18)
            # Add Esri satellite tiles (free, no API key needed)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Satellite",
                overlay=False,
            ).add_to(m)
            # Add marker
            folium.Marker(
                [lat, lon],
                popup=f"Property: {get_val(extracted, 'address')}",
                icon=folium.Icon(color="red", icon="home"),
            ).add_to(m)

            st_folium(m, width=700, height=450, key="v2_map")
            st.markdown("</div>", unsafe_allow_html=True)

        with action_col:
            st.markdown('<div class="avm-card">', unsafe_allow_html=True)
            st.markdown("### 🔍 AI Discrepancy Check")
            st.markdown(
                "Downloads a high-res satellite image from Google Maps "
                "and asks Gemini to compare it against the deed data."
            )

            if not gmaps_key:
                st.warning("Enter your Google Maps API Key in the sidebar.", icon="🔑")
            elif st.button("🔍 Run AI Discrepancy Check", use_container_width=True, key="v2_risk_check", type="primary"):
                with st.spinner("📡 Downloading satellite image…"):
                    try:
                        sat_img = download_satellite_image(lat, lon, gmaps_key)
                        st.session_state["v2_sat_img"] = sat_img
                        st.image(sat_img, caption=f"Satellite @ ({lat:.4f}, {lon:.4f})", use_container_width=True)
                    except Exception as exc:
                        st.error(f"Failed to download satellite image: {exc}")
                        sat_img = None

                if sat_img:
                    with st.spinner("🤖 Running AI discrepancy analysis…"):
                        try:
                            report = run_discrepancy_check(GEMINI_API_KEY, sat_img, extracted)
                            st.session_state["v2_report"] = report
                        except Exception as exc:
                            st.error(f"AI analysis failed: {exc}")
                            with st.expander("Details"):
                                st.code(traceback.format_exc())

            st.markdown("</div>", unsafe_allow_html=True)

        # ── Discrepancy Report ───────────────────────────────────────────────
        if st.session_state.get("v2_report"):
            report = st.session_state["v2_report"]
            risk_level = parse_risk_level(report)

            st.markdown("---")
            st.markdown('<span class="badge badge-red">Report</span>', unsafe_allow_html=True)
            st.markdown("## 📋 Discrepancy Report")

            risk_class = {
                "HIGH": "risk-high",
                "MEDIUM": "risk-medium",
                "LOW": "risk-low",
                "NONE": "risk-low",
            }.get(risk_level, "risk-low")

            risk_icon = {
                "HIGH": "🚨",
                "MEDIUM": "⚠️",
                "LOW": "✅",
                "NONE": "✅",
            }.get(risk_level, "ℹ️")

            st.markdown(f'<div class="avm-card {risk_class}">', unsafe_allow_html=True)

            if risk_level == "HIGH":
                st.error(f"{risk_icon} RISK LEVEL: HIGH — Significant discrepancies detected", icon="🚨")
            elif risk_level == "MEDIUM":
                st.warning(f"{risk_icon} RISK LEVEL: MEDIUM — Some concerns require verification", icon="⚠️")
            else:
                st.info(f"{risk_icon} RISK LEVEL: {risk_level} — No significant discrepancies", icon="✅")

            st.markdown(report)
            st.markdown("</div>", unsafe_allow_html=True)

            # Show satellite image alongside report
            if st.session_state.get("v2_sat_img"):
                with st.expander("🛰️ Satellite Image Used for Analysis"):
                    st.image(st.session_state["v2_sat_img"], caption="Google Maps Static API — Satellite View")

else:
    # Idle hero state
    st.markdown('<div class="avm-card">', unsafe_allow_html=True)
    st.markdown(
        """
        <div style="text-align:center; padding: 3rem 1rem;">
            <div style="font-size:4rem; margin-bottom:1rem;">🛰️</div>
            <h2 style="color:#7eb8f7; margin-bottom:0.5rem;">Satellite Risk Engine</h2>
            <p style="color:#607d8b; max-width:560px; margin:0 auto;">
                Upload a property deed, extract data with AI, then compare against
                satellite imagery to detect discrepancies — vacant land vs. built structures,
                boundary mismatches, and potential fraud risks.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    feat1, feat2, feat3 = st.columns(3)
    for col, icon, title, desc in [
        (feat1, "📄", "Deed Extraction", "AI reads Hindi handwriting with confidence scoring"),
        (feat2, "🛰️", "Satellite Imagery", "High-res Google Maps view of the property"),
        (feat3, "🔍", "AI Risk Analysis", "Gemini compares deed vs. reality for fraud detection"),
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
