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
GEMINI_API_KEY=your_key_here
SUPERMEMORY_API_KEY=your_key_here
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

## Project Structure

```
vision-compression-project/
├── backend/          # FastAPI backend
│   ├── app/         # Application code
│   └── requirements.txt
├── frontend/        # Next.js frontend
│   ├── app/        # Pages and components
│   └── package.json
└── README.md
```

## Requirements

- Python 3.7+ (backend)
- Node.js 18+ (frontend)
- Google Gemini API key
- Supermemory API key
- Poppler (for PDF processing) - see backend README for installation

## License

MIT
