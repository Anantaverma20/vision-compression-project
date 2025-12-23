"""Question answering module - retrieves from Supermemory and generates answers with Gemini."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.config import (
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
    SUPERMEMORY_API_KEY,
    SUPERMEMORY_BASE_URL,
    SUPERMEMORY_WORKSPACE_ID,
)
from app.pipeline.utils import retry
from app.llm.vertex_gemini import VertexGeminiClient

logger = logging.getLogger(__name__)


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


def _query_supermemory(client, query: str, doc_id: Optional[str] = None, corpus_id: Optional[str] = None, top_k: int = 8) -> List:
    """
    Query Supermemory for relevant memories filtered by doc_id or corpus_id.
    
    Args:
        client: Supermemory client
        query: Search query
        doc_id: Optional document ID to filter by
        corpus_id: Optional corpus ID to filter by (searches across all docs in corpus)
        top_k: Number of results to return
    
    Returns:
        list: List of result objects with memory_id, content, and metadata
    """
    # Build filter based on what's provided
    filter_dict = {}
    if doc_id:
        filter_dict['doc_id'] = doc_id
    elif corpus_id:
        filter_dict['corpus_id'] = corpus_id
    
    def _call():
        # For corpus queries, request more results to ensure we get enough after filtering
        request_limit = top_k * 3 if corpus_id else top_k
        
        # Try common SDK search patterns
        if hasattr(client, 'search') and hasattr(client.search, 'query'):
            try:
                if filter_dict:
                    response = client.search.query(q=query, limit=request_limit, filter=filter_dict)
                else:
                    response = client.search.query(q=query, limit=request_limit)
            except (TypeError, AttributeError):
                # Fallback: query without filter, filter results after
                response = client.search.query(q=query, limit=request_limit)
        elif hasattr(client, 'search') and hasattr(client.search, 'documents'):
            try:
                if filter_dict:
                    response = client.search.documents(q=query, limit=request_limit, filter=filter_dict)
                else:
                    response = client.search.documents(q=query, limit=request_limit)
            except (TypeError, AttributeError):
                response = client.search.documents(q=query, limit=request_limit)
        elif hasattr(client, 'query'):
            try:
                if filter_dict:
                    response = client.query(query=query, limit=request_limit, filter=filter_dict)
                else:
                    response = client.query(query=query, limit=request_limit)
            except (TypeError, AttributeError):
                response = client.query(query=query, limit=request_limit)
        elif hasattr(client, 'search'):
            try:
                if filter_dict:
                    response = client.search(query, limit=request_limit, filter=filter_dict)
                else:
                    response = client.search(query, limit=request_limit)
            except (TypeError, AttributeError):
                response = client.search(query, limit=request_limit)
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
        
        # Filter by doc_id or corpus_id if not done by SDK
        if filter_dict:
            filtered_results = []
            for result in results:
                # Extract metadata
                if hasattr(result, 'metadata'):
                    metadata = result.metadata
                elif isinstance(result, dict):
                    metadata = result.get('metadata', {})
                else:
                    metadata = {}
                
                # Check if filter matches - be more lenient with corpus_id matching
                match = True
                if doc_id:
                    result_doc_id = metadata.get('doc_id')
                    if result_doc_id != doc_id:
                        match = False
                elif corpus_id:
                    result_corpus_id = metadata.get('corpus_id')
                    # Match if corpus_id matches or if no corpus_id filter was applied by SDK
                    if result_corpus_id and result_corpus_id != corpus_id:
                        match = False
                    # If no corpus_id in metadata but we're filtering by corpus_id, 
                    # include it anyway (might be from same corpus but metadata missing)
                    # This helps with documents that were ingested but metadata wasn't set correctly
                
                if match:
                    filtered_results.append(result)
                    if len(filtered_results) >= top_k:
                        break
            
            # If we got fewer results than requested and filtering by corpus_id, 
            # return what we have (already tried broader search above)
            return filtered_results[:top_k] if filtered_results else results[:top_k]
        
        return results[:top_k]
    
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
        client = VertexGeminiClient(model_name=model_name)
        return client.generate_content(
            contents=prompt,
            temperature=GEMINI_TEMPERATURE,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS_ANSWERING,
        )
    
    return retry(_call, attempts=3)


def answer_question(
    doc_id: Optional[str] = None,
    corpus_id: Optional[str] = None,
    question: str = "",
    top_k: int = 8,
    max_chars_per_page: int = 1500,
    model: str = None,
    manifest_path: Optional[Path] = None
) -> Dict:
    """
    Answer a question using Supermemory retrieval and Gemini generation.
    
    Args:
        doc_id: Optional document ID (for single document queries)
        corpus_id: Optional corpus ID (for multi-document queries)
        question: User question
        top_k: Number of top results to retrieve
        max_chars_per_page: Maximum characters per page in evidence pack
        model: Gemini model to use (default: GEMINI_MODEL from config)
        manifest_path: Optional path to manifest file
        
    Returns:
        dict: {"answer_md": str, "retrieved": List[Dict]}
    """
    # Validate that either doc_id or corpus_id is provided
    if not doc_id and not corpus_id:
        raise ValueError("Either doc_id or corpus_id must be provided")
    
    # Use default model if not specified
    if model is None:
        model = GEMINI_MODEL
    
    # Validate Vertex AI configuration
    from app.config import GCP_PROJECT_ID
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
    
    # Query Supermemory
    client = _get_supermemory_client()
    results = _query_supermemory(client, question, doc_id=doc_id, corpus_id=corpus_id, top_k=top_k)
    
    # Log query results for debugging
    logger.info(f"Query returned {len(results) if results else 0} results for {'corpus_id=' + corpus_id if corpus_id else 'doc_id=' + doc_id}")
    if results:
        logger.debug(f"First result metadata: {results[0].metadata if hasattr(results[0], 'metadata') else (results[0].get('metadata') if isinstance(results[0], dict) else 'N/A')}")
    
    if not results:
        logger.warning(f"No results found for query: '{question}' with {'corpus_id=' + corpus_id if corpus_id else 'doc_id=' + doc_id}")
        return {
            "answer_md": "Not found in provided pages.",
            "retrieved": []
        }
    
    # For corpus queries, extract doc_id from results if available, otherwise use corpus_id
    citation_id = doc_id
    if not citation_id and corpus_id:
        # Try to get doc_id from first result's metadata
        if results:
            first_result = results[0]
            if hasattr(first_result, 'metadata'):
                citation_id = first_result.metadata.get('doc_id', corpus_id)
            elif isinstance(first_result, dict):
                citation_id = first_result.get('metadata', {}).get('doc_id', corpus_id)
        if not citation_id:
            citation_id = corpus_id  # Fallback to corpus_id
    
    # Build evidence pack - use citation_id for proper citations
    evidence_pack = _build_evidence_pack(results, manifest, citation_id, max_chars_per_page)
    
    if not evidence_pack:
        return {
            "answer_md": "Not found in provided pages.",
            "retrieved": []
        }
    
    # Generate answer with Gemini - use citation_id for citations
    answer_md = _generate_answer_with_gemini(question, evidence_pack, citation_id, model)
    
    # Build retrieved list with full content
    retrieved = []
    for result in results:
        info = _extract_result_info(result, manifest)
        if info:
            memory_id, page_number, content = info
            excerpt = content[:250] if len(content) > 250 else content
            
            # Try to get full content from page JSON file if available
            full_content = None
            if doc_id:
                # Try to find page JSON file
                doc_dir = None
                if corpus_id:
                    # For corpus, try to find doc_id from manifest or search in corpus structure
                    corpus_dir = Path("output") / "corpora" / corpus_id / "docs"
                    if corpus_dir.exists():
                        # Search for doc_id in corpus
                        for potential_doc_dir in corpus_dir.iterdir():
                            if potential_doc_dir.is_dir():
                                pages_dir = potential_doc_dir / "pages"
                                page_json_path = pages_dir / f"page_{page_number:03d}.json"
                                if page_json_path.exists():
                                    try:
                                        with open(page_json_path, 'r', encoding='utf-8') as f:
                                            page_data = json.load(f)
                                            full_content = page_data.get('markdown', content)
                                    except Exception:
                                        pass
                                    break
                else:
                    # Single doc - try tmp directory
                    doc_dir = Path("tmp") / doc_id
                    pages_dir = doc_dir / "pages"
                    page_json_path = pages_dir / f"page_{page_number:03d}.json"
                    if page_json_path.exists():
                        try:
                            with open(page_json_path, 'r', encoding='utf-8') as f:
                                page_data = json.load(f)
                                full_content = page_data.get('markdown', content)
                        except Exception:
                            pass
            
            # Fallback to content if full_content not found
            if full_content is None:
                full_content = content
            
            retrieved.append({
                "page": page_number,
                "memory_id": memory_id,
                "excerpt": excerpt,
                "full_content": full_content
            })
    
    return {
        "answer_md": answer_md,
        "retrieved": retrieved
    }

