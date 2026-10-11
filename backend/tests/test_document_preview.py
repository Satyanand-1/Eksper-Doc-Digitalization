"""
Automated test suite for Task 3.7: Secure Document Preview API.
Tests cover:
1. Previewing a PDF document version inline with HTTP 200, Content-Type, Content-Disposition: inline, and security headers.
2. Previewing a JPEG image document version inline.
3. Previewing a PNG image document version inline.
4. Previewing a TIFF image document version inline with Content-Type: image/tiff.
5. Rejection of unauthenticated preview requests (HTTP 401).
6. Non-disclosing HTTP 404 response when a user lacks view permissions (e.g. cross-department).
7. Rejection of unsupported document preview formats (e.g. HTML, SVG, TXT, EXE, DOCX) with HTTP 415.
8. Proper response for missing document (HTTP 404).
9. Proper response for missing version number (HTTP 404).
10. Correct security headers returned on every preview response:
    - X-Content-Type-Options: nosniff
    - Cache-Control: private, no-store
    - Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox
    - X-Frame-Options: SAMEORIGIN
11. Previewing historical versions (e.g., version 1 vs version 2).
12. Missing binary on disk handling (HTTP 404).
13. Storage key tampering and path traversal attempts (HTTP 400).
14. Audit logging on both successful previews and denied preview attempts, including audit write failure aborts.
"""
import io
import uuid
from unittest.mock import patch
import pytest

from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.storage import storage_service
from app.services.audit import AuditWriteError, audit_service

SAMPLE_PDF_V1 = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF\n"
SAMPLE_PDF_V2 = b"%PDF-1.4\n2 0 obj\n<<\n/Type /Catalog\n/Title (Version 2)\n>>\nendobj\ntrailer\n<<\n/Root 2 0 R\n>>\n%%EOF\n"
SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\xff\xd9"
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
SAMPLE_TIFF = b"II*\x00\x08\x00\x00\x00\x00\x00"  # Minimal Little-endian TIFF header
SAMPLE_TEXT_BINARY = b"Hello, this is a plain text file, not an allowed preview format."


@pytest.fixture
def multi_format_docs_setup(role_user_factory, db_session):
    """
    Creates test documents and versions with multiple formats:
    - Multi-version PDF document (Finance department, General)
    - JPEG document (Finance department, General)
    - PNG document (Finance department, General)
    - TIFF document (Finance department, General)
    - Text/Unsupported document (Finance department, General)
    - Restricted Finance document (Confidential)
    - HR department document (General)
    """
    creator = role_user_factory(role=UserRole.DEPARTMENT_USER)
    creator_user = creator["user"]
    creator_user.department = "Finance"
    db_session.commit()

    # 1. Multi-version PDF Doc
    pdf_v1_temp, pdf_v1_hash, pdf_v1_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V1))
    pdf_v1_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(pdf_v1_temp, pdf_v1_key)

    pdf_doc = DigitalDocument(
        document_reference=f"DOC-PDF-{uuid.uuid4().hex[:8].upper()}",
        title="Finance Report",
        subject="Financial Summary",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(pdf_doc)
    db_session.flush()

    pdf_ver1 = DocumentVersion(
        document_id=pdf_doc.id,
        version_number=1,
        storage_key=pdf_v1_key,
        original_filename="Finance_Report_v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=pdf_v1_size,
        file_hash_sha256=pdf_v1_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(pdf_ver1)

    pdf_v2_temp, pdf_v2_hash, pdf_v2_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V2))
    pdf_v2_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(pdf_v2_temp, pdf_v2_key)

    pdf_ver2 = DocumentVersion(
        document_id=pdf_doc.id,
        version_number=2,
        storage_key=pdf_v2_key,
        original_filename="Finance_Report_v2.pdf",
        mime_type="application/pdf",
        file_size_bytes=pdf_v2_size,
        file_hash_sha256=pdf_v2_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(pdf_ver2)

    # 2. JPEG Doc
    jpg_temp, jpg_hash, jpg_size = storage_service.stage_file(io.BytesIO(SAMPLE_JPEG))
    jpg_key = storage_service.generate_storage_key("jpg")
    storage_service.finalize_staged_file(jpg_temp, jpg_key)

    jpg_doc = DigitalDocument(
        document_reference=f"DOC-JPG-{uuid.uuid4().hex[:8].upper()}",
        title="Finance Chart",
        subject="Quarterly Chart",
        department="Finance",
        classification="General",
        mime_type="image/jpeg",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(jpg_doc)
    db_session.flush()

    jpg_ver = DocumentVersion(
        document_id=jpg_doc.id,
        version_number=1,
        storage_key=jpg_key,
        original_filename="Chart.jpg",
        mime_type="image/jpeg",
        file_size_bytes=jpg_size,
        file_hash_sha256=jpg_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(jpg_ver)

    # 3. PNG Doc
    png_temp, png_hash, png_size = storage_service.stage_file(io.BytesIO(SAMPLE_PNG))
    png_key = storage_service.generate_storage_key("png")
    storage_service.finalize_staged_file(png_temp, png_key)

    png_doc = DigitalDocument(
        document_reference=f"DOC-PNG-{uuid.uuid4().hex[:8].upper()}",
        title="Finance Diagram",
        subject="Diagram",
        department="Finance",
        classification="General",
        mime_type="image/png",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(png_doc)
    db_session.flush()

    png_ver = DocumentVersion(
        document_id=png_doc.id,
        version_number=1,
        storage_key=png_key,
        original_filename="Diagram.png",
        mime_type="image/png",
        file_size_bytes=png_size,
        file_hash_sha256=png_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(png_ver)

    # 4. TIFF Doc
    tiff_temp, tiff_hash, tiff_size = storage_service.stage_file(io.BytesIO(SAMPLE_TIFF))
    tiff_key = storage_service.generate_storage_key("tiff")
    storage_service.finalize_staged_file(tiff_temp, tiff_key)

    tiff_doc = DigitalDocument(
        document_reference=f"DOC-TIF-{uuid.uuid4().hex[:8].upper()}",
        title="Scanned Voucher",
        subject="Archival Scan",
        department="Finance",
        classification="General",
        mime_type="image/tiff",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(tiff_doc)
    db_session.flush()

    tiff_ver = DocumentVersion(
        document_id=tiff_doc.id,
        version_number=1,
        storage_key=tiff_key,
        original_filename="Scan.tif",
        mime_type="image/tiff",
        file_size_bytes=tiff_size,
        file_hash_sha256=tiff_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(tiff_ver)

    # 5. Unsupported Doc (Text / Markdown)
    txt_temp, txt_hash, txt_size = storage_service.stage_file(io.BytesIO(SAMPLE_TEXT_BINARY))
    txt_key = storage_service.generate_storage_key("txt")
    storage_service.finalize_staged_file(txt_temp, txt_key)

    txt_doc = DigitalDocument(
        document_reference=f"DOC-TXT-{uuid.uuid4().hex[:8].upper()}",
        title="Notes",
        subject="Raw Notes",
        department="Finance",
        classification="General",
        mime_type="text/plain",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(txt_doc)
    db_session.flush()

    txt_ver = DocumentVersion(
        document_id=txt_doc.id,
        version_number=1,
        storage_key=txt_key,
        original_filename="Notes.txt",
        mime_type="text/plain",
        file_size_bytes=txt_size,
        file_hash_sha256=txt_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(txt_ver)

    # 6. Confidential Finance Doc
    conf_temp, conf_hash, conf_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V1))
    conf_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(conf_temp, conf_key)

    conf_doc = DigitalDocument(
        document_reference=f"DOC-CNF-{uuid.uuid4().hex[:8].upper()}",
        title="Confidential Audit",
        subject="Audit Results",
        department="Finance",
        classification="Confidential",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator_user.id,
    )
    db_session.add(conf_doc)
    db_session.flush()

    conf_ver = DocumentVersion(
        document_id=conf_doc.id,
        version_number=1,
        storage_key=conf_key,
        original_filename="Audit.pdf",
        mime_type="application/pdf",
        file_size_bytes=conf_size,
        file_hash_sha256=conf_hash,
        created_by_id=creator_user.id,
    )
    db_session.add(conf_ver)

    # 7. HR Department Doc
    hr_creator = role_user_factory(role=UserRole.DEPARTMENT_USER)
    hr_user = hr_creator["user"]
    hr_user.department = "HR"
    db_session.commit()

    hr_temp, hr_hash, hr_size = storage_service.stage_file(io.BytesIO(SAMPLE_PDF_V1))
    hr_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(hr_temp, hr_key)

    hr_doc = DigitalDocument(
        document_reference=f"DOC-HR-{uuid.uuid4().hex[:8].upper()}",
        title="HR Policy",
        subject="Workplace Policy",
        department="HR",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=hr_user.id,
    )
    db_session.add(hr_doc)
    db_session.flush()

    hr_ver = DocumentVersion(
        document_id=hr_doc.id,
        version_number=1,
        storage_key=hr_key,
        original_filename="HR_Policy.pdf",
        mime_type="application/pdf",
        file_size_bytes=hr_size,
        file_hash_sha256=hr_hash,
        created_by_id=hr_user.id,
    )
    db_session.add(hr_ver)

    db_session.commit()

    yield {
        "creator_user": creator_user,
        "hr_user": hr_user,
        "pdf_doc": pdf_doc,
        "pdf_ver1": pdf_ver1,
        "pdf_ver2": pdf_ver2,
        "jpg_doc": jpg_doc,
        "jpg_ver": jpg_ver,
        "png_doc": png_doc,
        "png_ver": png_ver,
        "tiff_doc": tiff_doc,
        "tiff_ver": tiff_ver,
        "txt_doc": txt_doc,
        "txt_ver": txt_ver,
        "conf_doc": conf_doc,
        "conf_ver": conf_ver,
        "hr_doc": hr_doc,
        "hr_ver": hr_ver,
    }

    # Teardown: unlink disk files and delete test documents
    all_storage_keys = [
        pdf_v1_key,
        pdf_v2_key,
        jpg_key,
        png_key,
        tiff_key,
        txt_key,
        conf_key,
        hr_key,
    ]
    for k in all_storage_keys:
        try:
            storage_service.resolve_storage_path(k).unlink(missing_ok=True)
        except Exception:
            pass

    for d in [pdf_doc, jpg_doc, png_doc, tiff_doc, txt_doc, conf_doc, hr_doc]:
        try:
            db_session.delete(d)
            db_session.commit()
        except Exception:
            db_session.rollback()


def test_preview_pdf_success_and_headers(client, multi_format_docs_setup, role_user_factory, db_session):
    """
    Test 1 & 10: Previewing PDF document inline returns HTTP 200, Content-Type, Content-Disposition: inline,
    and all expected security headers.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["pdf_doc"]

    response = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.headers["Content-Disposition"] == 'inline; filename="Finance_Report_v1.pdf"'
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.content == SAMPLE_PDF_V1

    # Verify audit log
    audit_entry = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "document.preview",
            AuditLog.resource_id == multi_format_docs_setup["pdf_ver1"].id,
            AuditLog.outcome == AuditOutcome.SUCCESS,
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.actor_id == admin["user"].id
    assert audit_entry.details.get("mime_type") == "application/pdf"


def test_preview_jpeg_success(client, multi_format_docs_setup, role_user_factory):
    """
    Test 2: Previewing JPEG image returns HTTP 200, Content-Type: image/jpeg, inline disposition.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["jpg_doc"]

    response = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/jpeg"
    assert response.headers["Content-Disposition"] == 'inline; filename="Chart.jpg"'
    assert response.content == SAMPLE_JPEG


def test_preview_png_success(client, multi_format_docs_setup, role_user_factory):
    """
    Test 3: Previewing PNG image returns HTTP 200, Content-Type: image/png, inline disposition.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["png_doc"]

    response = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
    assert response.headers["Content-Disposition"] == 'inline; filename="Diagram.png"'
    assert response.content == SAMPLE_PNG


def test_preview_tiff_success(client, multi_format_docs_setup, role_user_factory):
    """
    Test 4: Previewing TIFF image returns HTTP 200, Content-Type: image/tiff, inline disposition.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["tiff_doc"]

    response = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/tiff"
    assert response.headers["Content-Disposition"] == 'inline; filename="Scan.tif"'
    assert response.content == SAMPLE_TIFF


def test_preview_historical_version(client, multi_format_docs_setup, role_user_factory):
    """
    Test 11: Previewing historical version (version 1) vs latest version (version 2).
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["pdf_doc"]

    # Version 1
    resp1 = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    assert resp1.content == SAMPLE_PDF_V1

    # Version 2
    resp2 = client.get(
        f"/api/v1/documents/{doc.id}/versions/2/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.content == SAMPLE_PDF_V2


def test_preview_unauthenticated(client, multi_format_docs_setup):
    """
    Test 5: Unauthenticated preview returns HTTP 401 Unauthorized.
    """
    doc = multi_format_docs_setup["pdf_doc"]

    # Missing token
    resp = client.get(f"/api/v1/documents/{doc.id}/versions/1/preview")
    assert resp.status_code == 401

    # Invalid token
    resp_invalid = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert resp_invalid.status_code == 401


def test_preview_unauthorized_cross_department_non_disclosing_404(
    client, multi_format_docs_setup, role_user_factory, db_session
):
    """
    Test 6: Department user attempting to preview another department's document
    receives non-disclosing HTTP 404, with audit log recording DENIED.
    """
    finance_user = multi_format_docs_setup["creator_user"]  # Finance dept
    token = create_access_token(user_id=finance_user.id)
    hr_doc = multi_format_docs_setup["hr_doc"]  # HR dept

    response = client.get(
        f"/api/v1/documents/{hr_doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."

    # Verify audit log captures the denied preview
    audit_entry = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.action == "document.preview",
            AuditLog.actor_id == finance_user.id,
            AuditLog.outcome == AuditOutcome.DENIED,
        )
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.details.get("user_dept") == "Finance"
    assert audit_entry.details.get("doc_dept") == "HR"


def test_preview_unauthorized_classification_denied(
    client, multi_format_docs_setup, role_user_factory, db_session
):
    """
    Test 6b: Readonly or Department user without sufficient classification clearance
    attempting to preview Confidential document receives non-disclosing HTTP 404.
    """
    reader = role_user_factory(role=UserRole.READ_ONLY)
    token = create_access_token(user_id=reader["user"].id)
    conf_doc = multi_format_docs_setup["conf_doc"]  # Confidential

    response = client.get(
        f"/api/v1/documents/{conf_doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_preview_unsupported_media_type_415(
    client, multi_format_docs_setup, role_user_factory
):
    """
    Test 7: Attempting to preview a document with unsupported media type (e.g. text/plain)
    returns HTTP 415 Unsupported Media Type.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    txt_doc = multi_format_docs_setup["txt_doc"]

    response = client.get(
        f"/api/v1/documents/{txt_doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 415
    assert "Preview is not supported for MIME type" in response.json()["detail"]
    assert "PDF, JPEG, PNG, and TIFF" in response.json()["detail"]


def test_preview_missing_document_404(client, role_user_factory):
    """
    Test 8: Non-existent document ID returns HTTP 404.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    random_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/documents/{random_id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_preview_missing_version_404(client, multi_format_docs_setup, role_user_factory):
    """
    Test 9: Non-existent version number returns HTTP 404.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["pdf_doc"]

    response = client.get(
        f"/api/v1/documents/{doc.id}/versions/999/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Version 999 not found for this document."


def test_preview_missing_binary_on_disk(
    client, multi_format_docs_setup, role_user_factory
):
    """
    Test 12: If disk file binary is missing, returns HTTP 404 without leaking storage paths.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["pdf_doc"]
    ver = multi_format_docs_setup["pdf_ver1"]

    # Delete physical disk file
    path = storage_service.resolve_storage_path(ver.storage_key)
    path.unlink(missing_ok=True)

    response = client.get(
        f"/api/v1/documents/{doc.id}/versions/1/preview",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "The requested file content was not found."


def test_preview_storage_path_traversal_anomaly(
    client, multi_format_docs_setup, role_user_factory, db_session
):
    """
    Test 13: Path traversal attempt in storage_key is detected and blocked with HTTP 400.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["pdf_doc"]
    ver = multi_format_docs_setup["pdf_ver2"]

    original_key = ver.storage_key
    malicious_key = f"../../etc/passwd_{uuid.uuid4().hex[:6]}"
    ver.storage_key = malicious_key
    db_session.commit()

    try:
        response = client.get(
            f"/api/v1/documents/{doc.id}/versions/2/preview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid storage reference."
    finally:
        ver.storage_key = original_key
        db_session.commit()


def test_preview_mandatory_audit_failure_blocks_preview(
    client, multi_format_docs_setup, role_user_factory
):
    """
    Test 14: Mandatory audit logging failure blocks preview response with AuditWriteError.
    """
    admin = role_user_factory(role=UserRole.ADMIN)
    token = create_access_token(user_id=admin["user"].id)
    doc = multi_format_docs_setup["pdf_doc"]

    with patch("app.api.v1.documents.audit_service.log_from_request", side_effect=AuditWriteError("Simulated database failure during audit write")):
        with pytest.raises(AuditWriteError):
            client.get(
                f"/api/v1/documents/{doc.id}/versions/1/preview",
                headers={"Authorization": f"Bearer {token}"},
            )
