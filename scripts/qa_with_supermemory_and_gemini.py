#!/usr/bin/env python3
"""
Question answering using Supermemory retrieval + Gemini reasoning with citations.

STEP 4: Retrieves relevant page memories from Supermemory and uses Gemini
to generate answers with proper citations.
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai package not found. Install with: pip install google-generativeai")

try:
    from supermemory import Supermemory
    SUPERMEMORY_AVAILABLE = True
except ImportError:
    SUPERMEMORY_AVAILABLE = False
    print("Warning: supermemory package not found. Install with: pip install supermemory")


def load_manifest(manifest_path):
    """Load the Supermemory manifest file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def query_supermemory(client, query, doc_id, top_k, max_retries=3):
    """
    Query Supermemory for relevant memories filtered by doc_id.
    
    Args:
        client: Supermemory client instance
        query: Search query string
        doc_id: Document ID to filter by
        top_k: Number of results to retrieve
        max_retries: Maximum retry attempts
    
    Returns:
        list: List of result objects with memory_id, content, and metadata
    """
    for attempt in range(max_retries):
        try:
            # Try common SDK search patterns
            if hasattr(client, 'search') and hasattr(client.search, 'query'):
                # Try with filter if supported
                try:
                    response = client.search.query(q=query, limit=top_k, filter={'doc_id': doc_id})
                except (TypeError, AttributeError):
                    # Fallback: query without filter, filter results after
                    response = client.search.query(q=query, limit=top_k * 2)  # Get more to account for filtering
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
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"  Retry {attempt + 1}/{max_retries} after {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise Exception(f"Supermemory query failed after {max_retries} attempts: {e}")
    
    return []


def extract_result_info(result, manifest):
    """
    Extract memory_id, page number, and content from a Supermemory result.
    
    Args:
        result: Supermemory result object
        manifest: Manifest dict with page->memory_id mapping
    
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
    if page_number is None:
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
    
    # Return None if content is empty (no point including empty results)
    if not content.strip():
        return None
    
    return memory_id, page_number, content


def rewrite_query_with_gemini(question, model_name='gemini-3-pro-preview', max_retries=3):
    """
    Use Gemini to rewrite the question into better search terms.
    
    Args:
        question: Original question
        model_name: Gemini model to use
        max_retries: Maximum retry attempts
    
    Returns:
        str: Rewritten query for search
    """
    prompt = f"""Rewrite the following question into concise search terms optimized for document retrieval.
Focus on key concepts, entities, and technical terms. Keep it brief (1-3 phrases).

Question: {question}

Rewritten search terms:"""
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    max_output_tokens=128
                )
            )
            
            rewritten = response.text.strip()
            # Remove quotes if present
            rewritten = rewritten.strip('"\'')
            return rewritten
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                print(f"Warning: Query rewriting failed, using original question: {e}")
                return question
    
    return question


def build_evidence_pack(results, manifest, doc_id, max_chars_per_page):
    """
    Build evidence pack string from retrieved results.
    
    Args:
        results: List of Supermemory result objects
        manifest: Manifest dict
        doc_id: Document ID
        max_chars_per_page: Maximum characters per page
    
    Returns:
        str: Formatted evidence pack
    """
    evidence_sections = []
    
    for result in results:
        info = extract_result_info(result, manifest)
        if info is None:
            continue
        
        memory_id, page_number, content = info
        
        # Skip if content is None or empty (shouldn't happen after fix, but be safe)
        if not content or not isinstance(content, str):
            continue
        
        # Truncate content if needed
        if len(content) > max_chars_per_page:
            content = content[:max_chars_per_page] + "... [truncated]"
        
        section = f"[Page {page_number} | memory_id={memory_id}]\n{content}"
        evidence_sections.append(section)
    
    return "\n\n---\n\n".join(evidence_sections)


def generate_answer_with_gemini(question, evidence_pack, doc_id, model_name='gemini-3-pro-preview', max_retries=3):
    """
    Use Gemini to generate an answer from the evidence pack with citations.
    
    Args:
        question: User question
        evidence_pack: Formatted evidence pack string
        doc_id: Document ID for citations
        model_name: Gemini model to use
        max_retries: Maximum retry attempts
    
    Returns:
        str: Generated answer with citations
    """
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
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0,
                    max_output_tokens=2048
                )
            )
            
            return response.text.strip()
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"  Retry {attempt + 1}/{max_retries} after {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise Exception(f"Gemini generation failed after {max_retries} attempts: {e}")
    
    return "Error: Failed to generate answer"


def save_answer(question, answer, retrieved_pages, output_dir):
    """
    Save the answer to a markdown file.
    
    Args:
        question: User question
        answer: Generated answer
        retrieved_pages: List of (page_number, memory_id) tuples
        output_dir: Output directory path
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp-based filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_answer.md"
    output_path = output_dir / filename
    
    # Format retrieved pages list
    pages_list = "\n".join([
        f"- Page {page}: memory_id={memory_id}"
        for page, memory_id in retrieved_pages
    ])
    
    content = f"""# Question

{question}

# Answer

{answer}

---

# Retrieved Pages (for debugging)

{pages_list}
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Question answering using Supermemory retrieval + Gemini reasoning with citations."
    )
    parser.add_argument(
        '--question',
        required=True,
        help='Question to answer'
    )
    parser.add_argument(
        '--manifest',
        default='output/supermemory_manifest.json',
        help='Path to Supermemory manifest (default: output/supermemory_manifest.json)'
    )
    parser.add_argument(
        '--top_k',
        type=int,
        default=8,
        help='Number of top results to retrieve (default: 8)'
    )
    parser.add_argument(
        '--max_chars_per_page',
        type=int,
        default=1500,
        help='Maximum characters per page in evidence pack (default: 1500)'
    )
    parser.add_argument(
        '--model',
        default='gemini-3-pro-preview',
        help='Gemini model to use (default: gemini-3-pro-preview)'
    )
    parser.add_argument(
        '--rewrite_query',
        action='store_true',
        help='Use Gemini to rewrite the question into search terms before retrieval'
    )
    
    args = parser.parse_args()
    
    # Check dependencies
    if not GEMINI_AVAILABLE:
        print("Error: google-generativeai package is not installed.")
        print("Install it with: pip install google-generativeai")
        return 1
    
    if not SUPERMEMORY_AVAILABLE:
        print("Error: supermemory package is not installed.")
        print("Install it with: pip install supermemory")
        return 1
    
    # Initialize Gemini
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    if not gemini_api_key:
        print("Error: GEMINI_API_KEY not found in environment variables.")
        print(f"Looking for .env file at: {env_path}")
        if not env_path.exists():
            print(f"  .env file not found at {env_path}")
            print("  Please create a .env file in the project root with:")
            print("  GEMINI_API_KEY=your_api_key_here")
        return 1
    
    genai.configure(api_key=gemini_api_key)
    
    # Initialize Supermemory
    supermemory_api_key = os.getenv('SUPERMEMORY_API_KEY')
    if not supermemory_api_key:
        print("Error: SUPERMEMORY_API_KEY not found in environment variables.")
        print(f"Looking for .env file at: {env_path}")
        return 1
    
    base_url = os.getenv('SUPERMEMORY_BASE_URL')
    workspace_id = os.getenv('SUPERMEMORY_WORKSPACE_ID')
    
    try:
        client_kwargs = {'api_key': supermemory_api_key}
        if base_url:
            client_kwargs['base_url'] = base_url
        if workspace_id:
            client_kwargs['workspace_id'] = workspace_id
        client = Supermemory(**client_kwargs)
    except Exception as e:
        print(f"Error initializing Supermemory client: {e}")
        return 1
    
    # Load manifest
    manifest_path = Path(args.manifest)
    try:
        manifest = load_manifest(manifest_path)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    
    doc_id = manifest.get('doc_id')
    if not doc_id:
        print("Error: doc_id not found in manifest.")
        return 1
    
    print(f"Document ID: {doc_id}")
    print(f"Question: {args.question}")
    
    # Rewrite query if requested
    search_query = args.question
    if args.rewrite_query:
        print("Rewriting query with Gemini...")
        search_query = rewrite_query_with_gemini(args.question, args.model)
        print(f"Rewritten query: {search_query}")
    
    # Query Supermemory
    print(f"\nQuerying Supermemory (top_k={args.top_k})...")
    try:
        results = query_supermemory(client, search_query, doc_id, args.top_k)
    except Exception as e:
        print(f"Error querying Supermemory: {e}")
        return 1
    
    if not results:
        print("\nNo results found. Please check:")
        print("  1. The question matches content in the document")
        print("  2. The manifest file is correct")
        print("  3. Pages were successfully ingested into Supermemory")
        return 1
    
    print(f"Retrieved {len(results)} results")
    
    # Build evidence pack
    print("Building evidence pack...")
    evidence_pack = build_evidence_pack(results, manifest, doc_id, args.max_chars_per_page)
    
    if not evidence_pack:
        print("Error: Could not extract content from retrieved results.")
        return 1
    
    # Generate answer with Gemini
    print(f"Generating answer with {args.model}...")
    try:
        answer = generate_answer_with_gemini(
            args.question,
            evidence_pack,
            doc_id,
            args.model
        )
    except Exception as e:
        print(f"Error generating answer: {e}")
        return 1
    
    # Extract retrieved pages info for output
    retrieved_pages = []
    for result in results:
        info = extract_result_info(result, manifest)
        if info:
            memory_id, page_number, _ = info
            retrieved_pages.append((page_number, memory_id))
    
    # Save answer
    output_dir = project_root / 'output' / 'answers'
    output_path = save_answer(args.question, answer, retrieved_pages, output_dir)
    
    print(f"\n✓ Answer saved to: {output_path}")
    print(f"\nRetrieved pages: {', '.join([f'p.{p}' for p, _ in retrieved_pages])}")
    
    return 0


if __name__ == '__main__':
    exit(main())

