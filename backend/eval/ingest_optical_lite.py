"""CLI entrypoint for optical-lite ingestion."""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.optical_lite_ingest import ingest_optical_lite
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest pages using optical-lite mode")
    parser.add_argument("--doc_id", type=str, required=True, help="Document ID")
    parser.add_argument("--pages_dir", type=str, required=True, help="Directory containing page_###.json files")
    parser.add_argument("--images_dir", type=str, required=True, help="Directory containing page_###.png files")
    parser.add_argument("--pdf_path", type=str, help="Path to original PDF file")
    parser.add_argument("--corpus_id", type=str, help="Corpus ID")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing ingested pages")
    parser.add_argument("--render_config_json", type=str, help="Render configuration as JSON string")
    
    args = parser.parse_args()
    
    # Parse render_config if provided
    render_config = None
    if args.render_config_json:
        try:
            render_config = json.loads(args.render_config_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse render_config_json: {e}")
            return 1
    
    # Validate paths
    pages_dir = Path(args.pages_dir)
    images_dir = Path(args.images_dir)
    
    if not pages_dir.exists():
        logger.error(f"Pages directory not found: {pages_dir}")
        return 1
    
    if not images_dir.exists():
        logger.error(f"Images directory not found: {images_dir}")
        return 1
    
    pdf_path = Path(args.pdf_path) if args.pdf_path else None
    if pdf_path and not pdf_path.exists():
        logger.warning(f"PDF path not found: {pdf_path}, continuing without it")
        pdf_path = None
    
    # Run ingestion
    try:
        logger.info(f"Starting optical-lite ingestion for doc_id={args.doc_id}")
        manifest = ingest_optical_lite(
            doc_id=args.doc_id,
            pages_dir=str(pages_dir),
            images_dir=str(images_dir),
            pdf_path=str(pdf_path) if pdf_path else None,
            corpus_id=args.corpus_id,
            render_config=render_config,
            overwrite=args.overwrite
        )
        
        # Print summary
        pages_ingested = len(manifest.get('pages', []))
        failed_pages = len(manifest.get('failed_pages', []))
        manifest_path = Path("output") / "optical_lite" / args.doc_id / "optical_lite_manifest.json"
        
        print(f"\n{'='*60}")
        print(f"Optical-Lite Ingestion Complete")
        print(f"{'='*60}")
        print(f"Doc ID: {args.doc_id}")
        print(f"Pages ingested: {pages_ingested}")
        print(f"Failed pages: {failed_pages}")
        print(f"Manifest saved to: {manifest_path}")
        print(f"{'='*60}\n")
        
        if failed_pages > 0:
            print("Failed pages:")
            for fp in manifest.get('failed_pages', []):
                print(f"  Page {fp.get('page', '?')}: {fp.get('error', 'Unknown error')}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

