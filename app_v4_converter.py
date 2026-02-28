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
    Extract the data and return a strict JSON object with these keys: 
    customer_name, property_address, total_land_area, built_up_area, 
    east_boundary, west_boundary, north_boundary, south_boundary, 
    fair_market_value, distress_value. 
    
    If a value is missing, return "N/A". Return ONLY the raw JSON object, without markdown formatting.
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

def inject_into_excel(data: dict) -> io.BytesIO:
    """Loads the target template, maps the extracted JSON to specific cells, and returns a BytesIO buffer."""
    template_path = "templates/axis_template.xlsx"
    
    # data_only=False ensures existing formulas (like B20/B19) remain intact
    wb = openpyxl.load_workbook(template_path, data_only=False)
    ws = wb.active
    
    # --- CELL MAPPING ---
    ws['B5'] = data.get('customer_name', 'N/A')
    ws['B6'] = data.get('property_address', 'N/A')
    
    ws['B11'] = data.get('total_land_area', 'N/A')
    ws['B12'] = data.get('built_up_area', 'N/A')
    
    ws['E11'] = data.get('east_boundary', 'N/A')
    ws['E12'] = data.get('west_boundary', 'N/A')
    ws['E13'] = data.get('north_boundary', 'N/A')
    ws['E14'] = data.get('south_boundary', 'N/A')
    
    # Usually currency values need cleaning, but inserting raw mapped strings for sandbox purposes
    ws['B19'] = data.get('fair_market_value', 'N/A')
    ws['B20'] = data.get('distress_value', 'N/A')
    
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
        st.markdown("### 📊 Extracted Data")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Customer Name", extracted_data.get('customer_name'))
            st.metric("Total Land Area", extracted_data.get('total_land_area'))
            st.metric("Fair Market Value", extracted_data.get('fair_market_value'))
        with col2:
            st.metric("Distress Value", extracted_data.get('distress_value'))
            st.metric("Built Up Area", extracted_data.get('built_up_area'))
            
        st.markdown("### 🧭 Boundaries")
        st.markdown(f"""
        - **North:** {extracted_data.get('north_boundary')}
        - **South:** {extracted_data.get('south_boundary')}
        - **East:** {extracted_data.get('east_boundary')}
        - **West:** {extracted_data.get('west_boundary')}
        """)
        
        st.markdown("### 📍 Address")
        st.info(extracted_data.get('property_address'))
        
        st.markdown("---")
        
        # 4. Excel Injection & Download
        try:
            excel_bytes = inject_into_excel(extracted_data)
            
            st.download_button(
                label="📥 Download Injected Axis Template (.xlsx)",
                data=excel_bytes,
                file_name=f"{extracted_data.get('customer_name', 'Report')}_Axis_Format.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
        except FileNotFoundError:
            st.error("Template 'templates/axis_template.xlsx' not found. Please ensure it exists.")
        except Exception as e:
            st.error(f"Failed to compile Excel file: {e}")
