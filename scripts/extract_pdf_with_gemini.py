#!/usr/bin/env python3
"""
Extract and compress PDF pages using Gemini vision model.
Processes entire PDF or a page range, saving per-page images and JSON outputs.
"""

import os
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from pdf2image import convert_from_path
from PIL import Image

# Load environment variables
load_dotenv()

# Gemini configuration
GEMINI_MODEL = "gemini-3-pro-preview"
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


def get_poppler_path():
    """Get Poppler path from .env file or environment variables."""
    from dotenv import dotenv_values
    env_vars = dotenv_values()
    poppler_path = env_vars.get("poppler") or env_vars.get("POPPLER")
    if not poppler_path:
        poppler_path = os.getenv("poppler") or os.getenv("POPPLER")
    return poppler_path


def setup_poppler_bin(poppler_path):
    """Setup Poppler bin path, handling different directory structures."""
    if not poppler_path:
        return None
    
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
    
    return str(poppler_bin) if poppler_bin.exists() else None


def call_gemini_with_retry(model, prompt, image, max_retries=3):
    """
    Call Gemini API with exponential backoff retry logic.
    
    Args:
        model: Gemini GenerativeModel instance
        prompt: Text prompt
        image: PIL Image
        max_retries: Maximum number of retry attempts
    
    Returns:
        Response text or None if all retries failed
    """
    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, image])
            return response.text
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"  Attempt {attempt + 1} failed: {e}")
                print(f"  Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"  All {max_retries} attempts failed. Last error: {e}")
                return None
    return None


def process_page(page_num, pdf_path, dpi, output_pages_dir, model, overwrite, sleep_time):
    """
    Process a single PDF page.
    
    Args:
        page_num: 1-indexed page number
        pdf_path: Path to PDF file
        dpi: DPI for image conversion
        output_pages_dir: Directory to save outputs
        model: Gemini GenerativeModel instance
        overwrite: Whether to overwrite existing files
        sleep_time: Seconds to sleep between API calls
    
    Returns:
        tuple: (success: bool, error_message: str or None, json_data: dict or None)
    """
    page_image_path = output_pages_dir / f"page_{page_num:03d}.png"
    page_json_path = output_pages_dir / f"page_{page_num:03d}.json"
    
    # Skip if JSON exists and not overwriting
    if not overwrite and page_json_path.exists():
        print(f"  Page {page_num}: Skipping (JSON already exists)")
        try:
            with open(page_json_path, "r", encoding="utf-8") as f:
                return True, None, json.load(f)
        except Exception as e:
            print(f"  Page {page_num}: Warning - Could not read existing JSON: {e}")
    
    # Convert PDF page to image
    print(f"  Page {page_num}: Converting to image...")
    try:
        poppler_path = get_poppler_path()
        poppler_bin = setup_poppler_bin(poppler_path) if poppler_path else None
        
        if poppler_bin:
            images = convert_from_path(
                str(pdf_path),
                first_page=page_num,
                last_page=page_num,
                dpi=dpi,
                poppler_path=poppler_bin
            )
        else:
            images = convert_from_path(
                str(pdf_path),
                first_page=page_num,
                last_page=page_num,
                dpi=dpi
            )
        
        if not images:
            return False, f"Failed to convert page {page_num} to image", None
        
        page_image = images[0]
        page_image.save(page_image_path)
        print(f"  Page {page_num}: Image saved to {page_image_path.name}")
        
    except Exception as e:
        return False, f"Error converting page {page_num}: {e}", None
    
    # Call Gemini API
    print(f"  Page {page_num}: Calling Gemini API...")
    response_text = call_gemini_with_retry(model, PROMPT, page_image)
    
    if response_text is None:
        return False, f"Gemini API call failed after retries", None
    
    # Parse response as JSON
    try:
        # Try to extract JSON from markdown code blocks if present
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            if end != -1:
                response_text = response_text[start:end].strip()
        
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        # If response is not valid JSON, wrap it
        response_json = {
            "page_number": page_num,
            "raw_response": response_text
        }
    
    # Ensure page_number is set correctly
    response_json["page_number"] = page_num
    
    # Save JSON response
    try:
        with open(page_json_path, "w", encoding="utf-8") as f:
            json.dump(response_json, f, indent=2, ensure_ascii=False)
        print(f"  Page {page_num}: JSON saved to {page_json_path.name}")
    except Exception as e:
        return False, f"Error saving JSON for page {page_num}: {e}", None
    
    # Sleep between API calls
    if sleep_time > 0:
        time.sleep(sleep_time)
    
    return True, None, response_json


def create_manifest(pdf_path, total_pages, processed_pages, failed_pages, model_name, dpi, start_page, end_page, output_dir):
    """Create manifest.json with processing metadata."""
    manifest = {
        "pdf_path": str(pdf_path),
        "total_pages": total_pages,
        "processed_pages": processed_pages,
        "failed_pages": failed_pages,
        "model_name": model_name,
        "dpi": dpi,
        "start_page": start_page,
        "end_page": end_page,
        "timestamp": datetime.now().isoformat()
    }
    
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    print(f"\nManifest saved to: {manifest_path}")


def create_combined_markdown(processed_pages, output_dir):
    """Create combined.md from all successful page JSON files."""
    combined_path = output_dir / "combined.md"
    output_pages_dir = output_dir / "pages"
    
    with open(combined_path, "w", encoding="utf-8") as f:
        for page_num in sorted(processed_pages):
            json_path = output_pages_dir / f"page_{page_num:03d}.json"
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as jf:
                        page_data = json.load(jf)
                    
                    # Write page header
                    f.write(f"# Page {page_num}\n\n")
                    
                    # Write markdown if available
                    if "markdown" in page_data:
                        f.write(page_data["markdown"])
                        f.write("\n\n")
                    elif "raw_response" in page_data:
                        f.write(page_data["raw_response"])
                        f.write("\n\n")
                    
                    f.write("---\n\n")
                except Exception as e:
                    print(f"Warning: Could not read JSON for page {page_num}: {e}")
    
    print(f"Combined markdown saved to: {combined_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract and compress PDF pages using Gemini vision model"
    )
    parser.add_argument(
        "--pdf",
        type=str,
        default="data/deepseek ocr paper.pdf",
        help="Path to PDF file (default: data/deepseek ocr paper.pdf)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="DPI for image conversion (default: 200)"
    )
    parser.add_argument(
        "--start_page",
        type=int,
        default=1,
        help="Start page (1-indexed, default: 1)"
    )
    parser.add_argument(
        "--end_page",
        type=int,
        default=None,
        help="End page (1-indexed, default: all pages)"
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="Seconds to sleep between Gemini API calls (default: 1.0)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSON files"
    )
    
    args = parser.parse_args()
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / args.pdf if not Path(args.pdf).is_absolute() else Path(args.pdf)
    output_dir = project_root / "output"
    output_pages_dir = output_dir / "pages"
    
    # Ensure output directories exist
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pages_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if PDF exists
    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}")
        return
    
    # Get API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment variables")
        print("Please create a .env file with: GEMINI_API_KEY=your_key_here")
        return
    
    # Configure Gemini
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        generation_config={
            "temperature": TEMPERATURE,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
    )
    
    # Get total number of pages
    print(f"Reading PDF: {pdf_path}")
    try:
        poppler_path = get_poppler_path()
        poppler_bin = setup_poppler_bin(poppler_path) if poppler_path else None
        
        # Try to convert a large range to get page count efficiently
        # Start with a reasonable upper limit (1000 pages)
        total_pages = 1
        try:
            if poppler_bin:
                test_images = convert_from_path(
                    str(pdf_path),
                    first_page=1,
                    last_page=1000,
                    poppler_path=poppler_bin
                )
            else:
                test_images = convert_from_path(
                    str(pdf_path),
                    first_page=1,
                    last_page=1000
                )
            total_pages = len(test_images)
        except:
            # If that fails, try pages sequentially
            if poppler_bin:
                for page_num in range(2, 1000):
                    try:
                        test_imgs = convert_from_path(
                            str(pdf_path),
                            first_page=page_num,
                            last_page=page_num,
                            poppler_path=poppler_bin
                        )
                        if test_imgs:
                            total_pages = page_num
                        else:
                            break
                    except:
                        break
            else:
                for page_num in range(2, 1000):
                    try:
                        test_imgs = convert_from_path(
                            str(pdf_path),
                            first_page=page_num,
                            last_page=page_num
                        )
                        if test_imgs:
                            total_pages = page_num
                        else:
                            break
                    except:
                        break
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return
    
    # Determine page range
    start_page = max(1, args.start_page)
    end_page = args.end_page if args.end_page is not None else total_pages
    end_page = min(end_page, total_pages)
    
    if start_page > end_page:
        print(f"Error: start_page ({start_page}) > end_page ({end_page})")
        return
    
    print(f"Total pages in PDF: {total_pages}")
    print(f"Processing pages {start_page} to {end_page}")
    print(f"Output directory: {output_pages_dir}")
    print(f"Overwrite existing: {args.overwrite}")
    print(f"Sleep between calls: {args.sleep}s")
    print()
    
    # Process pages
    processed_pages = []
    failed_pages = []
    
    for page_num in range(start_page, end_page + 1):
        print(f"Processing page {page_num}/{end_page}...")
        success, error, json_data = process_page(
            page_num, pdf_path, args.dpi, output_pages_dir, model, args.overwrite, args.sleep
        )
        
        if success:
            processed_pages.append(page_num)
        else:
            failed_pages.append({"page": page_num, "error": error or "Unknown error"})
            print(f"  Page {page_num}: FAILED - {error}")
    
    # Create manifest
    create_manifest(
        pdf_path, total_pages, processed_pages, failed_pages,
        GEMINI_MODEL, args.dpi, start_page, end_page, output_dir
    )
    
    # Create combined markdown
    if processed_pages:
        create_combined_markdown(processed_pages, output_dir)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"  Processed: {len(processed_pages)} pages")
    print(f"  Failed: {len(failed_pages)} pages")
    if failed_pages:
        print(f"\nFailed pages:")
        for failure in failed_pages:
            print(f"  Page {failure['page']}: {failure['error']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

