"""Configuration management for the backend application."""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file in backend directory
# Try multiple possible locations
env_paths = [
    Path(__file__).parent.parent / ".env",  # backend/.env
    Path(".env"),  # Current directory
    Path.home() / ".env",  # Home directory
]

env_loaded = False
loaded_path = None
for env_path in env_paths:
    abs_path = env_path.resolve() if env_path.exists() else None
    if abs_path and abs_path.exists():
        try:
            load_dotenv(abs_path, override=True)  # Use override=True to ensure values are loaded
            env_loaded = True
            loaded_path = abs_path
            # Use print since logging might not be configured yet
            print(f"[CONFIG] Loaded .env file from: {abs_path}")
            break
        except Exception as e:
            print(f"[CONFIG] Error loading .env from {abs_path}: {e}")

if not env_loaded:
    # If no .env file found, try loading from current directory anyway
    print("[CONFIG] Warning: No .env file found in expected locations, trying current directory")
    try:
        load_dotenv(override=True)
    except Exception as e:
        print(f"[CONFIG] Error loading .env from current directory: {e}")

# Vertex AI Gemini configuration
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")  # Default to "global"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-preview")  # Default to gemini-3-pro-preview

# Log configuration values (without sensitive data)
# Use print since logging might not be configured yet when this module loads
print(f"[CONFIG] GCP_PROJECT_ID: {'SET (' + GCP_PROJECT_ID + ')' if GCP_PROJECT_ID else 'NOT SET'}")
print(f"[CONFIG] GCP_LOCATION: {GCP_LOCATION}")
print(f"[CONFIG] GEMINI_MODEL: {GEMINI_MODEL}")
if GCP_PROJECT_ID:
    logger.info(f"GCP_PROJECT_ID: SET")
    logger.info(f"GCP_LOCATION: {GCP_LOCATION}")
    logger.info(f"GEMINI_MODEL: {GEMINI_MODEL}")
else:
    logger.error("GCP_PROJECT_ID: NOT SET - Vertex AI will not work!")
GEMINI_TEMPERATURE = 0
GEMINI_MAX_OUTPUT_TOKENS_EXTRACTION = 2048
GEMINI_MAX_OUTPUT_TOKENS_ANSWERING = 32768  # Increased for longer, more detailed chat responses

# Supermemory configuration
SUPERMEMORY_API_KEY = os.getenv("SUPERMEMORY_API_KEY")
SUPERMEMORY_BASE_URL = os.getenv("SUPERMEMORY_BASE_URL")  # Optional
SUPERMEMORY_WORKSPACE_ID = os.getenv("SUPERMEMORY_WORKSPACE_ID")  # Optional

# Langfuse removed - using local observability instead

# Validate required environment variables
if not GCP_PROJECT_ID:
    import warnings
    warnings.warn("GCP_PROJECT_ID not found in environment variables. Please set it in .env file or as an environment variable.")
if not SUPERMEMORY_API_KEY:
    import warnings
    warnings.warn("SUPERMEMORY_API_KEY not found in environment variables. Please set it in .env file or as an environment variable.")

# Extraction prompt (verbatim as specified)
EXTRACTION_PROMPT = """You are performing optical context compression.

Given an image of a document page:
- Extract structured markdown
- Preserve headings, tables, and key-value fields
- Produce a concise summary
- Return JSON with fields:
  - page_number
  - markdown
  - entities
  - summary"""

# Default values
DEFAULT_DPI = 150  # Reduced from 200 for faster processing (still good quality)
DEFAULT_START_PAGE = 1
DEFAULT_TOP_K = 8
DEFAULT_MAX_CHARS_PER_PAGE = 1500

