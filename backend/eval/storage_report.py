"""CLI tool to generate storage minimization reports."""

import argparse
import json
import logging
import sys
from pathlib import Path
from glob import glob

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.optical_lite_ingest import parse_json_file
from app.pipeline.supermemory_ingest import parse_json_file as parse_json_file_text
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_directory_size(directory: Path) -> int:
    """Calculate total size of all files in a directory."""
    total_size = 0
    if directory.exists():
        for file_path in directory.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    return total_size


def format_bytes(bytes_count: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.2f} TB"


def compute_storage_stats(
    doc_id: str,
    pages_dir: Path,
    images_dir: Path,
    mode: str
) -> dict:
    """
    Compute storage statistics for a document.
    
    Args:
        doc_id: Document ID
        pages_dir: Directory containing page JSON files
        images_dir: Directory containing page images
        mode: 'text' or 'optical_lite'
        
    Returns:
        dict with storage statistics
    """
    # Calculate image directory size
    images_bytes = get_directory_size(images_dir)
    
    # Calculate pages directory size (JSON files)
    pages_bytes = get_directory_size(pages_dir)
    
    # Parse all page JSON files
    page_files = sorted(glob(str(pages_dir / 'page_*.json')))
    
    if mode == "optical_lite":
        # For optical-lite: calculate indexed chars stored
        indexed_chars = 0
        
        for page_file in page_files:
            try:
                data = parse_json_file(Path(page_file))
                
                # Count chars in summary (truncated to 400)
                summary = data.get('summary', '')
                summary_chars = min(len(summary), 400)
                
                # Count chars in title (extracted from markdown, max 120)
                markdown = data.get('markdown', '')
                title = ""
                if markdown:
                    import re
                    heading_pattern = r'^#{1,6}\s+(.+)$'
                    for line in markdown.split('\n'):
                        match = re.match(heading_pattern, line.strip())
                        if match:
                            title = match.group(1).strip()
                            break
                title_chars = min(len(title), 120)
                
                # Count chars in entities (limited to 10, each entity string)
                entities = data.get('entities', [])
                entities_chars = sum(len(str(e)) for e in entities[:10])
                
                # Index string format: "doc_id=<...> corpus_id=<...> page=<n> title=<...> summary=<...> entities=<...>"
                # Approximate: doc_id (~20) + corpus_id (~20) + page (~10) + title + summary + entities
                page_indexed_chars = 50 + title_chars + summary_chars + entities_chars
                indexed_chars += page_indexed_chars
                
            except Exception as e:
                logger.warning(f"Failed to parse {page_file}: {e}")
        
        return {
            "mode": "optical_lite",
            "doc_id": doc_id,
            "images_bytes": images_bytes,
            "pages_bytes": pages_bytes,
            "indexed_chars": indexed_chars,
            "indexed_bytes": indexed_chars,  # Approximate: 1 char = 1 byte for ASCII
            "total_storage_bytes": images_bytes + indexed_chars,  # Only images + indexed metadata
            "pages_count": len(page_files)
        }
    
    else:  # text mode
        # For text mode: calculate markdown chars stored (use page JSON markdown length as proxy)
        markdown_chars = 0
        
        for page_file in page_files:
            try:
                data = parse_json_file_text(Path(page_file))
                markdown = data.get('markdown', '')
                if not markdown and 'raw_response' in data:
                    markdown = data.get('raw_response', '')
                markdown_chars += len(markdown)
            except Exception as e:
                logger.warning(f"Failed to parse {page_file}: {e}")
        
        return {
            "mode": "text",
            "doc_id": doc_id,
            "images_bytes": images_bytes,
            "pages_bytes": pages_bytes,
            "markdown_chars": markdown_chars,
            "markdown_bytes": markdown_chars,  # Approximate: 1 char = 1 byte
            "total_storage_bytes": images_bytes + markdown_chars,  # Images + full markdown
            "pages_count": len(page_files)
        }


def generate_markdown_report(stats: dict) -> str:
    """Generate markdown report from statistics."""
    lines = []
    lines.append("# Storage Minimization Report")
    lines.append("")
    lines.append(f"**Document ID:** {stats['doc_id']}")
    lines.append(f"**Mode:** {stats['mode']}")
    lines.append(f"**Pages:** {stats['pages_count']}")
    lines.append("")
    lines.append("## Storage Breakdown")
    lines.append("")
    lines.append(f"- **Images:** {format_bytes(stats['images_bytes'])} ({stats['images_bytes']:,} bytes)")
    lines.append(f"- **Page JSON files:** {format_bytes(stats['pages_bytes'])} ({stats['pages_bytes']:,} bytes)")
    lines.append("")
    
    if stats['mode'] == 'optical_lite':
        lines.append("## Optical-Lite Storage")
        lines.append("")
        lines.append(f"- **Indexed metadata (chars):** {stats['indexed_chars']:,}")
        lines.append(f"- **Indexed metadata (bytes):** {format_bytes(stats['indexed_bytes'])} ({stats['indexed_bytes']:,} bytes)")
        lines.append("")
        lines.append(f"**Total storage (images + indexed metadata):** {format_bytes(stats['total_storage_bytes'])} ({stats['total_storage_bytes']:,} bytes)")
    else:
        lines.append("## Text Mode Storage")
        lines.append("")
        lines.append(f"- **Markdown content (chars):** {stats['markdown_chars']:,}")
        lines.append(f"- **Markdown content (bytes):** {format_bytes(stats['markdown_bytes'])} ({stats['markdown_bytes']:,} bytes)")
        lines.append("")
        lines.append(f"**Total storage (images + markdown):** {format_bytes(stats['total_storage_bytes'])} ({stats['total_storage_bytes']:,} bytes)")
    
    lines.append("")
    
    # Calculate reduction if both modes available (would need to run twice)
    if stats['mode'] == 'optical_lite':
        lines.append("> Note: To compare with text mode, run with `--mode text` and compare results.")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate storage minimization report")
    parser.add_argument("--doc_id", type=str, required=True, help="Document ID")
    parser.add_argument("--pages_dir", type=str, required=True, help="Directory containing page_###.json files")
    parser.add_argument("--images_dir", type=str, required=True, help="Directory containing page_###.png files")
    parser.add_argument("--mode", type=str, choices=["text", "optical_lite"], default="optical_lite", help="Mode: text or optical_lite (default: optical_lite)")
    
    args = parser.parse_args()
    
    # Validate paths
    pages_dir = Path(args.pages_dir)
    images_dir = Path(args.images_dir)
    
    if not pages_dir.exists():
        logger.error(f"Pages directory not found: {pages_dir}")
        return 1
    
    if not images_dir.exists():
        logger.error(f"Images directory not found: {images_dir}")
        return 1
    
    # Compute statistics
    try:
        logger.info(f"Computing storage statistics for doc_id={args.doc_id}, mode={args.mode}")
        stats = compute_storage_stats(
            doc_id=args.doc_id,
            pages_dir=pages_dir,
            images_dir=images_dir,
            mode=args.mode
        )
        
        # Create output directory
        output_dir = Path("output") / "optical_lite" / args.doc_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON report
        json_path = output_dir / "storage_report.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        # Save Markdown report
        md_path = output_dir / "storage_report.md"
        md_content = generate_markdown_report(stats)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"Storage Report Generated")
        print(f"{'='*60}")
        print(f"Doc ID: {args.doc_id}")
        print(f"Mode: {args.mode}")
        print(f"Pages: {stats['pages_count']}")
        print(f"Images: {format_bytes(stats['images_bytes'])}")
        print(f"Page JSON files: {format_bytes(stats['pages_bytes'])}")
        
        if args.mode == 'optical_lite':
            print(f"Indexed metadata: {format_bytes(stats['indexed_bytes'])} ({stats['indexed_chars']:,} chars)")
            print(f"Total storage: {format_bytes(stats['total_storage_bytes'])}")
        else:
            print(f"Markdown content: {format_bytes(stats['markdown_bytes'])} ({stats['markdown_chars']:,} chars)")
            print(f"Total storage: {format_bytes(stats['total_storage_bytes'])}")
        
        print(f"\nReports saved to:")
        print(f"  JSON: {json_path}")
        print(f"  Markdown: {md_path}")
        print(f"{'='*60}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate report: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

