"""Optical mode: retrieve pages by metadata, then use page images as context."""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.config import (
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
    GCP_PROJECT_ID,
)
from app.llm.vertex_gemini import VertexGeminiClient
from app.pipeline.qa import _get_supermemory_client, _extract_result_info
from app.pipeline.utils import retry
from eval.modes.text_rag import query_with_corpus_filter

logger = logging.getLogger(__name__)


def load_page_image(image_path: Path) -> Optional[Image.Image]:
    """Load a page image from disk."""
    try:
        if image_path.exists():
            return Image.open(image_path)
        return None
    except Exception as e:
        logger.warning(f"Failed to load image {image_path}: {e}")
        return None


def generate_answer_with_images(
    question: str,
    page_images: List[Image.Image],
    page_metadata: List[Dict],
    corpus_id: str,
    model_name: str
) -> str:
    """
    Generate answer using Gemini with page images as context.
    
    Args:
        question: The question
        page_images: List of PIL Image objects
        page_metadata: List of dicts with doc_id and page number
        corpus_id: Corpus ID
        model_name: Gemini model name
    """
    # Build context description from metadata
    context_desc = "\n".join([
        f"- Page {m['page']} from document {m['doc_id']}"
        for m in page_metadata
    ])
    
    prompt = f"""You are answering a question based ONLY on the provided document page images. Use ONLY the information visible in the images. If the information is not present, explicitly state "Not found in provided documents."

CRITICAL CITATION REQUIREMENTS:
- Every non-trivial claim MUST have an inline citation in the format: (doc_id p.<page_number>)
- If multiple pages support a claim, cite all relevant pages: (doc_id p.X, p.Y)
- Use citations immediately after each claim or fact

Question: {question}

Document Pages Provided:
{context_desc}

Answer (with citations):"""
    
    def _call():
        client = VertexGeminiClient(model_name=model_name)
        
        # Build content list: prompt + images
        content = [prompt]
        for img in page_images:
            content.append(img)
        
        return client.generate_content(
            contents=content,
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
        )
    
    return retry(_call, attempts=3)


def generate_answer_proxy_optical(
    question: str,
    page_summaries: List[Dict],
    corpus_id: str,
    model_name: str
) -> str:
    """
    Proxy optical mode: use compact summaries instead of full images.
    This is used when image input is difficult or rate-limited.
    """
    # Build compact evidence pack from summaries
    evidence_sections = []
    for summary_info in page_summaries:
        doc_id = summary_info.get("doc_id", "")
        page = summary_info.get("page", 0)
        summary = summary_info.get("summary", "")
        entities = summary_info.get("entities", [])
        
        section = f"[Page {page} from {doc_id}]\nSummary: {summary}"
        if entities:
            section += f"\nKey entities: {', '.join(entities[:5])}"
        evidence_sections.append(section)
    
    evidence_pack = "\n\n---\n\n".join(evidence_sections)
    
    prompt = f"""You are answering a question based ONLY on the provided page summaries (compressed optical context). Use ONLY the information present. If the information is not present, explicitly state "Not found in provided documents."

CRITICAL CITATION REQUIREMENTS:
- Every non-trivial claim MUST have an inline citation in the format: (doc_id p.<page_number>)
- If multiple pages support a claim, cite all relevant pages: (doc_id p.X, p.Y)
- Use citations immediately after each claim or fact

Question: {question}

Compressed Page Summaries:
{evidence_pack}

Answer (with citations):"""
    
    def _call():
        client = VertexGeminiClient(model_name=model_name)
        return client.generate_content(
            contents=prompt,
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
        )
    
    return retry(_call, attempts=3)


def run_optical(
    corpus_id: str,
    question: str,
    corpus_dir: Path,
    top_k: int = 8,
    max_images: int = 6,
    doc_id: Optional[str] = None,
    model: str = None,
    manifest_path: Optional[Path] = None,
    use_proxy: bool = False
) -> Dict:
    """
    Run optical mode: retrieve pages by metadata, then use page images as context.
    
    Args:
        corpus_id: Corpus ID
        question: Question to answer
        corpus_dir: Path to corpus directory (output/corpora/<corpus_id>)
        top_k: Number of pages to retrieve
        max_images: Maximum number of images to send to Gemini
        doc_id: Optional doc_id filter
        model: Gemini model name
        manifest_path: Path to corpus manifest
        use_proxy: If True, use proxy mode (summaries instead of images)
    
    Returns:
        dict: {
            "answer_md": str,
            "retrieved": List[Dict],
            "evidence_pack": str (empty for optical, summaries for proxy)
        }
    """
    if model is None:
        model = GEMINI_MODEL
    
    if not GCP_PROJECT_ID:
        raise ValueError("GCP_PROJECT_ID not found in environment variables")
    
    # Load manifest
    manifest = None
    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    # Query Supermemory to get relevant pages (by metadata/summaries)
    client = _get_supermemory_client()
    results = query_with_corpus_filter(client, question, corpus_id, doc_id, top_k)
    
    if not results:
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": [],
            "evidence_pack": ""
        }
    
    # Extract page info and load images/summaries
    page_images = []
    page_summaries = []
    retrieved = []
    
    for result in results:
        info = _extract_result_info(result, manifest)
        if not info:
            continue
        
        memory_id, page_number, content = info
        
        # Extract metadata
        if hasattr(result, 'metadata'):
            metadata = result.metadata
        elif isinstance(result, dict):
            metadata = result.get('metadata', {})
        else:
            metadata = {}
        
        doc_id_from_result = metadata.get('doc_id', doc_id or '')
        summary = metadata.get('summary', '')
        entities = metadata.get('entities', [])
        
        retrieved.append({
            "doc_id": doc_id_from_result,
            "page": page_number,
            "memory_id": memory_id,
            "excerpt": summary[:250] if summary else content[:250]
        })
        
        if use_proxy:
            # Proxy mode: collect summaries
            page_summaries.append({
                "doc_id": doc_id_from_result,
                "page": page_number,
                "summary": summary,
                "entities": entities
            })
        else:
            # Real optical mode: load images
            # Find image path: output/corpora/<corpus_id>/docs/<doc_id>/images/page_###.png
            doc_dir = corpus_dir / "docs" / doc_id_from_result
            image_path = doc_dir / "images" / f"page_{page_number:03d}.png"
            
            img = load_page_image(image_path)
            if img:
                page_images.append(img)
                page_summaries.append({
                    "doc_id": doc_id_from_result,
                    "page": page_number,
                    "summary": summary,
                    "entities": entities
                })
    
    # Limit to max_images
    if len(page_images) > max_images:
        page_images = page_images[:max_images]
        page_summaries = page_summaries[:max_images]
        retrieved = retrieved[:max_images]
    
    if not page_images and not page_summaries:
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": [],
            "evidence_pack": ""
        }
    
    # Generate answer
    if use_proxy or not page_images:
        # Use proxy mode
        answer_md = generate_answer_proxy_optical(question, page_summaries, corpus_id, model)
        evidence_pack = "\n\n---\n\n".join([
            f"[Page {s['page']} from {s['doc_id']}]\nSummary: {s['summary']}"
            for s in page_summaries
        ])
    else:
        # Use real optical mode with images
        try:
            answer_md = generate_answer_with_images(
                question, page_images, page_summaries, corpus_id, model
            )
            evidence_pack = ""  # Images are the evidence, not text
        except Exception as e:
            logger.warning(f"Failed to use images, falling back to proxy mode: {e}")
            answer_md = generate_answer_proxy_optical(question, page_summaries, corpus_id, model)
            evidence_pack = "\n\n---\n\n".join([
                f"[Page {s['page']} from {s['doc_id']}]\nSummary: {s['summary']}"
                for s in page_summaries
            ])
    
    return {
        "answer_md": answer_md,
        "retrieved": retrieved,
        "evidence_pack": evidence_pack
    }

