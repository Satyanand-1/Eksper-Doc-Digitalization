from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.jwt import create_access_token
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.security import verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user with email and password.
    Returns signed Bearer JWT access token upon successful authentication.
    Returns HTTP 401 with generic error for nonexistent users, bad passwords, or inactive accounts.
    """
    # Normalize email to match User model normalization
    normalized_email = login_data.email.strip().lower()

    # Generic unauthorized exception to prevent user enumeration
    invalid_credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = db.query(User).filter(User.email == normalized_email).first()
    if user is None:
        raise invalid_credentials_exception

    if not verify_password(login_data.password, user.hashed_password):
        raise invalid_credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Issue signed access token
    token = create_access_token(user_id=user.id)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in_seconds,
    )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Retrieve current authenticated user profile and permissions.
    Requires valid Bearer access token in Authorization header.
    """
    return current_user
