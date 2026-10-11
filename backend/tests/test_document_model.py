import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.security import hash_password

@pytest.fixture
def test_user(db_session):
    """Provides an isolated user record for document foreign keys."""
    user = User(
        email=f"doc_creator_{uuid.uuid4().hex[:8]}@example.com",
        full_name="Document Creator",
        hashed_password=hash_password("CreatorPass123!"),
        role=UserRole.DEPARTMENT_USER,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    db_session.delete(user)
    db_session.commit()

def test_create_digital_document_model(db_session, test_user):
    """Verify DigitalDocument model instantiation and database persistence."""
    unique_ref = f"DOC-TEST-{uuid.uuid4().hex[:6].upper()}"
    doc = DigitalDocument(
        document_reference=unique_ref,
        title="Procurement Master Services Agreement",
        subject="Vendor agreement for cloud software services",
        department="Procurement",
        classification="Contract",
        mime_type="application/pdf",
        status=DocumentStatus.DRAFT,
        created_by_id=test_user.id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    assert doc.id is not None
    assert doc.document_reference == unique_ref
    assert doc.status == DocumentStatus.DRAFT
    assert doc.created_by.id == test_user.id
    assert doc.created_at is not None
    assert doc.updated_at is not None
    assert doc.archived_at is None

    # Cleanup
    db_session.delete(doc)
    db_session.commit()

def test_document_reference_uniqueness_constraint(db_session, test_user):
    """Verify document_reference uniqueness is enforced at database level."""
    shared_ref = f"DOC-DUP-{uuid.uuid4().hex[:6].upper()}"
    doc1 = DigitalDocument(
        document_reference=shared_ref,
        title="Document One",
        department="Legal",
        classification="Policy",
        mime_type="application/pdf",
        created_by_id=test_user.id,
    )
    db_session.add(doc1)
    db_session.commit()

    doc2 = DigitalDocument(
        document_reference=shared_ref,
        title="Document Duplicate Ref",
        department="Finance",
        classification="Invoice",
        mime_type="application/pdf",
        created_by_id=test_user.id,
    )
    db_session.add(doc2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.delete(doc1)
    db_session.commit()

def test_create_document_versions_and_relationship(db_session, test_user):
    """Verify multiple DocumentVersions can attach to DigitalDocument with sequential versioning."""
    doc = DigitalDocument(
        document_reference=f"DOC-VER-{uuid.uuid4().hex[:6].upper()}",
        title="Multi-Version Document",
        department="HR",
        classification="Handbook",
        mime_type="application/pdf",
        created_by_id=test_user.id,
    )
    db_session.add(doc)
    db_session.commit()

    # Version 1
    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/2026/10/{uuid.uuid4()}.pdf",
        original_filename="Employee_Handbook_Draft.pdf",
        mime_type="application/pdf",
        file_size_bytes=10240,
        file_hash_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        created_by_id=test_user.id,
    )
    # Version 2
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key=f"uploads/2026/10/{uuid.uuid4()}.pdf",
        original_filename="Employee_Handbook_Final.pdf",
        mime_type="application/pdf",
        file_size_bytes=20480,
        file_hash_sha256="ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        created_by_id=test_user.id,
    )
    db_session.add_all([v1, v2])
    db_session.commit()
    db_session.refresh(doc)

    assert len(doc.versions) == 2
    assert doc.versions[0].version_number == 1
    assert doc.versions[0].original_filename == "Employee_Handbook_Draft.pdf"
    assert doc.versions[1].version_number == 2
    assert doc.versions[1].original_filename == "Employee_Handbook_Final.pdf"

    # Cleanup (cascade deletes versions from DB)
    db_session.delete(doc)
    db_session.commit()

def test_document_version_number_unique_within_parent(db_session, test_user):
    """Verify duplicate version_number under same document violates UniqueConstraint."""
    doc = DigitalDocument(
        document_reference=f"DOC-UNIQVER-{uuid.uuid4().hex[:6].upper()}",
        title="Duplicate Version Test Document",
        department="Operations",
        classification="SOP",
        mime_type="application/pdf",
        created_by_id=test_user.id,
    )
    db_session.add(doc)
    db_session.commit()

    v1_a = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/2026/10/{uuid.uuid4()}.pdf",
        original_filename="FileA.pdf",
        mime_type="application/pdf",
        file_size_bytes=5000,
        file_hash_sha256="aaaa0000aaaa0000aaaa0000aaaa0000aaaa0000aaaa0000aaaa0000aaaa0000",
        created_by_id=test_user.id,
    )
    db_session.add(v1_a)
    db_session.commit()

    # Attempt adding duplicate version 1 to same document
    v1_b = DocumentVersion(
        document_id=doc.id,
        version_number=1,  # Duplicate version_number
        storage_key=f"uploads/2026/10/{uuid.uuid4()}.pdf",
        original_filename="FileB.pdf",
        mime_type="application/pdf",
        file_size_bytes=6000,
        file_hash_sha256="bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111bbbb1111",
        created_by_id=test_user.id,
    )
    db_session.add(v1_b)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.delete(doc)
    db_session.commit()

def test_document_version_foreign_key_protection_on_user(db_session, test_user):
    """Verify RESTRICT ondelete prevents deleting a User who owns active document records."""
    doc = DigitalDocument(
        document_reference=f"DOC-FK-{uuid.uuid4().hex[:6].upper()}",
        title="FK Protected Document",
        department="Security",
        classification="Report",
        mime_type="application/pdf",
        created_by_id=test_user.id,
    )
    db_session.add(doc)
    db_session.commit()

    # Attempt deleting test_user while document exists
    db_session.delete(test_user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Delete doc first, then user can be deleted safely
    db_session.delete(doc)
    db_session.commit()
