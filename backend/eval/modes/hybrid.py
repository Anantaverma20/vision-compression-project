"""Hybrid mode: retrieve text candidates, then use page images for final answer."""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.pipeline.qa import _get_supermemory_client, _extract_result_info
from eval.modes.text_rag import query_with_corpus_filter
from eval.modes.optical import (
    load_page_image,
    generate_answer_with_images,
    generate_answer_proxy_optical,
    run_optical
)

logger = logging.getLogger(__name__)


def run_hybrid(
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
    Run hybrid mode: retrieve text candidates, then use page images for final answer.
    
    This is similar to optical mode, but we first retrieve text candidates to identify
    relevant pages, then use those page images for the final answer.
    
    Args:
        corpus_id: Corpus ID
        question: Question to answer
        corpus_dir: Path to corpus directory
        top_k: Number of pages to retrieve initially
        max_images: Maximum number of images to send to Gemini
        doc_id: Optional doc_id filter
        model: Gemini model name
        manifest_path: Path to corpus manifest
        use_proxy: If True, use proxy mode
    
    Returns:
        dict: {
            "answer_md": str,
            "retrieved": List[Dict],
            "evidence_pack": str
        }
    """
    # Hybrid mode is essentially optical mode but with text-based retrieval first
    # The retrieval already happens in optical mode, so we can reuse it
    return run_optical(
        corpus_id=corpus_id,
        question=question,
        corpus_dir=corpus_dir,
        top_k=top_k,
        max_images=max_images,
        doc_id=doc_id,
        model=model,
        manifest_path=manifest_path,
        use_proxy=use_proxy
    )

