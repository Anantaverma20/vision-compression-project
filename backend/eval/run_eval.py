"""Run evaluation comparing different RAG modes."""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
# Now that eval is in backend/eval, .env is at backend/.env
backend_root = Path(__file__).parent.parent  # backend/
env_path = backend_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger_temp = logging.getLogger(__name__)
    logger_temp.info(f"Loaded .env from {env_path}")
else:
    # Try current directory as fallback
    load_dotenv()

# Add backend to path for imports (backend is already the parent, so add it)
sys.path.insert(0, str(backend_root))

from eval.modes.text_rag import run_text_rag
from eval.modes.optical import run_optical
from eval.modes.hybrid import run_hybrid
from eval.judge import judge_answer
from eval.metrics import compute_all_metrics
from eval.observability import LocalTracer, set_tracer, get_tracer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_questions(questions_path: Path) -> List[Dict]:
    """Load questions from JSON file."""
    if not questions_path.exists():
        logger.error(f"Questions file not found: {questions_path}")
        return []
    
    with open(questions_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Support both list and dict formats
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and 'questions' in data:
        return data['questions']
    else:
        logger.error("Invalid questions file format. Expected list or dict with 'questions' key.")
        return []


def run_mode(
    mode: str,
    corpus_id: str,
    question: Dict,
    corpus_dir: Path,
    manifest_path: Path,
    top_k: int,
    max_chars_per_page: int,
    max_images: int,
    model: str = None,
    use_proxy_optical: bool = True,
    judge_mode: str = "rule"
) -> Dict:
    """
    Run a single mode for a question.
    
    Returns:
        dict with answer, retrieved, metrics, etc.
    """
    q_text = question.get("question", "")
    q_id = question.get("id", "")
    expected_answer = question.get("expected_answer")
    doc_hint = question.get("doc_hint")
    
    logger.info(f"Running {mode} mode for question {q_id}")
    
    tracer = get_tracer()
    
    start_time = time.time()
    
    try:
        # Log retrieval start
        if tracer:
            tracer.log_event(
                stage="retrieve",
                mode=mode,
                question_id=q_id,
                payload={"query": q_text, "top_k": top_k}
            )
        
        if mode == "text_rag":
            result = run_text_rag(
                corpus_id=corpus_id,
                question=q_text,
                top_k=top_k,
                max_chars_per_page=max_chars_per_page,
                doc_id=doc_hint,
                model=model,
                manifest_path=manifest_path
            )
        elif mode == "optical":
            result = run_optical(
                corpus_id=corpus_id,
                question=q_text,
                corpus_dir=corpus_dir,
                top_k=top_k,
                max_images=max_images,
                doc_id=doc_hint,
                model=model,
                manifest_path=manifest_path,
                use_proxy=use_proxy_optical
            )
        elif mode == "hybrid":
            result = run_hybrid(
                corpus_id=corpus_id,
                question=q_text,
                corpus_dir=corpus_dir,
                top_k=top_k,
                max_images=max_images,
                doc_id=doc_hint,
                model=model,
                manifest_path=manifest_path,
                use_proxy=use_proxy_optical
            )
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        retrieval_latency = time.time() - start_time
        
        # Log retrieval completion
        if tracer:
            doc_ids = list(set(r.get("doc_id", "") for r in result["retrieved"]))
            pages = [r.get("page", 0) for r in result["retrieved"] if r.get("page")]
            tracer.log_event(
                stage="retrieve",
                mode=mode,
                question_id=q_id,
                doc_ids=doc_ids,
                pages=pages,
                latency_ms=retrieval_latency * 1000,
                payload={"result_count": len(result["retrieved"])}
            )
            
            # Save retrieval artifact
            if result["retrieved"]:
                tracer.save_artifact(
                    mode=mode,
                    question_id=q_id,
                    artifact_type="retrieval",
                    content=json.dumps(result["retrieved"], indent=2),
                    metadata={"count": len(result["retrieved"])}
                )
        
        # Log generation start
        gen_start_time = time.time()
        if tracer:
            tracer.log_event(
                stage="generate",
                mode=mode,
                question_id=q_id,
                payload={"has_evidence": bool(result.get("evidence_pack"))}
            )
        
        # Compute metrics
        metrics = compute_all_metrics(
            mode=mode,
            question=q_text,
            answer=result["answer_md"],
            retrieved=result["retrieved"],
            latency=retrieval_latency,
            evidence_pack=result.get("evidence_pack", "")
        )
        
        generation_latency = time.time() - gen_start_time
        
        # Save artifacts
        if tracer:
            if result.get("evidence_pack"):
                tracer.save_artifact(
                    mode=mode,
                    question_id=q_id,
                    artifact_type="evidence",
                    content=result["evidence_pack"]
                )
            
            # Save answer
            tracer.save_artifact(
                mode=mode,
                question_id=q_id,
                artifact_type="answer",
                content=result["answer_md"]
            )
        
        # Log generation completion
        if tracer:
            tracer.log_event(
                stage="generate",
                mode=mode,
                question_id=q_id,
                latency_ms=generation_latency * 1000,
                payload={"answer_length": len(result["answer_md"])}
            )
        
        # Judge answer
        judge_start_time = time.time()
        if tracer:
            tracer.log_event(
                stage="judge",
                mode=mode,
                question_id=q_id,
                payload={"judge_mode": judge_mode}
            )
        
        judge_result = judge_answer(
            question=q_text,
            answer=result["answer_md"],
            evidence_pack=result.get("evidence_pack"),
            expected_answer=expected_answer,
            model=model,
            judge_mode=judge_mode,
            retrieved_count=len(result["retrieved"])
        )
        
        judge_latency = time.time() - judge_start_time
        
        # Save judge artifact
        if tracer:
            tracer.save_artifact(
                mode=mode,
                question_id=q_id,
                artifact_type="judge",
                content=json.dumps(judge_result, indent=2),
                metadata={"judge_mode": judge_mode}
            )
            
            tracer.log_event(
                stage="judge",
                mode=mode,
                question_id=q_id,
                latency_ms=judge_latency * 1000,
                payload={"score": judge_result["score"]}
            )
        
        total_latency = time.time() - start_time
        
        return {
            "mode": mode,
            "question_id": q_id,
            "question": q_text,
            "answer": result["answer_md"],
            "retrieved": result["retrieved"],
            "metrics": metrics,
            "judge": judge_result,
            "latency": total_latency,
            "success": True
        }
    except Exception as e:
        logger.error(f"Error running {mode} mode: {e}", exc_info=True)
        if tracer:
            tracer.log_event(
                stage="error",
                mode=mode,
                question_id=q_id,
                payload={"error": str(e)}
            )
        return {
            "mode": mode,
            "question_id": q_id,
            "question": q_text,
            "answer": "",
            "retrieved": [],
            "metrics": {},
            "judge": {"score": 0.0, "rationale": f"Error: {str(e)}", "citation_correctness": 0.0, "coverage": 0.0},
            "latency": time.time() - start_time,
            "success": False,
            "error": str(e)
        }


def generate_summary_md(all_results: List[Dict], modes_to_run: List[str], corpus_id: str) -> str:
    """Generate a markdown summary of evaluation results."""
    from datetime import datetime
    
    timestamp = datetime.now().isoformat()
    lines = [f"# Evaluation Summary: {corpus_id}\n"]
    lines.append(f"**Evaluation Run Time**: {timestamp}\n")
    lines.append(f"**Total Questions Evaluated**: {len(set(r['question_id'] for r in all_results))}\n")
    lines.append(f"**Modes Evaluated**: {', '.join(modes_to_run)}\n")
    
    # Overall stats
    lines.append("## Overall Statistics\n")
    lines.append("> **Note**: These statistics aggregate performance across all questions for each mode.\n")
    
    for mode in modes_to_run:
        mode_results = [r for r in all_results if r["mode"] == mode]
        if not mode_results:
            continue
        
        avg_score = sum(r["judge"]["score"] for r in mode_results) / len(mode_results)
        avg_latency = sum(r["latency"] for r in mode_results) / len(mode_results)
        avg_context_units = sum(r["metrics"].get("estimated_context_units", 0) for r in mode_results) / len(mode_results)
        avg_citation_coverage = sum(r["metrics"].get("citation_coverage", 0) for r in mode_results) / len(mode_results)
        success_count = sum(1 for r in mode_results if r["success"])
        
        # Mode description
        mode_descriptions = {
            "text_rag": "Text-based RAG: Retrieves markdown content from Supermemory, builds evidence pack, generates answer with Gemini.",
            "optical": "Optical mode: Retrieves page images, uses images directly as context for Gemini.",
            "hybrid": "Hybrid mode: Combines text and optical approaches."
        }
        mode_desc = mode_descriptions.get(mode, "Unknown mode")
        
        lines.append(f"### {mode.upper()}")
        lines.append(f"*{mode_desc}*\n")
        lines.append(f"- **Average Score** (0-1): {avg_score:.3f}")
        lines.append(f"  - Higher is better. Based on groundedness (45%), citation quality (35%), and completeness (20%)")
        lines.append(f"- **Average Latency**: {avg_latency:.2f}s")
        lines.append(f"  - Time to retrieve and generate answer")
        lines.append(f"- **Average Context Units**: {avg_context_units:.0f}")
        lines.append(f"  - For text_rag: characters in evidence pack. For optical/hybrid: number of pages/images")
        lines.append(f"- **Average Citation Coverage**: {avg_citation_coverage:.2%}")
        lines.append(f"  - Percentage of sentences in answers that include citations (format: `(doc_id p.N)`)")
        lines.append(f"- **Success Rate**: {success_count}/{len(mode_results)}")
        lines.append(f"  - Number of questions successfully answered without errors\n")
    
    # Top 3 best/worst questions
    lines.append("## Top 3 Best Questions\n")
    all_scores = [(r["question_id"], r["question"], r["judge"]["score"], r["mode"], r.get("answer", "")) for r in all_results]
    all_scores.sort(key=lambda x: x[2], reverse=True)
    
    for i, (q_id, q_text, score, mode, answer) in enumerate(all_scores[:3], 1):
        lines.append(f"{i}. **{q_id}** ({mode}): {score:.3f}")
        lines.append(f"   **Question**: {q_text}")
        if answer:
            answer_preview = answer[:200] + "..." if len(answer) > 200 else answer
            lines.append(f"   **Answer**: {answer_preview}")
        lines.append("")
    
    lines.append("## Top 3 Worst Questions\n")
    for i, (q_id, q_text, score, mode, answer) in enumerate(all_scores[-3:], 1):
        lines.append(f"{i}. **{q_id}** ({mode}): {score:.3f}")
        lines.append(f"   **Question**: {q_text}")
        if answer:
            answer_preview = answer[:200] + "..." if len(answer) > 200 else answer
            lines.append(f"   **Answer**: {answer_preview}")
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run evaluation comparing RAG modes")
    parser.add_argument("--corpus_id", type=str, required=True, help="Corpus ID")
    parser.add_argument("--questions", type=str, default="eval/datasets/sample_questions.json", help="Path to questions JSON (relative to backend directory)")
    parser.add_argument("--mode", type=str, choices=["text_rag", "optical", "hybrid", "all"], default="all", help="Mode to evaluate")
    parser.add_argument("--top_k", type=int, default=8, help="Number of results to retrieve")
    parser.add_argument("--max_chars_per_page", type=int, default=1500, help="Max chars per page in evidence pack")
    parser.add_argument("--max_images", type=int, default=6, help="Max images for optical/hybrid modes")
    parser.add_argument("--judge", type=str, choices=["rule", "llm"], default="rule", help="Judge type: rule (default) or llm")
    parser.add_argument("--use_proxy_optical", action="store_true", help="Use proxy optical mode (summaries instead of images)")
    parser.add_argument("--run_id", type=str, help="Run ID (auto-generated if not provided)")
    parser.add_argument("--trace", action="store_true", default=True, help="Enable tracing (default: True)")
    parser.add_argument("--no-trace", dest="trace", action="store_false", help="Disable tracing")
    
    args = parser.parse_args()
    
    # Setup paths
    project_root = Path(__file__).parent.parent
    corpus_dir = project_root / "output" / "corpora" / args.corpus_id
    manifest_path = corpus_dir / "corpus_manifest.json"
    questions_path = project_root / args.questions
    
    if not corpus_dir.exists():
        logger.error(f"Corpus directory not found: {corpus_dir}")
        return 1
    
    if not manifest_path.exists():
        logger.error(f"Corpus manifest not found: {manifest_path}")
        return 1
    
    # Load questions
    questions = load_questions(questions_path)
    if not questions:
        logger.error("No questions loaded")
        return 1
    
    logger.info(f"Loaded {len(questions)} questions")
    
    # Initialize tracer
    tracer = None
    if args.trace:
        tracer = LocalTracer(
            corpus_id=args.corpus_id,
            run_id=args.run_id,
            output_dir=corpus_dir,
            enabled=True
        )
        set_tracer(tracer)
        logger.info(f"Tracing enabled: run_id={tracer.run_id}")
    
    # Determine modes to run
    modes_to_run = []
    if args.mode == "all":
        modes_to_run = ["text_rag", "optical", "hybrid"]
    else:
        modes_to_run = [args.mode]
    
    # Run evaluation
    all_results = []
    
    for question in questions:
        q_id = question.get("id", "")
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing question: {q_id}")
        logger.info(f"{'='*60}")
        
        for mode in modes_to_run:
            # Run mode
            result = run_mode(
                mode=mode,
                corpus_id=args.corpus_id,
                question=question,
                corpus_dir=corpus_dir,
                manifest_path=manifest_path,
                top_k=args.top_k,
                max_chars_per_page=args.max_chars_per_page,
                max_images=args.max_images,
                use_proxy_optical=args.use_proxy_optical,
                judge_mode=args.judge
            )
            
            all_results.append(result)
            
            # Log result summary
            logger.info(f"{mode}: score={result['judge']['score']:.2f}, "
                       f"latency={result['latency']:.2f}s, "
                       f"context_units={result['metrics'].get('estimated_context_units', 0)}")
    
    # Save results
    results_dir = corpus_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Save JSON with metadata
    results_data = {
        "corpus_id": args.corpus_id,
        "run_timestamp": datetime.now().isoformat(),
        "questions_source": str(questions_path.relative_to(project_root)),
        "total_questions": len(questions),
        "modes_evaluated": modes_to_run,
        "config": {
            "top_k": args.top_k,
            "max_chars_per_page": args.max_chars_per_page,
            "max_images": args.max_images,
            "judge_mode": args.judge,
            "use_proxy_optical": args.use_proxy_optical
        },
        "results": all_results
    }
    
    results_json_path = results_dir / "results.json"
    with open(results_json_path, 'w', encoding='utf-8') as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)
    logger.info(f"\nResults saved to {results_json_path}")
    
    # Save CSV
    csv_rows = []
    for r in all_results:
        row = {
            "mode": r["mode"],
            "question_id": r["question_id"],
            "question": r["question"],
            "answer": r["answer"],
            "judge_score": r["judge"]["score"],
            "judge_rationale": r["judge"]["rationale"],
            "citation_correctness": r["judge"].get("citation_correctness", 0),
            "coverage": r["judge"].get("coverage", 0),
            "is_grounded": r["judge"].get("is_grounded", False),
            "has_citations": r["metrics"].get("has_citations", False),
            "citation_coverage": r["metrics"].get("citation_coverage", 0),
            "citation_count": r["metrics"].get("citation_count", 0),
            "retrieved_pages_count": r["metrics"].get("retrieved_pages_count", 0),
            "estimated_context_units": r["metrics"].get("estimated_context_units", 0),
            "latency_seconds": r["latency"],
            "success": r["success"]
        }
        csv_rows.append(row)
    
    results_csv_path = results_dir / "results.csv"
    df = pd.DataFrame(csv_rows)
    df.to_csv(results_csv_path, index=False)
    logger.info(f"Results CSV saved to {results_csv_path}")
    
    # Generate and save summary
    summary_md = generate_summary_md(all_results, modes_to_run, args.corpus_id)
    summary_path = results_dir / "summary.md"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary_md)
    logger.info(f"Summary saved to {summary_path}")
    
    # Close tracer
    if tracer:
        tracer.close()
    
    # Print summary statistics
    logger.info("\n" + "="*60)
    logger.info("EVALUATION SUMMARY")
    logger.info("="*60)
    
    for mode in modes_to_run:
        mode_results = [r for r in all_results if r["mode"] == mode]
        if not mode_results:
            continue
        
        avg_score = sum(r["judge"]["score"] for r in mode_results) / len(mode_results)
        avg_latency = sum(r["latency"] for r in mode_results) / len(mode_results)
        avg_context_units = sum(r["metrics"].get("estimated_context_units", 0) for r in mode_results) / len(mode_results)
        success_count = sum(1 for r in mode_results if r["success"])
        
        logger.info(f"\n{mode.upper()}:")
        logger.info(f"  Average Score: {avg_score:.3f}")
        logger.info(f"  Average Latency: {avg_latency:.2f}s")
        logger.info(f"  Average Context Units: {avg_context_units:.0f}")
        logger.info(f"  Success Rate: {success_count}/{len(mode_results)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
