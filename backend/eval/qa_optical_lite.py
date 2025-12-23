"""CLI entrypoint for optical-lite QA."""

import argparse
import logging
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.optical_lite_qa import answer_optical_lite
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Answer questions using optical-lite mode")
    parser.add_argument("--doc_id", type=str, required=True, help="Document ID")
    parser.add_argument("--question", type=str, required=True, help="Question to answer")
    parser.add_argument("--corpus_id", type=str, help="Corpus ID")
    parser.add_argument("--top_k", type=int, default=8, help="Number of top results to retrieve (default: 8)")
    parser.add_argument("--max_images", type=int, default=6, help="Maximum number of images to send to Gemini (default: 6)")
    
    args = parser.parse_args()
    
    # Run QA
    try:
        logger.info(f"Answering question for doc_id={args.doc_id}")
        result = answer_optical_lite(
            doc_id=args.doc_id,
            question=args.question,
            top_k=args.top_k,
            max_images=args.max_images,
            corpus_id=args.corpus_id
        )
        
        # Print results
        print(f"\n{'='*60}")
        print(f"Question: {args.question}")
        print(f"{'='*60}\n")
        print("Answer:")
        print("-" * 60)
        print(result['answer_md'])
        print("-" * 60)
        
        retrieved = result.get('retrieved', [])
        if retrieved:
            print(f"\nRetrieved pages ({len(retrieved)}):")
            for r in retrieved:
                page = r.get('page', '?')
                memory_id = r.get('supermemory_id', '?')
                image_path = r.get('image_path', '?')
                error = r.get('error', '')
                if error:
                    print(f"  Page {page}: {image_path} [ERROR: {error}]")
                else:
                    print(f"  Page {page}: {image_path} (memory_id: {memory_id})")
        else:
            print("\nNo pages retrieved.")
        
        print(f"\n{'='*60}\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"QA failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

