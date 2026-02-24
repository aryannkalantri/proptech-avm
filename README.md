# PropTech AVM: Vision Extractor

AI-powered property document analyzer that extracts structured data from Indian property deeds (Sale Deeds, Pattas, Registry documents) containing printed and handwritten Hindi.

## Features
- 📄 **Multi-page PDF support** — reads every page, not just page 1
- 🤖 **Gemini Vision AI** — powered by Google Gemini 2.5 Flash
- 🧭 **Per-side boundary dimensions** — North/South/East/West with measurements
- 📍 **Smart identifiers** — distinguishes Patta No., Book No., Plot No., Khasra No., etc.
- 📋 **Full address** — one copy-pasteable address string
- 🌐 **Hindi → English translation** — all fields translated automatically

## Setup (Local)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:
```
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Run:
```bash
streamlit run app.py
```

## Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo, set `app.py` as the main file
4. Add your API key in **Settings → Secrets**:
   ```toml
   GEMINI_API_KEY = "your_key_here"
   GEMINI_MODEL = "gemini-2.5-flash"
   ```
5. Click Deploy

## Tech Stack
- [Streamlit](https://streamlit.io) — UI framework
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io) — PDF rendering
- [Google Gemini](https://ai.google.dev) — Vision AI extraction
- [python-dotenv](https://pypi.org/project/python-dotenv/) — Local env config
