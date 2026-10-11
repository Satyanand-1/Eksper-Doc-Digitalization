import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from app.models.user import UserRole

class EligibleApproverResponse(BaseModel):
    """
    Safe display schema for eligible approver selection.
    Strictly excludes sensitive attributes (password hash, roles, tokens, etc.).
    """
    id: uuid.UUID = Field(..., description="Unique UUID of the approver user")
    email: str = Field(..., description="Approver email address")
    full_name: str = Field(..., description="Approver full display name")
    department: str = Field(..., description="Approver department")

    model_config = ConfigDict(from_attributes=True)

class AdminUserResponse(BaseModel):
    """
    Safe user administration response schema.
    Never exposes passwords, password hashes, or token secrets.
    """
    id: uuid.UUID = Field(..., description="Unique UUID of the user")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="Full display name")
    department: str | None = Field(None, description="Assigned department")
    role: UserRole = Field(..., description="Assigned role")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    updated_at: datetime = Field(..., description="Last updated timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)

class PaginatedUsersResponse(BaseModel):
    """
    Paginated user listing response for admin directory.
    """
    items: list[AdminUserResponse] = Field(..., description="List of user records on current page")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Page size limit")
    total: int = Field(..., description="Total count of matching users")
    total_pages: int = Field(..., description="Total pages available")

    model_config = ConfigDict(from_attributes=True)

class UserCreateRequest(BaseModel):
    """
    Administrator payload for creating a new user account.
    """
    full_name: str = Field(..., min_length=1, max_length=255, description="Full display name")
    email: EmailStr = Field(..., description="Unique email address")
    role: UserRole = Field(..., description="Assigned user role")
    department: str | None = Field(None, max_length=100, description="Department assignment")
    password: str = Field(..., min_length=8, max_length=128, description="Initial plaintext password")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Full name cannot be empty or whitespace only")
        return s

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            return s if s else None
        return None

class UserUpdateRequest(BaseModel):
    """
    Administrator payload for updating profile fields, department, and role.
    Does not permit updating passwords, tokens, or immutable IDs.
    """
    full_name: str | None = Field(None, min_length=1, max_length=255, description="Updated full display name")
    department: str | None = Field(None, max_length=100, description="Updated department")
    role: UserRole | None = Field(None, description="Updated user role")

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Full name cannot be empty or whitespace only")
            return s
        return None

    @field_validator("department")
    @classmethod
    def validate_department(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            return s if s else None
        return None

class UserStatusUpdateRequest(BaseModel):
    """
    Administrator payload for activating or deactivating a user account.
    """
    is_active: bool = Field(..., description="New account active status")
