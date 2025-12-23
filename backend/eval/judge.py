"""Judge for evaluating answers - supports rule-based and LLM judge modes."""

import json
import logging
import re
from typing import Dict, Optional, Set

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.config import GEMINI_MODEL, GCP_PROJECT_ID
from app.pipeline.utils import retry, safe_json_loads
from app.llm.vertex_gemini import VertexGeminiClient

logger = logging.getLogger(__name__)


def extract_keywords(text: str) -> Set[str]:
    """Extract meaningful keywords from text (simple approach)."""
    if not text:
        return set()
    
    # Remove citations and special chars
    text = re.sub(r'\([^)]+\)', '', text)  # Remove citations
    text = re.sub(r'[^\w\s]', ' ', text)  # Keep only words and spaces
    
    # Split and filter
    words = text.lower().split()
    # Filter out common stop words and short words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'we', 'you', 'he', 'she', 'not', 'no', 'yes'}
    
    keywords = {w for w in words if len(w) > 3 and w not in stop_words}
    return keywords


def compute_groundedness_proxy(answer: str, evidence: str) -> float:
    """Compute a proxy for groundedness based on keyword overlap."""
    if not answer or not evidence:
        return 0.0
    
    answer_keywords = extract_keywords(answer)
    evidence_keywords = extract_keywords(evidence)
    
    if not answer_keywords:
        return 0.0
    
    overlap = len(answer_keywords & evidence_keywords)
    coverage = overlap / len(answer_keywords) if answer_keywords else 0.0
    
    return min(1.0, coverage)


def check_citations(answer: str) -> Dict[str, float]:
    """Check citation quality using regex patterns."""
    # Pattern: (doc_id p.1) or (doc_id p.1, p.2)
    citation_pattern = r'\([^)]+\s+p\.\d+(?:\s*,\s*p\.\d+)*\)'
    
    citations = re.findall(citation_pattern, answer, re.IGNORECASE)
    has_citations = len(citations) > 0
    
    # Count sentences
    sentences = re.split(r'[.!?]+', answer)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    sentences_with_citations = sum(
        1 for s in sentences 
        if re.search(citation_pattern, s, re.IGNORECASE)
    )
    
    citation_coverage = (
        sentences_with_citations / len(sentences) 
        if sentences else 0.0
    )
    
    # Citation correctness: assume correct if format matches
    citation_correctness = 1.0 if has_citations else 0.0
    
    return {
        "has_citations": has_citations,
        "citation_coverage": citation_coverage,
        "citation_correctness": citation_correctness,
        "citation_count": len(citations)
    }


def check_not_found_correctness(
    answer: str,
    retrieved_count: int,
    evidence: Optional[str] = None
) -> float:
    """Check if 'Not found' answer is correct given retrieval results."""
    answer_lower = answer.lower()
    is_not_found = "not found" in answer_lower or "not in" in answer_lower
    
    if retrieved_count == 0:
        # Correct to say "not found" when nothing retrieved
        return 1.0 if is_not_found else 0.0
    else:
        # Should not say "not found" when we have evidence
        return 0.0 if is_not_found else 1.0


def compute_length_penalty(answer: str) -> float:
    """Penalize overly verbose or too short answers."""
    word_count = len(answer.split())
    
    # Ideal range: 20-200 words
    if 20 <= word_count <= 200:
        return 1.0
    elif word_count < 10:
        return 0.5  # Too short
    elif word_count > 500:
        return 0.7  # Too verbose
    else:
        return 0.9  # Slightly off


def judge_answer_rule(
    question: str,
    answer: str,
    evidence_pack: Optional[str] = None,
    retrieved_count: int = 0
) -> Dict[str, any]:
    """
    Rule-based judge using deterministic checks.
    
    Returns:
        dict with keys: score (0-1), rationale, citation_correctness, coverage
    """
    # Compute components
    groundedness_proxy = compute_groundedness_proxy(answer, evidence_pack or "")
    citation_metrics = check_citations(answer)
    not_found_score = check_not_found_correctness(answer, retrieved_count, evidence_pack)
    length_penalty = compute_length_penalty(answer)
    
    # Weighted score
    # 0.45 * groundedness + 0.35 * citation_quality + 0.20 * completeness
    citation_quality = (
        0.6 * citation_metrics["citation_correctness"] +
        0.4 * citation_metrics["citation_coverage"]
    )
    
    completeness_proxy = (
        0.7 * not_found_score +
        0.3 * length_penalty
    )
    
    score = (
        0.45 * groundedness_proxy +
        0.35 * citation_quality +
        0.20 * completeness_proxy
    )
    
    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    
    rationale = (
        f"Rule-based score: groundedness={groundedness_proxy:.2f}, "
        f"citation_quality={citation_quality:.2f}, "
        f"completeness={completeness_proxy:.2f}"
    )
    
    return {
        "score": score,
        "rationale": rationale,
        "citation_correctness": citation_metrics["citation_correctness"],
        "coverage": completeness_proxy,
        "is_grounded": groundedness_proxy > 0.5
    }


def judge_answer_llm(
    question: str,
    answer: str,
    evidence_pack: Optional[str] = None,
    expected_answer: Optional[str] = None,
    model: str = None
) -> Dict[str, any]:
    """
    LLM-based judge using Gemini via Vertex AI.
    
    Returns:
        dict with keys: score (0-1), rationale, citation_correctness, coverage
    """
    if model is None:
        model = GEMINI_MODEL
    
    if not GCP_PROJECT_ID:
        logger.warning("GCP_PROJECT_ID not found. Falling back to rule-based judge.")
        return judge_answer_rule(question, answer, evidence_pack, 0)
    
    # Build judge prompt
    if expected_answer:
        judge_prompt = f"""You are an expert evaluator judging the quality of an answer to a question.

Question: {question}

Expected Answer (if available): {expected_answer}

Generated Answer:
{answer}

Evidence Used (if available):
{evidence_pack or "Not provided"}

Evaluate the answer on these criteria:
1. Correctness: Does the answer correctly address the question?
2. Citation Quality: Are citations present and correctly formatted (doc_id p.#)?
3. Coverage: Does the answer cover the key points from the evidence?
4. Completeness: Is the answer complete and well-structured?

Return a JSON object with:
- score: float between 0.0 and 1.0 (1.0 = perfect, 0.5 = partial, 0.0 = wrong/unsupported)
- rationale: brief explanation of the score
- citation_correctness: float 0-1 (1.0 = all claims cited correctly, 0.0 = no citations or incorrect)
- coverage: float 0-1 (1.0 = covers all key points, 0.0 = misses key information)
- is_grounded: boolean (true if answer is grounded in evidence)

Scoring rubric:
- 1.0: Correct answer, well-cited, complete, covers all key points
- 0.5: Partially correct or missing citations or incomplete
- 0.0: Wrong answer or unsupported claims

Return ONLY valid JSON, no markdown fences."""
    else:
        judge_prompt = f"""You are an expert evaluator judging the quality of an answer to a question.

Question: {question}

Generated Answer:
{answer}

Evidence Used (if available):
{evidence_pack or "Not provided"}

Evaluate the answer on these criteria:
1. Groundedness: Is the answer grounded in the provided evidence?
2. Citation Quality: Are citations present and correctly formatted (doc_id p.#)?
3. Coverage: Does the answer cover the key points from the evidence?
4. Completeness: Is the answer complete and well-structured?

Return a JSON object with:
- score: float between 0.0 and 1.0 (1.0 = perfect, 0.5 = partial, 0.0 = wrong/unsupported)
- rationale: brief explanation of the score
- citation_correctness: float 0-1 (1.0 = all claims cited correctly, 0.0 = no citations or incorrect)
- coverage: float 0-1 (1.0 = covers all key points, 0.0 = misses key information)
- is_grounded: boolean (true if answer is grounded in evidence)

Scoring rubric:
- 1.0: Well-grounded answer, well-cited, complete, covers all key points
- 0.5: Partially grounded or missing citations or incomplete
- 0.0: Not grounded in evidence or unsupported claims

Return ONLY valid JSON, no markdown fences."""
    
    def _call():
        client = VertexGeminiClient(model_name=model)
        try:
            return client.generate_content(
                contents=judge_prompt,
                temperature=0.0,  # Deterministic judging
                max_output_tokens=1024,
            )
        except Exception as e:
            # Handle cases where response might fail (e.g., safety filters)
            if "finish_reason" in str(e) or "safety" in str(e).lower():
                logger.warning(f"Judge response blocked by safety filter: {e}")
                return json.dumps({
                    "score": 0.5,
                    "rationale": "Judge response blocked by safety filter",
                    "citation_correctness": 0.5,
                    "coverage": 0.5,
                    "is_grounded": False
                })
            raise
    
    try:
        response_text = retry(_call, attempts=3)
        
        # Parse JSON response
        result = safe_json_loads(response_text)
        
        if result is None:
            logger.warning("Failed to parse judge response as JSON. Falling back to rule-based.")
            return judge_answer_rule(question, answer, evidence_pack, 0)
        
        # Ensure all required fields exist
        score = float(result.get("score", 0.5))
        score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
        
        citation_correctness = float(result.get("citation_correctness", 0.5))
        citation_correctness = max(0.0, min(1.0, citation_correctness))
        
        coverage = float(result.get("coverage", 0.5))
        coverage = max(0.0, min(1.0, coverage))
        
        is_grounded = result.get("is_grounded", False)
        if isinstance(is_grounded, str):
            is_grounded = is_grounded.lower() in ('true', 'yes', '1')
        
        return {
            "score": score,
            "rationale": result.get("rationale", "No rationale provided"),
            "citation_correctness": citation_correctness,
            "coverage": coverage,
            "is_grounded": is_grounded
        }
    except Exception as e:
        logger.error(f"LLM judge evaluation failed: {e}, falling back to rule-based", exc_info=True)
        return judge_answer_rule(question, answer, evidence_pack, 0)


def judge_answer(
    question: str,
    answer: str,
    evidence_pack: Optional[str] = None,
    expected_answer: Optional[str] = None,
    model: str = None,
    judge_mode: str = "rule",
    retrieved_count: int = 0
) -> Dict[str, any]:
    """
    Judge an answer using rule-based or LLM judge.
    
    Args:
        question: The question asked
        answer: The generated answer
        evidence_pack: The evidence used (optional)
        expected_answer: Expected answer if available (optional)
        model: Gemini model to use for LLM judge (default: GEMINI_MODEL)
        judge_mode: "rule" or "llm" (default: "rule")
        retrieved_count: Number of retrieved pages (for rule-based judge)
        
    Returns:
        dict with keys: score (0-1), rationale, citation_correctness, coverage, is_grounded
    """
    if judge_mode == "llm":
        return judge_answer_llm(question, answer, evidence_pack, expected_answer, model)
    else:
        return judge_answer_rule(question, answer, evidence_pack, retrieved_count)
