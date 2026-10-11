import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
import jwt
from app.config import settings

def create_access_token(
    user_id: uuid.UUID,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Creates a signed JWT access token.
    Contains subject (user_id), issued-at (iat), expiration (exp),
    token-id (jti), and type (access).
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }

    if extra_claims:
        payload.update(extra_claims)

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt

def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decodes and validates a JWT access token.
    Enforces expiration, signature, and algorithm.
    Raises jwt.PyJWTError subclasses on failure.
    """
    options = {
        "verify_signature": True,
        "require": ["sub", "exp", "iat", "type"],
        "verify_exp": True,
        "verify_iat": True,
    }

    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options=options,
    )

    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")

    return payload
