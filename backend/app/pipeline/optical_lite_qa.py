"""Optical-lite QA module - retrieves pages from minimal index and answers using page images."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.config import (
    GEMINI_MODEL,
    GCP_PROJECT_ID,
    GCP_LOCATION,
)
from app.pipeline.qa import _get_supermemory_client, _query_supermemory
from app.pipeline.utils import retry
from app.llm.vertex_gemini import VertexGeminiClient
from vertexai.generative_models import Part

logger = logging.getLogger(__name__)


def answer_optical_lite(
    doc_id: str,
    question: str,
    top_k: int = 8,
    max_images: int = 6,
    corpus_id: str | None = None
) -> dict:
    """
    Answer a question using optical-lite mode: retrieve pages from minimal index and use images as context.
    
    Args:
        doc_id: Document ID
        question: User question
        top_k: Number of top results to retrieve
        max_images: Maximum number of images to send to Gemini
        corpus_id: Optional corpus ID
        
    Returns:
        dict: {"answer_md": str, "retrieved": List[Dict]}
    """
    # Validate Vertex AI configuration
    if not GCP_PROJECT_ID:
        raise ValueError("GCP_PROJECT_ID not found in environment variables")
    
    # Query Supermemory
    client = _get_supermemory_client()
    results = _query_supermemory(client, question, doc_id=doc_id, corpus_id=corpus_id, top_k=top_k)
    
    if not results:
        logger.warning(f"No results found for query: '{question}' with doc_id={doc_id}")
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": []
        }
    
    # Extract page info and deduplicate by page number
    page_map = {}  # page_number -> (memory_id, image_path, metadata)
    
    for result in results:
        # Extract memory_id
        if hasattr(result, 'id'):
            memory_id = result.id
        elif isinstance(result, dict):
            memory_id = result.get('id') or result.get('memory_id', '')
        else:
            memory_id = ''
        
        # Extract metadata
        if hasattr(result, 'metadata'):
            metadata = result.metadata
        elif isinstance(result, dict):
            metadata = result.get('metadata', {})
        else:
            metadata = {}
        
        page_number = metadata.get('page')
        if page_number is None:
            continue
        
        # Get image_path from metadata
        image_path = metadata.get('image_path', '')
        
        # Deduplicate: keep first occurrence of each page
        if page_number not in page_map:
            page_map[page_number] = (memory_id, image_path, metadata)
    
    # Select top pages up to max_images
    selected_pages = sorted(page_map.items())[:max_images]
    
    if not selected_pages:
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": []
        }
    
    # Load image bytes for each selected page
    image_parts = []
    retrieved = []
    
    for page_number, (memory_id, image_path_str, metadata) in selected_pages:
        # Try to resolve image path
        image_path = None
        if image_path_str:
            image_path = Path(image_path_str)
            if not image_path.exists():
                # Try relative to common locations
                # Check tmp/<doc_id>/images/
                tmp_path = Path("tmp") / doc_id / "images" / f"page_{page_number:03d}.png"
                if tmp_path.exists():
                    image_path = tmp_path
                else:
                    # Try output/corpora/<corpus_id>/docs/<doc_id>/images/
                    if corpus_id:
                        corpus_path = Path("output") / "corpora" / corpus_id / "docs" / doc_id / "images" / f"page_{page_number:03d}.png"
                        if corpus_path.exists():
                            image_path = corpus_path
        
        if image_path and image_path.exists():
            try:
                # Load image bytes
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                
                # Create Part from image bytes
                image_part = Part.from_data(data=image_bytes, mime_type="image/png")
                image_parts.append(image_part)
                
                retrieved.append({
                    "page": page_number,
                    "supermemory_id": memory_id,
                    "image_path": str(image_path)
                })
            except Exception as e:
                logger.warning(f"Failed to load image {image_path}: {e}")
                retrieved.append({
                    "page": page_number,
                    "supermemory_id": memory_id,
                    "image_path": str(image_path) if image_path else image_path_str,
                    "error": f"Failed to load image: {e}"
                })
        else:
            logger.warning(f"Image not found for page {page_number}: {image_path_str}")
            retrieved.append({
                "page": page_number,
                "supermemory_id": memory_id,
                "image_path": image_path_str or "unknown",
                "error": "Image file not found"
            })
    
    if not image_parts:
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": retrieved
        }
    
    # Build prompt with strict instructions
    system_instruction = """You are answering questions using ONLY the provided document page images as evidence.
If the answer is not present in the images, say: 'Not found in provided documents.'
Every non-trivial statement must include citations in this exact format: (DOC_ID p.PAGE_NUMBER).
Use DOC_ID exactly as provided. Do NOT invent page numbers."""
    
    prompt = f"""{system_instruction}

DOC_ID = {doc_id}
Question = {question}

If you refer to multiple pages, cite each page."""

    # Generate answer with Gemini
    def _call():
        client = VertexGeminiClient(model_name=GEMINI_MODEL, location=GCP_LOCATION or "global")
        
        # Build content list: prompt + images
        contents = [prompt]
        contents.extend(image_parts)
        
        return client.generate_content(
            contents=contents,
            temperature=0,
            max_output_tokens=2048,
        )
    
    try:
        answer_md = retry(_call, attempts=3)
    except Exception as e:
        logger.error(f"Failed to generate answer: {e}")
        answer_md = f"Error generating answer: {str(e)}"
    
    return {
        "answer_md": answer_md,
        "retrieved": retrieved
    }

