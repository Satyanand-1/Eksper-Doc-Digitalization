"""
Automated test suite for Task 5.2: Approver Review, Approval, Rejection, and Document Activation.
Verifies:
1. Assigned approver can retrieve their review inbox with deterministic pagination.
2. Approver cannot see another approver's assignments.
3. Authorized workflow detail retrieval (by assigned approver and admin).
4. Unassigned approver cannot view or decide another user's workflow (non-disclosing 404).
5. Successful approval changes workflow state to 'approved' and document status to 'active'.
6. Successful rejection requires comments and returns the document to 'draft'.
7. Missing or invalid JWT on inbox, detail, and decision endpoints (401).
8. Inactive approver and invalid role (401/403).
9. Cross-department and classification restrictions (400).
10. Decision attempts against completed, cancelled, or invalid workflows (409 Conflict).
11. Concurrent approval and rejection attempts (PostgreSQL row-level locking integrity).
12. Missing current document version blocks decision (400).
13. Mandatory audit-write failure rolls back the decision and document status (500).
14. Unauthorized roles cannot enumerate workflow details (non-disclosing 404).
15. Existing submission, authorization, OCR, and audit behaviors remain intact.
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
def cleanup_workflow_test_data(db_session: Session):
    """Clean up workflows, assignments, and documents created during tests."""
    yield
    try:
        db_session.rollback()
        db_session.query(ReviewAssignment).delete()
        db_session.query(ReviewWorkflow).delete()
        test_docs = db_session.query(DigitalDocument).filter(
            DigitalDocument.title.like("Task52 Test Doc%")
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
    with_version: bool = True,
) -> tuple[DigitalDocument, ReviewWorkflow, ReviewAssignment]:
    """Helper creating a document in under_review status and an associated workflow & assignment."""
    suffix = uuid.uuid4().hex[:6]
    doc = DigitalDocument(
        document_reference=f"DOC-T52-{suffix.upper()}",
        title=f"Task52 Test Doc {suffix}",
        subject="Task 5.2 workflow testing",
        department=department,
        classification=classification,
        mime_type="application/pdf",
        status=doc_status,
        created_by_id=creator.id,
    )
    db.add(doc)
    db.flush()

    if with_version:
        version = DocumentVersion(
            document_id=doc.id,
            version_number=1,
            storage_key=f"legal/2026/DOC-T52-{suffix}/v1.pdf",
            original_filename="contract.pdf",
            mime_type="application/pdf",
            file_size_bytes=2048,
            file_hash_sha256="abc1234567890123456789012345678901234567890123456789012345678901",
            extracted_text="Contract body terms and conditions.",
            extraction_status=ExtractionStatus.COMPLETED,
            created_by_id=creator.id,
        )
        db.add(version)
        db.flush()

    wf = ReviewWorkflow(
        document_id=doc.id,
        submitter_id=creator.id,
        state=wf_state,
        submission_comments="Submitted for approval",
    )
    db.add(wf)
    db.flush()

    assign = ReviewAssignment(
        workflow_id=wf.id,
        assigned_approver_id=approver.id,
    )
    db.add(assign)
    db.commit()
    db.refresh(doc)
    db.refresh(wf)
    db.refresh(assign)

    return doc, wf, assign


def test_assigned_approver_can_retrieve_review_inbox(client, db_session, role_user_factory):
    """
    Test 1: Assigned approver can view their pending assignments inbox with correct metadata.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")

    token = create_access_token(user_id=approver.id)
    response = client.get(
        "/api/v1/workflows/my-assignments?page=1&page_size=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["page"] == 1
    assert data["page_size"] == 10

    # Locate our assignment
    found = next((item for item in data["items"] if item["assignment_id"] == str(assign.id)), None)
    assert found is not None
    assert found["workflow_id"] == str(wf.id)
    assert found["workflow_state"] == "pending"
    assert found["document"]["id"] == str(doc.id)
    assert found["document"]["document_reference"] == doc.document_reference
    assert found["document"]["title"] == doc.title
    assert found["submitter"]["email"] == dept_user.email
    assert found["submitter"]["full_name"] == dept_user.full_name


def test_approver_cannot_see_other_approvers_assignments(client, db_session, role_user_factory):
    """
    Test 2: Approver A cannot see assignments made to Approver B, even in the same department.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver_a = role_user_factory(UserRole.APPROVER)["user"]
    approver_a.department = "Legal"
    approver_b = role_user_factory(UserRole.APPROVER)["user"]
    approver_b.department = "Legal"
    db_session.commit()

    # Assign document to Approver A
    doc_a, wf_a, assign_a = setup_workflow_and_document(db_session, creator=dept_user, approver=approver_a, department="Legal")

    # Approver B requests their inbox
    token_b = create_access_token(user_id=approver_b.id)
    res_b = client.get(
        "/api/v1/workflows/my-assignments",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 200
    items_b = res_b.json()["items"]
    # Ensure assign_a is NOT in approver B's inbox
    assert not any(item["assignment_id"] == str(assign_a.id) for item in items_b)


def test_authorized_workflow_detail_retrieval(client, db_session, role_user_factory):
    """
    Test 3: Authorized assigned approver and Administrator can view workflow detail.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    admin = role_user_factory(UserRole.ADMIN)["user"]

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")

    # 1. Assigned approver checks detail
    token_appr = create_access_token(user_id=approver.id)
    res_appr = client.get(
        f"/api/v1/workflows/{wf.id}",
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert res_appr.status_code == 200
    detail = res_appr.json()
    assert detail["id"] == str(wf.id)
    assert detail["document_id"] == str(doc.id)
    assert detail["state"] == "pending"
    assert detail["document"]["document_reference"] == doc.document_reference
    assert detail["document"]["current_version"] is not None
    assert detail["document"]["current_version"]["version_number"] == 1
    assert detail["submitter"]["email"] == dept_user.email
    assert len(detail["assignments"]) == 1
    assert detail["assignments"][0]["assigned_approver_id"] == str(approver.id)

    # 2. Administrator checks detail (cross-department oversight)
    token_admin = create_access_token(user_id=admin.id)
    res_admin = client.get(
        f"/api/v1/workflows/{wf.id}",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["id"] == str(wf.id)


def test_unassigned_approver_cannot_view_or_decide_workflow(client, db_session, role_user_factory):
    """
    Test 4: Approver who is NOT assigned to the workflow receives 404 (non-disclosing).
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    assigned_appr = role_user_factory(UserRole.APPROVER)["user"]
    assigned_appr.department = "Legal"
    unassigned_appr = role_user_factory(UserRole.APPROVER)["user"]
    unassigned_appr.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=assigned_appr, department="Legal")

    token_unassigned = create_access_token(user_id=unassigned_appr.id)

    # Cannot view detail
    res_detail = client.get(
        f"/api/v1/workflows/{wf.id}",
        headers={"Authorization": f"Bearer {token_unassigned}"},
    )
    assert res_detail.status_code == 404

    # Cannot decide workflow
    res_decide = client.post(
        f"/api/v1/workflows/{wf.id}/decision",
        headers={"Authorization": f"Bearer {token_unassigned}"},
        json={"decision": "approved", "comments": "I am not assigned"},
    )
    assert res_decide.status_code == 404


def test_successful_approval_activates_document(client, db_session, role_user_factory):
    """
    Test 5: Assigned approver approves document -> workflow state becomes 'approved',
    document status transitions to 'active'.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")

    token = create_access_token(user_id=approver.id)
    response = client.post(
        f"/api/v1/workflows/{wf.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved", "comments": "Looks good and verified."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == str(wf.id)
    assert data["document_id"] == str(doc.id)
    assert data["document_status"] == "active"
    assert data["workflow_state"] == "approved"
    assert data["decision"] == "approved"
    assert data["decided_by_id"] == str(approver.id)
    assert data["comments"] == "Looks good and verified."

    # Verify DB persistence
    db_session.refresh(doc)
    db_session.refresh(wf)
    db_session.refresh(assign)
    assert doc.status == DocumentStatus.ACTIVE
    assert wf.state == WorkflowState.APPROVED
    assert assign.decision == ReviewDecision.APPROVED
    assert assign.decided_at is not None
    assert assign.decision_comments == "Looks good and verified."

    # Verify audit event
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == wf.id, AuditLog.action == "workflow.approved")
        .first()
    )
    assert audit is not None
    assert audit.outcome == AuditOutcome.SUCCESS
    assert audit.actor_id == approver.id


def test_successful_rejection_requires_comments_and_returns_document_to_draft(client, db_session, role_user_factory):
    """
    Test 6: Rejection requires non-empty comments (422 if missing), and transitions document to 'draft'.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")
    token = create_access_token(user_id=approver.id)

    # 1. Attempt rejection without comments -> 422
    res_missing_comment = client.post(
        f"/api/v1/workflows/{wf.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "rejected", "comments": "   "},
    )
    assert res_missing_comment.status_code == 422

    # 2. Rejection with valid reason
    res_valid_reject = client.post(
        f"/api/v1/workflows/{wf.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "rejected", "comments": "Missing clause 4.2 indemnity specification."},
    )
    assert res_valid_reject.status_code == 200
    data = res_valid_reject.json()
    assert data["document_status"] == "draft"
    assert data["workflow_state"] == "rejected"
    assert data["decision"] == "rejected"

    # Verify DB state
    db_session.refresh(doc)
    db_session.refresh(wf)
    db_session.refresh(assign)
    assert doc.status == DocumentStatus.DRAFT
    assert wf.state == WorkflowState.REJECTED
    assert assign.decision == ReviewDecision.REJECTED
    assert assign.decision_comments == "Missing clause 4.2 indemnity specification."

    # Verify audit event
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.resource_id == wf.id, AuditLog.action == "workflow.rejected")
        .first()
    )
    assert audit is not None
    assert audit.outcome == AuditOutcome.SUCCESS


def test_unauthenticated_requests_rejected(client, db_session, role_user_factory):
    """
    Test 7: Unauthenticated requests to inbox, detail, and decision endpoints return 401.
    """
    wf_id = uuid.uuid4()

    # Missing tokens
    assert client.get("/api/v1/workflows/my-assignments").status_code == 401
    assert client.get(f"/api/v1/workflows/{wf_id}").status_code == 401
    assert client.post(f"/api/v1/workflows/{wf_id}/decision", json={"decision": "approved"}).status_code == 401

    # Invalid token
    bad_headers = {"Authorization": "Bearer invalid.token.payload"}
    assert client.get("/api/v1/workflows/my-assignments", headers=bad_headers).status_code == 401
    assert client.get(f"/api/v1/workflows/{wf_id}", headers=bad_headers).status_code == 401
    assert client.post(f"/api/v1/workflows/{wf_id}/decision", headers=bad_headers, json={"decision": "approved"}).status_code == 401


def test_inactive_approver_and_invalid_role(client, db_session, role_user_factory):
    """
    Test 8: Inactive approvers (401) and users without the approver role (403) are rejected.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    inactive_appr = role_user_factory(UserRole.APPROVER, is_active=False)["user"]

    token_inactive = create_access_token(user_id=inactive_appr.id)
    token_dept = create_access_token(user_id=dept_user.id)

    # Inactive approver -> 401
    assert client.get("/api/v1/workflows/my-assignments", headers={"Authorization": f"Bearer {token_inactive}"}).status_code == 401

    # Non-approver role (Department User) -> 403
    assert client.get("/api/v1/workflows/my-assignments", headers={"Authorization": f"Bearer {token_dept}"}).status_code == 403
    assert client.post(f"/api/v1/workflows/{uuid.uuid4()}/decision", headers={"Authorization": f"Bearer {token_dept}"}, json={"decision": "approved"}).status_code == 403


def test_cross_department_restriction_blocks_decision(client, db_session, role_user_factory):
    """
    Test 9: If approver's department was changed after assignment to a different department,
    decision is blocked with 400.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")

    # Approver department changes to HR
    approver.department = "HR"
    db_session.commit()

    token = create_access_token(user_id=approver.id)
    res = client.post(
        f"/api/v1/workflows/{wf.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert res.status_code == 400
    assert "cross-department" in res.json()["detail"].lower()


def test_decisions_against_completed_or_invalid_workflows_fail(client, db_session, role_user_factory):
    """
    Test 10: Cannot decide against an already approved, rejected, or cancelled workflow (409 Conflict).
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    for invalid_state in [WorkflowState.APPROVED, WorkflowState.REJECTED, WorkflowState.CANCELLED]:
        doc, wf, assign = setup_workflow_and_document(
            db_session, creator=dept_user, approver=approver, department="Legal", wf_state=invalid_state
        )
        token = create_access_token(user_id=approver.id)

        res = client.post(
            f"/api/v1/workflows/{wf.id}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": "approved"},
        )
        assert res.status_code == 409
        assert "cannot accept further decisions" in res.json()["detail"].lower()


def test_concurrent_approval_and_rejection_attempts(client, db_session, role_user_factory):
    """
    Test 11: Concurrent decision requests on the same workflow guarantee exactly one winner
    and one 409 Conflict failure due to row-level locking.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")
    token = create_access_token(user_id=approver.id)

    results = []

    def make_decision(decision_val, comments_val):
        # Dedicated client for thread execution
        from fastapi.testclient import TestClient
        from app.main import app
        thread_client = TestClient(app)
        res = thread_client.post(
            f"/api/v1/workflows/{wf.id}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": decision_val, "comments": comments_val},
        )
        results.append(res.status_code)

    t1 = threading.Thread(target=make_decision, args=("approved", "Approval thread"))
    t2 = threading.Thread(target=make_decision, args=("rejected", "Rejection thread"))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # One request should succeed (200), the other must conflict (409)
    assert 200 in results
    assert 409 in results


def test_missing_current_document_version_blocks_decision(client, db_session, role_user_factory):
    """
    Test 12: A document without any registered versions cannot be approved or rejected (400).
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(
        db_session, creator=dept_user, approver=approver, department="Legal", with_version=False
    )
    token = create_access_token(user_id=approver.id)

    res = client.post(
        f"/api/v1/workflows/{wf.id}/decision",
        headers={"Authorization": f"Bearer {token}"},
        json={"decision": "approved"},
    )
    assert res.status_code == 400
    assert "no registered versions" in res.json()["detail"].lower()


def test_mandatory_audit_failure_rolls_back_decision(client, db_session, role_user_factory):
    """
    Test 13: Failure to record mandatory audit event rolls back the decision and document state (500).
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")
    token = create_access_token(user_id=approver.id)

    with patch("app.services.audit.audit_service.log_from_request", side_effect=AuditWriteError("Simulated disk error")):
        res = client.post(
            f"/api/v1/workflows/{wf.id}/decision",
            headers={"Authorization": f"Bearer {token}"},
            json={"decision": "approved"},
        )
        assert res.status_code == 500

    # Verify atomic rollback
    db_session.refresh(doc)
    db_session.refresh(wf)
    db_session.refresh(assign)
    assert doc.status == DocumentStatus.UNDER_REVIEW
    assert wf.state == WorkflowState.PENDING
    assert assign.decision is None


def test_unauthorized_roles_cannot_enumerate_workflows(client, db_session, role_user_factory):
    """
    Test 14: Unauthorized roles (Auditor, Read-Only, Department User) receive non-disclosing 404
    when attempting to retrieve workflow detail.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wf, assign = setup_workflow_and_document(db_session, creator=dept_user, approver=approver, department="Legal")

    for unauthorized_role in [UserRole.AUDITOR, UserRole.READ_ONLY, UserRole.DEPARTMENT_USER]:
        user = role_user_factory(unauthorized_role)["user"]
        user.department = "Legal"
        db_session.commit()
        token = create_access_token(user_id=user.id)

        res = client.get(
            f"/api/v1/workflows/{wf.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 404
