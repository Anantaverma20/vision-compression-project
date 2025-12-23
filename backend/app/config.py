"""Configuration management for the backend application."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in backend directory
# Try multiple possible locations
env_paths = [
    Path(__file__).parent.parent / ".env",  # backend/.env
    Path(".env"),  # Current directory
    Path.home() / ".env",  # Home directory
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    # If no .env file found, try loading from current directory anyway
    load_dotenv()

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3-pro-preview"
GEMINI_TEMPERATURE = 0
GEMINI_MAX_OUTPUT_TOKENS_EXTRACTION = 2048
GEMINI_MAX_OUTPUT_TOKENS_ANSWERING = 8192  # Increased from 2048 for longer, complete answers

# Supermemory configuration
SUPERMEMORY_API_KEY = os.getenv("SUPERMEMORY_API_KEY")
SUPERMEMORY_BASE_URL = os.getenv("SUPERMEMORY_BASE_URL")  # Optional
SUPERMEMORY_WORKSPACE_ID = os.getenv("SUPERMEMORY_WORKSPACE_ID")  # Optional

# Validate required environment variables
if not GEMINI_API_KEY:
    import warnings
    warnings.warn("GEMINI_API_KEY not found in environment variables. Please set it in .env file or as an environment variable.")
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

