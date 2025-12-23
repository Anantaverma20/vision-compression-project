"""Ingest multiple PDFs into a corpus."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from glob import glob
from typing import List, Dict

from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / "backend" / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger_temp = logging.getLogger(__name__)
    logger_temp.info(f"Loaded .env from {env_path}")
else:
    # Try project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger_temp = logging.getLogger(__name__)
        logger_temp.info(f"Loaded .env from {env_path}")

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.pipeline.pdf_extract import extract_pdf_to_page_jsons
from app.pipeline.supermemory_ingest import ingest_pages_dir, ingest_page_to_supermemory
from app.config import SUPERMEMORY_API_KEY
from supermemory import Supermemory
from eval.observability import LocalTracer, set_tracer, get_tracer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_corpus_id() -> str:
    """Generate a unique corpus ID."""
    return f"corpus_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def generate_doc_id(pdf_path: Path) -> str:
    """Generate a doc_id from PDF filename."""
    stem = pdf_path.stem
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{stem}_{timestamp}"


def ingest_pdf_to_corpus(
    pdf_path: Path,
    corpus_id: str,
    corpus_dir: Path,
    dpi: int = 150,
    start_page: int = 1,
    end_page: int = None,
    overwrite: bool = False
) -> Dict:
    """
    Ingest a single PDF into a corpus.
    
    Returns:
        dict with doc_id, pages info, and supermemory_ids
    """
    logger.info(f"Processing PDF: {pdf_path}")
    
    # Generate doc_id
    doc_id = generate_doc_id(pdf_path)
    
    # Create doc directory structure
    doc_dir = corpus_dir / "docs" / doc_id
    pages_dir = doc_dir / "pages"
    images_dir = doc_dir / "images"
    
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy PDF to doc directory
    uploaded_pdf_path = doc_dir / "uploaded.pdf"
    import shutil
    shutil.copy2(pdf_path, uploaded_pdf_path)
    logger.info(f"Copied PDF to {uploaded_pdf_path}")
    
    # Extract PDF pages
    logger.info(f"Extracting pages from PDF...")
    extract_stats = extract_pdf_to_page_jsons(
        pdf_path=pdf_path,
        out_pages_dir=pages_dir,
        images_dir=images_dir,
        dpi=dpi,
        start_page=start_page,
        end_page=end_page,
        overwrite=overwrite
    )
    
    logger.info(f"Extracted {len(extract_stats['processed_pages'])} pages")
    
    # Ingest into Supermemory with corpus_id metadata
    if not SUPERMEMORY_API_KEY:
        logger.warning("SUPERMEMORY_API_KEY not found. Skipping Supermemory ingestion.")
        return {
            "doc_id": doc_id,
            "pdf_path": str(pdf_path),
            "pages": [],
            "failed_pages": extract_stats.get("failed_pages", [])
        }
    
    # Initialize Supermemory client
    from app.config import SUPERMEMORY_BASE_URL, SUPERMEMORY_WORKSPACE_ID
    client_kwargs = {'api_key': SUPERMEMORY_API_KEY}
    if SUPERMEMORY_BASE_URL:
        client_kwargs['base_url'] = SUPERMEMORY_BASE_URL
    if SUPERMEMORY_WORKSPACE_ID:
        client_kwargs['workspace_id'] = SUPERMEMORY_WORKSPACE_ID
    
    client = Supermemory(**client_kwargs)
    
    # Log ingestion start to local tracer
    tracer = get_tracer()
    if tracer:
        tracer.log_event(
            stage="ingest",
            doc_ids=[doc_id],
            pages=list(extract_stats['processed_pages']),
            payload={"pages_total": len(extract_stats['processed_pages'])}
        )
    
    # Ingest each page with corpus_id in metadata
    pages = []
    failed_pages = []
    
    for page_num in extract_stats['processed_pages']:
        page_json_path = pages_dir / f"page_{page_num:03d}.json"
        
        if not page_json_path.exists():
            failed_pages.append({"page": page_num, "error": "Page JSON not found"})
            continue
        
        # Parse page JSON to get content and metadata
        try:
            with open(page_json_path, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
        except Exception as e:
            failed_pages.append({"page": page_num, "error": f"Failed to parse JSON: {e}"})
            continue
        
        # Extract content
        content = page_data.get('markdown', '')
        if not content and 'raw_response' in page_data:
            content = page_data['raw_response']
        if not content:
            content = str(page_data)
        
        # Build metadata with corpus_id
        metadata = {
            'corpus_id': corpus_id,
            'doc_id': doc_id,
            'page': page_num,
            'summary': page_data.get('summary', ''),
            'entities': page_data.get('entities', []),
            'source_file': str(pdf_path)
        }
        
        # Ingest to Supermemory
        try:
            # Use the same retry logic as supermemory_ingest
            from app.pipeline.supermemory_ingest import _ingest_page_with_retry
            memory_id = _ingest_page_with_retry(client, content, metadata)
            
            pages.append({
                'page': page_num,
                'file': str(page_json_path),
                'memory_id': memory_id
            })
        except Exception as e:
            failed_pages.append({"page": page_num, "error": str(e)})
            logger.warning(f"Failed to ingest page {page_num}: {e}")
    
    logger.info(f"Ingested {len(pages)} pages into Supermemory")
    
    # Log ingestion completion
    if tracer:
        tracer.log_event(
            stage="ingest",
            doc_ids=[doc_id],
            pages=[p['page'] for p in pages],
            payload={"pages_ingested": len(pages), "failed": len(failed_pages)}
        )
    
    return {
        "doc_id": doc_id,
        "pdf_path": str(pdf_path),
        "pages": pages,
        "failed_pages": failed_pages
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest multiple PDFs into a corpus")
    parser.add_argument("--corpus_id", type=str, help="Corpus ID (auto-generated if not provided)")
    parser.add_argument("--pdfs", type=str, nargs="+", required=True, help="PDF file paths (supports glob)")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for image conversion")
    parser.add_argument("--start_page", type=int, default=1, help="Start page (1-indexed)")
    parser.add_argument("--end_page", type=int, help="End page (1-indexed, None for all)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    parser.add_argument("--run_id", type=str, help="Run ID for tracing (auto-generated if not provided)")
    parser.add_argument("--trace", action="store_true", default=True, help="Enable tracing (default: True)")
    parser.add_argument("--no-trace", dest="trace", action="store_false", help="Disable tracing")
    
    args = parser.parse_args()
    
    # Expand glob patterns
    pdf_paths = []
    for pattern in args.pdfs:
        matched = glob(pattern)
        if matched:
            pdf_paths.extend([Path(p) for p in matched])
        else:
            # Try as direct path
            p = Path(pattern)
            if p.exists():
                pdf_paths.append(p)
            else:
                logger.warning(f"PDF not found: {pattern}")
    
    if not pdf_paths:
        logger.error("No PDF files found")
        return 1
    
    # Generate or use corpus_id
    corpus_id = args.corpus_id or generate_corpus_id()
    logger.info(f"Using corpus_id: {corpus_id}")
    
    # Create corpus directory
    project_root = Path(__file__).parent.parent
    corpus_dir = project_root / "output" / "corpora" / corpus_id
    corpus_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize tracer
    tracer = None
    if args.trace:
        tracer = LocalTracer(
            corpus_id=corpus_id,
            run_id=args.run_id,
            output_dir=corpus_dir,
            enabled=True
        )
        set_tracer(tracer)
        logger.info(f"Tracing enabled: run_id={tracer.run_id}")
    
    # Process each PDF
    docs = []
    for pdf_path in pdf_paths:
        try:
            doc_info = ingest_pdf_to_corpus(
                pdf_path=pdf_path,
                corpus_id=corpus_id,
                corpus_dir=corpus_dir,
                dpi=args.dpi,
                start_page=args.start_page,
                end_page=args.end_page,
                overwrite=args.overwrite
            )
            docs.append(doc_info)
        except Exception as e:
            logger.error(f"Failed to ingest {pdf_path}: {e}", exc_info=True)
            docs.append({
                "doc_id": generate_doc_id(pdf_path),
                "pdf_path": str(pdf_path),
                "pages": [],
                "failed_pages": [{"error": str(e)}]
            })
    
    # Create corpus manifest
    manifest = {
        "corpus_id": corpus_id,
        "created_at": datetime.now().isoformat(),
        "docs": docs,
        "total_pages": sum(len(doc.get("pages", [])) for doc in docs)
    }
    
    manifest_path = corpus_dir / "corpus_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Corpus manifest saved to {manifest_path}")
    logger.info(f"Corpus {corpus_id} created with {len(docs)} documents, {manifest['total_pages']} total pages")
    
    # Close tracer
    if tracer:
        tracer.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

