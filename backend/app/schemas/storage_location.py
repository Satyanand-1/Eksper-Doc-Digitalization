import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.storage_location import LocationType


class LocationUserShortInfo(BaseModel):
    """User summary for storage location creator/updater."""
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None

    model_config = ConfigDict(from_attributes=True)


class StorageLocationBreadcrumb(BaseModel):
    """Single node in the storage location hierarchy path."""
    id: uuid.UUID
    location_code: str
    name: str
    location_type: LocationType

    model_config = ConfigDict(from_attributes=True)


class StorageLocationCreateRequest(BaseModel):
    """Request schema for creating a storage location."""
    location_code: str = Field(..., min_length=2, max_length=64, description="Unique location code (e.g. LOC-BLD-01)")
    name: str = Field(..., min_length=1, max_length=255, description="Location name (e.g. Main Records Room)")
    location_type: LocationType = Field(..., description="Location hierarchy type")
    description: str | None = Field(None, max_length=1000, description="Optional description")
    department: str = Field(..., min_length=1, max_length=100, description="Owning department")
    parent_id: uuid.UUID | None = Field(None, description="Optional parent storage location UUID")
    max_capacity: int | None = Field(None, ge=1, le=100000, description="Optional maximum direct physical files capacity")


class StorageLocationUpdateRequest(BaseModel):
    """Request schema for updating storage location metadata or parent."""
    name: str | None = Field(None, min_length=1, max_length=255, description="Updated location name")
    description: str | None = Field(None, max_length=1000, description="Updated description")
    location_type: LocationType | None = Field(None, description="Updated location type")
    parent_id: uuid.UUID | None = Field(None, description="Updated parent location UUID")
    clear_parent: bool = Field(False, description="Set True to promote location to top-level (remove parent)")
    max_capacity: int | None = Field(None, ge=1, le=100000, description="Updated maximum capacity")
    clear_max_capacity: bool = Field(False, description="Set True to remove maximum capacity limit")
    department: str | None = Field(None, min_length=1, max_length=100, description="Updated department (Admin/Records Officer only)")


class StorageLocationStatusRequest(BaseModel):
    """Request schema for activating or deactivating a storage location."""
    is_active: bool = Field(..., description="Target active state (True to activate, False to deactivate)")
    reason: str | None = Field(None, max_length=500, description="Optional justification for status change")


class StorageLocationSummaryResponse(BaseModel):
    """Summary item for storage location listings and hierarchy trees."""
    id: uuid.UUID
    location_code: str
    name: str
    location_type: LocationType
    department: str
    parent_id: uuid.UUID | None = None
    is_active: bool
    max_capacity: int | None = None
    direct_file_count: int = 0
    child_count: int = 0
    location_path: str = ""
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StorageLocationDetailResponse(BaseModel):
    """Detailed view for a single storage location."""
    id: uuid.UUID
    location_code: str
    name: str
    location_type: LocationType
    description: str | None = None
    department: str
    parent_id: uuid.UUID | None = None
    parent: StorageLocationSummaryResponse | None = None
    is_active: bool
    max_capacity: int | None = None
    direct_file_count: int = 0
    child_count: int = 0
    location_path: str = ""
    breadcrumbs: list[StorageLocationBreadcrumb] = []
    created_by_id: uuid.UUID
    created_by: LocationUserShortInfo | None = None
    updated_by_id: uuid.UUID | None = None
    updated_by: LocationUserShortInfo | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedStorageLocationsResponse(BaseModel):
    """Paginated response for storage locations."""
    items: list[StorageLocationSummaryResponse]
    page: int
    page_size: int
    total: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)


class AssignFileLocationRequest(BaseModel):
    """Request schema for assigning or reassigning a physical file's storage location."""
    storage_location_id: uuid.UUID | None = Field(None, description="Destination storage location UUID, or null to unassign")
    notes: str | None = Field(None, max_length=500, description="Optional assignment notes or reason")
