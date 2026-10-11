import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.physical_file import PhysicalRecordType, PhysicalFileStatus


class UserShortInfo(BaseModel):
    """User minimal info for physical file creator/updater."""
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LinkedDigitalDocumentInfo(BaseModel):
    """Minimal linked digital document metadata."""
    id: uuid.UUID
    document_reference: str
    title: str
    department: str
    classification: str

    model_config = ConfigDict(from_attributes=True)


class PhysicalFileRegisterRequest(BaseModel):
    """Request schema for registering a new physical file."""
    title: str = Field(..., min_length=1, max_length=255, description="Physical file title")
    description: str | None = Field(None, max_length=2000, description="Optional description or summary")
    record_type: PhysicalRecordType = Field(..., description="Physical record type")
    department: str = Field(..., min_length=1, max_length=100, description="Owning department")
    classification: str | None = Field(None, max_length=100, description="Optional classification (e.g., Confidential, Public)")
    digital_document_id: uuid.UUID | None = Field(None, description="Optional linked digital document UUID")
    storage_location_id: uuid.UUID | None = Field(None, description="Optional storage location UUID")
    external_reference: str | None = Field(None, max_length=100, description="Optional external reference number")
    date_received: datetime | None = Field(None, description="Date received or registered in UTC (defaults to now)")


class PhysicalFileUpdateRequest(BaseModel):
    """Request schema for updating physical file metadata."""
    title: str | None = Field(None, min_length=1, max_length=255, description="Updated file title")
    description: str | None = Field(None, max_length=2000, description="Updated description")
    record_type: PhysicalRecordType | None = Field(None, description="Updated record type")
    department: str | None = Field(None, min_length=1, max_length=100, description="Updated department (Admin/Records Officer only)")
    classification: str | None = Field(None, max_length=100, description="Updated classification")
    digital_document_id: uuid.UUID | None = Field(None, description="Updated linked digital document UUID")
    unlink_digital_document: bool = Field(False, description="Set True to explicitly unlink digital document")
    storage_location_id: uuid.UUID | None = Field(None, description="Updated storage location UUID")
    unlink_storage_location: bool = Field(False, description="Set True to remove storage location assignment")
    external_reference: str | None = Field(None, max_length=100, description="Updated external reference")
    date_received: datetime | None = Field(None, description="Updated date received")


class PhysicalFileStatusChangeRequest(BaseModel):
    """Request schema for transitioning physical file status."""
    status: PhysicalFileStatus = Field(..., description="Target status: active, archived, or inactive")
    reason: str | None = Field(None, max_length=500, description="Optional justification for the transition")


class PhysicalFileSummaryResponse(BaseModel):
    """Summary item for physical file listings."""
    id: uuid.UUID
    file_reference: str
    title: str
    record_type: PhysicalRecordType
    department: str
    classification: str | None = None
    status: PhysicalFileStatus
    has_digital_document: bool = False
    is_checked_out: bool = False
    current_custodian_name: str | None = None
    is_overdue: bool = False
    storage_location_id: uuid.UUID | None = None
    storage_location_name: str | None = None
    storage_location_code: str | None = None
    location_path: str | None = None
    external_reference: str | None = None
    date_received: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PhysicalFileDetailResponse(BaseModel):
    """Full detail view for a physical file record."""
    id: uuid.UUID
    file_reference: str
    title: str
    description: str | None = None
    record_type: PhysicalRecordType
    department: str
    classification: str | None = None
    status: PhysicalFileStatus
    is_checked_out: bool = False
    current_custodian_name: str | None = None
    is_overdue: bool = False
    current_custody_id: uuid.UUID | None = None
    checked_out_at: datetime | None = None
    expected_return_at: datetime | None = None
    digital_document_id: uuid.UUID | None = None
    digital_document: LinkedDigitalDocumentInfo | None = None
    storage_location_id: uuid.UUID | None = None
    storage_location_name: str | None = None
    storage_location_code: str | None = None
    location_path: str | None = None
    external_reference: str | None = None
    date_received: datetime
    created_by_id: uuid.UUID
    created_by: UserShortInfo | None = None
    updated_by_id: uuid.UUID | None = None
    updated_by: UserShortInfo | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedPhysicalFilesResponse(BaseModel):
    """Paginated list response for physical files."""
    items: list[PhysicalFileSummaryResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class LabelPrintAuditRequest(BaseModel):
    """Payload to log label generation / printing for physical files."""
    file_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100, description="List of physical file IDs printed")
    label_format: str = Field("standard_label", max_length=50, description="Label design format used")
