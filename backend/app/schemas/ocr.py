import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.ocr_job import OCRJobStatus

class OCRJobResponse(BaseModel):
    """
    Operational metadata for an asynchronous durable OCR processing job.
    Does not expose extracted text, file binaries, internal storage paths, or sensitive credentials.
    """
    id: uuid.UUID = Field(..., description="Unique job identifier")
    document_version_id: uuid.UUID = Field(..., description="Associated document version identifier")
    status: OCRJobStatus = Field(..., description="Current job status: queued, running, completed, or failed")
    attempt_count: int = Field(..., description="Number of attempted executions")
    max_attempts: int = Field(..., description="Maximum allowed attempts")
    created_at: datetime = Field(..., description="Job creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last updated timestamp in UTC")
    next_retry_at: datetime | None = Field(None, description="Next retry timestamp in UTC")
    started_at: datetime | None = Field(None, description="Execution start timestamp in UTC")
    completed_at: datetime | None = Field(None, description="Completion timestamp in UTC")
    last_error: str | None = Field(None, description="Sanitized failure code or error message")

    model_config = ConfigDict(from_attributes=True)

class PaginatedOCRJobResponse(BaseModel):
    """
    Paginated response container for OCR jobs.
    """
    items: list[OCRJobResponse] = Field(..., description="OCR jobs on the current page")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Page size limit")
    total: int = Field(..., description="Total matching OCR jobs")
    total_pages: int = Field(..., description="Total pages available")

    model_config = ConfigDict(from_attributes=True)
