"""
processor.py
------------
Parses raw extracted text into structured property fields,
then computes valuation metrics using pandas.
"""

import re
from typing import Optional
import pandas as pd
from datetime import date


# ---------------------------------------------------------------------------
# Field Parsing
# ---------------------------------------------------------------------------

def _find(pattern: str, text: str, group: int = 1, default: str = "") -> str:
    """Helper: return first regex match or a default value."""
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group).strip() if m else default


def parse_fields(raw_text: str) -> dict:
    """
    Extract key property fields from raw OCR/PDF text using regex.
    Returns a flat dict of all recognized fields.
    """
    # ---- Subject property ----
    address  = _find(r"(?:property\s+)?address[:\s]+([^\n,]+)", raw_text)
    city     = _find(r"city[:\s]+([^\n,]+)", raw_text)
    state    = _find(r"\bstate[:\s]+([A-Z]{2})\b", raw_text)
    zip_code = _find(r"\b(\d{5}(?:-\d{4})?)\b", raw_text)

    sq_ft     = _find(r"(?:sq(?:uare)?\s*f(?:ee)?t|sqft|sf)[:\s]*([\d,]+)", raw_text)
    bedrooms  = _find(r"(?:beds?|bedrooms?)[:\s]*(\d+)", raw_text)
    bathrooms = _find(r"(?:baths?|bathrooms?)[:\s]*(\d+(?:\.\d)?)", raw_text)
    lot_size  = _find(r"lot\s*size[:\s]*([\d,\.]+\s*(?:acres?|sq\s*ft)?)", raw_text)
    year_built = _find(r"year\s*built[:\s]*(\d{4})", raw_text)
    list_price = _find(r"(?:list(?:ing)?\s*price|asking\s*price)[:\s]*\$?([\d,]+)", raw_text)

    # ---- Comparable sales (up to 3) ----
    # Looks for lines like: "123 Main St | $350,000 | 1,800 sqft"
    comp_pattern = re.compile(
        r"(?:comp\s*\d[\.:]\s*)?([^\|,\n]{5,50})\s*[\|,]\s*\$?([\d,]+)\s*[\|,]\s*([\d,]+)\s*(?:sq(?:uare)?\s*f(?:ee)?t|sqft|sf)?",
        re.IGNORECASE,
    )
    comps_raw = comp_pattern.findall(raw_text)
    comps = []
    for addr, price, sf in comps_raw[:3]:
        comps.append({
            "comp_address": addr.strip(),
            "comp_price":   price.replace(",", ""),
            "comp_sqft":    sf.replace(",", ""),
        })
    # Pad to 3 comps if fewer were found
    while len(comps) < 3:
        comps.append({"comp_address": "", "comp_price": "", "comp_sqft": ""})

    fields = {
        "address":    address,
        "city":       city,
        "state":      state,
        "zip_code":   zip_code,
        "sq_ft":      sq_ft.replace(",", ""),
        "bedrooms":   bedrooms,
        "bathrooms":  bathrooms,
        "lot_size":   lot_size,
        "year_built": year_built,
        "list_price": list_price.replace(",", ""),
        "report_date": date.today().strftime("%B %d, %Y"),
    }

    for i, comp in enumerate(comps, start=1):
        fields[f"comp{i}_address"] = comp["comp_address"]
        fields[f"comp{i}_price"]   = comp["comp_price"]
        fields[f"comp{i}_sqft"]    = comp["comp_sqft"]

    return fields


# ---------------------------------------------------------------------------
# Valuation Computation
# ---------------------------------------------------------------------------

def _safe_float(value: str) -> Optional[float]:
    """Convert a string to float, returning None on failure."""
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def compute_valuation(fields: dict) -> dict:
    """
    Derive valuation metrics from parsed fields.
    Adds computed keys to a copy of the fields dict.
    """
    result = dict(fields)

    subject_sqft  = _safe_float(fields.get("sq_ft"))
    list_price_val = _safe_float(fields.get("list_price"))

    # Price-per-sqft for subject property
    if subject_sqft and list_price_val and subject_sqft > 0:
        result["price_per_sqft"] = f"${list_price_val / subject_sqft:,.2f}"
    else:
        result["price_per_sqft"] = "N/A"

    # Avg comparable price-per-sqft
    comp_ppsf_values = []
    for i in range(1, 4):
        cp = _safe_float(fields.get(f"comp{i}_price"))
        cs = _safe_float(fields.get(f"comp{i}_sqft"))
        if cp and cs and cs > 0:
            comp_ppsf_values.append(cp / cs)

    if comp_ppsf_values:
        avg_comp_ppsf = sum(comp_ppsf_values) / len(comp_ppsf_values)
        result["avg_comp_ppsf"] = f"${avg_comp_ppsf:,.2f}"
        # Estimated market value = avg comp $/sqft × subject sqft
        if subject_sqft:
            est_value = avg_comp_ppsf * subject_sqft
            result["estimated_value"] = f"${est_value:,.0f}"
        else:
            result["estimated_value"] = "N/A"
    else:
        result["avg_comp_ppsf"]   = "N/A"
        result["estimated_value"] = "N/A"

    # Format list price for display
    if list_price_val:
        result["list_price_display"] = f"${list_price_val:,.0f}"
    else:
        result["list_price_display"] = fields.get("list_price", "N/A")

    # Format comp prices for display
    for i in range(1, 4):
        cp = _safe_float(fields.get(f"comp{i}_price"))
        result[f"comp{i}_price_display"] = f"${cp:,.0f}" if cp else ""
        cs = _safe_float(fields.get(f"comp{i}_sqft"))
        result[f"comp{i}_sqft_display"]  = f"{cs:,.0f}" if cs else ""
        if cp and cs and cs > 0:
            result[f"comp{i}_ppsf"] = f"${cp/cs:,.2f}"
        else:
            result[f"comp{i}_ppsf"] = ""

    return result


# ---------------------------------------------------------------------------
# DataFrame helpers (for Streamlit editable table)
# ---------------------------------------------------------------------------

SUBJECT_FIELDS = [
    ("address",    "Address"),
    ("city",       "City"),
    ("state",      "State"),
    ("zip_code",   "ZIP Code"),
    ("sq_ft",      "Square Footage"),
    ("bedrooms",   "Bedrooms"),
    ("bathrooms",  "Bathrooms"),
    ("lot_size",   "Lot Size"),
    ("year_built", "Year Built"),
    ("list_price", "List Price ($)"),
]

COMP_FIELDS = [
    ("comp_address", "Address"),
    ("comp_price",   "Sale Price ($)"),
    ("comp_sqft",    "Square Footage"),
]


def fields_to_subject_df(fields: dict) -> pd.DataFrame:
    """Return a 2-column DataFrame (Field, Value) for subject property."""
    rows = [{"Field": label, "Value": fields.get(key, "")}
            for key, label in SUBJECT_FIELDS]
    return pd.DataFrame(rows)


def subject_df_to_fields(df: pd.DataFrame, original: dict) -> dict:
    """Merge edited subject DataFrame back into the fields dict."""
    updated = dict(original)
    label_to_key = {label: key for key, label in SUBJECT_FIELDS}
    for _, row in df.iterrows():
        key = label_to_key.get(row["Field"])
        if key:
            updated[key] = row["Value"]
    return updated


def fields_to_comps_df(fields: dict) -> pd.DataFrame:
    """Return a DataFrame of the 3 comparable sales."""
    rows = []
    for i in range(1, 4):
        rows.append({
            "Comp #":         i,
            "Address":        fields.get(f"comp{i}_address", ""),
            "Sale Price ($)": fields.get(f"comp{i}_price", ""),
            "Square Footage": fields.get(f"comp{i}_sqft", ""),
        })
    return pd.DataFrame(rows)


def comps_df_to_fields(df: pd.DataFrame, original: dict) -> dict:
    """Merge edited comps DataFrame back into the fields dict."""
    updated = dict(original)
    for _, row in df.iterrows():
        i = int(row["Comp #"])
        updated[f"comp{i}_address"] = row["Address"]
        updated[f"comp{i}_price"]   = str(row["Sale Price ($)"])
        updated[f"comp{i}_sqft"]    = str(row["Square Footage"])
    return updated
