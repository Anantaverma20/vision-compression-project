"""Pydantic schemas for API request/response models."""

from pydantic import BaseModel, Field
from typing import List, Optional


class ChatRequest(BaseModel):
    """Request schema for /chat endpoint."""
    doc_id: str = Field(..., description="Document ID")
    question: str = Field(..., description="Question to answer")
    top_k: int = Field(default=8, ge=1, le=50, description="Number of top results to retrieve")
    max_chars_per_page: int = Field(default=1500, ge=100, le=10000, description="Maximum characters per page in evidence pack")


class RetrievedPage(BaseModel):
    """Schema for a retrieved page in chat response."""
    page: int = Field(..., description="Page number")
    memory_id: str = Field(..., description="Supermemory memory ID")
    excerpt: str = Field(..., description="Excerpt from the page (first 250 chars)")


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

