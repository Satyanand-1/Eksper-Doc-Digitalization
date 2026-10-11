"""
Automated test suite for Task 5.3: Workflow History and Decision Traceability.
Verifies:
1. Authorized admin retrieves complete workflow history.
2. Authorized records officer retrieves workflow history.
3. Assigned approver retrieves permitted workflow history.
4. Unassigned approver cannot enumerate another approver's workflows (404).
5. Submitting user can retrieve workflow history for their document.
6. Unauthorized roles receive expected non-disclosing 404 response.
7. Inactive users are denied (401).
8. Missing document returns 404.
9. Document with no workflow returns empty history (attempts = [], total_attempts = 0).
10. Rejected workflow remains visible after a later resubmission.
11. Previous decisions and comments remain unchanged.
12. Workflow attempts are returned in deterministic chronological order (oldest first).
13. History response contains no sensitive or internal storage fields.
14. History retrieval does not modify application state.
15. Existing document authorization and Task 5.2 decision tests continue to pass.
"""
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState, ReviewDecision
from app.models.audit import AuditLog, AuditOutcome
from app.jwt import create_access_token


@pytest.fixture(autouse=True)
def cleanup_workflow_history_test_data(db_session: Session):
    """Clean up test workflows, assignments, and documents."""
    yield
    try:
        db_session.rollback()
        db_session.query(ReviewAssignment).delete()
        db_session.query(ReviewWorkflow).delete()
        test_docs = db_session.query(DigitalDocument).filter(
            DigitalDocument.title.like("Task53 Test Doc%")
        ).all()
        for doc in test_docs:
            db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()


def create_document_with_history(
    db: Session,
    creator: User,
    approver1: User,
    approver2: User | None = None,
    department: str = "Legal",
    classification: str = "Internal",
) -> tuple[DigitalDocument, list[ReviewWorkflow]]:
    """
    Creates a document and simulates multiple historical review attempts:
    Attempt 1: Submitted -> Rejected by approver1 (returns to draft)
    Attempt 2: Resubmitted -> Approved by approver2 or approver1 (document becomes active)
    """
    suffix = uuid.uuid4().hex[:6]
    now = datetime.now(timezone.utc)

    doc = DigitalDocument(
        document_reference=f"DOC-T53-{suffix.upper()}",
        title=f"Task53 Test Doc {suffix}",
        subject="Task 5.3 history testing",
        department=department,
        classification=classification,
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=creator.id,
    )
    db.add(doc)
    db.flush()

    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"legal/2026/DOC-T53-{suffix}/v1.pdf",
        original_filename="contract_v1.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="1111111111111111111111111111111111111111111111111111111111111111",
        extracted_text="Initial text content",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=creator.id,
    )
    db.add(v1)
    db.flush()

    # Attempt 1: 2 hours ago, Rejected
    t1_submitted = now - timedelta(hours=2)
    t1_decided = now - timedelta(hours=1, minutes=45)
    wf1 = ReviewWorkflow(
        document_id=doc.id,
        submitter_id=creator.id,
        state=WorkflowState.REJECTED,
        submission_comments="Initial submission for review",
        submitted_at=t1_submitted,
    )
    db.add(wf1)
    db.flush()

    assign1 = ReviewAssignment(
        workflow_id=wf1.id,
        assigned_approver_id=approver1.id,
        assigned_at=t1_submitted,
        decision=ReviewDecision.REJECTED,
        decided_at=t1_decided,
        decision_comments="Missing exhibit B annexure.",
    )
    db.add(assign1)

    # Attempt 2: 1 hour ago, Approved
    target_approver2 = approver2 if approver2 is not None else approver1
    t2_submitted = now - timedelta(hours=1)
    t2_decided = now - timedelta(minutes=30)
    wf2 = ReviewWorkflow(
        document_id=doc.id,
        submitter_id=creator.id,
        state=WorkflowState.APPROVED,
        submission_comments="Resubmitted with exhibit B attached",
        submitted_at=t2_submitted,
    )
    db.add(wf2)
    db.flush()

    assign2 = ReviewAssignment(
        workflow_id=wf2.id,
        assigned_approver_id=target_approver2.id,
        assigned_at=t2_submitted,
        decision=ReviewDecision.APPROVED,
        decided_at=t2_decided,
        decision_comments="Approved with all attachments verified.",
    )
    db.add(assign2)

    db.commit()
    db.refresh(doc)
    db.refresh(wf1)
    db.refresh(wf2)

    return doc, [wf1, wf2]


def test_admin_retrieves_workflow_history(client, db_session, role_user_factory):
    """
    Test 1: Administrator can retrieve full workflow history across attempts.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    admin = role_user_factory(UserRole.ADMIN)["user"]
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=approver)

    token = create_access_token(user_id=admin.id)
    response = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == str(doc.id)
    assert data["document_reference"] == doc.document_reference
    assert data["document_status"] == "active"
    assert data["total_attempts"] == 2
    assert len(data["attempts"]) == 2

    # Verify chronological ordering (oldest first)
    assert data["attempts"][0]["workflow_id"] == str(wfs[0].id)
    assert data["attempts"][0]["state"] == "rejected"
    assert data["attempts"][0]["submission_comments"] == "Initial submission for review"
    assert data["attempts"][0]["assignments"][0]["decision"] == "rejected"
    assert data["attempts"][0]["assignments"][0]["decision_comments"] == "Missing exhibit B annexure."

    assert data["attempts"][1]["workflow_id"] == str(wfs[1].id)
    assert data["attempts"][1]["state"] == "approved"
    assert data["attempts"][1]["submission_comments"] == "Resubmitted with exhibit B attached"
    assert data["attempts"][1]["assignments"][0]["decision"] == "approved"
    assert data["attempts"][1]["assignments"][0]["decision_comments"] == "Approved with all attachments verified."


def test_records_officer_retrieves_workflow_history(client, db_session, role_user_factory):
    """
    Test 2: Records Officer can view workflow history across departments.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Finance"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Finance"
    records_officer = role_user_factory(UserRole.RECORDS_OFFICER)["user"]
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=approver, department="Finance")

    token = create_access_token(user_id=records_officer.id)
    res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["total_attempts"] == 2


def test_assigned_approver_retrieves_permitted_history(client, db_session, role_user_factory):
    """
    Test 3: Approver assigned to attempt 1 can retrieve that attempt in history.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    approver1 = role_user_factory(UserRole.APPROVER)["user"]
    approver1.department = "Legal"
    approver2 = role_user_factory(UserRole.APPROVER)["user"]
    approver2.department = "Legal"
    db_session.commit()

    # Attempt 1 assigned to approver1, Attempt 2 assigned to approver2
    doc, wfs = create_document_with_history(
        db_session, creator=creator, approver1=approver1, approver2=approver2, department="Legal"
    )

    # Approver 1 retrieves history
    token1 = create_access_token(user_id=approver1.id)
    res1 = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    # Approver 1 was assigned ONLY to attempt 1, so only attempt 1 is revealed
    assert data1["total_attempts"] == 1
    assert data1["attempts"][0]["workflow_id"] == str(wfs[0].id)
    assert data1["attempts"][0]["assignments"][0]["assigned_approver"]["id"] == str(approver1.id)


def test_unassigned_approver_cannot_enumerate_other_approvers_workflows(client, db_session, role_user_factory):
    """
    Test 4: Approver who was NOT assigned to any workflow on the document receives non-disclosing 404.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    assigned_appr = role_user_factory(UserRole.APPROVER)["user"]
    assigned_appr.department = "Legal"
    unassigned_appr = role_user_factory(UserRole.APPROVER)["user"]
    unassigned_appr.department = "Legal"
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=assigned_appr, department="Legal")

    token_unassigned = create_access_token(user_id=unassigned_appr.id)
    res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token_unassigned}"},
    )
    # Must return 404 to prevent enumerating workflow existence
    assert res.status_code == 404


def test_submitting_user_can_retrieve_workflow_history(client, db_session, role_user_factory):
    """
    Test 5: Submitting user in the owning department can retrieve the full history of their document.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=approver, department="Legal")

    token_creator = create_access_token(user_id=creator.id)
    res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token_creator}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_attempts"] == 2
    assert data["attempts"][0]["submitter"]["id"] == str(creator.id)


def test_unauthorized_roles_receive_non_disclosing_404(client, db_session, role_user_factory):
    """
    Test 6: Department User from another department receives 404.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"

    other_dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    other_dept_user.department = "HR"  # Foreign department
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=approver, department="Legal")

    token_foreign = create_access_token(user_id=other_dept_user.id)
    res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token_foreign}"},
    )
    assert res.status_code == 404


def test_inactive_user_denied(client, db_session, role_user_factory):
    """
    Test 7: Inactive users are rejected with 401.
    """
    inactive_user = role_user_factory(UserRole.ADMIN, is_active=False)["user"]
    token = create_access_token(user_id=inactive_user.id)

    res = client.get(
        f"/api/v1/documents/{uuid.uuid4()}/workflow-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 401


def test_missing_document_returns_404(client, db_session, role_user_factory):
    """
    Test 8: Request for a nonexistent document returns 404.
    """
    admin = role_user_factory(UserRole.ADMIN)["user"]
    token = create_access_token(user_id=admin.id)

    res = client.get(
        f"/api/v1/documents/{uuid.uuid4()}/workflow-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


def test_document_with_no_workflow_returns_empty_history(client, db_session, role_user_factory):
    """
    Test 9: An authorized document that has never been submitted returns empty attempts list.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    db_session.commit()

    suffix = uuid.uuid4().hex[:6]
    doc = DigitalDocument(
        document_reference=f"DOC-NOWF-{suffix.upper()}",
        title=f"Task53 Test Doc NoWF {suffix}",
        subject="No workflow testing",
        department="Legal",
        classification="Internal",
        mime_type="application/pdf",
        status=DocumentStatus.DRAFT,
        created_by_id=dept_user.id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    token = create_access_token(user_id=dept_user.id)
    res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == str(doc.id)
    assert data["total_attempts"] == 0
    assert data["attempts"] == []


def test_rejected_workflow_remains_visible_after_resubmission_lifecycle(client, db_session, role_user_factory):
    """
    Test 10 & 11: End-to-end resubmission flow via APIs:
    1. Submit draft doc for review.
    2. Approver rejects with comments -> document returns to draft.
    3. User resubmits -> new pending workflow created.
    4. History endpoint displays both workflows; original rejection comment and new state are preserved.
    """
    dept_user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    dept_user.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    token_user = create_access_token(user_id=dept_user.id)
    token_appr = create_access_token(user_id=approver.id)

    # 1. Create a draft document
    suffix = uuid.uuid4().hex[:6]
    doc = DigitalDocument(
        document_reference=f"DOC-LIFECYCLE-{suffix.upper()}",
        title=f"Task53 Test Doc Lifecycle {suffix}",
        subject="Lifecycle testing",
        department="Legal",
        classification="Internal",
        mime_type="application/pdf",
        status=DocumentStatus.DRAFT,
        created_by_id=dept_user.id,
    )
    db_session.add(doc)
    db_session.flush()

    v1 = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"legal/2026/DOC-LIFECYCLE-{suffix}/v1.pdf",
        original_filename="initial.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="1111111111111111111111111111111111111111111111111111111111111111",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=dept_user.id,
    )
    db_session.add(v1)
    db_session.commit()
    db_session.refresh(doc)

    # Step A: User submits draft document
    res_sub1 = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token_user}"},
        json={"approver_id": str(approver.id), "comments": "First submission attempt"},
    )
    assert res_sub1.status_code == 201
    wf1_id = res_sub1.json()["workflow_id"]

    # Step B: Approver rejects document
    res_dec1 = client.post(
        f"/api/v1/workflows/{wf1_id}/decision",
        headers={"Authorization": f"Bearer {token_appr}"},
        json={"decision": "rejected", "comments": "Missing critical legal clause 8."},
    )
    assert res_dec1.status_code == 200
    assert res_dec1.json()["document_status"] == "draft"

    # Step C: User resubmits the document
    res_sub2 = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        headers={"Authorization": f"Bearer {token_user}"},
        json={"approver_id": str(approver.id), "comments": "Second submission with clause 8 added"},
    )
    assert res_sub2.status_code == 201
    wf2_id = res_sub2.json()["workflow_id"]
    assert wf1_id != wf2_id

    # Step D: Retrieve workflow history
    res_hist = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token_user}"},
    )
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert hist["total_attempts"] == 2

    # Verify attempt 1 preserved
    att1 = hist["attempts"][0]
    assert att1["workflow_id"] == wf1_id
    assert att1["state"] == "rejected"
    assert att1["submission_comments"] == "First submission attempt"
    assert att1["assignments"][0]["decision"] == "rejected"
    assert att1["assignments"][0]["decision_comments"] == "Missing critical legal clause 8."

    # Verify attempt 2 active
    att2 = hist["attempts"][1]
    assert att2["workflow_id"] == wf2_id
    assert att2["state"] == "pending"
    assert att2["submission_comments"] == "Second submission with clause 8 added"
    assert att2["assignments"][0]["decision"] is None


def test_history_response_contains_no_sensitive_or_internal_storage_fields(client, db_session, role_user_factory):
    """
    Test 13: Response does not expose password hashes, internal storage paths, or file binaries.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=approver)

    token = create_access_token(user_id=creator.id)
    res = client.get(
        f"/api/v1/documents/{doc.id}/workflow-history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    res_text = res.text

    assert "password" not in res_text.lower()
    assert "hashed_password" not in res_text.lower()
    assert "storage_key" not in res_text.lower()
    assert "/var/edrms" not in res_text
    assert "extracted_text" not in res_text


def test_history_retrieval_does_not_modify_application_state(client, db_session, role_user_factory):
    """
    Test 14: Calling workflow-history is strictly idempotent and does not alter workflow or document status.
    """
    creator = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    creator.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc, wfs = create_document_with_history(db_session, creator=creator, approver1=approver)

    token = create_access_token(user_id=creator.id)

    # Call twice
    res1 = client.get(f"/api/v1/documents/{doc.id}/workflow-history", headers={"Authorization": f"Bearer {token}"})
    res2 = client.get(f"/api/v1/documents/{doc.id}/workflow-history", headers={"Authorization": f"Bearer {token}"})

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json() == res2.json()

    # Verify DB state untouched
    db_session.refresh(doc)
    assert doc.status == DocumentStatus.ACTIVE
