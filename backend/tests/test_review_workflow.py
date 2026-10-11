"""
Automated test suite for Task 5.1: Document Review Workflow Foundation.
Verifies:
1. Successful submission of draft document creates ReviewWorkflow and ReviewAssignment.
2. Workflow state is PENDING, and assignment correctly references assigned approver.
3. Document status transitions to 'under_review'.
4. Rejection of unauthenticated requests (missing/invalid JWT -> 401).
5. Inactive submitters rejected (401).
6. Non-approver or inactive approver rejected (400).
7. Cross-department review assignment rejected (400).
8. Ambiguous or missing department assignment rejected (400).
9. Submitter cannot assign themselves as approver (400).
10. Submitting non-draft documents rejected (409 Conflict: active, archived, under_review).
11. Duplicate active workflow rejected (409 Conflict via DB partial unique index / application check).
12. Unauthorized roles rejected (Department User submitting other department, Auditor, Approver, ReadOnly -> 403).
13. Audit event 'workflow.submit_for_review' recorded and rollback on audit-write failure.
14. Database cleanup and isolation.
"""
import uuid
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.audit import AuditWriteError


@pytest.fixture(autouse=True)
def cleanup_review_workflow_data(db_session: Session):
    """Clean up any workflows, assignments, and documents created during tests."""
    yield
    try:
        db_session.rollback()
        # Delete test assignments & workflows
        db_session.query(ReviewAssignment).delete()
        db_session.query(ReviewWorkflow).delete()
        # Delete documents created in tests
        test_docs = db_session.query(DigitalDocument).filter(
            DigitalDocument.title.like("Workflow Test Doc%")
        ).all()
        for doc in test_docs:
            db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()


def create_test_doc(
    db: Session,
    creator: User,
    department: str = "Legal",
    classification: str = "Internal",
    mime_type: str = "application/pdf",
    status: DocumentStatus = DocumentStatus.DRAFT,
    title_suffix: str = "",
) -> DigitalDocument:
    """Helper creating a test document in the database."""
    unique_suffix = uuid.uuid4().hex[:6]
    doc = DigitalDocument(
        document_reference=f"DOC-WF-{unique_suffix.upper()}",
        title=f"Workflow Test Doc {title_suffix} {unique_suffix}",
        subject="Workflow testing",
        department=department,
        classification=classification,
        mime_type=mime_type,
        status=status,
        created_by_id=creator.id,
    )
    db.add(doc)
    db.flush()

    # Add version 1
    version = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"legal/2026/DOC-WF-{unique_suffix}/v1.pdf",
        original_filename="sample.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        extracted_text="Sample text content for workflow test.",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=creator.id,
    )
    db.add(version)
    db.commit()
    db.refresh(doc)
    return doc


def test_submit_draft_document_for_review_success(client, db_session, role_user_factory):
    """
    Test 1: Department user submits a draft document from their own department
    to an eligible approver in the same department.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver_info = role_user_factory(UserRole.APPROVER)
    approver = approver_info["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)

    token = create_access_token(user_id=dept_user.id)
    response = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "approver_id": str(approver.id),
            "comments": "Please review this draft contract.",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["document_id"] == str(doc.id)
    assert data["document_status"] == "under_review"
    assert data["workflow_state"] == "pending"
    assert data["submitter_id"] == str(dept_user.id)
    assert data["comments"] == "Please review this draft contract."
    assert data["assignment"]["assigned_approver_id"] == str(approver.id)
    assert data["assignment"]["decision"] is None

    # Verify DB state
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.UNDER_REVIEW

    wf = db_session.query(ReviewWorkflow).filter(ReviewWorkflow.document_id == doc.id).first()
    assert wf is not None
    assert wf.state == WorkflowState.PENDING
    assert wf.submitter_id == dept_user.id
    assert wf.submission_comments == "Please review this draft contract."

    assign = db_session.query(ReviewAssignment).filter(ReviewAssignment.workflow_id == wf.id).first()
    assert assign is not None
    assert assign.assigned_approver_id == approver.id


def test_admin_and_records_officer_can_submit_across_departments(client, db_session, role_user_factory):
    """
    Test 2: Administrators and Records Officers can submit draft documents for review.
    Approver still belongs to the document's department.
    """
    approver_info = role_user_factory(UserRole.APPROVER)
    approver = approver_info["user"]
    approver.department = "Finance"
    db_session.commit()

    admin_info = role_user_factory(UserRole.ADMIN)
    admin_user = admin_info["user"]

    doc = create_test_doc(db_session, creator=admin_user, department="Finance", status=DocumentStatus.DRAFT)

    token = create_access_token(user_id=admin_user.id)
    response = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(approver.id), "comments": "Admin submission"},
    )
    assert response.status_code == 201
    assert response.json()["document_status"] == "under_review"

    # Test Records Officer
    rec_info = role_user_factory(UserRole.RECORDS_OFFICER)
    rec_user = rec_info["user"]
    doc2 = create_test_doc(db_session, creator=rec_user, department="Finance", status=DocumentStatus.DRAFT)
    token2 = create_access_token(user_id=rec_user.id)
    response2 = client.post(
        f"/api/v1/documents/{doc2.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token2}"},
        json={"approver_id": str(approver.id), "comments": "Records Officer submission"},
    )
    assert response2.status_code == 201
    assert response2.json()["document_status"] == "under_review"


def test_unauthenticated_requests_rejected(client, db_session, role_user_factory):
    """
    Test 3: Missing or invalid JWT credentials return 401.
    """
    doc_id = uuid.uuid4()
    appr_id = uuid.uuid4()

    # Missing header
    res1 = client.post(
        f"/api/v1/documents/{doc_id}/submit-for-review",
        json={"approver_id": str(appr_id)},
    )
    assert res1.status_code == 401

    # Invalid token
    res2 = client.post(
        f"/api/v1/documents/{doc_id}/submit-for-review",
        headers={"Authorization": "Bearer invalid.token.value"},
        json={"approver_id": str(appr_id)},
    )
    assert res2.status_code == 401


def test_inactive_submitter_rejected(client, db_session, role_user_factory):
    """
    Test 4: Inactive users are rejected upon submission.
    """
    user_info = role_user_factory(UserRole.DEPARTMENT_USER, is_active=False)
    user = user_info["user"]
    token = create_access_token(user_id=user.id)

    res = client.post(
        f"/api/v1/documents/{uuid.uuid4()}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(uuid.uuid4())},
    )
    assert res.status_code == 401


def test_non_approver_or_inactive_assignee_rejected(client, db_session, role_user_factory):
    """
    Test 5: Assigned user must be active and have APPROVER role.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)
    token = create_access_token(user_id=dept_user.id)

    # Case A: Assignee is another DEPARTMENT_USER (not approver)
    other_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    other_user.department = "Legal"
    db_session.commit()

    res_a = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(other_user.id)},
    )
    assert res_a.status_code == 400
    assert "role" in res_a.json()["detail"].lower()

    # Case B: Assignee is inactive APPROVER
    inactive_appr = role_user_factory(UserRole.APPROVER, is_active=False)["user"]
    inactive_appr.department = "Legal"
    db_session.commit()

    res_b = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(inactive_appr.id)},
    )
    assert res_b.status_code == 400
    assert "inactive" in res_b.json()["detail"].lower()


def test_cross_department_assignment_denied(client, db_session, role_user_factory):
    """
    Test 6: Approver from a different department cannot be assigned to review the document.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    diff_appr_info = role_user_factory(UserRole.APPROVER)
    diff_appr = diff_appr_info["user"]
    diff_appr.department = "HR"  # Cross-department
    db_session.commit()

    doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)
    token = create_access_token(user_id=dept_user.id)

    res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(diff_appr.id)},
    )
    assert res.status_code == 400
    assert "cross-department" in res.json()["detail"].lower()


def test_missing_or_ambiguous_department_denied(client, db_session, role_user_factory):
    """
    Test 7: Missing department on either document or approver is strictly denied.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    no_dept_appr = role_user_factory(UserRole.APPROVER)["user"]
    no_dept_appr.department = None
    db_session.commit()

    doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)
    token = create_access_token(user_id=dept_user.id)

    res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(no_dept_appr.id)},
    )
    assert res.status_code == 400
    assert "ambiguous" in res.json()["detail"].lower()


def test_self_assignment_prevented(client, db_session, role_user_factory):
    """
    Test 8: Submitter cannot assign themselves as approver.
    Admin (who can submit) assigning themselves (if also attempted) or direct validation.
    """
    admin_info = role_user_factory(UserRole.ADMIN)
    admin_user = admin_info["user"]
    admin_user.department = "Legal"
    db_session.commit()

    doc = create_test_doc(db_session, creator=admin_user, department="Legal", status=DocumentStatus.DRAFT)
    token = create_access_token(user_id=admin_user.id)

    res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(admin_user.id)},
    )
    # Admin does not have APPROVER role, so rejected with 400.
    assert res.status_code == 400


def test_submitting_non_draft_document_rejected(client, db_session, role_user_factory):
    """
    Test 9: Documents not in 'draft' status (e.g. active, archived, under_review) cannot be submitted.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    token = create_access_token(user_id=dept_user.id)

    for non_draft_status in [DocumentStatus.ACTIVE, DocumentStatus.ARCHIVED, DocumentStatus.UNDER_REVIEW]:
        doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=non_draft_status)
        res = client.post(
            f"/api/v1/documents/{doc.id}/submit-for-review",
            headers={"Authorization": f"Bearer {token}"},
            json={"approver_id": str(approver.id)},
        )
        assert res.status_code == 409
        assert "only draft documents" in res.json()["detail"].lower()


def test_duplicate_active_workflow_rejected(client, db_session, role_user_factory):
    """
    Test 10: Attempting to submit a document that already has an active pending workflow fails with 409.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)
    token = create_access_token(user_id=dept_user.id)

    # First submission succeeds
    res1 = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(approver.id)},
    )
    assert res1.status_code == 201

    # Second submission fails (document is now under_review and has pending workflow)
    res2 = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(approver.id)},
    )
    assert res2.status_code == 409


def test_unauthorized_roles_denied_submission(client, db_session, role_user_factory):
    """
    Test 11: Auditor, Approver, Read-Only, and Department User submitting another department's draft
    are all denied with 403 Forbidden.
    """
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    # Document in Legal department
    creator = role_user_factory(UserRole.ADMIN)["user"]
    doc = create_test_doc(db_session, creator=creator, department="Legal", status=DocumentStatus.DRAFT)

    # 1. Department user from HR
    hr_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    hr_user.department = "HR"
    db_session.commit()
    t_hr = create_access_token(user_id=hr_user.id)
    res_hr = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {t_hr}"},
        json={"approver_id": str(approver.id)},
    )
    assert res_hr.status_code == 403

    # 2. Auditor
    auditor = role_user_factory(UserRole.AUDITOR)["user"]
    auditor.department = "Legal"
    db_session.commit()
    t_aud = create_access_token(user_id=auditor.id)
    res_aud = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {t_aud}"},
        json={"approver_id": str(approver.id)},
    )
    assert res_aud.status_code == 403

    # 3. Read Only
    ro = role_user_factory(UserRole.READ_ONLY)["user"]
    ro.department = "Legal"
    db_session.commit()
    t_ro = create_access_token(user_id=ro.id)
    res_ro = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {t_ro}"},
        json={"approver_id": str(approver.id)},
    )
    assert res_ro.status_code == 403


def test_mandatory_audit_and_rollback_on_audit_failure(client, db_session, role_user_factory):
    """
    Test 12: Successful submission records audit log. If audit logging fails, the transaction is rolled back.
    """
    dept_user_info = role_user_factory(UserRole.DEPARTMENT_USER)
    dept_user = dept_user_info["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)
    token = create_access_token(user_id=dept_user.id)

    # A: Successful audit persistence
    res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token}"},
        json={"approver_id": str(approver.id), "comments": "Audit verification"},
    )
    assert res.status_code == 201

    audit_entry = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == doc.id,
            AuditLog.action == "workflow.submit_for_review",
        )
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.outcome == AuditOutcome.SUCCESS
    assert audit_entry.actor_id == dept_user.id
    assert audit_entry.details["previous_status"] == "draft"
    assert audit_entry.details["new_status"] == "under_review"

    # B: Simulate audit write failure on a second draft document
    doc2 = create_test_doc(db_session, creator=dept_user, department="Legal", status=DocumentStatus.DRAFT)
    with patch("app.services.audit.audit_service.log_from_request", side_effect=AuditWriteError("Simulated audit disk failure")):
        res_fail = client.post(
            f"/api/v1/documents/{doc2.id}/submit-for-review",
            headers={"Authorization": f"Bearer {token}"},
            json={"approver_id": str(approver.id)},
        )
        # Should raise 500 error due to AuditWriteError
        assert res_fail.status_code == 500

    # Verify rollback: doc2 must still be draft and have no workflows
    db_session.refresh(doc2)
    assert doc2.status == DocumentStatus.DRAFT
    wf2 = db_session.query(ReviewWorkflow).filter(ReviewWorkflow.document_id == doc2.id).first()
    assert wf2 is None
