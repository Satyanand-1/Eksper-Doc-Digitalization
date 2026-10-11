import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.document import DocumentStatus, ExtractionStatus

class DocumentUploadResponse(BaseModel):
    """Structured response for successful document upload."""
    document_id: uuid.UUID = Field(..., description="Unique UUID of the logical DigitalDocument")
    document_reference: str = Field(..., description="Unique human-readable reference code")
    version_id: uuid.UUID = Field(..., description="Unique UUID of the initial DocumentVersion")
    version_number: int = Field(..., description="Sequence version number (1 for initial upload)")
    title: str = Field(..., description="Document title")
    subject: str | None = Field(None, description="Optional subject/abstract")
    department: str = Field(..., description="Responsible department")
    classification: str = Field(..., description="Document classification")
    original_filename: str = Field(..., description="Sanitized original filename")
    mime_type: str = Field(..., description="Verified MIME type")
    file_size_bytes: int = Field(..., description="Exact file size in bytes")
    file_hash_sha256: str = Field(..., description="Cryptographic SHA-256 checksum")
    created_at: datetime = Field(..., description="Upload timestamp in UTC")
    status: DocumentStatus = Field(..., description="Processing and lifecycle status")
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.PENDING, description="Initial OCR/text extraction status")

    model_config = ConfigDict(from_attributes=True)

class CreatorInfo(BaseModel):
    """Safe, non-sensitive creator presentation model."""
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None

    model_config = ConfigDict(from_attributes=True)

class DocumentSummaryResponse(BaseModel):
    """Lightweight summary model for repository listings."""
    id: uuid.UUID = Field(..., description="Document unique identifier")
    document_reference: str = Field(..., description="Human-readable document reference code")
    title: str = Field(..., description="Document title")
    subject: str | None = Field(None, description="Document subject or summary")
    department: str = Field(..., description="Owning department")
    classification: str = Field(..., description="Classification category")
    mime_type: str = Field(..., description="MIME type")
    status: DocumentStatus = Field(..., description="Document lifecycle status")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last updated timestamp in UTC")
    version_count: int = Field(1, description="Number of registered document versions")

    model_config = ConfigDict(from_attributes=True)

class DocumentDetailResponse(BaseModel):
    """Detailed metadata model for single document retrieval."""
    id: uuid.UUID = Field(..., description="Document unique identifier")
    document_reference: str = Field(..., description="Human-readable document reference code")
    title: str = Field(..., description="Document title")
    subject: str | None = Field(None, description="Document subject or summary")
    department: str = Field(..., description="Owning department")
    classification: str = Field(..., description="Classification category")
    mime_type: str = Field(..., description="MIME type")
    status: DocumentStatus = Field(..., description="Document lifecycle status")
    created_by_id: uuid.UUID = Field(..., description="Creator user UUID")
    creator: CreatorInfo | None = Field(None, description="Creator user details")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last updated timestamp in UTC")
    archived_at: datetime | None = Field(None, description="Archival timestamp if archived")
    retention_rule_id: uuid.UUID | None = Field(None, description="Assigned retention rule ID")
    retention_start_date: datetime | None = Field(None, description="Retention calculated start date")
    retention_end_date: datetime | None = Field(None, description="Retention calculated expiry date")
    available_versions: list[int] = Field(default_factory=list, description="List of available version numbers")
    version_count: int = Field(0, description="Total number of versions")

    model_config = ConfigDict(from_attributes=True)

class DocumentVersionResponse(BaseModel):
    """Metadata model for a document version revision."""
    id: uuid.UUID = Field(..., description="Version unique identifier")
    document_id: uuid.UUID = Field(..., description="Parent document UUID")
    version_number: int = Field(..., description="Sequential version number")
    original_filename: str = Field(..., description="Original user filename")
    mime_type: str = Field(..., description="MIME type of this version")
    file_size_bytes: int = Field(..., description="File size in bytes")
    file_hash_sha256: str = Field(..., description="SHA-256 cryptographic checksum")
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.PENDING, description="OCR text extraction status")
    extraction_completed_at: datetime | None = Field(None, description="Timestamp when text extraction completed")
    extraction_error: str | None = Field(None, description="Sanitized error description if extraction failed")
    extracted_text: str | None = Field(None, description="Extracted OCR text content")
    created_by_id: uuid.UUID = Field(..., description="User UUID who uploaded this version")
    creator: CreatorInfo | None = Field(None, description="Creator user details")
    created_at: datetime = Field(..., description="Upload timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)

class PaginatedDocumentResponse(BaseModel):
    """Paginated document listing response."""
    items: list[DocumentSummaryResponse] = Field(..., description="List of authorized documents on current page")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Page size limit")
    total: int = Field(..., description="Total count of authorized matching documents")
    total_pages: int = Field(..., description="Total pages available")

    model_config = ConfigDict(from_attributes=True)

class VersionUploadResponse(BaseModel):
    """Structured response for successful new version upload."""
    document_id: uuid.UUID = Field(..., description="UUID of the parent DigitalDocument")
    document_reference: str = Field(..., description="Unique human-readable reference code")
    version_id: uuid.UUID = Field(..., description="Unique UUID of the newly uploaded DocumentVersion")
    version_number: int = Field(..., description="Assigned sequential version number")
    original_filename: str = Field(..., description="Sanitized original filename")
    mime_type: str = Field(..., description="Verified MIME type")
    file_size_bytes: int = Field(..., description="Exact file size in bytes")
    file_hash_sha256: str = Field(..., description="Cryptographic SHA-256 checksum")
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.PENDING, description="Initial OCR/text extraction status")
    created_at: datetime = Field(..., description="Version upload timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)


