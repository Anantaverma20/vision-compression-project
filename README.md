# Vision Compression Document Chat

A web application that lets you upload PDF documents and chat with an AI assistant that answers questions using the document content. Uses Gemini Vision API for document compression and Supermemory for semantic search.

## How It Works

1. **Upload PDF**: Upload a PDF document through the web interface
2. **Process**: Backend extracts each page using Gemini Vision API, compresses it to structured JSON, and ingests into Supermemory
3. **Chat**: Ask questions about the document - the system retrieves relevant pages and generates answers with citations

## Architecture

- **Frontend**: Next.js web UI (React + TypeScript + TailwindCSS)
- **Backend**: FastAPI service (Python) that handles PDF processing and question answering
- **APIs**: Google Gemini (vision + text) and Supermemory (semantic search)

## Quick Start

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

Create `backend/.env`:
```
GCP_PROJECT_ID=your-gcp-project-id
SUPERMEMORY_API_KEY=your_key_here
```

**Important:** For local development, authenticate with Google Cloud:
```bash
gcloud auth application-default login
```

Run backend:
```bash
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`

### Frontend Setup

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:
```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Run frontend:
```bash
npm run dev
```

Frontend runs at `http://localhost:3000`

## Usage

1. Open `http://localhost:3000` in your browser
2. Upload a PDF file and click "Process & Ingest"
3. Wait for processing to complete (shows progress: pages ingested/total)
4. Ask questions in the chat interface
5. View retrieved evidence in the right panel

## Deployment

### Backend (Google Cloud Run)

See `backend/CLOUD_RUN_SETUP.md` for detailed instructions. Use `backend/deploy-with-cloud-build.ps1` script for automated deployment.

### Frontend (Vercel)

1. Push frontend code to GitHub
2. Import repository in Vercel
3. Set `NEXT_PUBLIC_BACKEND_URL` environment variable to your Cloud Run URL
4. Deploy

## Features

- **Parallel Processing**: Pages processed concurrently for faster ingestion
- **Thread-Safe**: Each processing thread creates its own model instance
- **Error Handling**: Failed pages are tracked and can be retried
- **Citations**: Answers include page references like `(doc_id p.7)`
- **Evidence Panel**: View retrieved pages and excerpts supporting answers
- **Evaluation Framework**: Research-grade evaluation comparing text RAG, optical, and hybrid modes

## Evaluation Framework

The project includes a comprehensive evaluation layer to measure "effective context window enhancement" by comparing three RAG modes:

1. **text_rag**: Traditional text-based retrieval and generation
2. **optical**: Metadata-based retrieval with page images as context (vision context)
3. **hybrid**: Text retrieval followed by page images for final answer

### Setup

Install evaluation dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### Ingest Multiple PDFs into a Corpus

```bash
# From project root
python -m eval.ingest_corpus --pdfs "data/*.pdf" --corpus_id demo_corpus

# Or specify individual PDFs
python -m eval.ingest_corpus --pdfs data/paper1.pdf data/paper2.pdf --corpus_id demo_corpus

# Options:
#   --dpi 150              # DPI for image conversion (default: 150)
#   --start_page 1         # Start page (default: 1)
#   --end_page 10          # End page (default: all)
#   --overwrite            # Overwrite existing files
```

This creates:
- `output/corpora/<corpus_id>/docs/<doc_id>/` for each PDF
- Page JSON files and images
- Corpus manifest with metadata

### Run Evaluation

```bash
# Evaluate all modes
python -m eval.run_eval --corpus_id demo_corpus --mode all

# Evaluate specific mode
python -m eval.run_eval --corpus_id demo_corpus --mode text_rag

# Custom questions file
python -m eval.run_eval --corpus_id demo_corpus --questions eval/datasets/my_questions.json

# Options:
#   --top_k 8                    # Number of results to retrieve (default: 8)
#   --max_chars_per_page 1500    # Max chars per page (default: 1500)
#   --max_images 6               # Max images for optical/hybrid (default: 6)
#   --judge rule|llm             # Judge type: rule (default) or llm
#   --use_proxy_optical          # Use proxy optical mode (summaries instead of images)
#   --run_id <id>                # Run ID for tracing (auto-generated if not provided)
#   --trace / --no-trace         # Enable/disable tracing (default: enabled)
```

Results are saved to:
- `output/corpora/<corpus_id>/results/results.json` (detailed JSON)
- `output/corpora/<corpus_id>/results/results.csv` (CSV for analysis)
- `output/corpora/<corpus_id>/results/summary.md` (markdown summary)

### Evaluation Metrics

Each evaluation computes:
- **Judge Score** (0-1): Quality score (rule-based or LLM-based)
- **Citation Correctness**: Quality of citations
- **Coverage**: How well answer covers key points
- **Has Citations**: Boolean indicating citation presence
- **Citation Coverage**: % of sentences with citations
- **Retrieved Pages Count**: Number of pages retrieved
- **Estimated Context Units**: 
  - text_rag: character count in evidence pack
  - optical/hybrid: number of page-images selected
- **Latency**: Time to generate answer

### Observability

The evaluation framework includes local observability and tracing:

**Trace Files**: JSONL format events stored in `output/corpora/<corpus_id>/traces/<run_id>.jsonl`
- Each line is a JSON event with: timestamp, run_id, corpus_id, stage (ingest|retrieve|generate|judge), mode, question_id, latency, and payload
- Secrets are automatically redacted from trace data

**Artifacts**: Per-question artifacts stored in `output/corpora/<corpus_id>/results/artifacts/<run_id>/<mode>/<question_id>/`
- `retrieval.json`: Retrieved pages and metadata
- `evidence.txt`: Evidence pack used for generation
- `prompt.txt`: Prompt sent to LLM (if available)
- `answer.md`: Generated answer
- `judge.json`: Judge evaluation results

**Inspecting Traces**:
```bash
# View trace file
cat output/corpora/demo_corpus/traces/run_*.jsonl | jq

# Filter by stage
cat output/corpora/demo_corpus/traces/run_*.jsonl | jq 'select(.stage=="retrieve")'
```

### Evaluation Judge Modes

The framework supports two judge modes:

**Rule-based Judge** (default, `--judge rule`):
- Deterministic scoring based on:
  - Groundedness proxy (keyword overlap between answer and evidence)
  - Citation quality (presence, format, coverage)
  - Completeness (not-found correctness, length penalty)
- Fast, no API calls required
- Score formula: `0.45 * groundedness + 0.35 * citation_quality + 0.20 * completeness`

**LLM Judge** (`--judge llm`):
- Uses Gemini via Vertex AI to evaluate answers
- Provides detailed rationale and nuanced scoring
- Requires GCP_PROJECT_ID to be set
- Falls back to rule-based if LLM judge fails

**Usage**:
```bash
# Use rule-based judge (default)
python -m eval.run_eval --corpus_id demo_corpus --mode all --judge rule

# Use LLM judge
python -m eval.run_eval --corpus_id demo_corpus --mode all --judge llm
```

### What Metrics Demonstrate "Effective Context Window Enhancement"

The evaluation framework measures:
1. **Context Efficiency**: Compare `estimated_context_units` across modes. Optical/hybrid modes should achieve similar or better quality with fewer context units (pages vs. full text chunks).
2. **Quality Preservation**: Compare `judge_score` and `coverage` across modes. Optical/hybrid should maintain or improve answer quality.
3. **Citation Quality**: Compare `citation_correctness` and `citation_coverage`. Vision-based modes should maintain citation accuracy.
4. **Latency**: Compare `latency_seconds`. Optical modes may be faster due to compressed context.

The key insight: **Optical modes compress context (pages vs. full text) while maintaining answer quality**, effectively expanding the usable context window.

## Project Structure

```
vision-compression-project/
├── backend/          # FastAPI backend
│   ├── app/         # Application code
│   └── requirements.txt
├── frontend/        # Next.js frontend
│   ├── app/        # Pages and components
│   └── package.json
├── eval/            # Evaluation framework
│   ├── datasets/    # Question datasets
│   ├── modes/       # RAG mode implementations
│   ├── ingest_corpus.py
│   ├── run_eval.py
│   ├── judge.py
│   ├── metrics.py
│   └── observability.py  # Local tracing and observability
├── output/          # Generated outputs
│   └── corpora/     # Corpus data and results
└── README.md
```

## Requirements

- Python 3.7+ (backend)
- Node.js 18+ (frontend)
- Google Cloud Project with Vertex AI enabled
- Google Cloud SDK installed and authenticated (`gcloud auth application-default login`)
- Supermemory API key
- Poppler (for PDF processing) - see backend README for installation

**Note:** This project uses Vertex AI Gemini (not Google AI Studio API key). Billing goes through your Google Cloud project, enabling use of GenAI App Builder/Vertex credits.

## License

MIT
