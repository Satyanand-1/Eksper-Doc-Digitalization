import io
import uuid
import hashlib
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.jwt import create_access_token
from app.services.storage import storage_service

# Minimal valid file byte headers for testing
SAMPLE_PDF_CONTENT = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
SAMPLE_PNG_CONTENT = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
SAMPLE_JPEG_CONTENT = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xd9"
SAMPLE_TIFF_CONTENT = b"II*\x00\x08\x00\x00\x00\x00\x00\x00\x00"

@pytest.fixture
def auth_headers(role_user_factory):
    """Provides Authorization headers for an authenticated test user."""
    user_info = role_user_factory(role=UserRole.DEPARTMENT_USER)
    token = create_access_token(user_id=user_info["user"].id)
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "user": user_info["user"],
    }

def test_upload_pdf_success(client, auth_headers, db_session):
    """Verify authenticated user can successfully upload a valid PDF document."""
    files = {
        "file": ("Vendor_Contract.pdf", io.BytesIO(SAMPLE_PDF_CONTENT), "application/pdf")
    }
    data = {
        "title": "Master Services Agreement",
        "subject": "Vendor cloud computing contract",
        "department": "Legal",
        "classification": "Contract",
    }

    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers["headers"],
        files=files,
        data=data,
    )

    assert response.status_code == 201
    res_data = response.json()

    assert res_data["title"] == "Master Services Agreement"
    assert res_data["department"] == "Legal"
    assert res_data["classification"] == "Contract"
    assert res_data["original_filename"] == "Vendor_Contract.pdf"
    assert res_data["mime_type"] == "application/pdf"
    assert res_data["version_number"] == 1
    assert res_data["status"] == "active"
    assert res_data["document_reference"].startswith("DOC-")
    assert res_data["file_size_bytes"] == len(SAMPLE_PDF_CONTENT)
    assert res_data["file_hash_sha256"] == hashlib.sha256(SAMPLE_PDF_CONTENT).hexdigest()

    # Ensure no internal filesystem paths are exposed
    assert "/" not in res_data["document_reference"]
    assert "uploads" not in response.text
    assert "storage" not in response.text

    # Verify database persistence
    doc = db_session.query(DigitalDocument).filter_by(id=res_data["document_id"]).first()
    assert doc is not None
    assert doc.created_by_id == auth_headers["user"].id
    assert len(doc.versions) == 1
    assert doc.versions[0].version_number == 1
    assert storage_service.file_exists(doc.versions[0].storage_key) is True

    # Cleanup disk file and DB
    path = storage_service.resolve_storage_path(doc.versions[0].storage_key)
    path.unlink(missing_ok=True)
    db_session.delete(doc)
    db_session.commit()

def test_upload_image_success(client, auth_headers, db_session):
    """Verify uploading a PNG image succeeds and detects image/png MIME type."""
    files = {
        "file": ("Receipt_Scan.png", io.BytesIO(SAMPLE_PNG_CONTENT), "image/png")
    }
    data = {
        "title": "Hardware Receipt",
        "classification": "Receipt",
    }

    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers["headers"],
        files=files,
        data=data,
    )

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["mime_type"] == "image/png"
    assert res_data["file_hash_sha256"] == hashlib.sha256(SAMPLE_PNG_CONTENT).hexdigest()

    # Cleanup
    doc = db_session.query(DigitalDocument).filter_by(id=res_data["document_id"]).first()
    path = storage_service.resolve_storage_path(doc.versions[0].storage_key)
    path.unlink(missing_ok=True)
    db_session.delete(doc)
    db_session.commit()

def test_upload_missing_authentication(client):
    """Verify unauthenticated request is rejected with HTTP 401."""
    files = {
        "file": ("Document.pdf", io.BytesIO(SAMPLE_PDF_CONTENT), "application/pdf")
    }
    data = {"title": "Test Title"}

    response = client.post("/api/v1/documents/upload", files=files, data=data)
    assert response.status_code == 401

def test_upload_invalid_token(client):
    """Verify request with invalid token is rejected with HTTP 401."""
    files = {
        "file": ("Document.pdf", io.BytesIO(SAMPLE_PDF_CONTENT), "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": "Bearer fraudulent_invalid_token"},
        files=files,
        data={"title": "Test Title"},
    )
    assert response.status_code == 401

def test_upload_empty_file_rejected(client, auth_headers):
    """Verify empty 0-byte file is rejected with HTTP 400."""
    files = {
        "file": ("Empty.pdf", io.BytesIO(b""), "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers["headers"],
        files=files,
        data={"title": "Empty File"},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()

def test_upload_oversized_file_rejected(client, auth_headers):
    """Verify file exceeding MAX_UPLOAD_SIZE_BYTES is rejected with HTTP 400."""
    with patch("app.config.settings.MAX_UPLOAD_SIZE_BYTES", 50):
        files = {
            "file": ("Large.pdf", io.BytesIO(SAMPLE_PDF_CONTENT * 10), "application/pdf")
        }
        response = client.post(
            "/api/v1/documents/upload",
            headers=auth_headers["headers"],
            files=files,
            data={"title": "Oversized File"},
        )
        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"].lower()

def test_upload_unsupported_file_extension(client, auth_headers):
    """Verify file with unsupported extension (e.g. .exe) is rejected with HTTP 400."""
    files = {
        "file": ("malicious.exe", io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00"), "application/x-msdownload")
    }
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers["headers"],
        files=files,
        data={"title": "Executable File"},
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()

def test_upload_mismatched_extension_and_content(client, auth_headers):
    """Verify file content disguised with wrong extension (e.g. text disguised as .pdf) is rejected."""
    files = {
        "file": ("fake.pdf", io.BytesIO(b"This is plain text disguised as PDF"), "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers["headers"],
        files=files,
        data={"title": "Disguised File"},
    )
    assert response.status_code == 400

def test_upload_empty_title_rejected(client, auth_headers):
    """Verify request with whitespace or empty title is rejected with HTTP 422."""
    files = {
        "file": ("Valid.pdf", io.BytesIO(SAMPLE_PDF_CONTENT), "application/pdf")
    }
    response = client.post(
        "/api/v1/documents/upload",
        headers=auth_headers["headers"],
        files=files,
        data={"title": "   "},
    )
    assert response.status_code == 422

def test_upload_failure_cleans_up_staged_and_final_files(client, auth_headers, db_session):
    """
    Verify that if a failure occurs during database commit,
    compensation logic cleanly deletes temporary and finalized files.
    """
    files = {
        "file": ("WillFail.pdf", io.BytesIO(SAMPLE_PDF_CONTENT), "application/pdf")
    }
    data = {"title": "Failing Document"}

    # Mock database commit to simulate a database failure
    with patch.object(Session, "commit", side_effect=RuntimeError("Simulated DB Connection Failure")):
        response = client.post(
            "/api/v1/documents/upload",
            headers=auth_headers["headers"],
            files=files,
            data=data,
        )
        assert response.status_code == 500

    # Verify no orphaned temp files left in temp directory
    temp_files = list(storage_service.temp_dir.glob("stage_*.tmp"))
    assert len(temp_files) == 0

    # Verify no orphaned records in database
    failed_doc = db_session.query(DigitalDocument).filter_by(title="Failing Document").first()
    assert failed_doc is None
