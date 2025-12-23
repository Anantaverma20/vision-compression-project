"""PDF extraction module - converts PDF pages to compressed JSON using Gemini."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import google.generativeai as genai
from pdf2image import convert_from_path
from PIL import Image

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS_EXTRACTION,
    EXTRACTION_PROMPT,
)
from app.pipeline.utils import retry, safe_json_loads, ensure_dirs

# Set up logger
logger = logging.getLogger(__name__)


def get_poppler_path() -> Optional[str]:
    """Get Poppler path from environment variables."""
    return os.getenv("POPPLER") or os.getenv("poppler")


def setup_poppler_bin(poppler_path: Optional[str]) -> Optional[str]:
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


def _call_gemini_with_retry(model, prompt: str, image: Image.Image, page_num: int) -> Optional[str]:
    """Call Gemini API with retry logic."""
    def _call():
        try:
            response = model.generate_content([prompt, image])
            if not response or not response.text:
                logger.warning(f"Page {page_num}: Gemini API returned empty response")
                return None
            return response.text
        except Exception as api_error:
            logger.error(f"Page {page_num}: Gemini API call failed: {type(api_error).__name__}: {api_error}")
            raise
    
    try:
        return retry(_call, attempts=3)
    except Exception as e:
        logger.error(f"Page {page_num}: Gemini API call failed after retries: {type(e).__name__}: {e}")
        return None


def _process_single_page(
    page_num: int,
    pdf_path: Path,
    dpi: int,
    images_dir: Path,
    pages_dir: Path,
    overwrite: bool = False
) -> tuple[bool, Optional[str], Optional[dict]]:
    """
    Process a single PDF page.
    
    Creates its own Gemini model instance for thread safety.
    
    Returns:
        tuple: (success: bool, error_message: str or None, json_data: dict or None)
    """
    page_image_path = images_dir / f"page_{page_num:03d}.png"
    page_json_path = pages_dir / f"page_{page_num:03d}.json"
    
    try:
        # Skip if JSON exists and not overwriting
        if not overwrite and page_json_path.exists():
            try:
                with open(page_json_path, "r", encoding="utf-8") as f:
                    logger.debug(f"Page {page_num}: Using existing JSON file")
                    return True, None, json.load(f)
            except Exception as e:
                logger.warning(f"Page {page_num}: Failed to read existing JSON, will reprocess: {e}")
                # If we can't read existing JSON, reprocess
                pass
        
        # Convert PDF page to image
        logger.debug(f"Page {page_num}: Converting PDF page to image (DPI: {dpi})")
        poppler_path = get_poppler_path()
        poppler_bin = setup_poppler_bin(poppler_path) if poppler_path else None
        
        try:
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
                error_msg = f"Failed to convert page {page_num} to image: No images returned"
                logger.error(error_msg)
                return False, error_msg, None
            
            page_image = images[0]
            page_image.save(page_image_path)
            logger.debug(f"Page {page_num}: Image saved to {page_image_path}")
            
        except Exception as e:
            error_msg = f"Error converting page {page_num} to image: {type(e).__name__}: {e}"
            logger.error(error_msg)
            return False, error_msg, None
        
        # Create model instance for this thread (thread-safe)
        logger.debug(f"Page {page_num}: Creating Gemini model instance")
        if not GEMINI_API_KEY:
            error_msg = f"Page {page_num}: GEMINI_API_KEY not found"
            logger.error(error_msg)
            return False, error_msg, None
        
        # Configure Gemini (this is thread-safe as it's just setting a global config)
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Create a new model instance for this thread
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": GEMINI_TEMPERATURE,
                "max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS_EXTRACTION,
            }
        )
        
        # Call Gemini API
        logger.debug(f"Page {page_num}: Calling Gemini API")
        response_text = _call_gemini_with_retry(model, EXTRACTION_PROMPT, page_image, page_num)
        
        if response_text is None:
            error_msg = f"Page {page_num}: Gemini API call failed after retries"
            logger.error(error_msg)
            return False, error_msg, None
        
        logger.debug(f"Page {page_num}: Gemini API response received ({len(response_text)} chars)")
        
        # Parse response as JSON
        response_json = safe_json_loads(response_text)
        
        # If parsing failed, wrap response into JSON structure
        if response_json is None:
            logger.warning(f"Page {page_num}: Failed to parse JSON response, wrapping as markdown")
            response_json = {
                "page_number": page_num,
                "markdown": response_text,
                "entities": [],
                "summary": ""
            }
        else:
            # Ensure page_number is set correctly
            response_json["page_number"] = page_num
            # Ensure required fields exist
            if "markdown" not in response_json:
                response_json["markdown"] = response_text
            if "entities" not in response_json:
                response_json["entities"] = []
            if "summary" not in response_json:
                response_json["summary"] = ""
        
        # Save JSON response
        try:
            with open(page_json_path, "w", encoding="utf-8") as f:
                json.dump(response_json, f, indent=2, ensure_ascii=False)
            logger.debug(f"Page {page_num}: JSON saved to {page_json_path}")
        except Exception as e:
            error_msg = f"Error saving JSON for page {page_num}: {type(e).__name__}: {e}"
            logger.error(error_msg)
            return False, error_msg, None
        
        logger.info(f"Page {page_num}: Successfully processed")
        return True, None, response_json
        
    except Exception as e:
        error_msg = f"Page {page_num}: Unexpected error: {type(e).__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg, None


def extract_pdf_to_page_jsons(
    pdf_path: Path,
    out_pages_dir: Path,
    images_dir: Path,
    dpi: int = 200,
    start_page: int = 1,
    end_page: Optional[int] = None,
    overwrite: bool = False
) -> Dict:
    """
    Extract PDF pages to compressed JSON files using Gemini.
    
    Args:
        pdf_path: Path to PDF file
        out_pages_dir: Directory to save page JSON files
        images_dir: Directory to save page images
        dpi: DPI for image conversion
        start_page: Start page (1-indexed)
        end_page: End page (1-indexed, None for all pages)
        overwrite: Whether to overwrite existing files
        
    Returns:
        dict: Statistics with keys: pages_total, processed_pages, failed_pages
    """
    # Ensure directories exist
    ensure_dirs(out_pages_dir, images_dir)
    
    # Validate API key (model instances will be created per thread)
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    logger.info(f"Starting PDF extraction: {pdf_path}, pages {start_page}-{end_page or 'all'}, DPI: {dpi}")
    
    # Get total number of pages
    try:
        poppler_path = get_poppler_path()
        poppler_bin = setup_poppler_bin(poppler_path) if poppler_path else None
        
        # Try to convert a large range to get page count efficiently
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
        raise Exception(f"Error reading PDF: {e}")
    
    # Determine page range
    start_page = max(1, start_page)
    end_page = end_page if end_page is not None else total_pages
    end_page = min(end_page, total_pages)
    
    if start_page > end_page:
        raise ValueError(f"start_page ({start_page}) > end_page ({end_page})")
    
    # Process pages in parallel for faster processing
    processed_pages: List[int] = []
    failed_pages: List[Dict] = []
    
    # Use ThreadPoolExecutor for parallel processing
    # Process 5 pages concurrently (adjust based on API rate limits)
    max_workers = 5
    
    def process_page_wrapper(page_num):
        """Wrapper function for parallel processing. Each thread creates its own model instance."""
        try:
            logger.debug(f"Page {page_num}: Starting processing in thread")
            result = _process_single_page(
                page_num, pdf_path, dpi, images_dir, out_pages_dir, overwrite
            )
            return page_num, result
        except Exception as e:
            logger.error(f"Page {page_num}: Exception in process_page_wrapper: {type(e).__name__}: {e}", exc_info=True)
            return page_num, (False, f"Wrapper exception: {type(e).__name__}: {e}", None)
    
    logger.info(f"Processing {end_page - start_page + 1} pages with {max_workers} workers")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all pages for processing
        future_to_page = {
            executor.submit(process_page_wrapper, page_num): page_num 
            for page_num in range(start_page, end_page + 1)
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_page):
            try:
                page_num, (success, error, json_data) = future.result()
                if success:
                    processed_pages.append(page_num)
                    logger.debug(f"Page {page_num}: Added to processed pages")
                else:
                    error_entry = {"page": page_num, "error": error or "Unknown error"}
                    failed_pages.append(error_entry)
                    logger.error(f"Page {page_num}: Failed - {error}")
            except Exception as e:
                page_num = future_to_page.get(future, "unknown")
                error_entry = {"page": page_num, "error": f"Processing error: {type(e).__name__}: {e}"}
                failed_pages.append(error_entry)
                logger.error(f"Page {page_num}: Exception collecting result: {type(e).__name__}: {e}", exc_info=True)
    
    # Sort processed_pages for consistent output
    processed_pages.sort()
    
    logger.info(f"PDF extraction complete: {len(processed_pages)} processed, {len(failed_pages)} failed")
    if failed_pages:
        logger.warning(f"Failed pages: {[p.get('page', 'unknown') for p in failed_pages]}")
    
    return {
        "pages_total": total_pages,
        "processed_pages": processed_pages,
        "failed_pages": failed_pages
    }

