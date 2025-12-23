# Vision Compression Backend

FastAPI backend for PDF document ingestion and question answering using Gemini and Supermemory.

## Features

- **PDF Ingestion**: Extract and compress PDF pages using Gemini vision model
- **Supermemory Integration**: Ingest compressed pages into Supermemory for semantic search
- **Question Answering**: Retrieve relevant pages and generate answers with citations using Gemini

## Environment Variables

Create a `.env` file in the `backend` directory or set these environment variables:

```bash
GEMINI_API_KEY=your_gemini_api_key_here
SUPERMEMORY_API_KEY=your_supermemory_api_key_here

# Optional (only if required by Supermemory SDK)
SUPERMEMORY_BASE_URL=https://api.supermemory.com
SUPERMEMORY_WORKSPACE_ID=your_workspace_id
```

## Local Development

### Install Dependencies

**Important:** Make sure you're in a virtual environment before installing.

```bash
cd backend

# Upgrade pip and setuptools first (helps with Windows build issues)
python -m pip install --upgrade pip setuptools wheel

# Install dependencies
pip install -r requirements.txt
```

**Windows Troubleshooting:**

If `pillow` fails to build on Windows, try one of these solutions:

1. **Install pre-built wheel (recommended):**
   ```bash
   pip install --upgrade pip wheel
   pip install pillow --only-binary :all:
   pip install -r requirements.txt
   ```

2. **Or install pillow separately first:**
   ```bash
   pip install pillow
   pip install -r requirements.txt
   ```

3. **If still failing, use a more recent Python version (3.11+ recommended)**

### Run Locally

```bash
# From backend directory
uvicorn app.main:app --reload
```

**Note:** If `uvicorn` command is not found, make sure:
1. Your virtual environment is activated
2. Dependencies were installed successfully
3. Try: `python -m uvicorn app.main:app --reload`

The API will be available at `http://localhost:8000`

### API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### GET /health

Health check endpoint.

**Response:**
```json
{
  "ok": true
}
```

### POST /ingest

Ingest a PDF file: extract pages and ingest into Supermemory.

**Request:** multipart/form-data
- `file` (required): PDF file
- `dpi` (optional, default: 200): DPI for image conversion
- `start_page` (optional, default: 1): Start page (1-indexed)
- `end_page` (optional, default: all pages): End page (1-indexed)
- `overwrite` (optional, default: false): Overwrite existing files

**Response:**
```json
{
  "doc_id": "20251221_123456_abc123",
  "pages_total": 10,
  "pages_ingested": 10,
  "failed_pages": [],
  "manifest_path": "tmp/20251221_123456_abc123/supermemory_manifest.json"
}
```

**Example with curl:**
```bash
curl -X POST "http://localhost:8000/ingest" \
  -F "file=@document.pdf" \
  -F "dpi=200" \
  -F "start_page=1" \
  -F "end_page=10" \
  -F "overwrite=false"
```

### POST /chat

Answer a question about an ingested document.

**Request:** application/json
```json
{
  "doc_id": "20251221_123456_abc123",
  "question": "What is the main topic of this document?",
  "top_k": 8,
  "max_chars_per_page": 1500
}
```

**Response:**
```json
{
  "doc_id": "20251221_123456_abc123",
  "answer_md": "The main topic is... (doc_id p.1, p.2)",
  "retrieved": [
    {
      "page": 1,
      "memory_id": "mem_123",
      "excerpt": "First 250 characters of the page..."
    }
  ]
}
```

**Example with curl:**
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "20251221_123456_abc123",
    "question": "What is the main topic?",
    "top_k": 8,
    "max_chars_per_page": 1500
  }'
```

## Docker Deployment

### Build Docker Image

```bash
cd backend
docker build -t vision-compression-backend .
```

### Run Docker Container

```bash
docker run -p 8080:8080 \
  -e GEMINI_API_KEY=your_key \
  -e SUPERMEMORY_API_KEY=your_key \
  vision-compression-backend
```

## Cloud Run Deployment

### Build and Push to Google Container Registry

```bash
# Set your project ID
export PROJECT_ID=your-project-id
export SERVICE_NAME=vision-compression-backend

# Build and push
gcloud builds submit --tag gcr.io/${PROJECT_ID}/${SERVICE_NAME}

# Deploy to Cloud Run
gcloud run deploy ${SERVICE_NAME} \
  --image gcr.io/${PROJECT_ID}/${SERVICE_NAME} \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_key,SUPERMEMORY_API_KEY=your_key \
  --memory 2Gi \
  --timeout 300
```

### Set Environment Variables in Cloud Run

You can also set environment variables via the Cloud Run console or using:

```bash
gcloud run services update ${SERVICE_NAME} \
  --update-env-vars GEMINI_API_KEY=your_key,SUPERMEMORY_API_KEY=your_key
```

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application and endpoints
│   ├── config.py            # Configuration and environment variables
│   ├── schemas.py           # Pydantic request/response models
│   └── pipeline/
│       ├── __init__.py
│       ├── pdf_extract.py   # PDF extraction with Gemini
│       ├── supermemory_ingest.py  # Supermemory ingestion
│       ├── qa.py            # Question answering
│       └── utils.py         # Utility functions
├── tmp/                     # Temporary file storage (per doc_id)
├── requirements.txt
├── Dockerfile
└── README.md
```

## Notes

- Temporary files are stored under `tmp/<doc_id>/` directory
- Each document gets a unique `doc_id` based on timestamp + random suffix
- The extraction process creates:
  - `tmp/<doc_id>/uploaded.pdf` - Original PDF
  - `tmp/<doc_id>/images/page_###.png` - Page images
  - `tmp/<doc_id>/pages/page_###.json` - Compressed JSON per page
  - `tmp/<doc_id>/supermemory_manifest.json` - Manifest with memory IDs

## License

MIT

