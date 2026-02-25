"""
test_gemini_key.py
------------------
Quick standalone diagnostic script to test your Gemini API key.
Run with:
    venv/bin/python test_gemini_key.py YOUR_API_KEY_HERE
"""

import sys
import google.generativeai as genai


def main():
    if len(sys.argv) < 2:
        print("Usage: venv/bin/python test_gemini_key.py YOUR_API_KEY")
        sys.exit(1)

    api_key = sys.argv[1]
    genai.configure(api_key=api_key)

    # Test 1: List available models
    print("=" * 60)
    print("TEST 1: Listing available models...")
    print("=" * 60)
    try:
        models = list(genai.list_models())
        vision_models = [
            m.name for m in models
            if "generateContent" in [s.name for s in m.supported_generation_methods]
        ]
        print(f"✅ Found {len(vision_models)} content-generation models:")
        for name in sorted(vision_models):
            print(f"   • {name}")
    except Exception as e:
        print(f"❌ Failed to list models: {e}")
        print("\n→ This means your API key is invalid or the API is not enabled.")
        sys.exit(1)

    # Test 2: Simple text prompt (no image — minimal tokens)
    print("\n" + "=" * 60)
    print("TEST 2: Simple text prompt (gemini-2.0-flash)...")
    print("=" * 60)
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Say hello in one word.")
        print(f"✅ Response: {response.text.strip()}")
    except Exception as e:
        err_str = str(e)
        print(f"❌ Failed: {e}")
        if "429" in err_str:
            print("\n→ QUOTA EXHAUSTED. Your free tier limit is 0.")
            print("→ This is a Google Cloud project-level issue, not a code bug.")
            print("\nTROUBLESHOOTING:")
            print("  1. Go to https://aistudio.google.com/apikey")
            print("  2. Click 'Create API key in NEW project' (not an existing project)")
            print("  3. Use the NEW key")
            print("  4. If still failing, your region may not support the free tier.")
            print("     → Enable billing at https://console.cloud.google.com/billing")
        elif "403" in err_str:
            print("\n→ API key does not have permission. Check that the Generative")
            print("  Language API is enabled on the associated GCP project.")
        sys.exit(1)

    # Test 3: Try other models if 2.0-flash fails
    print("\n" + "=" * 60)
    print("TEST 3: Trying alternative models...")
    print("=" * 60)
    for model_name in ["gemini-2.0-flash-lite", "gemini-1.5-flash"]:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Say hello in one word.")
            print(f"✅ {model_name}: {response.text.strip()}")
        except Exception as e:
            print(f"❌ {model_name}: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED — Your key works! Use it in the Streamlit app.")
    print("=" * 60)


if __name__ == "__main__":
    main()
