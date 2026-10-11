import uuid
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.jwt import decode_access_token
from app.models.user import User

# HTTP Bearer scheme auto-extracts Bearer tokens from the Authorization header
security_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    token_query: str | None = Query(None, alias="token"),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency that authenticates requests using Bearer JWT.
    Validates token signature, expiration, and user active status in PostgreSQL.
    Accepts token via Authorization: Bearer header, or via ?token= query parameter (for direct browser preview/download tabs).
    Rejects missing, expired, invalid tokens, or inactive users with HTTP 401.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials if credentials else token_query
    if not token:
        raise credentials_exception
    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
