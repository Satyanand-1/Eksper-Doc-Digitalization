"""
Automated test suite for Task 5.4: Workflow Cancellation and Submission Withdrawal.
Verifies:
1. Submitter can cancel their pending review workflow, transitioning workflow state to 'cancelled'
   and document status to 'draft'.
2. Admin can cancel a pending review workflow across departments.
3. Records Officer can cancel a pending review workflow across departments.
4. Assigned approver cannot cancel or withdraw a review workflow (404/403).
5. Unassigned approver cannot cancel or discover a workflow (non-disclosing 404).
6. Department user cannot cancel another user's review workflow (non-disclosing 404).
7. Read-only user and Auditor are denied cancellation permissions (non-disclosing 404).
8. Inactive user is rejected when attempting to cancel (401).
9. Missing or invalid Bearer JWT is rejected with 401 Unauthorized.
10. Cancelling an already approved, rejected, or cancelled workflow returns 409 Conflict.
11. Cancelling when document is not in 'under_review' status returns 409 Conflict.
12. Empty, whitespace-only, or missing cancellation comments are rejected (422 Unprocessable Entity).
13. Mandatory audit event 'workflow.cancelled' is persisted; failed audit write rolls back the transaction.
14. Workflow history includes cancellation metadata (cancelled_by, cancelled_at, cancellation_comments).
15. Resubmission lifecycle: After cancellation, the draft document can be successfully submitted again.
16. Concurrent cancellation vs approver decision attempts handled safely via row-level locking.
"""
import uuid
import threading
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState, ReviewDecision
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token
from app.services.audit import AuditWriteError
from app.database import SessionLocal


@pytest.fixture(autouse=True)
def cleanup_cancellation_test_data(db_session: Session):
    """Clean up workflows, assignments, and documents created during tests."""
    yield
    try:
        db_session.rollback()
        db_session.query(ReviewAssignment).delete()
        db_session.query(ReviewWorkflow).delete()
        test_docs = db_session.query(DigitalDocument).filter(
            DigitalDocument.title.like("Task54 Test Doc%")
        ).all()
        for doc in test_docs:
            db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()


def setup_workflow_and_document(
    db: Session,
    creator: User,
    approver: User,
    department: str = "Legal",
    classification: str = "Internal",
    doc_status: DocumentStatus = DocumentStatus.UNDER_REVIEW,
    wf_state: WorkflowState = WorkflowState.PENDING,
) -> tuple[DigitalDocument, ReviewWorkflow, ReviewAssignment]:
    """Helper creating a document in under_review status and an associated workflow & assignment."""
    suffix = uuid.uuid4().hex[:6]
    doc = DigitalDocument(
        document_reference=f"DOC-T54-{suffix.upper()}",
        title=f"Task54 Test Doc {suffix}",
        subject="Task 5.4 cancellation testing",
        department=department,
        classification=classification,
        mime_type="application/pdf",
        status=doc_status,
        created_by_id=creator.id,
    )
    db.add(doc)
    db.flush()

    # Add a version
    v = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"legal/2026/DOC-T54-{suffix}/v1.pdf",
        original_filename="sample.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="abc1234567890123456789012345678901234567890123456789012345678901",
        extracted_text="Sample text content",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=creator.id,
    )
    db.add(v)
    db.flush()

    wf = ReviewWorkflow(
        document_id=doc.id,
        state=wf_state,
        submitter_id=creator.id,
        submission_comments="Initial submission for review",
    )
    db.add(wf)
    db.flush()

    assignment = ReviewAssignment(
        workflow_id=wf.id,
        assigned_approver_id=approver.id,
    )
    db.add(assignment)
    db.commit()
    db.refresh(doc)
    db.refresh(wf)
    db.refresh(assignment)
    return doc, wf, assignment


def test_submitter_can_cancel_pending_workflow(client, db_session, role_user_factory):
    """
    1. Submitter can withdraw/cancel their pending workflow.
    Workflow transitions to 'cancelled', document returns to 'draft',
    cancellation metadata is properly recorded.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=dept_user, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=dept_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Withdrawing submission for content revision"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == str(wf.id)
    assert data["document_id"] == str(doc.id)
    assert data["document_reference"] == doc.document_reference
    assert data["document_status"] == DocumentStatus.DRAFT.value
    assert data["workflow_state"] == WorkflowState.CANCELLED.value
    assert data["cancelled_by_id"] == str(dept_user.id)
    assert data["comments"] == "Withdrawing submission for content revision"
    assert data["cancelled_at"] is not None

    # Verify database persistence
    db_session.refresh(wf)
    db_session.refresh(doc)
    assert wf.state == WorkflowState.CANCELLED
    assert doc.status == DocumentStatus.DRAFT
    assert wf.cancelled_by_id == dept_user.id
    assert wf.cancellation_comments == "Withdrawing submission for content revision"


def test_admin_can_cancel_pending_workflow_across_departments(client, db_session, role_user_factory):
    """
    2. Administrator can cancel any pending workflow across departments.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    admin = role_user_factory(UserRole.ADMIN)["user"]
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=dept_user, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Administrative intervention: cancelled review"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_state"] == WorkflowState.CANCELLED.value
    assert data["document_status"] == DocumentStatus.DRAFT.value
    assert data["cancelled_by_id"] == str(admin.id)


def test_records_officer_can_cancel_pending_workflow_across_departments(client, db_session, role_user_factory):
    """
    3. Records Officer can cancel any pending workflow across departments.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    records_officer = role_user_factory(UserRole.RECORDS_OFFICER)["user"]
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=dept_user, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=records_officer.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Records officer withdrawal per compliance policy"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_state"] == WorkflowState.CANCELLED.value
    assert data["document_status"] == DocumentStatus.DRAFT.value
    assert data["cancelled_by_id"] == str(records_officer.id)


def test_assigned_approver_cannot_cancel_workflow(client, db_session, role_user_factory):
    """
    4. Assigned approver cannot cancel the workflow (they can only approve or reject).
    Receives non-disclosing 404.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=dept_user, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=approver.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Approver attempting to cancel workflow"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 404

    # Ensure state was not changed
    db_session.refresh(wf)
    db_session.refresh(doc)
    assert wf.state == WorkflowState.PENDING
    assert doc.status == DocumentStatus.UNDER_REVIEW


def test_unassigned_approver_cannot_cancel_workflow(client, db_session, role_user_factory):
    """
    5. An unassigned approver cannot cancel or discover another approver's workflow.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    assigned_approver = role_user_factory(UserRole.APPROVER)["user"]
    assigned_approver.department = "Legal"

    # Create a second approver
    unassigned_approver = role_user_factory(UserRole.APPROVER)["user"]
    unassigned_approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=dept_user, approver=assigned_approver, department="Legal"
    )

    token = create_access_token(user_id=unassigned_approver.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Unassigned approver attempt"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 404
    db_session.refresh(wf)
    assert wf.state == WorkflowState.PENDING


def test_other_department_user_cannot_cancel_workflow(client, db_session, role_user_factory):
    """
    6. Another department user (not the submitter) cannot cancel someone else's workflow.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"

    other_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    other_user.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=other_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Colleague cancelling someone else's submission"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 404
    db_session.refresh(wf)
    assert wf.state == WorkflowState.PENDING


def test_unauthorized_roles_denied_cancellation(client, db_session, role_user_factory):
    """
    7. Read-Only users and Auditors cannot cancel review workflows.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    for role in [UserRole.READ_ONLY, UserRole.AUDITOR]:
        user = role_user_factory(role)["user"]
        user.department = "Legal"
        db_session.commit()

        token = create_access_token(user_id=user.id)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"comments": f"Role {role.value} attempting cancellation"}
        response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

        assert response.status_code == 404

    db_session.refresh(wf)
    assert wf.state == WorkflowState.PENDING


def test_inactive_user_rejected_on_cancellation(client, db_session, role_user_factory):
    """
    8. Inactive submitter cannot cancel workflow.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    submitter.is_active = False
    db_session.commit()

    try:
        token = create_access_token(user_id=submitter.id)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"comments": "Inactive user cancellation attempt"}
        response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

        assert response.status_code == 401
    finally:
        submitter.is_active = True
        db_session.commit()


def test_unauthenticated_requests_rejected(client, db_session):
    """
    9. Missing or invalid Bearer JWT returns 401 Unauthorized.
    """
    wf_id = uuid.uuid4()
    payload = {"comments": "Some comment"}

    # No token
    res1 = client.post(f"/api/v1/workflows/{wf_id}/cancel", json=payload)
    assert res1.status_code == 401

    # Invalid token
    res2 = client.post(
        f"/api/v1/workflows/{wf_id}/cancel",
        json=payload,
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert res2.status_code == 401


def test_cancelling_already_completed_or_cancelled_workflow_fails(client, db_session, role_user_factory):
    """
    10. Cancelling an already approved, rejected, or cancelled workflow returns 409 Conflict.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    for non_pending_state in [WorkflowState.APPROVED, WorkflowState.REJECTED, WorkflowState.CANCELLED]:
        doc, wf, _ = setup_workflow_and_document(
            db_session,
            creator=submitter,
            approver=approver,
            department="Legal",
            doc_status=DocumentStatus.ACTIVE if non_pending_state == WorkflowState.APPROVED else DocumentStatus.DRAFT,
            wf_state=non_pending_state,
        )

        token = create_access_token(user_id=submitter.id)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"comments": "Attempting to cancel non-pending workflow"}
        response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

        assert response.status_code == 409
        assert "cannot be cancelled" in response.json()["detail"].lower() or "state" in response.json()["detail"].lower()


def test_cancelling_workflow_when_document_not_under_review_fails(client, db_session, role_user_factory):
    """
    11. Cancelling when document status is not 'under_review' returns 409 Conflict.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session,
        creator=submitter,
        approver=approver,
        department="Legal",
        doc_status=DocumentStatus.DRAFT,  # Mismatched status
        wf_state=WorkflowState.PENDING,
    )

    token = create_access_token(user_id=submitter.id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"comments": "Attempting cancellation on draft document"}
    response = client.post(f"/api/v1/workflows/{wf.id}/cancel", json=payload, headers=headers)

    assert response.status_code == 409
    assert "under_review" in response.json()["detail"]


def test_empty_or_whitespace_cancellation_comments_rejected(client, db_session, role_user_factory):
    """
    12. Cancellation reason is mandatory, bounded (max 1000 chars), and cannot be empty or whitespace.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=submitter.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Empty string
    res1 = client.post(f"/api/v1/workflows/{wf.id}/cancel", json={"comments": ""}, headers=headers)
    assert res1.status_code == 422

    # Whitespace only
    res2 = client.post(f"/api/v1/workflows/{wf.id}/cancel", json={"comments": "   \n\t  "}, headers=headers)
    assert res2.status_code == 422

    # Missing field
    res3 = client.post(f"/api/v1/workflows/{wf.id}/cancel", json={}, headers=headers)
    assert res3.status_code == 422

    # Over 1000 characters
    res4 = client.post(f"/api/v1/workflows/{wf.id}/cancel", json={"comments": "x" * 1001}, headers=headers)
    assert res4.status_code == 422


def test_mandatory_audit_and_rollback_on_audit_failure(client, db_session, role_user_factory):
    """
    13. Audit event 'workflow.cancelled' is recorded on success.
    If audit logging fails, the transaction is atomically rolled back (500).
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=submitter.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Simulate audit write failure
    with patch("app.api.v1.workflows.audit_service.log_from_request", side_effect=AuditWriteError("Simulated DB audit error")):
        response = client.post(
            f"/api/v1/workflows/{wf.id}/cancel",
            json={"comments": "Audit rollback test"},
            headers=headers,
        )
        assert response.status_code == 500

    # Ensure transaction rolled back
    db_session.refresh(wf)
    db_session.refresh(doc)
    assert wf.state == WorkflowState.PENDING
    assert doc.status == DocumentStatus.UNDER_REVIEW

    # Now perform real cancellation without error
    response_ok = client.post(
        f"/api/v1/workflows/{wf.id}/cancel",
        json={"comments": "Real cancellation after simulated audit error"},
        headers=headers,
    )
    assert response_ok.status_code == 200

    # Verify audit event in DB
    audit_record = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.resource_id == wf.id,
            AuditLog.action == "workflow.cancelled",
            AuditLog.outcome == AuditOutcome.SUCCESS,
        )
        .first()
    )
    assert audit_record is not None
    assert audit_record.details["previous_document_status"] == DocumentStatus.UNDER_REVIEW.value
    assert audit_record.details["new_document_status"] == DocumentStatus.DRAFT.value
    assert audit_record.details["comments"] == "Real cancellation after simulated audit error"


def test_workflow_history_exposes_cancellation_metadata(client, db_session, role_user_factory):
    """
    14. GET /api/v1/documents/{document_id}/workflow-history exposes cancellation metadata
    (cancelled_by, cancelled_at, cancellation_comments).
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    admin = role_user_factory(UserRole.ADMIN)["user"]
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    # Cancel via submitter
    token_sub = create_access_token(user_id=submitter.id)
    cancel_res = client.post(
        f"/api/v1/workflows/{wf.id}/cancel",
        json={"comments": "Cancelled for history verification"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert cancel_res.status_code == 200

    # Check workflow history as Admin
    token_admin = create_access_token(user_id=admin.id)
    hist_res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert hist_res.status_code == 200
    hist_data = hist_res.json()

    assert hist_data["total_attempts"] == 1
    attempt = hist_data["attempts"][0]
    assert attempt["state"] == WorkflowState.CANCELLED.value
    assert attempt["cancelled_by"] is not None
    assert attempt["cancelled_by"]["id"] == str(submitter.id)
    assert attempt["cancelled_by"]["email"] == submitter.email
    assert attempt["cancelled_at"] is not None
    assert attempt["cancellation_comments"] == "Cancelled for history verification"


def test_resubmission_lifecycle_after_cancellation(client, db_session, role_user_factory):
    """
    15. Resubmission lifecycle:
    Draft document -> Submit for review -> Cancel -> Document returned to draft ->
    Submit for review again -> New pending workflow created -> History displays both attempts.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf1, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    token = create_access_token(user_id=submitter.id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Cancel the initial workflow
    c_res = client.post(
        f"/api/v1/workflows/{wf1.id}/cancel",
        json={"comments": "Cancelled to add more information"},
        headers=headers,
    )
    assert c_res.status_code == 200

    # Verify document is back to draft
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.DRAFT

    # 2. Resubmit the document for review
    sub_res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Second submission with corrections"},
        headers=headers,
    )
    assert sub_res.status_code == 201
    new_wf_data = sub_res.json()
    wf2_id = uuid.UUID(new_wf_data["workflow_id"])
    assert wf2_id != wf1.id
    assert new_wf_data["workflow_state"] == WorkflowState.PENDING.value
    assert new_wf_data["document_status"] == DocumentStatus.UNDER_REVIEW.value

    # 3. Retrieve history and verify both attempts are present in chronological order
    hist_res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers=headers,
    )
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["total_attempts"] == 2
    assert hist["attempts"][0]["workflow_id"] == str(wf1.id)
    assert hist["attempts"][0]["state"] == WorkflowState.CANCELLED.value
    assert hist["attempts"][0]["cancellation_comments"] == "Cancelled to add more information"
    assert hist["attempts"][1]["workflow_id"] == str(wf2_id)
    assert hist["attempts"][1]["state"] == WorkflowState.PENDING.value


def test_concurrent_cancellation_and_approval_race(client, db_session, role_user_factory):
    """
    16. Concurrent race condition safety:
    When approver attempts to approve and submitter attempts to cancel at the same time,
    row-level locking ensures exactly one succeeds and the other receives 409 Conflict.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, _ = setup_workflow_and_document(
        db_session, creator=submitter, approver=approver, department="Legal"
    )

    results = []
    barrier = threading.Barrier(2)

    def do_cancel():
        session = SessionLocal()
        try:
            token = create_access_token(user_id=submitter.id)
            barrier.wait()
            res = client.post(
                f"/api/v1/workflows/{wf.id}/cancel",
                json={"comments": "Concurrent cancellation attempt"},
                headers={"Authorization": f"Bearer {token}"},
            )
            results.append(("cancel", res.status_code))
        finally:
            session.close()

    def do_approve():
        session = SessionLocal()
        try:
            token = create_access_token(user_id=approver.id)
            barrier.wait()
            res = client.post(
                f"/api/v1/workflows/{wf.id}/decision",
                json={"decision": "approved", "comments": "Concurrent approval attempt"},
                headers={"Authorization": f"Bearer {token}"},
            )
            results.append(("approve", res.status_code))
        finally:
            session.close()

    t1 = threading.Thread(target=do_cancel)
    t2 = threading.Thread(target=do_approve)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One should succeed (200) and the other should get Conflict (409)
    status_codes = [r[1] for r in results]
    assert 200 in status_codes
    assert 409 in status_codes

    # Verify database consistency
    db_session.refresh(wf)
    db_session.refresh(doc)
    if wf.state == WorkflowState.CANCELLED:
        assert doc.status == DocumentStatus.DRAFT
    elif wf.state == WorkflowState.APPROVED:
        assert doc.status == DocumentStatus.ACTIVE
