#!/usr/bin/env python3
"""
Extract and compress the first page of a PDF using Gemini vision model.
"""

import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from pdf2image import convert_from_path
from PIL import Image

# Load environment variables
load_dotenv()

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.llm.vertex_gemini import VertexGeminiClient
from app.config import GEMINI_MODEL, GCP_PROJECT_ID

# Configuration
PDF_PATH = Path(__file__).parent.parent / "data" / "deepseek ocr paper.pdf"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_IMAGE = OUTPUT_DIR / "page_1.png"
OUTPUT_JSON = OUTPUT_DIR / "page_1.json"

# Gemini configuration
TEMPERATURE = 0
MAX_OUTPUT_TOKENS = 2048

# Prompt (must be used verbatim)
PROMPT = """You are performing optical context compression.

Given an image of a document page:
- Extract structured markdown
- Preserve headings, tables, and key-value fields
- Produce a concise summary
- Return JSON with fields:
  - page_number
  - markdown
  - entities
  - summary"""


def main():
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if PDF exists
    if not PDF_PATH.exists():
        print(f"Error: PDF not found at {PDF_PATH}")
        return
    
    # Validate GCP project ID
    if not GCP_PROJECT_ID:
        print("Error: GCP_PROJECT_ID not found in environment variables")
        print("Please create a .env file with: GCP_PROJECT_ID=your_project_id")
        print("Also ensure you have authenticated with: gcloud auth application-default login")
        return
    
    # Create Vertex Gemini client
    try:
        client = VertexGeminiClient(model_name=GEMINI_MODEL)
    except Exception as e:
        print(f"Error initializing Vertex Gemini client: {e}")
        print("Make sure you have authenticated with: gcloud auth application-default login")
        return
    
    # Convert first page of PDF to image
    print(f"Converting first page of {PDF_PATH} to image...")
    
    # Check for poppler path - prioritize .env file over Windows environment variables
    from dotenv import dotenv_values
    env_vars = dotenv_values()
    poppler_path = env_vars.get("poppler") or env_vars.get("POPPLER")
    # Fall back to Windows environment variable if not in .env
    if not poppler_path:
        poppler_path = os.getenv("poppler") or os.getenv("POPPLER")
    
    print(f"DEBUG: poppler environment variable = {poppler_path}")
    
    # Try to convert PDF
    try:
        if poppler_path:
            poppler_path_obj = Path(poppler_path)
            # If the path ends with "bin", use it directly; otherwise append "bin"
            if poppler_path_obj.name == "bin" or (poppler_path_obj / "bin").exists():
                poppler_bin = poppler_path_obj if poppler_path_obj.name == "bin" else poppler_path_obj / "bin"
            else:
                # Try Library\bin structure (common in poppler-windows releases)
                if (poppler_path_obj / "Library" / "bin").exists():
                    poppler_bin = poppler_path_obj / "Library" / "bin"
                else:
                    poppler_bin = poppler_path_obj / "bin"
            
            print(f"Using Poppler from: {poppler_bin}")
            if not poppler_bin.exists():
                print(f"ERROR: Poppler path {poppler_bin} does not exist!")
                print(f"Please verify the path is correct and the Poppler files are extracted.")
                print(f"Expected to find: {poppler_bin / 'pdftoppm.exe'}")
                return
            images = convert_from_path(str(PDF_PATH), first_page=1, last_page=1, poppler_path=str(poppler_bin))
        else:
            # Try without explicit path (will use PATH)
            print("No poppler environment variable found. Trying system PATH...")
            images = convert_from_path(str(PDF_PATH), first_page=1, last_page=1)
    except Exception as e:
        print(f"Error converting PDF: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure Poppler is extracted (not still in a .zip file)")
        print("2. Restart VS Code/terminal after adding Poppler to PATH")
        print("3. Or set 'poppler' variable in .env file pointing to the bin directory")
        print("4. Verify pdftoppm.exe exists in the Poppler bin directory")
        return
    
    if not images:
        print("Error: Failed to convert PDF page to image")
        return
    
    page_image = images[0]
    
    # Save the image
    print(f"Saving image to {OUTPUT_IMAGE}...")
    page_image.save(OUTPUT_IMAGE)
    
    # Send image to Gemini
    print("Sending image to Gemini...")
    response_text = client.generate_content(
        contents=[PROMPT, page_image],
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    
    # Try to parse as JSON, if not wrap it
    try:
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        # If response is not valid JSON, wrap it
        response_json = {
            "page_number": 1,
            "raw_response": response_text
        }
    
    # Ensure page_number is set
    if "page_number" not in response_json:
        response_json["page_number"] = 1
    
    # Save JSON response
    print(f"Saving response to {OUTPUT_JSON}...")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(response_json, f, indent=2, ensure_ascii=False)
    
    print("Done!")
    print(f"Image saved to: {OUTPUT_IMAGE}")
    print(f"JSON saved to: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()

