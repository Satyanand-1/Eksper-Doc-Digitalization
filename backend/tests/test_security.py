import pytest
from app.security import hash_password, verify_password, needs_rehash, MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH

def test_hash_password_produces_argon2id():
    """Verify hash_password generates valid Argon2id hash different from plaintext."""
    pwd = "SecurePassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert hashed.startswith("$argon2id$")

def test_verify_password_success():
    """Verify correct password matches generated hash."""
    pwd = "CorrectHorseBatteryStaple!"
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed) is True

def test_verify_password_failure():
    """Verify incorrect password fails verification."""
    pwd = "CorrectPassword123!"
    wrong_pwd = "WrongPassword456!"
    hashed = hash_password(pwd)
    assert verify_password(wrong_pwd, hashed) is False

def test_verify_password_safe_on_invalid_inputs():
    """Verify verify_password safely handles empty, malformed or non-string inputs."""
    assert verify_password("", "somehash") is False
    assert verify_password("pwd", "") is False
    assert verify_password(None, "somehash") is False
    assert verify_password("pwd", None) is False
    assert verify_password("pwd", "not_an_argon_hash") is False

def test_password_length_boundaries():
    """Verify password length boundaries (min 8, max 128 chars)."""
    # Too short (< 8)
    with pytest.raises(ValueError, match="at least 8 characters"):
        hash_password("short1")
    
    # Empty string
    with pytest.raises(ValueError, match="at least 8 characters"):
        hash_password("")

    # Exact min length
    min_pwd = "a" * MIN_PASSWORD_LENGTH
    assert hash_password(min_pwd) is not None

    # Exact max length
    max_pwd = "a" * MAX_PASSWORD_LENGTH
    assert hash_password(max_pwd) is not None

    # Oversized password (> 128)
    with pytest.raises(ValueError, match="not exceed 128 characters"):
        hash_password("a" * (MAX_PASSWORD_LENGTH + 1))

def test_needs_rehash():
    """Verify hash created with current parameters does not need rehash."""
    hashed = hash_password("ValidPassword123!")
    assert needs_rehash(hashed) is False
