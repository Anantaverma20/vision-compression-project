"""Optical-lite ingestion module - stores minimal metadata + image references in Supermemory."""

import json
import re
import logging
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
from app.pipeline.utils import retry, safe_json_loads, strip_code_fences

logger = logging.getLogger(__name__)


def _extract_title_from_markdown(markdown: str, max_length: int = 120) -> str:
    """
    Extract first heading from markdown text.
    
    Args:
        markdown: Markdown text
        max_length: Maximum length of title
        
    Returns:
        First heading found, or empty string
    """
    if not markdown:
        return ""
    
    # Look for markdown headings (# Heading, ## Heading, etc.)
    heading_pattern = r'^#{1,6}\s+(.+)$'
    for line in markdown.split('\n'):
        match = re.match(heading_pattern, line.strip())
        if match:
            title = match.group(1).strip()
            if len(title) > max_length:
                title = title[:max_length] + "..."
            return title
    
    return ""


def _truncate_summary(summary: str, max_length: int = 400) -> str:
    """Truncate summary to max_length characters."""
    if not summary:
        return ""
    if len(summary) <= max_length:
        return summary
    return summary[:max_length] + "..."


def _limit_entities(entities: List, max_count: int = 10) -> List:
    """Limit entities list to max_count items."""
    if not entities:
        return []
    if isinstance(entities, list):
        return entities[:max_count]
    return []


def parse_json_file(file_path: Path) -> Dict:
    """
    Parse JSON file, handling potential issues with fences and formatting.
    
    Returns:
        dict: Parsed data with 'markdown', 'entities', 'summary', 'page_number'
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Strip code fences if present
    cleaned = strip_code_fences(content)
    
    try:
        outer_data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try parsing inner JSON if raw_response exists
        try:
            outer_data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from {file_path}")
            return {
                'page_number': 1,
                'markdown': '',
                'entities': [],
                'summary': ''
            }
    
    # Extract raw_response if present
    raw_response = outer_data.get('raw_response', '')
    
    # If raw_response exists, try to parse the inner JSON
    if raw_response:
        inner_data = safe_json_loads(raw_response)
        if inner_data:
            # Merge with outer data, preferring inner data
            result = {**outer_data, **inner_data}
            return result
    
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


def ingest_optical_lite(
    doc_id: str,
    pages_dir: str,
    images_dir: str,
    pdf_path: str | None = None,
    corpus_id: str | None = None,
    render_config: dict | None = None,
    overwrite: bool = False
) -> dict:
    """
    Ingest pages using optical-lite mode: store ONLY minimal metadata + image references.
    
    Args:
        doc_id: Document ID
        pages_dir: Directory containing page_###.json files
        images_dir: Directory containing page_###.png files
        pdf_path: Optional path to original PDF
        corpus_id: Optional corpus ID
        render_config: Optional render configuration dict
        overwrite: Whether to overwrite existing ingested pages
        
    Returns:
        dict: Manifest with pages list and failures
    """
    pages_dir_path = Path(pages_dir)
    images_dir_path = Path(images_dir)
    
    # Initialize Supermemory client
    if not SUPERMEMORY_API_KEY:
        raise ValueError("SUPERMEMORY_API_KEY not found in environment variables")
    
    client_kwargs = {'api_key': SUPERMEMORY_API_KEY}
    if SUPERMEMORY_BASE_URL:
        client_kwargs['base_url'] = SUPERMEMORY_BASE_URL
    if SUPERMEMORY_WORKSPACE_ID:
        client_kwargs['workspace_id'] = SUPERMEMORY_WORKSPACE_ID
    
    client = Supermemory(**client_kwargs)
    
    # Create output directory for manifest
    output_dir = Path("output") / "optical_lite" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "optical_lite_manifest.json"
    
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
        except Exception as e:
            logger.warning(f"Failed to load existing manifest: {e}")
    
    # Find all page JSON files
    page_files = sorted(glob(str(pages_dir_path / 'page_*.json')))
    
    if not page_files:
        return {
            'doc_id': doc_id,
            'pdf_path': str(pdf_path) if pdf_path else None,
            'pages': [],
            'failed_pages': []
        }
    
    # Process pages in parallel
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
        
        # Parse the JSON file
        try:
            data = parse_json_file(file_path)
        except Exception as e:
            return page_number, None, {'page': page_number, 'error': f"Failed to parse JSON: {e}"}
        
        # Extract minimal fields
        summary = _truncate_summary(data.get('summary', ''), max_length=400)
        entities = _limit_entities(data.get('entities', []), max_count=10)
        markdown = data.get('markdown', '')
        title = _extract_title_from_markdown(markdown, max_length=120)
        
        # Build image path
        image_path = images_dir_path / f"page_{page_number:03d}.png"
        if not image_path.exists():
            # Try without zero-padding
            image_path = images_dir_path / f"page_{page_number}.png"
        
        # Build index string for Supermemory content
        # Format: "doc_id=<...> corpus_id=<...> page=<n> title=<...> summary=<...> entities=<...>"
        index_parts = [f"doc_id={doc_id}"]
        if corpus_id:
            index_parts.append(f"corpus_id={corpus_id}")
        index_parts.append(f"page={page_number}")
        if title:
            index_parts.append(f"title={title}")
        if summary:
            index_parts.append(f"summary={summary}")
        if entities:
            entities_str = ", ".join(str(e) for e in entities[:5])  # Limit to 5 for index string
            index_parts.append(f"entities={entities_str}")
        
        index_string = " ".join(index_parts)
        
        # Build metadata
        metadata = {
            'doc_id': doc_id,
            'page': page_number,
            'image_path': str(image_path),
            'title': title,
            'summary': summary,
            'entities': entities,
        }
        
        if corpus_id:
            metadata['corpus_id'] = corpus_id
        if pdf_path:
            metadata['source_file'] = str(pdf_path)
        if render_config:
            metadata['render_config'] = render_config
        
        # Ingest with retry
        try:
            memory_id = _ingest_page_with_retry(client, index_string, metadata)
            return page_number, {
                'page': page_number,
                'image_path': str(image_path),
                'supermemory_id': memory_id
            }, None
        except Exception as e:
            return page_number, None, {'page': page_number, 'error': str(e)}
    
    # Process in parallel (20 workers)
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
    
    # Sort pages by page number
    pages.sort(key=lambda x: x['page'])
    
    # Create manifest
    manifest = {
        'doc_id': doc_id,
        'pdf_path': str(pdf_path) if pdf_path else None,
        'corpus_id': corpus_id,
        'pages': pages,
        'failed_pages': failed_pages,
        'render_config': render_config
    }
    
    # Save manifest
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Optical-lite ingestion complete: {len(pages)} pages ingested, {len(failed_pages)} failed")
    
    return manifest

