"""FastAPI main application."""

import os
import random
import string
from datetime import datetime
from pathlib import Path

from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    DEFAULT_DPI,
    DEFAULT_START_PAGE,
    DEFAULT_TOP_K,
    DEFAULT_MAX_CHARS_PER_PAGE,
)
from app.schemas import (
    HealthResponse,
    IngestResponse,
    ChatRequest,
    ChatResponse,
    FailedPage,
    RetrievedPage,
)
from app.pipeline import pdf_extract, supermemory_ingest, qa

app = FastAPI(title="Vision Compression Backend", version="1.0.0")

# Add CORS middleware
# Note: Cannot use allow_origins=["*"] with allow_credentials=True
# So we allow credentials=False or specify origins explicitly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Must be False when using "*" origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Base directory for temporary files
BASE_TMP_DIR = Path("tmp")


def generate_doc_id() -> str:
    """Generate a stable doc_id: timestamp + random suffix."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{timestamp}_{random_suffix}"


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Vision Compression Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "GET /health": "Health check",
            "POST /ingest": "Ingest PDF file",
            "POST /chat": "Answer questions about ingested documents"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return {"ok": True}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(..., description="PDF file to ingest"),
    dpi: int = Form(default=DEFAULT_DPI, description="DPI for image conversion"),
    start_page: int = Form(default=DEFAULT_START_PAGE, description="Start page (1-indexed)"),
    end_page: Optional[int] = Form(default=None, description="End page (1-indexed, None for all pages)"),
    overwrite: bool = Form(default=False, description="Overwrite existing files")
):
    """
    Ingest a PDF file: extract pages and ingest into Supermemory.
    
    Process:
    1. Generate doc_id
    2. Create working directory: tmp/<doc_id>/{pages,images}
    3. Save PDF as tmp/<doc_id>/uploaded.pdf
    4. Run extraction to produce tmp/<doc_id>/pages/page_###.json
    5. Run ingestion to create tmp/<doc_id>/supermemory_manifest.json
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Generate doc_id
    doc_id = generate_doc_id()
    
    # Create working directories
    doc_dir = BASE_TMP_DIR / doc_id
    pages_dir = doc_dir / "pages"
    images_dir = doc_dir / "images"
    
    pages_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded PDF
    pdf_path = doc_dir / "uploaded.pdf"
    try:
        with open(pdf_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {e}")
    
    # Run extraction
    try:
        extract_stats = pdf_extract.extract_pdf_to_page_jsons(
            pdf_path=pdf_path,
            out_pages_dir=pages_dir,
            images_dir=images_dir,
            dpi=dpi,
            start_page=start_page,
            end_page=end_page,
            overwrite=overwrite
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")
    
    # Run ingestion
    manifest_path = doc_dir / "supermemory_manifest.json"
    try:
        manifest = supermemory_ingest.ingest_pages_dir(
            pages_dir=pages_dir,
            pdf_path=pdf_path,
            doc_id=doc_id,
            manifest_path=manifest_path,
            overwrite=overwrite
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")
    
    # Count successful and failed pages
    pages_ingested = len([p for p in manifest.get('pages', []) if 'error' not in p])
    failed_pages_list = [
        FailedPage(page=fp['page'], error=fp['error'])
        for fp in manifest.get('failed_pages', [])
    ]
    
    # Also include extraction failures
    for fp in extract_stats.get('failed_pages', []):
        # Check if this page failure is not already in failed_pages_list
        if not any(f.page == fp['page'] for f in failed_pages_list):
            failed_pages_list.append(FailedPage(page=fp['page'], error=fp['error']))
    
    return IngestResponse(
        doc_id=doc_id,
        pages_total=extract_stats['pages_total'],
        pages_ingested=pages_ingested,
        failed_pages=failed_pages_list,
        manifest_path=str(manifest_path)
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Answer a question about an ingested document.
    
    Process:
    1. Load manifest from tmp/<doc_id>/supermemory_manifest.json (if exists)
    2. Query Supermemory filtered by doc_id
    3. Build evidence pack
    4. Generate answer with Gemini using strict citation rules
    """
    doc_id = request.doc_id
    
    # Try to load manifest
    manifest_path = BASE_TMP_DIR / doc_id / "supermemory_manifest.json"
    manifest_path = manifest_path if manifest_path.exists() else None
    
    # Answer question
    try:
        result = qa.answer_question(
            doc_id=doc_id,
            question=request.question,
            top_k=request.top_k,
            max_chars_per_page=request.max_chars_per_page,
            model=None,  # Uses default from config (gemini-3-pro-preview)
            manifest_path=manifest_path
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"QA failed: {e}")
    
    # Convert retrieved list to schema
    retrieved_list = [
        RetrievedPage(
            page=r['page'],
            memory_id=r['memory_id'],
            excerpt=r['excerpt']
        )
        for r in result['retrieved']
    ]
    
    return ChatResponse(
        doc_id=doc_id,
        answer_md=result['answer_md'],
        retrieved=retrieved_list
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

