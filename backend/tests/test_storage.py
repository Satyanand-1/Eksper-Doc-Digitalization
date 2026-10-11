import io
import os
import shutil
import tempfile
import hashlib
from pathlib import Path
import pytest

from app.services.storage import (
    LocalStorageService,
    StorageSecurityError,
    StorageFileExistsError,
    StorageFileNotFoundError,
)

@pytest.fixture
def temp_storage():
    """Provides an isolated temporary storage service for testing."""
    tmp_dir = tempfile.mkdtemp(prefix="edrms_test_storage_")
    service = LocalStorageService(root_dir=tmp_dir)
    yield service
    shutil.rmtree(tmp_dir, ignore_errors=True)

def test_generate_storage_key(temp_storage):
    """Verify generated storage keys are relative, partitioned, and have valid extensions."""
    key = temp_storage.generate_storage_key("pdf")
    assert key.startswith("uploads/")
    assert key.endswith(".pdf")
    # Verify no drive letter or absolute path
    assert not key.startswith("/")
    assert ":" not in key

def test_resolve_storage_path_valid(temp_storage):
    """Verify safe storage key resolves inside the storage root."""
    key = temp_storage.generate_storage_key("pdf")
    resolved = temp_storage.resolve_storage_path(key)
    assert resolved.is_relative_to(temp_storage.root_path)

def test_path_traversal_rejection(temp_storage):
    """Verify path traversal attempts with '../' or root slashes are rejected."""
    # Attempting directory traversal
    with pytest.raises(StorageSecurityError):
        temp_storage.resolve_storage_path("uploads/../../etc/passwd")

    with pytest.raises(StorageSecurityError):
        temp_storage.resolve_storage_path("/etc/passwd")

    with pytest.raises(StorageSecurityError):
        temp_storage.resolve_storage_path("C:\\Windows\\System32\\cmd.exe")

    with pytest.raises(StorageSecurityError):
        temp_storage.resolve_storage_path("..")

def test_stage_file_calculates_hash_and_size(temp_storage):
    """Verify stage_file streams data, computes exact SHA-256 and size."""
    test_content = b"Electronic Document and Records Management System Payload"
    expected_hash = hashlib.sha256(test_content).hexdigest()
    expected_size = len(test_content)

    stream = io.BytesIO(test_content)
    temp_path, computed_hash, file_size = temp_storage.stage_file(stream)

    assert temp_path.exists()
    assert temp_path.is_relative_to(temp_storage.temp_dir)
    assert computed_hash == expected_hash
    assert file_size == expected_size

    # Verify disk content matches
    assert temp_path.read_bytes() == test_content

    # Cleanup temp
    temp_storage.cleanup_temp_file(temp_path)
    assert not temp_path.exists()

def test_finalize_staged_file_success(temp_storage):
    """Verify finalize_staged_file moves file to final path and cleans temp."""
    test_content = b"Finalized Document Data"
    stream = io.BytesIO(test_content)
    temp_path, _, _ = temp_storage.stage_file(stream)
    assert temp_path.exists()

    storage_key = temp_storage.generate_storage_key("pdf")
    final_path = temp_storage.finalize_staged_file(temp_path, storage_key)

    assert final_path.exists()
    assert final_path.is_relative_to(temp_storage.uploads_dir)
    assert not temp_path.exists()
    assert final_path.read_bytes() == test_content
    assert temp_storage.file_exists(storage_key) is True

def test_finalize_duplicate_destination_protection(temp_storage):
    """Verify finalize_staged_file refuses to overwrite an existing persistent file."""
    test_content = b"Version 1"
    stream = io.BytesIO(test_content)
    temp_path, _, _ = temp_storage.stage_file(stream)

    storage_key = temp_storage.generate_storage_key("pdf")
    temp_storage.finalize_staged_file(temp_path, storage_key)

    # Attempt to finalize another file with identical storage key
    stream2 = io.BytesIO(b"Version Overwrite Attempt")
    temp_path2, _, _ = temp_storage.stage_file(stream2)

    with pytest.raises(StorageFileExistsError):
        temp_storage.finalize_staged_file(temp_path2, storage_key)

    # Clean up second temp file
    temp_storage.cleanup_temp_file(temp_path2)

def test_cleanup_temp_file_after_simulated_failure(temp_storage):
    """Verify cleanup_temp_file safely removes stranded staging files."""
    stream = io.BytesIO(b"Data before failure")
    temp_path, _, _ = temp_storage.stage_file(stream)
    assert temp_path.exists()

    # Simulate error condition
    temp_storage.cleanup_temp_file(temp_path)
    assert not temp_path.exists()

def test_compute_sha256(temp_storage):
    """Verify compute_sha256 helper calculates matching checksum."""
    data = b"Testing SHA256 helper"
    stream = io.BytesIO(data)
    temp_path, expected_hash, _ = temp_storage.stage_file(stream)
    
    assert temp_storage.compute_sha256(temp_path) == expected_hash
    temp_storage.cleanup_temp_file(temp_path)
