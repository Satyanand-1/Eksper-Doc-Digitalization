import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.user import UserRole

class LoginRequest(BaseModel):
    """Credentials payload for POST /api/v1/auth/login."""
    email: EmailStr = Field(..., description="User registered email address")
    password: str = Field(..., min_length=1, max_length=128, description="User password")

class TokenResponse(BaseModel):
    """Bearer token payload returned upon successful login."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Expiration lifetime in seconds")

class UserResponse(BaseModel):
    """Current authenticated user profile returned by GET /api/v1/auth/me."""
    id: uuid.UUID
    email: str
    full_name: str
    department: str | None = None
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
