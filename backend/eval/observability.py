"""Local observability and tracing system for evaluation runs."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def redact_secrets(text: str) -> str:
    """Remove API keys and secrets from text."""
    if not text:
        return text
    
    # Patterns to redact
    patterns = [
        (r'sk-[a-zA-Z0-9_-]+', 'sk-***'),
        (r'pk-[a-zA-Z0-9_-]+', 'pk-***'),
        (r'AIza[0-9A-Za-z_-]{35}', 'AIza***'),
        (r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '***'),
    ]
    
    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    
    return redacted


class LocalTracer:
    """Local tracer that writes JSONL events and artifacts."""
    
    def __init__(
        self,
        corpus_id: str,
        run_id: Optional[str] = None,
        output_dir: Optional[Path] = None,
        enabled: bool = True
    ):
        self.corpus_id = corpus_id
        self.run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        self.enabled = enabled
        
        if not enabled:
            return
        
        # Setup output directories
        if output_dir is None:
            project_root = Path(__file__).parent.parent
            output_dir = project_root / "output" / "corpora" / corpus_id
        
        self.output_dir = output_dir
        self.traces_dir = output_dir / "traces"
        self.artifacts_dir = output_dir / "results" / "artifacts" / self.run_id
        
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Open JSONL file for writing
        self.trace_file = self.traces_dir / f"{self.run_id}.jsonl"
        self.trace_fp = open(self.trace_file, 'a', encoding='utf-8')
        
        logger.info(f"Local tracer initialized: run_id={self.run_id}, trace_file={self.trace_file}")
    
    def log_event(
        self,
        stage: str,
        mode: Optional[str] = None,
        question_id: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        pages: Optional[List[int]] = None,
        latency_ms: Optional[float] = None,
        payload: Optional[Dict[str, Any]] = None
    ):
        """Log an event to JSONL trace file."""
        if not self.enabled:
            return
        
        event = {
            "ts": datetime.now().isoformat(),
            "run_id": self.run_id,
            "corpus_id": self.corpus_id,
            "stage": stage,
        }
        
        if mode:
            event["mode"] = mode
        if question_id:
            event["question_id"] = question_id
        if doc_ids:
            event["doc_ids"] = doc_ids
        if pages:
            event["pages"] = pages
        if latency_ms is not None:
            event["latency_ms"] = latency_ms
        if payload:
            # Redact secrets from payload
            redacted_payload = {}
            for k, v in payload.items():
                if isinstance(v, str):
                    redacted_payload[k] = redact_secrets(v)
                elif isinstance(v, dict):
                    redacted_payload[k] = {k2: redact_secrets(v2) if isinstance(v2, str) else v2 
                                          for k2, v2 in v.items()}
                else:
                    redacted_payload[k] = v
            event["payload"] = redacted_payload
        
        try:
            self.trace_fp.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.trace_fp.flush()
        except Exception as e:
            logger.warning(f"Failed to write trace event: {e}")
    
    def save_artifact(
        self,
        mode: str,
        question_id: str,
        artifact_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Path]:
        """Save an artifact file and return its path."""
        if not self.enabled:
            return None
        
        artifact_dir = self.artifacts_dir / mode / question_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Map artifact types to file extensions
        ext_map = {
            "retrieval": ".json",
            "evidence": ".txt",
            "prompt": ".txt",
            "answer": ".md",
            "judge": ".json"
        }
        
        ext = ext_map.get(artifact_type, ".txt")
        artifact_path = artifact_dir / f"{artifact_type}{ext}"
        
        try:
            if artifact_type == "retrieval" or artifact_type == "judge":
                # JSON format
                data = {"content": content}
                if metadata:
                    data["metadata"] = metadata
                with open(artifact_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                # Text format
                with open(artifact_path, 'w', encoding='utf-8') as f:
                    f.write(redact_secrets(content))
            
            return artifact_path
        except Exception as e:
            logger.warning(f"Failed to save artifact {artifact_type}: {e}")
            return None
    
    def close(self):
        """Close the trace file."""
        if self.enabled and hasattr(self, 'trace_fp'):
            try:
                self.trace_fp.close()
            except Exception:
                pass


# Global tracer instance (set by run_eval.py)
_current_tracer: Optional[LocalTracer] = None


def get_tracer() -> Optional[LocalTracer]:
    """Get the current tracer instance."""
    return _current_tracer


def set_tracer(tracer: LocalTracer):
    """Set the current tracer instance."""
    global _current_tracer
    _current_tracer = tracer

