import re
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2id password hasher with secure recommended parameters
# Default time_cost=3, memory_cost=65536 (64 MiB), parallelism=4
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

def hash_password(password: str) -> str:
    """
    Hashes a plaintext password using Argon2id.
    Validates input length to prevent DOS attacks with oversized passwords
    and ensure minimum password entropy.
    """
    if not isinstance(password, str):
        raise ValueError("Password must be a string")
    
    password = password.strip()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must not exceed {MAX_PASSWORD_LENGTH} characters")

    return _hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against an existing Argon2id hash.
    Safely returns False on mismatch or corrupted hash without leaking timing/internal exceptions.
    """
    if not isinstance(plain_password, str) or not isinstance(hashed_password, str):
        return False
    if not plain_password or not hashed_password:
        return False

    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False

def needs_rehash(hashed_password: str) -> bool:
    """Checks whether the hash needs to be upgraded to newer security parameters."""
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except Exception:
        return False
