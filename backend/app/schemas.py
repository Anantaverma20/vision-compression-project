"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel, Field, model_validator
from typing import List, Optional


class ChatRequest(BaseModel):
    """Request schema for /chat endpoint."""
    doc_id: Optional[str] = Field(default=None, description="Document ID (for single document queries)")
    corpus_id: Optional[str] = Field(default=None, description="Corpus ID (for multi-document queries)")
    question: str = Field(..., description="Question to answer")
    top_k: int = Field(default=8, ge=1, le=50, description="Number of top results to retrieve")
    max_chars_per_page: int = Field(default=1500, ge=100, le=10000, description="Maximum characters per page in evidence pack")
    
    @model_validator(mode='after')
    def validate_doc_or_corpus(self):
        """Ensure either doc_id or corpus_id is provided."""
        if not self.doc_id and not self.corpus_id:
            raise ValueError("Either doc_id or corpus_id must be provided")
        return self


class RetrievedPage(BaseModel):
    """Schema for a retrieved page in chat response."""
    page: int = Field(..., description="Page number")
    memory_id: str = Field(..., description="Supermemory memory ID")
    excerpt: str = Field(..., description="Excerpt from the page (first 250 chars)")
    full_content: Optional[str] = Field(default=None, description="Full content from the page JSON file")


class ChatResponse(BaseModel):
    """Response schema for /chat endpoint."""
    doc_id: str = Field(..., description="Document ID")
    answer_md: str = Field(..., description="Answer in markdown format with citations")
    retrieved: List[RetrievedPage] = Field(..., description="List of retrieved pages")


class FailedPage(BaseModel):
    """Schema for a failed page in ingest response."""
    page: int = Field(..., description="Page number")
    error: str = Field(..., description="Error message")


class IngestResponse(BaseModel):
    """Response schema for /ingest endpoint."""
    doc_id: str = Field(..., description="Generated document ID")
    pages_total: int = Field(..., description="Total number of pages processed")
    pages_ingested: int = Field(..., description="Number of successfully ingested pages")
    failed_pages: List[FailedPage] = Field(default_factory=list, description="List of failed pages")
    manifest_path: str = Field(..., description="Path to supermemory manifest file")


class HealthResponse(BaseModel):
    """Response schema for /health endpoint."""
    ok: bool = Field(..., description="Health status")


class DocIngestResult(BaseModel):
    """Result for a single document in corpus ingestion."""
    doc_id: str = Field(..., description="Document ID")
    pages_total: int = Field(..., description="Total number of pages processed")
    pages_ingested: int = Field(..., description="Number of successfully ingested pages")
    failed_pages: List[FailedPage] = Field(default_factory=list, description="List of failed pages")


class CorpusIngestResponse(BaseModel):
    """Response schema for /ingest-corpus endpoint."""
    corpus_id: str = Field(..., description="Corpus ID")
    docs: List[DocIngestResult] = Field(..., description="List of document ingestion results")
    total_pages: int = Field(..., description="Total pages ingested across all documents")
    eval_status: Optional[str] = Field(default=None, description="Evaluation status if auto_eval was enabled")
    eval_run_id: Optional[str] = Field(default=None, description="Evaluation run ID if auto_eval was enabled")


class OpticalLiteIngestRequest(BaseModel):
    """Request schema for /ingest-optical-lite endpoint."""
    doc_id: str = Field(..., description="Document ID")
    pages_dir: str = Field(..., description="Directory containing page_###.json files (relative to backend/)")
    images_dir: str = Field(..., description="Directory containing page_###.png files (relative to backend/)")
    pdf_path: Optional[str] = Field(default=None, description="Path to original PDF file")
    corpus_id: Optional[str] = Field(default=None, description="Corpus ID")
    overwrite: bool = Field(default=False, description="Overwrite existing ingested pages")
    render_config: Optional[dict] = Field(default=None, description="Render configuration dict")


class OpticalLiteIngestResponse(BaseModel):
    """Response schema for /ingest-optical-lite endpoint."""
    doc_id: str = Field(..., description="Document ID")
    pages_ingested: int = Field(..., description="Number of successfully ingested pages")
    failed_pages: List[FailedPage] = Field(default_factory=list, description="List of failed pages")
    manifest_path: str = Field(..., description="Path to optical-lite manifest file")


class OpticalLiteChatRequest(BaseModel):
    """Request schema for /chat-optical-lite endpoint."""
    doc_id: str = Field(..., description="Document ID")
    question: str = Field(..., description="Question to answer")
    corpus_id: Optional[str] = Field(default=None, description="Corpus ID")
    top_k: int = Field(default=8, ge=1, le=50, description="Number of top results to retrieve")
    max_images: int = Field(default=6, ge=1, le=20, description="Maximum number of images to send to Gemini")


class OpticalLiteRetrievedPage(BaseModel):
    """Schema for a retrieved page in optical-lite chat response."""
    page: int = Field(..., description="Page number")
    supermemory_id: str = Field(..., description="Supermemory memory ID")
    image_path: str = Field(..., description="Path to page image file")
    error: Optional[str] = Field(default=None, description="Error message if image loading failed")


class OpticalLiteChatResponse(BaseModel):
    """Response schema for /chat-optical-lite endpoint."""
    doc_id: str = Field(..., description="Document ID")
    answer_md: str = Field(..., description="Answer in markdown format with citations")
    retrieved: List[OpticalLiteRetrievedPage] = Field(..., description="List of retrieved pages")