import streamlit as st
import fitz  # PyMuPDF
import openpyxl
import google.generativeai as genai
import os
import io
import json
from PIL import Image
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.error("Missing Gemini API Key. Please add it to your .env file.")

st.set_page_config(
    page_title="Format Shifting Engine",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- DARK MODE CSS ---
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0E1117; }
    [data-testid="stHeader"] { background-color: rgba(0,0,0,0); }
    [data-testid="stToolbar"] { right: 2rem; }
    div[data-testid="stExpander"] { border: none; box-shadow: none; background-color: #161B22; border-radius: 10px; }
    h1 { color: #f8fafc !important; font-weight: 700 !important; }
    h2, h3 { color: #e2e8f0 !important; font-weight: 600 !important; }
    p, span, div { color: #cbd5e0; }
</style>
""", unsafe_allow_html=True)

# --- LOGIC ---
def pdf_to_pil_images(pdf_bytes: bytes, max_pages: int = 5, dpi: int = 150) -> list:
    """Converts the first N pages of a PDF byte stream into PIL Images."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    num_pages = min(len(doc), max_pages)
    
    for page_num in range(num_pages):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=dpi)
        
        # Convert fitz pixmap to PIL Image
        img_data = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_data))
        images.append(pil_img)
        
    doc.close()
    return images

def extract_data_via_gemini(images: list) -> dict:
    """Sends the PIL images to Gemini and requests strictly formatted JSON."""
    
    prompt = """
    You are an expert Data Extractor. Read these scanned pages of a property valuation report. 
    Extract the data and return a strict JSON object. If a value is missing, return "N/A". Return ONLY the raw JSON object, without markdown formatting.

    Extract these exact keys:
    "report_date" -> Date of report
    "owner_name" -> Name of the property owner/borrower
    "sale_deed_no" -> Sale deed number
    "plot_no" -> Plot Number / Khasra No / Patta No
    "road_width" -> Width of the road
    "colony" -> Colony / Nagar / Sector
    "landmark" -> Locality / Landmark
    "city" -> Village / Town / City
    "pincode" -> Pincode
    "lat" -> Latitude
    "lon" -> Longitude
    "property_type" -> Type of Property (e.g. Residential, Commercial)
    "land_level" -> Level of land with topographical conditions
    "construction_observed" -> Any construction observed on plot
    "civic_amenities" -> Civic Amenities like school, hospital etc
    "transport_availability" -> Availability of local transport
    "plot_area_doc" -> Plot Area as per documents (Sqft)
    "plot_area_actual" -> Plot area as per actual site (Sqft)
    "north_boundary", "south_boundary", "east_boundary", "west_boundary" -> Boundaries out of actual site
    "structure_type" -> Type of Structure
    "no_of_floors" -> No. of Floors
    "occupancy" -> Occupancy Details (Self-Occupied / Rented / Vacant)
    "current_life_years" -> Current Life of the structure in years
    "projected_life_years" -> Projected Life of the Structure in years
    "land_rate" -> Rate per Sq.Ft for Land
    "land_value" -> Amount in Rs for Land
    "building_rate" -> Rate per Sq.Ft for Building
    "building_value" -> Amount in Rs for Building
    "total_market_value" -> Market value Total Valuation in numbers
    "distress_value" -> Distressed / Forced Sale Value
    """
    
    # Send all images + prompt in a single list payload
    payload = images + [prompt]
    
    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
        with st.spinner("🧠 Initializing Format Shifting Engine (Gemini 2.5 Pro Vision)..."):
            response = model.generate_content(payload)
    except Exception as e:
        if "429" in str(e) or "Quota exceeded" in str(e):
            st.warning("⚠️ Gemini 2.5 Pro rate limit reached. Automatically falling back to high-capacity Gemini 2.5 Flash model...")
            try:
                model_fallback = genai.GenerativeModel("gemini-2.5-flash")
                with st.spinner("⚡ Re-running extraction with Gemini 2.5 Flash..."):
                    response = model_fallback.generate_content(payload)
            except Exception as inner_e:
                 st.error(f"Fallback model also failed: {inner_e}")
                 return {}
        else:
            st.error(f"API Error: {e}")
            return {}
    
    
    try:
        # Strip potential markdown formatting (```json ... ```)
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        return json.loads(raw_text)
    except Exception as e:
        st.error(f"Failed to parse JSON response: {e}")
        with st.expander("Raw AI Output"):
            st.code(response.text)
        return {}

from copy import copy

def inject_value_preserve_style(ws, coord, value):
    """Injects a value into a cell while strictly maintaining its original Excel formatting."""
    target_cell = ws[coord]
    
    # Cache the original styles before overwriting
    original_font = copy(target_cell.font) if target_cell.font else None
    original_border = copy(target_cell.border) if target_cell.border else None
    original_fill = copy(target_cell.fill) if target_cell.fill else None
    original_number_format = copy(target_cell.number_format) if target_cell.number_format else None
    original_protection = copy(target_cell.protection) if target_cell.protection else None
    original_alignment = copy(target_cell.alignment) if target_cell.alignment else None

    # Inject Value
    target_cell.value = value
    
    # Re-apply styles
    if original_font: target_cell.font = original_font
    if original_border: target_cell.border = original_border
    if original_fill: target_cell.fill = original_fill
    if original_number_format: target_cell.number_format = original_number_format
    if original_protection: target_cell.protection = original_protection
    if original_alignment: target_cell.alignment = original_alignment


def inject_into_excel(data: dict) -> io.BytesIO:
    """Loads the target template, maps the extracted JSON to specific cells, and returns a BytesIO buffer."""
    template_path = "templates/axis_template.xlsx"
    
    # data_only=False ensures existing formulas (like B20/B19) remain intact
    wb = openpyxl.load_workbook(template_path, data_only=False)
    ws = wb.active
    
    # --- CELL MAPPING (With Style Preservation) ---
    inject_value_preserve_style(ws, 'D10', data.get('report_date', 'N/A'))
    inject_value_preserve_style(ws, 'D11', data.get('owner_name', 'N/A'))
    inject_value_preserve_style(ws, 'D22', data.get('sale_deed_no', 'N/A'))
    inject_value_preserve_style(ws, 'D23', data.get('plot_no', 'N/A'))
    inject_value_preserve_style(ws, 'J23', data.get('road_width', 'N/A'))
    inject_value_preserve_style(ws, 'D24', data.get('colony', 'N/A'))
    inject_value_preserve_style(ws, 'J24', data.get('landmark', 'N/A'))
    inject_value_preserve_style(ws, 'D25', data.get('city', 'N/A'))
    inject_value_preserve_style(ws, 'J26', data.get('pincode', 'N/A'))
    inject_value_preserve_style(ws, 'E28', data.get('lat', 'N/A'))
    inject_value_preserve_style(ws, 'K28', data.get('lon', 'N/A'))
    
    inject_value_preserve_style(ws, 'G31', data.get('property_type', 'N/A'))
    inject_value_preserve_style(ws, 'G32', data.get('land_level', 'N/A'))
    inject_value_preserve_style(ws, 'G33', data.get('construction_observed', 'N/A'))
    inject_value_preserve_style(ws, 'G37', data.get('civic_amenities', 'N/A'))
    inject_value_preserve_style(ws, 'G41', data.get('transport_availability', 'N/A'))
    
    inject_value_preserve_style(ws, 'E54', data.get('plot_area_doc', 'N/A'))
    inject_value_preserve_style(ws, 'K54', data.get('plot_area_actual', 'N/A'))
    
    inject_value_preserve_style(ws, 'H52', data.get('east_boundary', 'N/A'))
    inject_value_preserve_style(ws, 'H53', data.get('west_boundary', 'N/A'))
    inject_value_preserve_style(ws, 'H50', data.get('north_boundary', 'N/A'))
    inject_value_preserve_style(ws, 'H51', data.get('south_boundary', 'N/A'))
    
    inject_value_preserve_style(ws, 'G61', data.get('structure_type', 'N/A'))
    inject_value_preserve_style(ws, 'G62', data.get('no_of_floors', 'N/A'))
    inject_value_preserve_style(ws, 'G63', data.get('occupancy', 'N/A'))
    inject_value_preserve_style(ws, 'E100', data.get('current_life_years', 'N/A'))
    inject_value_preserve_style(ws, 'K100', data.get('projected_life_years', 'N/A'))
    
    inject_value_preserve_style(ws, 'G107', data.get('land_rate', 'N/A'))
    inject_value_preserve_style(ws, 'J107', data.get('land_value', 'N/A'))
    inject_value_preserve_style(ws, 'G108', data.get('building_rate', 'N/A'))
    inject_value_preserve_style(ws, 'J108', data.get('building_value', 'N/A'))
    inject_value_preserve_style(ws, 'J121', data.get('total_market_value', 'N/A'))
    inject_value_preserve_style(ws, 'J122', data.get('distress_value', 'N/A'))
    
    # Save the modified workbook to a binary memory stream
    output_stream = io.BytesIO()
    wb.save(output_stream)
    output_stream.seek(0)
    
    return output_stream


# --- UI DASHBOARD ---
st.title("🔄 Format Shifting Engine")
st.markdown("Upload a scanned PDF valuation report. AI will extract the data and safely inject it into the Axis Bank Excel template.")

uploaded_pdf = st.file_uploader("Upload Scanned Report", type=["pdf"])

if uploaded_pdf is not None:
    pdf_bytes = uploaded_pdf.read()
    
    # 1. Convert PDF to Images
    pil_images = pdf_to_pil_images(pdf_bytes)
    st.info(f"Processed first {len(pil_images)} pages of the document.")
    
    # 2. Extract Data
    extracted_data = extract_data_via_gemini(pil_images)
    
    if extracted_data:
        st.success("Extraction Complete")
        
        # 3. Render Metrics
        st.markdown("### 📊 Bulk Data Migration Overview")
        st.info("Successfully extracted and compiled all comprehensive valuation parameters from the legacy PDF. Generating Excel package...")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Owner Name", extracted_data.get('owner_name', 'N/A'))
            st.metric("Property Type", extracted_data.get('property_type', 'N/A'))
            st.metric("City", extracted_data.get('city', 'N/A'))
        with col2:
            st.metric("Plot Area (Doc)", extracted_data.get('plot_area_doc', 'N/A'))
            st.metric("Plot Area (Actual)", extracted_data.get('plot_area_actual', 'N/A'))
            st.metric("No. of Floors", extracted_data.get('no_of_floors', 'N/A'))
        with col3:
            st.metric("Total Market Value", extracted_data.get('total_market_value', 'N/A'))
            st.metric("Distress Value", extracted_data.get('distress_value', 'N/A'))
            st.metric("Land Value", extracted_data.get('land_value', 'N/A'))
            
        with st.expander("Show All Extracted Fields"):
            st.json(extracted_data)
        
        st.markdown("---")
        
        # 4. Excel Injection & Download
        try:
            excel_bytes = inject_into_excel(extracted_data)
            
            st.download_button(
                label="📥 Download Injected Axis Template (.xlsx)",
                data=excel_bytes,
                file_name=f"{extracted_data.get('owner_name', 'Report')}_Axis_Format.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
        except FileNotFoundError:
            st.error("Template 'templates/axis_template.xlsx' not found. Please ensure it exists.")
        except Exception as e:
            st.error(f"Failed to compile Excel file: {e}")
