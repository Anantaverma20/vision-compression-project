"""Metrics computation for evaluation results."""

import re
from typing import Dict, List, Optional, Any


def extract_citations(text: str) -> List[Dict[str, Any]]:
    """
    Extract citations from answer text.
    
    Looks for patterns like: (doc_id p.1) or (doc_id p.1, p.2)
    
    Returns:
        List of dicts with keys: doc_id, pages (list of ints)
    """
    citations = []
    
    # Pattern: (doc_id p.1) or (doc_id p.1, p.2, p.3)
    pattern = r'\(([^)]+?)\s+p\.(\d+(?:\s*,\s*p\.\d+)*)\)'
    
    matches = re.finditer(pattern, text, re.IGNORECASE)
    
    for match in matches:
        doc_id = match.group(1).strip()
        pages_str = match.group(2)
        
        # Extract page numbers
        page_nums = re.findall(r'\d+', pages_str)
        pages = [int(p) for p in page_nums]
        
        citations.append({
            "doc_id": doc_id,
            "pages": pages
        })
    
    return citations


def compute_citation_metrics(answer: str, retrieved_pages: List[Dict]) -> Dict[str, float]:
    """
    Compute citation-related metrics.
    
    Args:
        answer: The generated answer text
        retrieved_pages: List of retrieved pages with doc_id and page number
        
    Returns:
        dict with keys: has_citations, citation_coverage
    """
    citations = extract_citations(answer)
    
    has_citations = len(citations) > 0
    
    # Compute citation coverage: % of sentences with citations
    sentences = re.split(r'[.!?]+', answer)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    sentences_with_citations = 0
    for sentence in sentences:
        if re.search(r'\([^)]+\s+p\.\d+', sentence, re.IGNORECASE):
            sentences_with_citations += 1
    
    citation_coverage = (
        sentences_with_citations / len(sentences) 
        if sentences else 0.0
    )
    
    return {
        "has_citations": has_citations,
        "citation_coverage": citation_coverage,
        "citation_count": len(citations)
    }


def compute_context_units(mode: str, retrieved: List[Dict], evidence_pack: Optional[str] = None) -> int:
    """
    Compute estimated context units used.
    
    Args:
        mode: One of 'text_rag', 'optical', 'hybrid'
        retrieved: List of retrieved pages
        evidence_pack: The evidence pack text (for text_rag)
        
    Returns:
        Estimated context units (chars for text_rag, page count for optical/hybrid)
    """
    if mode == "text_rag":
        # Count characters in evidence pack
        if evidence_pack:
            return len(evidence_pack)
        return 0
    elif mode in ("optical", "hybrid"):
        # Count number of pages selected
        unique_pages = set()
        for r in retrieved:
            doc_id = r.get("doc_id", "")
            page = r.get("page", 0)
            if doc_id and page:
                unique_pages.add((doc_id, page))
        return len(unique_pages)
    else:
        return 0


def compute_all_metrics(
    mode: str,
    question: str,
    answer: str,
    retrieved: List[Dict],
    latency: float,
    evidence_pack: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compute all metrics for an evaluation result.
    
    Returns:
        dict with all computed metrics
    """
    citation_metrics = compute_citation_metrics(answer, retrieved)
    context_units = compute_context_units(mode, retrieved, evidence_pack)
    
    return {
        "has_citations": citation_metrics["has_citations"],
        "citation_coverage": citation_metrics["citation_coverage"],
        "citation_count": citation_metrics["citation_count"],
        "retrieved_pages_count": len(retrieved),
        "estimated_context_units": context_units,
        "latency_seconds": latency
    }

