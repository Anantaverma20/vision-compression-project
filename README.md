# Vision-Based Context Compression Pipeline

A minimal research-grade prototype for extracting and compressing document pages using Gemini's multimodal capabilities.

## Overview

This project implements a vision-based context compression pipeline:
- **STEP 1:** Converts the first page of a PDF to an image and processes it with Gemini
- **STEP 2:** Processes entire PDFs (or page ranges) into per-page compressed outputs
- **STEP 3:** Ingests compressed per-page outputs into Supermemory as searchable memories
- **STEP 4:** Question answering using Supermemory retrieval + Gemini reasoning with citations

## Project Structure

```
vision-compression-project/
├── data/
│   └── sample.pdf          # Input PDF file
├── output/
│   ├── pages/              # Per-page outputs (STEP 2)
│   │   ├── page_001.png
│   │   ├── page_001.json
│   │   ├── page_002.png
│   │   ├── page_002.json
│   │   └── ...
│   ├── answers/            # Question answering outputs (STEP 4)
│   │   └── YYYYMMDD_HHMMSS_answer.md
│   ├── supermemory_manifest.json  # Supermemory ingestion manifest (STEP 3)
│   ├── manifest.json       # Processing metadata (STEP 2)
│   ├── combined.md         # Combined markdown (STEP 2)
│   ├── page_1.png          # First page image (STEP 1)
│   └── page_1.json         # First page JSON (STEP 1)
├── scripts/
│   ├── extract_page_with_gemini.py    # STEP 1: Single page
│   ├── extract_pdf_with_gemini.py    # STEP 2: Full PDF
│   ├── ingest_to_supermemory.py      # STEP 3: Supermemory ingestion
│   └── qa_with_supermemory_and_gemini.py  # STEP 4: Question answering
├── requirements.txt
└── README.md
```

## Prerequisites

- Python 3.7+
- A Gemini API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

## Installation

1. Create and activate a virtual environment (recommended):
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python -m venv venv
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

**Note:** `pdf2image` requires `poppler` to be installed on your system:
- **Windows:** Download from [poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases/) and add to PATH
- **macOS:** `brew install poppler`
- **Linux:** `sudo apt-get install poppler-utils`

3. Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_api_key_here
poppler=C:\path\to\poppler\directory
SUPERMEMORY_API_KEY=your_supermemory_api_key_here
# Optional - only needed for self-hosted or custom Supermemory setups:
# SUPERMEMORY_BASE_URL=your_base_url_here
# SUPERMEMORY_WORKSPACE_ID=your_workspace_id_here
```

**Note:** For STEP 3, only `SUPERMEMORY_API_KEY` is required. `SUPERMEMORY_BASE_URL` and `SUPERMEMORY_WORKSPACE_ID` are optional and only needed if you're using a self-hosted instance or custom endpoint.

**Note about Poppler:**
- If you set `poppler` as a Windows environment variable, you must **restart VS Code/terminal** for it to take effect
- Alternatively, add `poppler=C:\path\to\poppler\directory` to your `.env` file (no restart needed)
- The path should point to the Poppler root directory (the script will find `bin` or `Library\bin` automatically)

## Usage

**Important:** Make sure you're in the `vision-compression-project` directory before running commands.

### Quick Start (Easiest Method)

Simply run one of these helper scripts from the project root:

**Windows (Command Prompt or PowerShell):**
```bash
run.bat
```

**Windows (PowerShell - alternative):**
```powershell
.\run.ps1
```

### Manual Method

1. Navigate to the project directory:
```bash
cd vision-compression-project
```

2. Activate the virtual environment:
```bash
# Windows (Command Prompt or PowerShell)
venv\Scripts\activate.bat

# Windows (PowerShell - if execution policy allows)
.\venv\Scripts\Activate.ps1

# macOS/Linux
source venv/bin/activate
```

**Note:** If you get an execution policy error in PowerShell, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

3. Place your PDF file in `data/sample.pdf` (or specify a different path)

## Usage

### STEP 1: Process First Page Only

Run the single-page extraction script:
```bash
python scripts/extract_page_with_gemini.py
```

**Output:**
- `output/page_1.png` - The extracted page image
- `output/page_1.json` - The structured JSON response from Gemini

### STEP 2: Process Entire PDF (or Page Range)

Run the full PDF extraction script:
```bash
python scripts/extract_pdf_with_gemini.py
```

**Basic usage:**
```bash
# Process entire PDF (default: data/sample.pdf)
python scripts/extract_pdf_with_gemini.py

# Process specific PDF
python scripts/extract_pdf_with_gemini.py --pdf data/my_document.pdf

# Process specific page range
python scripts/extract_pdf_with_gemini.py --start_page 1 --end_page 10

# Process with custom DPI and sleep interval
python scripts/extract_pdf_with_gemini.py --dpi 300 --sleep 2.0

# Overwrite existing JSON files
python scripts/extract_pdf_with_gemini.py --overwrite
```

**Command-line arguments:**
- `--pdf`: Path to PDF file (default: `data/sample.pdf`)
- `--dpi`: DPI for image conversion (default: `200`)
- `--start_page`: Start page number, 1-indexed (default: `1`)
- `--end_page`: End page number, 1-indexed (default: all pages)
- `--sleep`: Seconds to sleep between Gemini API calls (default: `1.0`)
- `--overwrite`: Overwrite existing JSON files (default: skip if JSON exists)

**Examples:**
```bash
# Process pages 5-15 of a specific PDF
python scripts/extract_pdf_with_gemini.py --pdf data/report.pdf --start_page 5 --end_page 15

# Process entire PDF with higher resolution
python scripts/extract_pdf_with_gemini.py --dpi 300

# Resume processing (skips pages that already have JSON)
python scripts/extract_pdf_with_gemini.py --pdf data/large_document.pdf
```

**STEP 2 Output:**
- `output/pages/page_###.png` - Page images (one per page)
- `output/pages/page_###.json` - JSON responses (one per page)
- `output/manifest.json` - Processing metadata and statistics
- `output/combined.md` - Combined markdown from all pages

### STEP 3: Ingest Pages into Supermemory

After completing STEP 2, ingest the compressed per-page outputs into Supermemory as searchable memories:

```bash
python scripts/ingest_to_supermemory.py
```

**Basic usage:**
```bash
# Ingest all pages (default: output/pages)
python scripts/ingest_to_supermemory.py

# Specify custom pages directory and PDF path
python scripts/ingest_to_supermemory.py --pages_dir output/pages --pdf_path "data/my_document.pdf"

# Handle paths with spaces (use quotes!)
python scripts/ingest_to_supermemory.py --pdf_path "data/deepseek ocr paper.pdf" --pages_dir output/pages

# Overwrite existing ingestions
python scripts/ingest_to_supermemory.py --overwrite

# Custom smoke test query
python scripts/ingest_to_supermemory.py --smoke_test_query "What are the main contributions?"
```

**Important:** If your PDF path contains spaces, you must quote it:
```bash
# Correct (with quotes)
python scripts/ingest_to_supermemory.py --pdf_path "data/deepseek ocr paper.pdf"

# Incorrect (without quotes - will cause an error)
python scripts/ingest_to_supermemory.py --pdf_path data/deepseek ocr paper.pdf
```

**Command-line arguments:**
- `--pages_dir`: Directory containing page JSON files (default: `output/pages`)
- `--pdf_path`: Path to original PDF file (default: `data/deepseek ocr paper.pdf`)
- `--doc_id`: Document ID. If not provided, generated from PDF filename
- `--overwrite`: Overwrite existing ingested pages (default: skip already ingested pages)
- `--smoke_test_query`: Query for smoke test (default: `"Summarize the document"`)

**STEP 3 Output:**
- `output/supermemory_manifest.json` - Ingestion manifest with memory IDs and metadata

**Supermemory Manifest Structure:**
```json
{
  "doc_id": "deepseek_ocr_paper",
  "pdf_path": "data/deepseek ocr paper.pdf",
  "created_at": "2025-01-XXT...",
  "pages": [
    {"page": 1, "file": "output/pages/page_001.json", "memory_id": "mem_123..."},
    {"page": 2, "file": "output/pages/page_002.json", "memory_id": "mem_456..."},
    {"page": 5, "file": "output/pages/page_005.json", "error": "API error message"}
  ]
}
```

**Environment Setup for STEP 3:**
- Set `SUPERMEMORY_API_KEY` in your `.env` file (required)
- `SUPERMEMORY_BASE_URL` and `SUPERMEMORY_WORKSPACE_ID` are optional - only needed for self-hosted or custom Supermemory setups

**Smoke Test:**
After ingestion, the script automatically runs a smoke test query to verify the memories are searchable. The default query is "Summarize the document", but you can customize it with `--smoke_test_query`.

### STEP 4: Question Answering with Supermemory + Gemini

After completing STEP 3, you can ask questions about the document using Supermemory retrieval and Gemini reasoning:

```bash
python scripts/qa_with_supermemory_and_gemini.py --question "What is the main contribution of this paper?"
```

**Basic usage:**
```bash
# Basic question answering
python scripts/qa_with_supermemory_and_gemini.py --question "What are the key findings?"

# Use query rewriting (Gemini rewrites question into better search terms)
python scripts/qa_with_supermemory_and_gemini.py --question "What did they discover?" --rewrite_query

# Customize retrieval and model settings
python scripts/qa_with_supermemory_and_gemini.py --question "Explain the methodology" --top_k 10 --model gemini-1.5-flash

# Use custom manifest path
python scripts/qa_with_supermemory_and_gemini.py --question "..." --manifest output/custom_manifest.json
```

**Command-line arguments:**
- `--question`: Question to answer (required)
- `--manifest`: Path to Supermemory manifest (default: `output/supermemory_manifest.json`)
- `--top_k`: Number of top results to retrieve (default: `8`)
- `--max_chars_per_page`: Maximum characters per page in evidence pack (default: `1500`)
- `--model`: Gemini model to use (default: `gemini-1.5-pro`)
- `--rewrite_query`: Use Gemini to rewrite the question into search terms before retrieval (flag)

**Examples:**
```bash
# Ask about specific technical details
python scripts/qa_with_supermemory_and_gemini.py --question "What compression ratio did they achieve?" --top_k 8

# Use query rewriting for better retrieval
python scripts/qa_with_supermemory_and_gemini.py --question "How does the encoder work?" --rewrite_query

# Retrieve more context for complex questions
python scripts/qa_with_supermemory_and_gemini.py --question "Compare the different approaches mentioned" --top_k 15
```

**STEP 4 Output:**
- `output/answers/YYYYMMDD_HHMMSS_answer.md` - Answer file with question, answer (with citations), and retrieved pages list

**Answer Format:**
Each answer file contains:
- Question
- Answer with inline citations in format: `(doc_id p.<page_number>)`
- Retrieved pages list (for debugging)

**Citation Requirements:**
- Every non-trivial claim has an inline citation
- Multiple pages can be cited: `(doc_id p.1, p.2)`
- If information is not found, the answer explicitly states "Not found in provided pages."

**Environment Setup for STEP 4:**
- Requires both `GEMINI_API_KEY` and `SUPERMEMORY_API_KEY` in your `.env` file
- `SUPERMEMORY_BASE_URL` and `SUPERMEMORY_WORKSPACE_ID` are optional (same as STEP 3)

**Manifest.json structure:**
```json
{
  "pdf_path": "data/sample.pdf",
  "total_pages": 25,
  "processed_pages": [1, 2, 3, ...],
  "failed_pages": [{"page": 5, "error": "..."}],
  "model_name": "gemini-1.5-pro",
  "dpi": 200,
  "start_page": 1,
  "end_page": 25,
  "timestamp": "2025-01-XX..."
}
```

## Configuration

Both scripts use the following Gemini settings:
- **Model:** gemini-1.5-pro
- **Temperature:** 0 (deterministic)
- **Max Output Tokens:** 2048

## Output Format

Each page JSON contains:
- `page_number`: Page number (1-indexed)
- `markdown`: Structured markdown representation
- `entities`: Extracted entities
- `summary`: Concise summary

## Features

**STEP 2 Robustness:**
- Automatic retry logic with exponential backoff (up to 3 retries)
- Continues processing even if individual pages fail
- Skips already-processed pages (unless `--overwrite` is used)
- Rate limiting via configurable sleep interval between API calls
- Comprehensive error tracking in manifest.json

## Notes

- This is a minimal prototype - no UI components or server framework
- Designed for local execution and reproducibility
- STEP 2 processes pages sequentially to respect API rate limits
- Failed pages are recorded in manifest.json for later retry
- STEP 3 includes basic retry logic (3 attempts with exponential backoff) around Supermemory API calls
- STEP 3 skips already-ingested pages by default (use `--overwrite` to re-ingest)
- STEP 4 includes retry logic for both Supermemory queries and Gemini generation (3 attempts with exponential backoff)
- STEP 4 requires pages to be ingested via STEP 3 before use

