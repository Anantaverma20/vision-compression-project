"""Supermemory ingestion module - ingests page JSON files into Supermemory."""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from glob import glob
from concurrent.futures import ThreadPoolExecutor, as_completed

from supermemory import Supermemory

from app.config import (
    SUPERMEMORY_API_KEY,
    SUPERMEMORY_BASE_URL,
    SUPERMEMORY_WORKSPACE_ID,
)
from app.pipeline.utils import retry, safe_json_loads


def parse_json_file(file_path: Path) -> Dict:
    """
    Parse JSON file, handling potential issues with fences and formatting.
    
    Returns:
        dict: Parsed data with 'markdown', 'entities', 'summary', 'page_number'
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        outer_data = json.load(f)
    
    # Extract raw_response if present
    raw_response = outer_data.get('raw_response', '')
    
    # If raw_response exists, try to parse the inner JSON
    if raw_response:
        inner_data = safe_json_loads(raw_response)
        if inner_data:
            # Merge with outer data, preferring inner data
            result = {**outer_data, **inner_data}
            return result
        else:
            # If parsing fails, treat as raw text
            return {
                'page_number': outer_data.get('page_number', 1),
                'markdown': raw_response,
                'entities': [],
                'summary': ''
            }
    
    # If no raw_response, use outer_data directly
    return outer_data


def _ingest_page_with_retry(client, content: str, metadata: Dict) -> str:
    """Ingest a page into Supermemory with retry logic."""
    def _call():
        # Try common SDK patterns
        if hasattr(client, 'memories') and hasattr(client.memories, 'create'):
            response = client.memories.create(content=content, metadata=metadata)
        elif hasattr(client, 'memories') and hasattr(client.memories, 'add'):
            response = client.memories.add(content=content, metadata=metadata)
        elif hasattr(client, 'create_memory'):
            response = client.create_memory(content=content, metadata=metadata)
        elif hasattr(client, 'add_memory'):
            response = client.add_memory(content=content, metadata=metadata)
        else:
            # Fallback: try direct call with common pattern
            response = client.create(content=content, metadata=metadata)
        
        # Extract memory ID from response
        if hasattr(response, 'id'):
            return response.id
        elif hasattr(response, 'memory_id'):
            return response.memory_id
        elif isinstance(response, dict):
            return response.get('id') or response.get('memory_id') or str(response)
        else:
            return str(response)
    
    return retry(_call, attempts=3)


def ingest_page_to_supermemory(
    client: Supermemory,
    file_path: Path,
    doc_id: str,
    page_number: int,
    pdf_path: Path,
    overwrite: bool = False,
    corpus_id: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Ingest a single page into Supermemory.
    
    Args:
        corpus_id: Optional corpus ID to include in metadata
    
    Returns:
        tuple: (success: bool, memory_id: str or None, error: str or None)
    """
    # Parse the JSON file
    try:
        data = parse_json_file(file_path)
    except Exception as e:
        return False, None, f"Failed to parse JSON: {e}"
    
    # Extract content and metadata
    content = data.get('markdown', '')
    if not content and 'raw_response' in data:
        content = data['raw_response']
    if not content:
        content = str(data)  # Fallback to string representation
    
    metadata = {
        'doc_id': doc_id,
        'page': page_number,
        'summary': data.get('summary', ''),
        'entities': data.get('entities', []),
        'source_file': str(pdf_path)
    }
    
    # Add corpus_id if provided
    if corpus_id:
        metadata['corpus_id'] = corpus_id
    
    # Ingest with retry
    try:
        memory_id = _ingest_page_with_retry(client, content, metadata)
        return True, memory_id, None
    except Exception as e:
        return False, None, str(e)


def ingest_pages_dir(
    pages_dir: Path,
    pdf_path: Path,
    doc_id: str,
    manifest_path: Path,
    overwrite: bool = False,
    corpus_id: Optional[str] = None
) -> Dict:
    """
    Ingest all page JSON files from a directory into Supermemory.
    
    Args:
        pages_dir: Directory containing page_*.json files
        pdf_path: Path to original PDF file
        doc_id: Document ID
        manifest_path: Path to save manifest file
        overwrite: Whether to overwrite existing ingested pages
        
    Returns:
        dict: Manifest with pages list and failures
    """
    # Initialize Supermemory client
    if not SUPERMEMORY_API_KEY:
        raise ValueError("SUPERMEMORY_API_KEY not found in environment variables")
    
    client_kwargs = {'api_key': SUPERMEMORY_API_KEY}
    if SUPERMEMORY_BASE_URL:
        client_kwargs['base_url'] = SUPERMEMORY_BASE_URL
    if SUPERMEMORY_WORKSPACE_ID:
        client_kwargs['workspace_id'] = SUPERMEMORY_WORKSPACE_ID
    
    client = Supermemory(**client_kwargs)
    
    # Load existing manifest if it exists
    existing_pages = {}
    if manifest_path.exists() and not overwrite:
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                existing_manifest = json.load(f)
                if existing_manifest.get('doc_id') == doc_id:
                    for page_entry in existing_manifest.get('pages', []):
                        if 'page' in page_entry and 'error' not in page_entry:
                            existing_pages[page_entry['page']] = page_entry
        except Exception:
            pass
    
    # Find all page JSON files
    page_files = sorted(glob(str(pages_dir / 'page_*.json')))
    
    if not page_files:
        return {
            'doc_id': doc_id,
            'pdf_path': str(pdf_path),
            'pages': [],
            'failed_pages': []
        }
    
    # Process pages in parallel for faster ingestion
    pages = []
    failed_pages = []
    
    def ingest_page_wrapper(file_path_str):
        """Wrapper for parallel ingestion."""
        file_path = Path(file_path_str)
        
        # Extract page number from filename
        match = re.search(r'page_(\d+)\.json', file_path.name)
        if not match:
            return None, None, None
        
        page_number = int(match.group(1))
        
        # Skip if already ingested (unless overwrite)
        if not overwrite and page_number in existing_pages:
            return page_number, existing_pages[page_number], None
        
        # Ingest page
        success, memory_id, error = ingest_page_to_supermemory(
            client, file_path, doc_id, page_number, pdf_path, overwrite, corpus_id
        )
        
        if success:
            return page_number, {
                'page': page_number,
                'file': str(file_path),
                'memory_id': memory_id
            }, None
        else:
            return page_number, None, {'page': page_number, 'error': error or 'Unknown error'}
    
    # Process in parallel (20 workers for Supermemory API calls - increased for faster ingestion)
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_file = {
            executor.submit(ingest_page_wrapper, file_path_str): file_path_str
            for file_path_str in page_files
        }
        
        for future in as_completed(future_to_file):
            try:
                page_num, page_entry, failed_entry = future.result()
                if page_entry:
                    pages.append(page_entry)
                elif failed_entry:
                    failed_pages.append(failed_entry)
            except Exception as e:
                file_path_str = future_to_file[future]
                failed_pages.append({'page': 0, 'error': f'Ingestion error for {file_path_str}: {e}'})
    
    # Sort pages by page number for consistent output
    pages.sort(key=lambda x: x['page'])
    
    # Create manifest
    manifest = {
        'doc_id': doc_id,
        'pdf_path': str(pdf_path),
        'pages': pages,
        'failed_pages': failed_pages
    }
    
    # Save manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    # Ingestion complete
    return manifest

