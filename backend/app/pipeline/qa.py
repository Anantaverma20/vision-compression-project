"""Question answering module - retrieves from Supermemory and generates answers with Gemini."""

import json
from pathlib import Path
from typing import Dict, List, Optional

import google.generativeai as genai

from app.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
    SUPERMEMORY_API_KEY,
    SUPERMEMORY_BASE_URL,
    SUPERMEMORY_WORKSPACE_ID,
)
from app.pipeline.utils import retry


def _get_supermemory_client():
    """Initialize and return Supermemory client."""
    if not SUPERMEMORY_API_KEY:
        raise ValueError("SUPERMEMORY_API_KEY not found in environment variables")
    
    from supermemory import Supermemory
    
    client_kwargs = {'api_key': SUPERMEMORY_API_KEY}
    if SUPERMEMORY_BASE_URL:
        client_kwargs['base_url'] = SUPERMEMORY_BASE_URL
    if SUPERMEMORY_WORKSPACE_ID:
        client_kwargs['workspace_id'] = SUPERMEMORY_WORKSPACE_ID
    
    return Supermemory(**client_kwargs)


def _query_supermemory(client, query: str, doc_id: str, top_k: int) -> List:
    """
    Query Supermemory for relevant memories filtered by doc_id.
    
    Returns:
        list: List of result objects with memory_id, content, and metadata
    """
    def _call():
        # Try common SDK search patterns
        if hasattr(client, 'search') and hasattr(client.search, 'query'):
            try:
                response = client.search.query(q=query, limit=top_k, filter={'doc_id': doc_id})
            except (TypeError, AttributeError):
                # Fallback: query without filter, filter results after
                response = client.search.query(q=query, limit=top_k * 2)
        elif hasattr(client, 'search') and hasattr(client.search, 'documents'):
            try:
                response = client.search.documents(q=query, limit=top_k, filter={'doc_id': doc_id})
            except (TypeError, AttributeError):
                response = client.search.documents(q=query, limit=top_k * 2)
        elif hasattr(client, 'query'):
            try:
                response = client.query(query=query, limit=top_k, filter={'doc_id': doc_id})
            except (TypeError, AttributeError):
                response = client.query(query=query, limit=top_k * 2)
        elif hasattr(client, 'search'):
            try:
                response = client.search(query, limit=top_k, filter={'doc_id': doc_id})
            except (TypeError, AttributeError):
                response = client.search(query, limit=top_k * 2)
        else:
            raise AttributeError("Could not find search method in Supermemory client")
        
        # Extract results
        if hasattr(response, 'results'):
            results = response.results
        elif hasattr(response, 'data'):
            results = response.data
        elif isinstance(response, list):
            results = response
        else:
            results = [response]
        
        # Filter by doc_id if not done by SDK
        filtered_results = []
        for result in results:
            # Extract metadata
            if hasattr(result, 'metadata'):
                metadata = result.metadata
            elif isinstance(result, dict):
                metadata = result.get('metadata', {})
            else:
                metadata = {}
            
            # Check if doc_id matches
            if metadata.get('doc_id') == doc_id:
                filtered_results.append(result)
                if len(filtered_results) >= top_k:
                    break
        
        return filtered_results[:top_k]
    
    return retry(_call, attempts=3)


def _extract_result_info(result, manifest: Optional[Dict]) -> Optional[tuple]:
    """
    Extract memory_id, page number, and content from a Supermemory result.
    
    Returns:
        tuple: (memory_id, page_number, content) or None if extraction fails
    """
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
    
    # Get page number from metadata or map via manifest
    page_number = metadata.get('page')
    if page_number is None and manifest:
        # Try to find page number from manifest using memory_id
        for page_entry in manifest.get('pages', []):
            if page_entry.get('memory_id') == memory_id:
                page_number = page_entry.get('page')
                break
    
    if page_number is None:
        return None
    
    # Extract content
    content = None
    if hasattr(result, 'content'):
        content = result.content
    elif hasattr(result, 'text'):
        content = result.text
    elif isinstance(result, dict):
        content = result.get('content') or result.get('text')
    
    # Ensure content is not None and is a string
    if content is None:
        content = str(result) if result else ''
    elif not isinstance(content, str):
        content = str(content)
    
    # Return None if content is empty
    if not content.strip():
        return None
    
    return memory_id, page_number, content


def _build_evidence_pack(results: List, manifest: Optional[Dict], doc_id: str, max_chars_per_page: int) -> str:
    """
    Build evidence pack string from retrieved results.
    
    Returns:
        str: Formatted evidence pack
    """
    evidence_sections = []
    
    for result in results:
        info = _extract_result_info(result, manifest)
        if info is None:
            continue
        
        memory_id, page_number, content = info
        
        # Skip if content is None or empty
        if not content or not isinstance(content, str):
            continue
        
        # Truncate content if needed
        if len(content) > max_chars_per_page:
            content = content[:max_chars_per_page] + "... [truncated]"
        
        section = f"[Page {page_number} | memory_id={memory_id}]\n{content}"
        evidence_sections.append(section)
    
    return "\n\n---\n\n".join(evidence_sections)


def _generate_answer_with_gemini(question: str, evidence_pack: str, doc_id: str, model_name: str) -> str:
    """Use Gemini to generate an answer from the evidence pack with citations."""
    prompt = f"""You are answering a question based ONLY on the provided evidence pack. Use ONLY the information present in the evidence pack. If the information is not present, explicitly state "Not found in provided pages."

CRITICAL CITATION REQUIREMENTS:
- Every non-trivial claim MUST have an inline citation in the format: ({doc_id} p.<page_number>)
- If multiple pages support a claim, cite all relevant pages: ({doc_id} p.X, p.Y)
- Use citations immediately after each claim or fact
- Format: ({doc_id} p.1) or ({doc_id} p.1, p.2) for multiple pages

Question: {question}

Evidence Pack:
{evidence_pack}

Answer (with citations):"""
    
    def _call():
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS_ANSWERING
            )
        )
        return response.text.strip()
    
    return retry(_call, attempts=3)


def answer_question(
    doc_id: str,
    question: str,
    top_k: int = 8,
    max_chars_per_page: int = 1500,
    model: str = None,
    manifest_path: Optional[Path] = None
) -> Dict:
    """
    Answer a question using Supermemory retrieval and Gemini generation.
    
    Args:
        doc_id: Document ID
        question: User question
        top_k: Number of top results to retrieve
        max_chars_per_page: Maximum characters per page in evidence pack
        model: Gemini model to use (default: GEMINI_MODEL from config)
        manifest_path: Optional path to manifest file
        
    Returns:
        dict: {"answer_md": str, "retrieved": List[Dict]}
    """
    # Use default model if not specified
    if model is None:
        model = GEMINI_MODEL
    
    # Configure Gemini
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Load manifest if provided
    manifest = None
    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            pass
    
    # Query Supermemory
    client = _get_supermemory_client()
    results = _query_supermemory(client, question, doc_id, top_k)
    
    if not results:
        return {
            "answer_md": "Not found in provided pages.",
            "retrieved": []
        }
    
    # Build evidence pack
    evidence_pack = _build_evidence_pack(results, manifest, doc_id, max_chars_per_page)
    
    if not evidence_pack:
        return {
            "answer_md": "Not found in provided pages.",
            "retrieved": []
        }
    
    # Generate answer with Gemini
    answer_md = _generate_answer_with_gemini(question, evidence_pack, doc_id, model)
    
    # Build retrieved list
    retrieved = []
    for result in results:
        info = _extract_result_info(result, manifest)
        if info:
            memory_id, page_number, content = info
            excerpt = content[:250] if len(content) > 250 else content
            retrieved.append({
                "page": page_number,
                "memory_id": memory_id,
                "excerpt": excerpt
            })
    
    return {
        "answer_md": answer_md,
        "retrieved": retrieved
    }

