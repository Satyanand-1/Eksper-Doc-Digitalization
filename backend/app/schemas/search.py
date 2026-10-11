import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.document import DocumentStatus

class SearchItemMatch(BaseModel):
    """
    Detailed search result for a matching document.
    Does not expose sensitive system attributes, absolute file paths, or binary storage keys.
    """
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
    matching_version_numbers: list[int] = Field(default_factory=list, description="List of matching version numbers for this document")
    snippet: str | None = Field(None, description="Sanitized excerpt illustrating matched content or metadata")
    relevance_score: float = Field(..., description="Computed relevance rank score")

    model_config = ConfigDict(from_attributes=True)

class PaginatedSearchResponse(BaseModel):
    """
    Paginated search response envelope.
    """
    items: list[SearchItemMatch] = Field(..., description="Matching authorized document items on the current page")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Page size limit")
    total: int = Field(..., description="Total count of authorized matching documents")
    total_pages: int = Field(..., description="Total pages available")

    model_config = ConfigDict(from_attributes=True)
