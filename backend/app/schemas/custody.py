import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.custody import CustodyStatus, PhysicalMovementType
from app.schemas.physical_file import UserShortInfo


class CustodyCheckoutRequest(BaseModel):
    """Request schema for checking out a physical file."""
    custodian_user_id: uuid.UUID | None = Field(None, description="Optional registered EDRMS user ID of recipient")
    custodian_name: str = Field(..., min_length=1, max_length=255, description="Full name of custodian / recipient")
    custodian_department: str | None = Field(None, max_length=100, description="Department of custodian")
    custodian_contact: str | None = Field(None, max_length=255, description="Phone, email, or contact details")
    purpose: str = Field(..., min_length=1, max_length=2000, description="Checkout purpose / business reason")
    expected_return_at: datetime | None = Field(None, description="Optional expected return timestamp in UTC")


class CustodyCheckinRequest(BaseModel):
    """Request schema for checking in a physical file."""
    destination_location_id: uuid.UUID | None = Field(None, description="Optional destination storage location UUID. If omitted, file returns to its previous storage location.")
    checkin_notes: str | None = Field(None, max_length=2000, description="Optional condition, return notes, or remarks")


class FileTransferRequest(BaseModel):
    """Request schema for transferring a physical file between storage locations."""
    destination_location_id: uuid.UUID = Field(..., description="Target active storage location UUID")
    reason: str = Field(..., min_length=1, max_length=2000, description="Transfer reason / operational justification")


class CustodyRecordResponse(BaseModel):
    """Detail view for a custody record."""
    id: uuid.UUID
    physical_file_id: uuid.UUID
    file_reference: str | None = None
    file_title: str | None = None
    custodian_user_id: uuid.UUID | None = None
    custodian_name: str
    custodian_department: str | None = None
    custodian_contact: str | None = None
    status: CustodyStatus
    checked_out_at: datetime
    expected_return_at: datetime | None = None
    checked_in_at: datetime | None = None
    purpose: str
    checkin_notes: str | None = None
    issued_by_id: uuid.UUID
    issued_by: UserShortInfo | None = None
    received_by_id: uuid.UUID | None = None
    received_by: UserShortInfo | None = None
    is_overdue: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MovementHistoryResponse(BaseModel):
    """Detail view for a movement history event."""
    id: uuid.UUID
    physical_file_id: uuid.UUID
    movement_type: PhysicalMovementType
    source_location_id: uuid.UUID | None = None
    source_location_code: str | None = None
    source_location_name: str | None = None
    destination_location_id: uuid.UUID | None = None
    destination_location_code: str | None = None
    destination_location_name: str | None = None
    from_custody_state: str | None = None
    to_custody_state: str | None = None
    actor_id: uuid.UUID
    actor: UserShortInfo | None = None
    event_at: datetime
    reason: str
    custody_record_id: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedCustodyRecordsResponse(BaseModel):
    """Paginated list of custody records."""
    items: list[CustodyRecordResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class PaginatedMovementHistoryResponse(BaseModel):
    """Paginated list of movement history events."""
    items: list[MovementHistoryResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class OverdueFileSummary(BaseModel):
    """Summary of an overdue physical file with active custody info."""
    physical_file_id: uuid.UUID
    file_reference: str
    title: str
    department: str
    classification: str | None = None
    custody_record_id: uuid.UUID
    custodian_name: str
    custodian_department: str | None = None
    custodian_contact: str | None = None
    checked_out_at: datetime
    expected_return_at: datetime
    days_overdue: int
    purpose: str
    storage_location_name: str | None = None
    storage_location_code: str | None = None
    issued_by: UserShortInfo | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedOverdueFilesResponse(BaseModel):
    """Paginated list of overdue physical files."""
    items: list[OverdueFileSummary]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class CustodyIntegrityIssue(BaseModel):
    """Diagnostic detail of an identified chain-of-custody inconsistency."""
    issue_type: str = Field(..., description="Machine-readable code for the inconsistency")
    severity: str = Field(..., description="Severity level: error, warning")
    physical_file_id: uuid.UUID = Field(..., description="Target physical file UUID")
    file_reference: str = Field(..., description="Human-readable file reference number")
    title: str = Field(..., description="File title")
    department: str = Field(..., description="File department")
    description: str = Field(..., description="Human-readable explanation of the detected anomaly")
    diagnostic_details: dict = Field(default_factory=dict, description="Safe diagnostic information")
    detected_at: datetime = Field(..., description="Timestamp when verification was run")

    model_config = ConfigDict(from_attributes=True)


class CustodyIntegrityReport(BaseModel):
    """Summary and itemized report of chain-of-custody integrity verification."""
    total_files_scanned: int
    total_issues_found: int
    issues_by_type: dict[str, int]
    items: list[CustodyIntegrityIssue]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class LocationTransferEventItem(BaseModel):
    """Item detail for storage location transfers governance reporting."""
    movement_id: uuid.UUID
    physical_file_id: uuid.UUID
    file_reference: str
    title: str
    department: str
    source_location_code: str | None = None
    source_location_name: str | None = None
    destination_location_code: str | None = None
    destination_location_name: str | None = None
    transferred_at: datetime
    reason: str
    transferred_by: UserShortInfo | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedLocationTransfersResponse(BaseModel):
    """Paginated list of location transfers over a date range."""
    items: list[LocationTransferEventItem]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)

