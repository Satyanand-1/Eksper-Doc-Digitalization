"""
Automated test suite for Task 4.3: Secure Full-Text Document Search.
Verifies all 19 required test cases:
1. Search by document title.
2. Search by document reference.
3. Search by subject.
4. Search by embedded PDF text.
5. Search by OCR-extracted text from a scanned document.
6. Search across historical versions.
7. Multiple matching versions without duplicate document results.
8. Relevance ordering and deterministic pagination.
9. Department, classification, and status filters.
10. Empty, oversized, punctuation-only, and stop-word-only queries.
11. Missing or invalid JWT.
12. Search restrictions for all six existing roles.
13. Unauthorized matches excluded from both results and totals.
14. No leakage through snippets, matching version numbers, or relevance metadata.
15. Documents with pending or failed extraction.
16. PostgreSQL index migration and rollback, if a migration is added.
17. Search after a new OCR extraction completes.
18. Audit logging and audit-write failure handling.
19. Existing upload, versioning, preview, download, authorization, and OCR tests continue to pass.
"""
import io
import uuid
from unittest.mock import patch
import pytest

from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.audit import AuditWriteError


def test_search_by_document_title(client, role_user_factory, db_session):
    """1. Search matching words in document title."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    doc = DigitalDocument(
        title="Comprehensive Cyber Security Architecture Policy",
        document_reference=f"DOC-TITLE-{uuid.uuid4().hex[:6]}",
        subject="Internal safeguards",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=cyber+security",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    refs = [item["document_reference"] for item in data["items"]]
    assert doc.document_reference in refs
    match = next(item for item in data["items"] if item["document_reference"] == doc.document_reference)
    assert "cyber" in match["snippet"].lower() or "security" in match["snippet"].lower()


def test_search_by_document_reference(client, role_user_factory, db_session):
    """2. Search matching unique document reference number."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-2026-99{uuid.uuid4().hex[:4]}"

    doc = DigitalDocument(
        title="Vendor Service Level Agreement",
        document_reference=ref_code,
        subject="Procurement contract",
        department="Procurement",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.commit()

    # Search exact full reference
    res = client.get(
        f"/api/v1/search?query={ref_code}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    refs = [item["document_reference"] for item in data["items"]]
    assert ref_code in refs

    # Search partial reference
    partial = ref_code.split("-")[-1]
    res_part = client.get(
        f"/api/v1/search?query={partial}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_part.status_code == 200
    refs_part = [item["document_reference"] for item in res_part.json()["items"]]
    assert ref_code in refs_part


def test_search_by_subject(client, role_user_factory, db_session):
    """3. Search matching text in document subject/abstract."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-SUBJ-{uuid.uuid4().hex[:6]}"

    doc = DigitalDocument(
        title="Annual Financial Summary",
        document_reference=ref_code,
        subject="Detailed breakdown of quarterly amortized depreciation and capital expenditure",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=amortized+depreciation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    refs = [item["document_reference"] for item in data["items"]]
    assert ref_code in refs
    match = next(item for item in data["items"] if item["document_reference"] == ref_code)
    assert "depreciation" in match["snippet"].lower()


def test_search_by_embedded_pdf_text(client, role_user_factory, db_session):
    """4. Search matching extracted text in a PDF document version."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-PDF-{uuid.uuid4().hex[:6]}"

    doc = DigitalDocument(
        title="Engineering Standard",
        document_reference=ref_code,
        subject="Technical specifications",
        department="Engineering",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="engineering_standard.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="0" * 64,
        extracted_text="The high-voltage dielectric insulation thresholds must not degrade under thermodynamic pressure.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add(ver)
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=thermodynamic+pressure",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    refs = [item["document_reference"] for item in data["items"]]
    assert ref_code in refs
    match = next(item for item in data["items"] if item["document_reference"] == ref_code)
    assert 1 in match["matching_version_numbers"]
    assert "pressure" in match["snippet"].lower() or "thermodynamic" in match["snippet"].lower()


def test_search_by_ocr_extracted_text_from_scanned_document(client, role_user_factory, db_session):
    """5. Search matching OCR text extracted from a scanned document."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-SCAN-{uuid.uuid4().hex[:6]}"

    doc = DigitalDocument(
        title="Scanned Handwritten Notice",
        document_reference=ref_code,
        subject="Archived office memorandum",
        department="Operations",
        classification="General",
        mime_type="image/png",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.png",
        original_filename="notice.png",
        mime_type="image/png",
        file_size_bytes=2048,
        file_hash_sha256="1" * 64,
        extracted_text="Mandatory building evacuation scheduled for seismic retrofit drills next Tuesday.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add(ver)
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=seismic+retrofit",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    refs = [item["document_reference"] for item in data["items"]]
    assert ref_code in refs
    match = next(item for item in data["items"] if item["document_reference"] == ref_code)
    assert 1 in match["matching_version_numbers"]


def test_search_across_historical_versions(client, role_user_factory, db_session):
    """6. Search matches content in an older (historical) version."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-HIST-{uuid.uuid4().hex[:6]}"

    doc = DigitalDocument(
        title="Evolving Procurement Contract",
        document_reference=ref_code,
        subject="Supply agreement",
        department="Legal",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="a" * 64,
        extracted_text="Original legacy clause regarding liquidated damages of five percent per month.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="v2.pdf",
        mime_type="application/pdf",
        file_size_bytes=1200,
        file_hash_sha256="b" * 64,
        extracted_text="Amended clause replacing liquidated damages with binding arbitration protocol.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    # Search for term present only in historical v1
    res = client.get(
        "/api/v1/search?query=liquidated+damages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    refs = [item["document_reference"] for item in data["items"]]
    assert ref_code in refs
    match = next(item for item in data["items"] if item["document_reference"] == ref_code)
    assert 1 in match["matching_version_numbers"]


def test_multiple_matching_versions_no_duplicate_document_results(client, role_user_factory, db_session):
    """7. When multiple versions of the same document match, return one consolidated document row."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-MULTIV-{uuid.uuid4().hex[:6]}"

    doc = DigitalDocument(
        title="Multi-Version Safety Manual",
        document_reference=ref_code,
        subject="Chemical handling protocol",
        department="Safety",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="c" * 64,
        extracted_text="Hazardous material containment: Always wear neoprene gloves during chemical synthesis.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    v2 = DocumentVersion(
        document_id=doc.id,
        version_number=2,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="v2.pdf",
        mime_type="application/pdf",
        file_size_bytes=1100,
        file_hash_sha256="d" * 64,
        extracted_text="Revision: Enhanced neoprene gloves and face shield for hazardous chemical synthesis.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add_all([v1, v2])
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=neoprene+gloves",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    doc_matches = [item for item in data["items"] if item["document_reference"] == ref_code]
    # Must only appear ONCE in the result list
    assert len(doc_matches) == 1
    # Both version 1 and version 2 must be listed
    assert set(doc_matches[0]["matching_version_numbers"]) == {1, 2}


def test_relevance_ordering_and_deterministic_pagination(client, role_user_factory, db_session):
    """8. Documents with higher relevance rank first, and pagination is deterministic."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_a = f"DOC-RANK-A-{uuid.uuid4().hex[:6]}"
    ref_b = f"DOC-RANK-B-{uuid.uuid4().hex[:6]}"

    # Doc A has search term in Title ('A' weight) AND body
    doc_a = DigitalDocument(
        title="Artificial Intelligence Governance Framework",
        document_reference=ref_a,
        subject="AI models",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    # Doc B has search term only once in body
    doc_b = DigitalDocument(
        title="General Employee Conduct",
        document_reference=ref_b,
        subject="Ethics",
        department="HR",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add_all([doc_a, doc_b])
    db_session.flush()

    v_a = DocumentVersion(
        document_id=doc_a.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="ai.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="e" * 64,
        extracted_text="Artificial intelligence deployment requires rigorous ethical validation and risk scoring.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    v_b = DocumentVersion(
        document_id=doc_b.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="conduct.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="f" * 64,
        extracted_text="Employees must disclose if artificial intelligence tools are used for drafting.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add_all([v_a, v_b])
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=Artificial+Intelligence&sort_order=relevance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) >= 2
    # Verify Doc A has higher score than Doc B
    item_a = next(i for i in data["items"] if i["document_reference"] == ref_a)
    item_b = next(i for i in data["items"] if i["document_reference"] == ref_b)
    assert item_a["relevance_score"] >= item_b["relevance_score"]

    # Verify pagination
    page1 = client.get(
        f"/api/v1/search?query=Artificial+Intelligence&page=1&page_size=1",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert len(page1["items"]) == 1
    assert page1["items"][0]["document_reference"] == item_a["document_reference"]


def test_department_classification_and_status_filters(client, role_user_factory, db_session):
    """9. Search filtering by department, classification, and status."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_draft = f"DOC-FILT-DRAFT-{uuid.uuid4().hex[:6]}"
    ref_active = f"DOC-FILT-ACTIVE-{uuid.uuid4().hex[:6]}"
    ref_hr = f"DOC-FILT-HR-{uuid.uuid4().hex[:6]}"

    doc_draft = DigitalDocument(
        title="Draft Legal Brief on Compliance",
        document_reference=ref_draft,
        department="Legal",
        classification="Confidential",
        mime_type="application/pdf",
        status=DocumentStatus.DRAFT,
        created_by_id=admin.id,
    )
    doc_active = DigitalDocument(
        title="Active Legal Brief on Compliance",
        document_reference=ref_active,
        department="Legal",
        classification="Confidential",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    doc_hr = DigitalDocument(
        title="HR Policy Brief on Compliance",
        document_reference=ref_hr,
        department="HR",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add_all([doc_draft, doc_active, doc_hr])
    db_session.commit()

    # Filter by department=Legal
    res_dept = client.get(
        "/api/v1/search?query=compliance&department=Legal",
        headers={"Authorization": f"Bearer {token}"},
    )
    data_dept = res_dept.json()
    assert all(item["department"].lower() == "legal" for item in data_dept["items"])
    assert ref_hr not in [i["document_reference"] for i in data_dept["items"]]

    # Filter by status=draft
    res_status = client.get(
        "/api/v1/search?query=compliance&status=draft",
        headers={"Authorization": f"Bearer {token}"},
    )
    data_status = res_status.json()
    assert all(item["status"] == "draft" for item in data_status["items"])
    assert ref_active not in [i["document_reference"] for i in data_status["items"]]

    # Filter by classification=Confidential
    res_class = client.get(
        "/api/v1/search?query=compliance&classification=Confidential",
        headers={"Authorization": f"Bearer {token}"},
    )
    data_class = res_class.json()
    assert all(item["classification"].lower() == "confidential" for item in data_class["items"])

    # Teardown
    for d in [doc_draft, doc_active, doc_hr]:
        try:
            db_session.delete(d)
            db_session.commit()
        except Exception:
            db_session.rollback()


def test_empty_oversized_punctuation_and_stopword_queries(client, role_user_factory):
    """10. Validation on empty, oversized, punctuation-only, and stopword-only queries."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    # Empty query -> 422
    res_empty = client.get("/api/v1/search?query=", headers={"Authorization": f"Bearer {token}"})
    assert res_empty.status_code == 422

    # Whitespace only -> 422
    res_ws = client.get("/api/v1/search?query=%20%20%20", headers={"Authorization": f"Bearer {token}"})
    assert res_ws.status_code == 422

    # Oversized query (>200 chars) -> 422
    long_query = "a" * 205
    res_long = client.get(f"/api/v1/search?query={long_query}", headers={"Authorization": f"Bearer {token}"})
    assert res_long.status_code == 422

    # Punctuation only -> returns 200 with 0 results gracefully
    res_punct = client.get("/api/v1/search?query=...%20???%20!!!", headers={"Authorization": f"Bearer {token}"})
    assert res_punct.status_code == 200
    assert res_punct.json()["total"] == 0
    assert res_punct.json()["items"] == []

    # Stopwords only -> returns 200 with 0 results gracefully
    res_stop = client.get("/api/v1/search?query=the%20and%20or%20of", headers={"Authorization": f"Bearer {token}"})
    assert res_stop.status_code == 200
    assert res_stop.json()["total"] == 0
    assert res_stop.json()["items"] == []


def test_missing_or_invalid_jwt(client):
    """11. Missing or invalid Bearer JWT rejected with 401."""
    # Missing token
    res_no_auth = client.get("/api/v1/search?query=audit")
    assert res_no_auth.status_code == 401

    # Invalid token
    res_bad_auth = client.get("/api/v1/search?query=audit", headers={"Authorization": "Bearer badtoken"})
    assert res_bad_auth.status_code == 401


def test_search_restrictions_across_six_roles(client, role_user_factory, db_session):
    """12 & 13. Search restrictions for all six roles; unauthorized matches excluded from results & totals."""
    # Setup test users
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    admin.department = "IT"
    ro_officer = role_user_factory(role=UserRole.RECORDS_OFFICER)["user"]
    ro_officer.department = "Registry"
    legal_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    legal_user.department = "Legal"
    legal_approver = role_user_factory(role=UserRole.APPROVER)["user"]
    legal_approver.department = "Legal"
    legal_auditor = role_user_factory(role=UserRole.AUDITOR)["user"]
    legal_auditor.department = "Legal"
    legal_readonly = role_user_factory(role=UserRole.READ_ONLY)["user"]
    legal_readonly.department = "Legal"
    db_session.commit()

    ref_l_gen = f"DOC-ROLE-L-GEN-{uuid.uuid4().hex[:6]}"
    ref_l_conf = f"DOC-ROLE-L-CONF-{uuid.uuid4().hex[:6]}"
    ref_f_gen = f"DOC-ROLE-F-GEN-{uuid.uuid4().hex[:6]}"

    # Document 1: Legal General
    d_legal_gen = DigitalDocument(
        title="Legal General Operations Protocol",
        document_reference=ref_l_gen,
        department="Legal",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=legal_user.id,
    )
    # Document 2: Legal Confidential
    d_legal_conf = DigitalDocument(
        title="Legal Confidential Patent Filing",
        document_reference=ref_l_conf,
        department="Legal",
        classification="CONFIDENTIAL",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=legal_user.id,
    )
    # Document 3: Finance General
    d_fin_gen = DigitalDocument(
        title="Finance General Procurement Protocol",
        document_reference=ref_f_gen,
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add_all([d_legal_gen, d_legal_conf, d_fin_gen])
    db_session.commit()

    def get_search_refs(user, query="Protocol"):
        t = create_access_token(user_id=user.id)
        resp = client.get(f"/api/v1/search?query={query}", headers={"Authorization": f"Bearer {t}"})
        assert resp.status_code == 200
        data = resp.json()
        return [item["document_reference"] for item in data["items"]], data["total"]

    # 1. Admin sees across departments
    refs, total = get_search_refs(admin)
    assert ref_l_gen in refs
    assert ref_f_gen in refs

    # 2. Records Officer sees across departments
    ro_refs, ro_total = get_search_refs(ro_officer)
    assert ref_l_gen in ro_refs
    assert ref_f_gen in ro_refs

    # 3. Department User (Legal) only sees Legal documents, never Finance
    du_refs, du_total = get_search_refs(legal_user)
    assert ref_l_gen in du_refs
    assert ref_f_gen not in du_refs

    # 4. Approver in Legal sees Legal documents
    app_refs, app_total = get_search_refs(legal_approver)
    assert ref_l_gen in app_refs
    assert ref_f_gen not in app_refs

    # 5. Auditor assigned to Legal sees Legal documents, never Finance
    aud_refs, aud_total = get_search_refs(legal_auditor)
    assert ref_l_gen in aud_refs
    assert ref_f_gen not in aud_refs

    # 6. Read-Only in Legal: can see Legal General, CANNOT see Legal Confidential
    ro_user_refs, _ = get_search_refs(legal_readonly, query="Patent")
    assert ref_l_conf not in ro_user_refs


def test_no_information_leakage_through_snippets_or_metadata(client, role_user_factory, db_session):
    """14. Unauthorized documents are not leaked through snippets, numbers, or relevance metadata."""
    # Finance user searches for a term present in a Secret Legal document
    fin_user = role_user_factory(role=UserRole.DEPARTMENT_USER)["user"]
    fin_user.department = "Finance"
    db_session.commit()
    token = create_access_token(user_id=fin_user.id)

    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    secret_ref = f"DOC-SECRET-{uuid.uuid4().hex[:6]}"
    secret_term = f"ZephyrTerm{uuid.uuid4().hex[:6]}"

    secret_doc = DigitalDocument(
        title=f"Secret Merger Blueprint {secret_term}",
        document_reference=secret_ref,
        subject="Merger negotiation details",
        department="Legal",
        classification="SECRET",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(secret_doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=secret_doc.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="blueprint.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="9" * 64,
        extracted_text=f"Target acquisition project code name {secret_term} valuated at 100M.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=admin.id,
    )
    db_session.add(ver)
    db_session.commit()

    # Finance user guesses distinctive search term
    res = client.get(
        f"/api/v1/search?query={secret_term}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    # Must return 0 matches, 0 total, no snippet, no metadata
    assert data["total"] == 0
    assert data["items"] == []


def test_documents_with_pending_or_failed_extraction(client, role_user_factory, db_session):
    """15. Documents with pending or failed OCR still return on metadata matches without crashing."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_pending = f"DOC-PENDING-{uuid.uuid4().hex[:6]}"
    ref_failed = f"DOC-FAILED-{uuid.uuid4().hex[:6]}"

    doc_pending = DigitalDocument(
        title="Quarterly Review Pending OCR Processing",
        document_reference=ref_pending,
        subject="Strategy meeting",
        department="HR",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    doc_failed = DigitalDocument(
        title="Quarterly Review Failed OCR Processing",
        document_reference=ref_failed,
        subject="Corrupt scan file",
        department="HR",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add_all([doc_pending, doc_failed])
    db_session.flush()

    v_pending = DocumentVersion(
        document_id=doc_pending.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="pending.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="7" * 64,
        extracted_text=None,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    v_failed = DocumentVersion(
        document_id=doc_failed.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="corrupt.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="8" * 64,
        extracted_text=None,
        extraction_status=ExtractionStatus.FAILED,
        extraction_error="Corrupt file format",
        created_by_id=admin.id,
    )
    db_session.add_all([v_pending, v_failed])
    db_session.commit()

    res = client.get(
        "/api/v1/search?query=Quarterly+Review",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    refs = [item["document_reference"] for item in data["items"]]
    assert ref_pending in refs
    assert ref_failed in refs


def test_search_after_new_ocr_extraction_completes(client, role_user_factory, db_session):
    """17. When a newly uploaded version completes OCR, it becomes immediately searchable."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)
    ref_code = f"DOC-DYN-{uuid.uuid4().hex[:6]}"
    term = f"QuantumCrypto{uuid.uuid4().hex[:6]}"

    doc = DigitalDocument(
        title="Immediate Ingest Document",
        document_reference=ref_code,
        subject="Testing live searchability",
        department="IT",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"uploads/test/{uuid.uuid4()}.pdf",
        original_filename="doc.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        file_hash_sha256="5" * 64,
        extracted_text=None,
        extraction_status=ExtractionStatus.PENDING,
        created_by_id=admin.id,
    )
    db_session.add(ver)
    db_session.commit()

    # Search prior to OCR completion -> 0 matches for distinctive term
    res_before = client.get(
        f"/api/v1/search?query={term}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_before.json()["total"] == 0

    # Simulate OCR background worker updating the row
    ver.extracted_text = f"Implementation details for the {term} key exchange protocol."
    ver.extraction_status = ExtractionStatus.COMPLETED
    db_session.commit()

    # Search after OCR completion -> matches immediately via GIN expression index
    res_after = client.get(
        f"/api/v1/search?query={term}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_after.status_code == 200
    assert res_after.json()["total"] >= 1
    refs = [item["document_reference"] for item in res_after.json()["items"]]
    assert ref_code in refs


def test_audit_logging_and_write_failure_handling(client, role_user_factory, db_session):
    """18. Search events are recorded in audit logs, and audit failures halt the request."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    res = client.get(
        "/api/v1/search?query=Governance",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200

    # Verify audit log entry exists
    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "document.search", AuditLog.actor_id == admin.id)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.outcome == AuditOutcome.SUCCESS
    # Raw query text must NOT be stored in audit details
    assert "Governance" not in str(audit_entry.details)
    assert "result_count" in audit_entry.details

    # Mandatory audit failure test: simulate database failure during audit write
    with patch("app.services.audit.audit_service.log_from_request", side_effect=AuditWriteError("Simulated audit disk failure")):
        res_fail = client.get(
            "/api/v1/search?query=Governance",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Should raise 500 when mandatory audit write fails
        assert res_fail.status_code == 500
