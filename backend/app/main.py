"""FastAPI main application."""

import os
import random
import string
import logging
from datetime import datetime
from pathlib import Path

from typing import Optional, List
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app.config import (
    DEFAULT_DPI,
    DEFAULT_START_PAGE,
    DEFAULT_TOP_K,
    DEFAULT_MAX_CHARS_PER_PAGE,
    GCP_PROJECT_ID,
    GEMINI_MODEL,
)
from app.schemas import (
    HealthResponse,
    IngestResponse,
    ChatRequest,
    ChatResponse,
    FailedPage,
    RetrievedPage,
    CorpusIngestResponse,
    DocIngestResult,
    OpticalLiteIngestRequest,
    OpticalLiteIngestResponse,
    OpticalLiteChatRequest,
    OpticalLiteChatResponse,
    OpticalLiteRetrievedPage,
)
from app.pipeline import pdf_extract, supermemory_ingest, qa
from app.pipeline import optical_lite_ingest, optical_lite_qa
from app.eval_runner import run_eval_async, get_eval_results
from fastapi import BackgroundTasks

app = FastAPI(title="Vision Compression Backend", version="1.0.0")

# Verify critical configuration at startup
if not GCP_PROJECT_ID:
    logger.error("=" * 80)
    logger.error("CRITICAL: GCP_PROJECT_ID is not set!")
    logger.error("Please ensure your .env file exists in the backend/ directory")
    logger.error("and contains: GCP_PROJECT_ID=your-project-id")
    logger.error("=" * 80)
else:
    logger.info(f"✓ Configuration loaded: GCP_PROJECT_ID={GCP_PROJECT_ID}, GEMINI_MODEL={GEMINI_MODEL}")

# Add middleware to ensure CORS headers are added to all responses
# This runs AFTER CORS middleware (middleware executes in reverse order)
@app.middleware("http")
async def add_cors_header(request, call_next):
    """Ensure CORS headers are added to all responses."""
    response = await call_next(request)
    # Always add CORS headers to ensure they're present
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Max-Age"] = "3600"
    return response

# Add CORS middleware (runs first, before the above middleware)
# Note: Cannot use allow_origins=["*"] with allow_credentials=True
# So we allow credentials=False or specify origins explicitly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,  # Must be False when using "*" origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],  # Allow all headers including Content-Type, Authorization, etc.
    expose_headers=["*"],
    max_age=3600,
)

# Explicit OPTIONS handler for CORS preflight requests
# Some proxies/load balancers don't handle OPTIONS correctly
@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """Handle CORS preflight OPTIONS requests."""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "3600",
        }
    )

# Base directory for temporary files
BASE_TMP_DIR = Path("tmp")
# Output directory for corpora (used by eval system)
OUTPUT_DIR = Path("output") / "corpora"


def generate_doc_id() -> str:
    """Generate a stable doc_id: timestamp + random suffix."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{timestamp}_{random_suffix}"


def generate_corpus_id() -> str:
    """Generate a corpus_id: timestamp-based."""
    return f"corpus_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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
            "POST /ingest-corpus": "Ingest multiple PDF files into a corpus",
            "POST /chat": "Answer questions about ingested documents",
            "POST /ingest-optical-lite": "Ingest pages using optical-lite mode (minimal metadata)",
            "POST /chat-optical-lite": "Answer questions using optical-lite mode (image-based)",
            "GET /eval-results/{corpus_id}": "Get evaluation results for a corpus"
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
            overwrite=overwrite,
            corpus_id=None  # Single doc ingestion doesn't use corpus_id
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
    Answer a question about ingested document(s).
    
    Supports both single document queries (doc_id) and corpus queries (corpus_id).
    
    Process:
    1. Load manifest(s) if available
    2. Query Supermemory filtered by doc_id or corpus_id
    3. Build evidence pack
    4. Generate answer with Gemini using strict citation rules
    """
    # Validate request
    if not request.doc_id and not request.corpus_id:
        raise HTTPException(status_code=400, detail="Either doc_id or corpus_id must be provided")
    
    doc_id = request.doc_id
    corpus_id = request.corpus_id
    
    # Try to load manifest(s)
    manifest_path = None
    if doc_id:
        # Single document: try to load its manifest
        manifest_path = BASE_TMP_DIR / doc_id / "supermemory_manifest.json"
        manifest_path = manifest_path if manifest_path.exists() else None
    elif corpus_id:
        # Corpus: try to load corpus manifest (contains info about all docs)
        corpus_manifest_path = OUTPUT_DIR / corpus_id / "corpus_manifest.json"
        if corpus_manifest_path.exists():
            # For corpus queries, we don't use a single manifest, but we could load it for reference
            manifest_path = None  # Will query across all docs in corpus
    
    # Answer question
    try:
        result = qa.answer_question(
            doc_id=doc_id,
            corpus_id=corpus_id,
            question=request.question,
            top_k=request.top_k,
            max_chars_per_page=request.max_chars_per_page,
            model=None,  # Uses default from config
            manifest_path=manifest_path
        )
    except Exception as e:
        logger.error(f"QA failed: {type(e).__name__}: {e}", exc_info=True)
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
    
    # Use corpus_id if provided, otherwise doc_id
    response_doc_id = corpus_id if corpus_id else doc_id
    
    return ChatResponse(
        doc_id=response_doc_id or "unknown",
        answer_md=result['answer_md'],
        retrieved=retrieved_list
    )


def _process_single_pdf(
    file_content: bytes,
    filename: str,
    corpus_id: str,
    dpi: int,
    start_page: int,
    end_page: Optional[int],
    overwrite: bool
) -> DocIngestResult:
    """
    Process a single PDF file (synchronous function for parallel execution).
    
    Returns:
        DocIngestResult with processing results
    """
    doc_id = None
    try:
        logger.info(f"Processing file: {filename}")
        # Generate doc_id for this file
        doc_id = generate_doc_id()
        
        # Create working directories: tmp/<corpus_id>/docs/<doc_id>/
        doc_dir = BASE_TMP_DIR / corpus_id / "docs" / doc_id
        pages_dir = doc_dir / "pages"
        images_dir = doc_dir / "images"
        
        pages_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Save uploaded PDF
        pdf_path = doc_dir / "uploaded.pdf"
        logger.info(f"Saving PDF to {pdf_path}")
        with open(pdf_path, "wb") as f:
            f.write(file_content)
        logger.info(f"PDF saved, size: {len(file_content)} bytes")
        
        # Run extraction
        logger.info(f"Starting PDF extraction for {filename}")
        extract_stats = pdf_extract.extract_pdf_to_page_jsons(
            pdf_path=pdf_path,
            out_pages_dir=pages_dir,
            images_dir=images_dir,
            dpi=dpi,
            start_page=start_page,
            end_page=end_page,
            overwrite=overwrite
        )
        logger.info(f"Extraction complete: {extract_stats.get('pages_total', 0)} total pages, {len(extract_stats.get('processed_pages', []))} processed, {len(extract_stats.get('failed_pages', []))} failed")
        
        # Run ingestion with corpus_id
        manifest_path = doc_dir / "supermemory_manifest.json"
        logger.info(f"Starting Supermemory ingestion for {filename}")
        manifest = supermemory_ingest.ingest_pages_dir(
            pages_dir=pages_dir,
            pdf_path=pdf_path,
            doc_id=doc_id,
            manifest_path=manifest_path,
            overwrite=overwrite,
            corpus_id=corpus_id  # Pass corpus_id to include in metadata
        )
        
        # Count successful and failed pages
        pages_ingested = len([p for p in manifest.get('pages', []) if 'error' not in p])
        failed_pages_list = [
            FailedPage(page=fp['page'], error=fp['error'])
            for fp in manifest.get('failed_pages', [])
        ]
        
        # Also include extraction failures
        for fp in extract_stats.get('failed_pages', []):
            if not any(f.page == fp['page'] for f in failed_pages_list):
                failed_pages_list.append(FailedPage(page=fp['page'], error=fp['error']))
        
        logger.info(f"Successfully processed {filename}: {pages_ingested} pages ingested")
        return DocIngestResult(
            doc_id=doc_id,
            pages_total=extract_stats['pages_total'],
            pages_ingested=pages_ingested,
            failed_pages=failed_pages_list
        )
        
    except Exception as e:
        error_msg = f"Error processing {filename if filename else 'unknown file'}: {type(e).__name__}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return DocIngestResult(
            doc_id=doc_id if doc_id else "unknown",
            pages_total=0,
            pages_ingested=0,
            failed_pages=[FailedPage(page=0, error=error_msg)]
        )


@app.post("/ingest-corpus", response_model=CorpusIngestResponse)
async def ingest_corpus(
    files: List[UploadFile] = File(..., description="PDF files to ingest"),
    corpus_id: Optional[str] = Form(default=None),
    dpi: int = Form(default=DEFAULT_DPI),
    start_page: int = Form(default=DEFAULT_START_PAGE),
    end_page: Optional[int] = Form(default=None),
    overwrite: bool = Form(default=False),
    auto_eval: bool = Form(default=False, description="Automatically run evaluation after ingestion"),
    eval_mode: str = Form(default="text_rag", description="Evaluation mode: text_rag, optical, hybrid, or all"),
    eval_judge: str = Form(default="rule", description="Judge type: rule or llm")
):
    """
    Ingest multiple PDF files into a corpus.
    
    Each PDF becomes a separate doc_id within the corpus.
    All pages are ingested into Supermemory with corpus_id in metadata.
    Processes multiple PDFs in parallel for faster ingestion.
    """
    # Generate corpus_id if not provided
    if not corpus_id:
        corpus_id = generate_corpus_id()
    
    # Validate all files are PDFs and read their contents
    file_data = []
    for file in files:
        if not file.filename or not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"File {file.filename} must be a PDF")
        # Read file content asynchronously
        content = await file.read()
        file_data.append({
            'filename': file.filename,
            'content': content
        })
    
    # Process files in parallel using ThreadPoolExecutor
    # Use up to 5 concurrent PDFs (adjust based on system resources and API limits)
    max_parallel_pdfs = 5
    doc_results = []
    total_pages = 0
    
    logger.info(f"Processing {len(file_data)} PDFs with up to {max_parallel_pdfs} concurrent workers")
    
    with ThreadPoolExecutor(max_workers=max_parallel_pdfs) as executor:
        # Submit all PDF processing tasks
        future_to_file = {
            executor.submit(
                _process_single_pdf,
                file_info['content'],
                file_info['filename'],
                corpus_id,
                dpi,
                start_page,
                end_page,
                overwrite
            ): file_info['filename']
            for file_info in file_data
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_file):
            filename = future_to_file[future]
            try:
                result = future.result()
                doc_results.append(result)
                total_pages += result.pages_ingested
            except Exception as e:
                logger.error(f"Unexpected error processing {filename}: {e}", exc_info=True)
                doc_results.append(DocIngestResult(
                    doc_id="unknown",
                    pages_total=0,
                    pages_ingested=0,
                    failed_pages=[FailedPage(page=0, error=f"Unexpected error: {str(e)}")]
                ))
    
    # Create corpus manifest (similar to eval/ingest_corpus.py)
    corpus_dir = OUTPUT_DIR / corpus_id
    corpus_dir.mkdir(parents=True, exist_ok=True)
    
    # Move/copy files from tmp to output structure
    tmp_corpus_dir = BASE_TMP_DIR / corpus_id
    if tmp_corpus_dir.exists():
        import shutil
        output_docs_dir = corpus_dir / "docs"
        if tmp_corpus_dir / "docs" != output_docs_dir:
            if output_docs_dir.exists():
                shutil.rmtree(output_docs_dir)
            shutil.copytree(tmp_corpus_dir / "docs", output_docs_dir, dirs_exist_ok=True)
    
    # Create corpus manifest
    corpus_manifest = {
        "corpus_id": corpus_id,
        "created_at": datetime.now().isoformat(),
        "docs": [
            {
                "doc_id": doc.doc_id,
                "pdf_path": str(OUTPUT_DIR / corpus_id / "docs" / doc.doc_id / "uploaded.pdf"),
                "pages": [{"page": p.page, "error": p.error} for p in doc.failed_pages] if doc.failed_pages else [],
                "failed_pages": [{"page": p.page, "error": p.error} for p in doc.failed_pages]
            }
            for doc in doc_results
        ],
        "total_pages": total_pages
    }
    
    manifest_path = corpus_dir / "corpus_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(corpus_manifest, f, indent=2, ensure_ascii=False)
    
    # Trigger evaluation if requested
    eval_status = None
    eval_run_id = None
    if auto_eval and total_pages > 0:
        eval_result = run_eval_async(
            corpus_id=corpus_id,
            mode=eval_mode,
            judge_mode=eval_judge
        )
        eval_status = eval_result.get("status")
        eval_run_id = eval_result.get("run_id")
    
    return CorpusIngestResponse(
        corpus_id=corpus_id,
        docs=doc_results,
        total_pages=total_pages,
        eval_status=eval_status,
        eval_run_id=eval_run_id
    )


@app.post("/run-eval/{corpus_id}")
async def run_eval_endpoint(
    corpus_id: str,
    mode: str = "text_rag",
    judge: str = "rule"
):
    """
    Trigger evaluation for a corpus.
    
    Args:
        corpus_id: Corpus ID to evaluate
        mode: Evaluation mode (text_rag, optical, hybrid, all) - default: text_rag
        judge: Judge type (rule or llm) - default: rule
        
    Returns:
        dict with status and run_id
    """
    # Validate corpus exists
    corpus_dir = OUTPUT_DIR / corpus_id
    manifest_path = corpus_dir / "corpus_manifest.json"
    
    if not corpus_dir.exists():
        raise HTTPException(status_code=404, detail=f"Corpus {corpus_id} not found")
    
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Corpus manifest not found for {corpus_id}")
    
    # Trigger evaluation
    try:
        eval_result = run_eval_async(
            corpus_id=corpus_id,
            mode=mode,
            judge_mode=judge
        )
        return JSONResponse(content=eval_result)
    except Exception as e:
        logger.error(f"Failed to trigger evaluation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to trigger evaluation: {str(e)}")


@app.get("/eval-results/{corpus_id}")
async def get_eval_results_endpoint(corpus_id: str):
    """
    Get evaluation results for a corpus.
    
    Returns evaluation results if available, or a status indicating results are not ready.
    """
    results = get_eval_results(corpus_id)
    if results is None:
        # Return 200 with status indicating results not ready (instead of 404)
        # This allows frontend to distinguish between "not ready" and "error"
        return JSONResponse(
            status_code=200,
            content={
                "status": "not_ready",
                "message": f"Evaluation results not yet available for corpus {corpus_id}. The evaluation may still be running.",
                "corpus_id": corpus_id
            }
        )
    return JSONResponse(content=results)


@app.get("/page-content/{doc_id}/{page_num}")
async def get_page_content(doc_id: str, page_num: int):
    """
    Get full content from a page JSON file.
    
    Useful for displaying proof/evidence from PDFs.
    """
    # Try tmp directory first (single doc)
    page_json_path = BASE_TMP_DIR / doc_id / "pages" / f"page_{page_num:03d}.json"
    
    # If not found, try corpus structure
    if not page_json_path.exists():
        corpus_dirs = list(OUTPUT_DIR.glob(f"*/docs/*/{doc_id}"))
        if corpus_dirs:
            page_json_path = corpus_dirs[0] / "pages" / f"page_{page_num:03d}.json"
    
    if not page_json_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Page {page_num} JSON file not found for doc {doc_id}"
        )
    
    try:
        with open(page_json_path, 'r', encoding='utf-8') as f:
            page_data = json.load(f)
        
        return JSONResponse(content={
            "page": page_num,
            "doc_id": doc_id,
            "markdown": page_data.get('markdown', ''),
            "summary": page_data.get('summary', ''),
            "entities": page_data.get('entities', []),
            "page_number": page_data.get('page_number', page_num)
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read page content: {str(e)}"
        )


@app.post("/retry-page/{corpus_id}/{doc_id}/{page_num}")
async def retry_failed_page(corpus_id: str, doc_id: str, page_num: int):
    """
    Retry processing a failed page.
    
    Useful for manually retrying pages that failed during ingestion.
    """
    try:
        # Find the PDF file
        doc_dir = OUTPUT_DIR / corpus_id / "docs" / doc_id
        pdf_path = doc_dir / "uploaded.pdf"
        
        if not pdf_path.exists():
            # Try tmp directory
            doc_dir = BASE_TMP_DIR / corpus_id / "docs" / doc_id
            pdf_path = doc_dir / "uploaded.pdf"
        
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail=f"PDF file not found for doc {doc_id}")
        
        pages_dir = doc_dir / "pages"
        images_dir = doc_dir / "images"
        pages_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        
        # Process the page - import the function directly
        from app.pipeline.pdf_extract import _process_single_page
        result = _process_single_page(
            page_num=page_num,
            pdf_path=pdf_path,
            dpi=150,  # Use default DPI
            images_dir=images_dir,
            pages_dir=pages_dir,
            overwrite=True  # Overwrite existing
        )
        
        success, error, json_data = result
        
        if success:
            # Also try to ingest to Supermemory
            from app.pipeline import supermemory_ingest
            manifest_path = doc_dir / "supermemory_manifest.json"
            # This will update the manifest with the new page
            try:
                supermemory_ingest.ingest_pages_dir(
                    pages_dir=pages_dir,
                    pdf_path=pdf_path,
                    doc_id=doc_id,
                    manifest_path=manifest_path,
                    overwrite=False,  # Don't overwrite existing pages
                    corpus_id=corpus_id
                )
            except Exception as ingest_error:
                logger.warning(f"Page {page_num} processed but ingestion failed: {ingest_error}")
            
            return JSONResponse(content={
                "success": True,
                "message": f"Page {page_num} processed successfully",
                "page_data": json_data
            })
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": error or "Unknown error"
                }
            )
    except Exception as e:
        logger.error(f"Failed to retry page {page_num}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retry page: {str(e)}")


@app.post("/ingest-optical-lite", response_model=OpticalLiteIngestResponse)
async def ingest_optical_lite(request: OpticalLiteIngestRequest):
    """
    Ingest pages using optical-lite mode: store ONLY minimal metadata + image references.
    
    This endpoint expects pages to already be extracted (use /ingest first to extract pages).
    Then call this endpoint to ingest using the storage-minimized optical-lite mode.
    
    Process:
    1. Parse page JSONs from pages_dir
    2. Extract minimal metadata (summary ≤400 chars, title ≤120 chars, limited entities)
    3. Create Supermemory items with index strings (no full markdown)
    4. Save manifest to output/optical_lite/<doc_id>/optical_lite_manifest.json
    """
    # Resolve paths relative to backend directory
    pages_dir = Path(request.pages_dir)
    images_dir = Path(request.images_dir)
    
    # If relative paths, try common locations
    if not pages_dir.is_absolute():
        # Try tmp/<doc_id>/pages first
        tmp_pages_dir = BASE_TMP_DIR / request.doc_id / "pages"
        if tmp_pages_dir.exists():
            pages_dir = tmp_pages_dir
        elif not pages_dir.exists():
            # Try as-is relative to backend
            pages_dir = Path(request.pages_dir)
    
    if not images_dir.is_absolute():
        # Try tmp/<doc_id>/images first
        tmp_images_dir = BASE_TMP_DIR / request.doc_id / "images"
        if tmp_images_dir.exists():
            images_dir = tmp_images_dir
        elif not images_dir.exists():
            # Try as-is relative to backend
            images_dir = Path(request.images_dir)
    
    # Validate paths exist
    if not pages_dir.exists():
        raise HTTPException(status_code=400, detail=f"Pages directory not found: {pages_dir}")
    if not images_dir.exists():
        raise HTTPException(status_code=400, detail=f"Images directory not found: {images_dir}")
    
    # Resolve PDF path if provided
    pdf_path = None
    if request.pdf_path:
        pdf_path = Path(request.pdf_path)
        if not pdf_path.is_absolute():
            # Try tmp/<doc_id>/uploaded.pdf
            tmp_pdf = BASE_TMP_DIR / request.doc_id / "uploaded.pdf"
            if tmp_pdf.exists():
                pdf_path = tmp_pdf
            elif not pdf_path.exists():
                pdf_path = Path(request.pdf_path)
    
    # Run optical-lite ingestion
    try:
        manifest = optical_lite_ingest.ingest_optical_lite(
            doc_id=request.doc_id,
            pages_dir=str(pages_dir),
            images_dir=str(images_dir),
            pdf_path=str(pdf_path) if pdf_path else None,
            corpus_id=request.corpus_id,
            render_config=request.render_config,
            overwrite=request.overwrite
        )
    except Exception as e:
        logger.error(f"Optical-lite ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Optical-lite ingestion failed: {e}")
    
    # Count successful and failed pages
    pages_ingested = len([p for p in manifest.get('pages', []) if 'error' not in p])
    failed_pages_list = [
        FailedPage(page=fp['page'], error=fp['error'])
        for fp in manifest.get('failed_pages', [])
    ]
    
    manifest_path = Path("output") / "optical_lite" / request.doc_id / "optical_lite_manifest.json"
    
    return OpticalLiteIngestResponse(
        doc_id=request.doc_id,
        pages_ingested=pages_ingested,
        failed_pages=failed_pages_list,
        manifest_path=str(manifest_path)
    )


@app.post("/chat-optical-lite", response_model=OpticalLiteChatResponse)
async def chat_optical_lite(request: OpticalLiteChatRequest):
    """
    Answer a question using optical-lite mode: retrieve pages from minimal index and use images as context.
    
    Process:
    1. Query Supermemory using the question, filtered by doc_id (and corpus_id if present)
    2. Select top pages (dedupe) up to max_images
    3. Load PNG image bytes for each selected page
    4. Call Vertex AI Gemini with images as context
    5. Return answer with citations in format: (DOC_ID p.PAGE_NUMBER)
    """
    try:
        result = optical_lite_qa.answer_optical_lite(
            doc_id=request.doc_id,
            question=request.question,
            top_k=request.top_k,
            max_images=request.max_images,
            corpus_id=request.corpus_id
        )
    except Exception as e:
        logger.error(f"Optical-lite QA failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Optical-lite QA failed: {e}")
    
    # Convert retrieved list to schema
    retrieved_list = [
        OpticalLiteRetrievedPage(
            page=r['page'],
            supermemory_id=r['supermemory_id'],
            image_path=r['image_path'],
            error=r.get('error')
        )
        for r in result['retrieved']
    ]
    
    return OpticalLiteChatResponse(
        doc_id=request.doc_id,
        answer_md=result['answer_md'],
        retrieved=retrieved_list
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

