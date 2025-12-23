"""Utility functions for the pipeline."""

import json
import re
import time
from pathlib import Path
from typing import Callable, Any, Optional


def strip_code_fences(text: str) -> str:
    """
    Strip markdown code fences (```json or ```) from text.
    
    Args:
        text: Text that may contain code fences
        
    Returns:
        Text with code fences removed
    """
    if not text:
        return text
    
    # Remove ```json fences
    text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    
    # Remove generic ``` fences
    text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    
    return text.strip()


def safe_json_loads(text: str) -> Optional[dict]:
    """
    Safely parse JSON from text, handling code fences and errors.
    
    Args:
        text: Text that may contain JSON
        
    Returns:
        Parsed JSON dict or None if parsing fails
    """
    if not text:
        return None
    
    # Strip code fences
    cleaned = strip_code_fences(text)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def retry(fn: Callable, attempts: int = 3, backoff: list = None, *args, **kwargs) -> Any:
    """
    Retry a function call with exponential backoff.
    
    Args:
        fn: Function to call
        attempts: Number of retry attempts
        backoff: List of wait times in seconds (default: [1, 2, 4])
        *args: Positional arguments to pass to fn
        **kwargs: Keyword arguments to pass to fn
        
    Returns:
        Result of fn call
        
    Raises:
        Exception: If all attempts fail, raises the last exception
    """
    if backoff is None:
        backoff = [1, 2, 4]
    
    last_exception = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < attempts - 1:
                wait_time = backoff[min(attempt, len(backoff) - 1)]
                time.sleep(wait_time)
            else:
                raise last_exception
    
    raise last_exception


def ensure_dirs(*paths: Path) -> None:
    """
    Ensure directories exist, creating them if necessary.
    
    Args:
        *paths: Path objects to create
    """
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

