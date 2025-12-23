#!/usr/bin/env python3
"""
Ingest compressed per-page outputs into Supermemory as searchable memories.

STEP 3: Ingests page JSON files into Supermemory with metadata.
"""

import argparse
import json
import os
import re
import time
from glob import glob
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
# Get the project root (parent of scripts directory)
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

try:
    from supermemory import Supermemory
    SUPERMEMORY_AVAILABLE = True
except ImportError:
    SUPERMEMORY_AVAILABLE = False
    print("Warning: supermemory package not found. Install with: pip install supermemory")


def parse_json_file(file_path):
    """
    Parse JSON file, handling potential issues with fences and formatting.
    
    Returns:
        dict: Parsed data with 'markdown', 'entities', 'summary', 'page_number'
              If parsing fails, returns {'markdown': raw_content}
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        outer_data = json.load(f)
    
    # Extract raw_response if present
    raw_response = outer_data.get('raw_response', '')
    
    # If raw_response exists, try to parse the inner JSON
    if raw_response:
        # Strip ```json fences if present
        content = raw_response.strip()
        content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
        content = content.strip()
        
        try:
            inner_data = json.loads(content)
            # Merge with outer data, preferring inner data
            result = {**outer_data, **inner_data}
            return result
        except json.JSONDecodeError:
            # If parsing fails, treat as raw text
            return {
                'page_number': outer_data.get('page_number', 1),
                'markdown': raw_response,
                'entities': [],
                'summary': ''
            }
    
    # If no raw_response, use outer_data directly
    return outer_data


def ingest_page_to_supermemory(client, file_path, doc_id, page_number, pdf_path, max_retries=3):
    """
    Ingest a single page into Supermemory with retry logic.
    
    Args:
        client: Supermemory client instance
        file_path: Path to page JSON file
        doc_id: Document ID
        page_number: Page number
        pdf_path: Path to original PDF
        max_retries: Maximum number of retry attempts
    
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
        'source_file': pdf_path
    }
    
    # Retry logic for API calls
    for attempt in range(max_retries):
        try:
            # Try common SDK patterns - adjust based on actual SDK
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
                memory_id = response.id
            elif hasattr(response, 'memory_id'):
                memory_id = response.memory_id
            elif isinstance(response, dict):
                memory_id = response.get('id') or response.get('memory_id')
            else:
                memory_id = str(response)
            
            return True, memory_id, None
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
            else:
                return False, None, str(e)
    
    return False, None, "Failed after all retries"


def load_manifest(manifest_path):
    """Load existing manifest or create new one."""
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    
    return {
        'doc_id': None,
        'pdf_path': None,
        'created_at': None,
        'pages': []
    }


def save_manifest(manifest_path, doc_id, pdf_path, pages):
    """Save manifest to file."""
    manifest = {
        'doc_id': doc_id,
        'pdf_path': pdf_path,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'pages': pages
    }
    
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def smoke_test(client, query):
    """
    Perform a smoke test by querying Supermemory.
    
    Args:
        client: Supermemory client instance
        query: Query string
    
    Returns:
        list: List of results with page numbers and memory_ids
    """
    print(f"\nRunning smoke test with query: '{query}'")
    
    try:
        # Try common SDK search patterns
        if hasattr(client, 'search') and hasattr(client.search, 'query'):
            response = client.search.query(q=query)
        elif hasattr(client, 'search') and hasattr(client.search, 'documents'):
            response = client.search.documents(q=query)
        elif hasattr(client, 'query'):
            response = client.query(query=query)
        elif hasattr(client, 'search'):
            response = client.search(query)
        else:
            print("Warning: Could not find search method in Supermemory client")
            return []
        
        # Extract results
        if hasattr(response, 'results'):
            results = response.results
        elif hasattr(response, 'data'):
            results = response.data
        elif isinstance(response, list):
            results = response
        else:
            results = [response]
        
        print(f"Found {len(results)} results:")
        for i, result in enumerate(results[:10], 1):  # Top 10 results
            if hasattr(result, 'metadata'):
                metadata = result.metadata
            elif isinstance(result, dict):
                metadata = result.get('metadata', {})
            else:
                metadata = {}
            
            if hasattr(result, 'id'):
                memory_id = result.id
            elif isinstance(result, dict):
                memory_id = result.get('id') or result.get('memory_id', 'N/A')
            else:
                memory_id = 'N/A'
            
            page = metadata.get('page', 'N/A')
            print(f"  {i}. Page {page}, Memory ID: {memory_id}")
        
        return results
        
    except Exception as e:
        print(f"Smoke test failed: {e}")
        return []


def generate_doc_id(pdf_path):
    """Generate a stable doc_id from PDF path."""
    basename = os.path.basename(pdf_path)
    # Remove extension and replace spaces/special chars
    doc_id = os.path.splitext(basename)[0]
    doc_id = re.sub(r'[^\w\-_]', '_', doc_id)
    return doc_id


def main():
    parser = argparse.ArgumentParser(
        description="Ingest compressed per-page outputs into Supermemory as searchable memories."
    )
    parser.add_argument(
        '--pages_dir',
        default='output/pages',
        help='Directory containing page JSON files (default: output/pages)'
    )
    parser.add_argument(
        '--pdf_path',
        default='data/deepseek ocr paper.pdf',
        help='Path to original PDF file (default: data/deepseek ocr paper.pdf). Use quotes if path contains spaces.'
    )
    parser.add_argument(
        '--doc_id',
        help='Document ID. If not provided, generated from PDF filename.'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing ingested pages (default: skip already ingested pages)'
    )
    parser.add_argument(
        '--smoke_test_query',
        default='Summarize the document',
        help='Query for smoke test (default: "Summarize the document")'
    )
    
    args = parser.parse_args()
    
    # Check if Supermemory is available
    if not SUPERMEMORY_AVAILABLE:
        print("Error: supermemory package is not installed.")
        print("Install it with: pip install supermemory")
        return 1
    
    # Initialize Supermemory client
    api_key = os.getenv('SUPERMEMORY_API_KEY')
    if not api_key:
        print("Error: SUPERMEMORY_API_KEY not found in environment variables.")
        print(f"Looking for .env file at: {env_path}")
        if not env_path.exists():
            print(f"  .env file not found at {env_path}")
            print("  Please create a .env file in the project root with:")
            print("  SUPERMEMORY_API_KEY=your_api_key_here")
        else:
            print(f"  .env file exists at {env_path}")
            print("  Please ensure it contains: SUPERMEMORY_API_KEY=your_api_key_here")
        return 1
    
    # base_url and workspace_id are optional - only use if provided
    base_url = os.getenv('SUPERMEMORY_BASE_URL')
    workspace_id = os.getenv('SUPERMEMORY_WORKSPACE_ID')
    
    # Initialize client with only the parameters that are provided
    try:
        client_kwargs = {'api_key': api_key}
        if base_url:
            client_kwargs['base_url'] = base_url
        if workspace_id:
            client_kwargs['workspace_id'] = workspace_id
        client = Supermemory(**client_kwargs)
    except Exception as e:
        print(f"Error initializing Supermemory client: {e}")
        print("Note: base_url and workspace_id are optional - only api_key is required.")
        return 1
    
    # Generate doc_id if not provided
    doc_id = args.doc_id or generate_doc_id(args.pdf_path)
    
    # Load manifest
    manifest_path = Path('output/supermemory_manifest.json')
    manifest = load_manifest(manifest_path)
    
    # Check if we should update existing manifest or create new
    if not args.overwrite and manifest.get('doc_id') == doc_id:
        existing_pages = {p['page'] for p in manifest.get('pages', []) if 'page' in p and 'error' not in p}
    else:
        existing_pages = set()
        manifest['doc_id'] = doc_id
        manifest['pdf_path'] = args.pdf_path
    
    # Find all page JSON files
    pages_dir = Path(args.pages_dir)
    if not pages_dir.exists():
        print(f"Error: Pages directory not found: {pages_dir}")
        return 1
    
    page_files = sorted(glob(str(pages_dir / 'page_*.json')))
    if not page_files:
        print(f"Warning: No page_*.json files found in {pages_dir}")
        return 0
    
    print(f"Found {len(page_files)} page JSON files")
    print(f"Document ID: {doc_id}")
    print(f"PDF path: {args.pdf_path}")
    
    # Process each page
    pages = manifest.get('pages', []) if not args.overwrite else []
    successful = 0
    failed = 0
    
    for file_path in page_files:
        # Extract page number from filename
        match = re.search(r'page_(\d+)\.json', file_path)
        if not match:
            print(f"Warning: Could not extract page number from {file_path}")
            continue
        
        page_number = int(match.group(1))
        
        # Skip if already ingested (unless overwrite)
        if not args.overwrite and page_number in existing_pages:
            print(f"  Page {page_number}: Skipping (already ingested)")
            continue
        
        print(f"  Page {page_number}: Ingesting...", end=' ', flush=True)
        
        # Ingest page
        success, memory_id, error = ingest_page_to_supermemory(
            client, file_path, doc_id, page_number, args.pdf_path
        )
        
        if success:
            print(f"✓ (Memory ID: {memory_id})")
            # Update or add page entry
            page_entry = {'page': page_number, 'file': file_path, 'memory_id': memory_id}
            # Remove old entry if exists
            pages = [p for p in pages if p.get('page') != page_number]
            pages.append(page_entry)
            successful += 1
        else:
            print(f"✗ Error: {error}")
            page_entry = {'page': page_number, 'file': file_path, 'error': error}
            # Remove old entry if exists
            pages = [p for p in pages if p.get('page') != page_number]
            pages.append(page_entry)
            failed += 1
    
    # Save manifest
    save_manifest(manifest_path, doc_id, args.pdf_path, pages)
    print(f"\nManifest saved to: {manifest_path}")
    print(f"Summary: {successful} successful, {failed} failed")
    
    # Run smoke test if we have any successfully ingested pages
    # This verifies that memories are searchable (even if they were ingested previously)
    total_pages = len([p for p in pages if 'error' not in p and 'memory_id' in p])
    if total_pages > 0:
        print(f"\nRunning smoke test on {total_pages} ingested pages...")
        smoke_test(client, args.smoke_test_query)
    else:
        print("\nSkipping smoke test (no successfully ingested pages found)")
    
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    exit(main())

