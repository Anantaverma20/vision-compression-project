"""Integration module to run evaluations from backend."""

import json
import logging
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Path to eval module (eval is now in backend/eval)
BACKEND_ROOT = Path(__file__).parent.parent  # backend/
EVAL_MODULE_PATH = BACKEND_ROOT / "eval"
PROJECT_ROOT = BACKEND_ROOT  # For compatibility, use backend as project root in container


def run_eval_async(
    corpus_id: str,
    questions_path: Optional[Path] = None,
    mode: str = "text_rag",
    top_k: int = 8,
    judge_mode: str = "rule",
    run_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run evaluation asynchronously (non-blocking).
    
    Args:
        corpus_id: Corpus ID to evaluate
        questions_path: Path to questions JSON (default: eval/datasets/sample_questions.json)
        mode: Evaluation mode (text_rag, optical, hybrid, all)
        top_k: Number of results to retrieve
        judge_mode: Judge type (rule or llm)
        run_id: Optional run ID for tracing
        
    Returns:
        dict with status and run_id
    """
    if not EVAL_MODULE_PATH.exists():
        logger.warning(f"Eval module not found at {EVAL_MODULE_PATH}")
        return {
            "status": "error",
            "error": "Eval module not found",
            "run_id": None
        }
    
    # Default questions path
    if questions_path is None:
        questions_path = EVAL_MODULE_PATH / "datasets" / "sample_questions.json"
    
    if not questions_path.exists():
        logger.warning(f"Questions file not found: {questions_path}")
        return {
            "status": "error",
            "error": f"Questions file not found: {questions_path}",
            "run_id": None
        }
    
    # Build command - run from backend directory
    cmd = [
        sys.executable,
        "-m", "eval.run_eval",
        "--corpus_id", corpus_id,
        "--questions", str(questions_path.relative_to(BACKEND_ROOT)),
        "--mode", mode,
        "--top_k", str(top_k),
        "--judge", judge_mode,
    ]
    
    if run_id:
        cmd.extend(["--run_id", run_id])
    
    logger.info(f"Starting eval for corpus {corpus_id} with command: {' '.join(cmd)}")
    logger.info(f"Eval module path: {EVAL_MODULE_PATH}")
    logger.info(f"Working directory will be: {BACKEND_ROOT}")
    
    # Run in background thread
    def _run():
        try:
            result = subprocess.run(
                cmd,
                cwd=str(BACKEND_ROOT),  # Run from backend directory
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            if result.returncode == 0:
                logger.info(f"Eval completed successfully for corpus {corpus_id}")
            else:
                logger.error(f"Eval failed for corpus {corpus_id}: {result.stderr}")
        except Exception as e:
            logger.error(f"Eval error for corpus {corpus_id}: {e}", exc_info=True)
    
    # Start in background thread
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(_run)
    
    return {
        "status": "started",
        "run_id": run_id,
        "corpus_id": corpus_id
    }


def get_eval_results(corpus_id: str, run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get evaluation results for a corpus.
    
    Args:
        corpus_id: Corpus ID
        run_id: Optional run ID (if None, gets latest)
        
    Returns:
        dict with results or None if not found
    """
    results_dir = BACKEND_ROOT / "output" / "corpora" / corpus_id / "results"
    
    if not results_dir.exists():
        return None
    
    # Try to load results.json
    results_json = results_dir / "results.json"
    if not results_json.exists():
        return None
    
    try:
        with open(results_json, 'r', encoding='utf-8') as f:
            results_data = json.load(f)
        
        # Handle both old format (list) and new format (dict with metadata)
        if isinstance(results_data, list):
            # Old format: just a list of results
            results = results_data
            metadata = {}
        elif isinstance(results_data, dict) and "results" in results_data:
            # New format: dict with metadata and results
            results = results_data["results"]
            metadata = {
                "corpus_id": results_data.get("corpus_id"),
                "run_timestamp": results_data.get("run_timestamp"),
                "questions_source": results_data.get("questions_source"),
                "total_questions": results_data.get("total_questions"),
                "modes_evaluated": results_data.get("modes_evaluated"),
                "config": results_data.get("config", {})
            }
        else:
            # Fallback: treat as old format
            results = results_data if isinstance(results_data, list) else []
            metadata = {}
        
        # Load summary if available
        summary_md = results_dir / "summary.md"
        summary = None
        if summary_md.exists():
            with open(summary_md, 'r', encoding='utf-8') as f:
                summary = f.read()
        
        return {
            "results": results,
            "summary": summary,
            "metadata": metadata,
            "results_path": str(results_json),
            "summary_path": str(summary_md) if summary_md.exists() else None
        }
    except Exception as e:
        logger.error(f"Failed to load eval results: {e}", exc_info=True)
        return None

