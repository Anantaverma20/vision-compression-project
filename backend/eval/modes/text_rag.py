"""Text RAG mode: traditional text-based retrieval and generation."""

import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.config import (
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
    GCP_PROJECT_ID,
)
from app.llm.vertex_gemini import VertexGeminiClient
from app.pipeline.qa import (
    _get_supermemory_client,
    _query_supermemory,
    _extract_result_info,
    _build_evidence_pack,
)
from app.pipeline.utils import retry

logger = logging.getLogger(__name__)


def query_with_corpus_filter(
    client,
    query: str,
    corpus_id: str,
    doc_id: Optional[str] = None,
    top_k: int = 8
) -> List:
    """
    Query Supermemory with corpus_id filter (and optionally doc_id).
    
    Returns:
        list: List of result objects
    """
    def _call():
        # Try to filter by corpus_id and doc_id
        filter_dict = {"corpus_id": corpus_id}
        if doc_id:
            filter_dict["doc_id"] = doc_id
        
        # Try common SDK search patterns
        if hasattr(client, 'search') and hasattr(client.search, 'query'):
            try:
                response = client.search.query(q=query, limit=top_k, filter=filter_dict)
            except (TypeError, AttributeError):
                # Fallback: query without filter, filter results after
                response = client.search.query(q=query, limit=top_k * 2)
        elif hasattr(client, 'search') and hasattr(client.search, 'documents'):
            try:
                response = client.search.documents(q=query, limit=top_k, filter=filter_dict)
            except (TypeError, AttributeError):
                response = client.search.documents(q=query, limit=top_k * 2)
        elif hasattr(client, 'query'):
            try:
                response = client.query(query=query, limit=top_k, filter=filter_dict)
            except (TypeError, AttributeError):
                response = client.query(query=query, limit=top_k * 2)
        else:
            raise AttributeError("Could not find search method in Supermemory client. Available: " + str(dir(client)))
        
        # Extract results
        if hasattr(response, 'results'):
            results = response.results
        elif hasattr(response, 'data'):
            results = response.data
        elif isinstance(response, list):
            results = response
        else:
            results = [response]
        
        # Filter by corpus_id and doc_id if not done by SDK
        filtered_results = []
        for result in results:
            # Extract metadata
            if hasattr(result, 'metadata'):
                metadata = result.metadata
            elif isinstance(result, dict):
                metadata = result.get('metadata', {})
            else:
                metadata = {}
            
            # Check if corpus_id matches (and doc_id if specified)
            if metadata.get('corpus_id') == corpus_id:
                if doc_id is None or metadata.get('doc_id') == doc_id:
                    filtered_results.append(result)
                    if len(filtered_results) >= top_k:
                        break
        
        return filtered_results[:top_k]
    
    return retry(_call, attempts=3)


def generate_answer_with_gemini(
    question: str,
    evidence_pack: str,
    corpus_id: str,
    model_name: str
) -> str:
    """Generate answer using Gemini with strict citation requirements."""
    prompt = f"""You are answering a question based ONLY on the provided evidence pack. Use ONLY the information present in the evidence pack. If the information is not present, explicitly state "Not found in provided documents."

CRITICAL CITATION REQUIREMENTS:
- Every non-trivial claim MUST have an inline citation in the format: (doc_id p.<page_number>)
- If multiple pages support a claim, cite all relevant pages: (doc_id p.X, p.Y)
- Use citations immediately after each claim or fact
- Format: (doc_id p.1) or (doc_id p.1, p.2) for multiple pages

Question: {question}

Evidence Pack:
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


def run_text_rag(
    corpus_id: str,
    question: str,
    top_k: int = 8,
    max_chars_per_page: int = 1500,
    doc_id: Optional[str] = None,
    model: str = None,
    manifest_path: Optional[Path] = None
) -> Dict:
    """
    Run text RAG mode: retrieve text chunks, build evidence pack, generate answer.
    
    Returns:
        dict: {
            "answer_md": str,
            "retrieved": List[Dict],
            "evidence_pack": str
        }
    """
    if model is None:
        model = GEMINI_MODEL
    
    if not GCP_PROJECT_ID:
        raise ValueError("GCP_PROJECT_ID not found in environment variables")
    
    # Load manifest if provided
    manifest = None
    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    # Query Supermemory with corpus filter
    client = _get_supermemory_client()
    results = query_with_corpus_filter(client, question, corpus_id, doc_id, top_k)
    
    if not results:
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": [],
            "evidence_pack": ""
        }
    
    # Build evidence pack
    evidence_pack = _build_evidence_pack(results, manifest, doc_id or "", max_chars_per_page)
    
    if not evidence_pack:
        return {
            "answer_md": "Not found in provided documents.",
            "retrieved": [],
            "evidence_pack": ""
        }
    
    # Generate answer
    answer_md = generate_answer_with_gemini(question, evidence_pack, corpus_id, model)
    
    # Build retrieved list
    retrieved = []
    for result in results:
        info = _extract_result_info(result, manifest)
        if info:
            memory_id, page_number, content = info
            excerpt = content[:250] if len(content) > 250 else content
            
            # Extract doc_id from metadata
            if hasattr(result, 'metadata'):
                metadata = result.metadata
            elif isinstance(result, dict):
                metadata = result.get('metadata', {})
            else:
                metadata = {}
            
            doc_id_from_result = metadata.get('doc_id', doc_id or '')
            
            retrieved.append({
                "doc_id": doc_id_from_result,
                "page": page_number,
                "memory_id": memory_id,
                "excerpt": excerpt
            })
    
    return {
        "answer_md": answer_md,
        "retrieved": retrieved,
        "evidence_pack": evidence_pack
    }

