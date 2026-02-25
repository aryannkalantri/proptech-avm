"""
report_generator.py
-------------------
Fills a Word (.docx) template with valuation data using docxtpl,
then returns the rendered document as bytes for Streamlit download.
"""

import io
from docxtpl import DocxTemplate


def generate_report(data: dict, template_path: str) -> bytes:
    """
    Load the Word template, render it with `data`, and return as bytes.

    Parameters
    ----------
    data : dict
        Flat dictionary of template context variables (all {{ keys }}).
    template_path : str
        Absolute or relative path to the .docx template file.

    Returns
    -------
    bytes
        The rendered .docx file as raw bytes (suitable for st.download_button).
    """
    tpl = DocxTemplate(template_path)
    tpl.render(data)

    buffer = io.BytesIO()
    tpl.save(buffer)
    buffer.seek(0)
    return buffer.read()
