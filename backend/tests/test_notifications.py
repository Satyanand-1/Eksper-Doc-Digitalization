"""
Automated test suite for Task 5.5: In-App Workflow Notifications.
Verifies:
1. Document submission creates a notification for the assigned approver with safe reference and title.
2. Workflow approval creates a notification for the submitter indicating approval & activation.
3. Workflow rejection creates a notification for the submitter without exposing confidential comments.
4. Workflow cancellation creates a notification for assigned approvers indicating withdrawal.
5. Failed workflow transitions do not create notifications.
6. Audit failure and transaction rollback do not leave orphan notification records.
7. Notifications are visible only to their intended recipients.
8. A user cannot read or modify another user's notification (non-disclosing 404).
9. Pagination and deterministic ordering (newest first) work correctly.
10. Unread-only filtering works correctly.
11. Unread count updates when a notification is marked as read.
12. Repeated marking-as-read requests are safe and idempotent.
13. Duplicate requests and conflicting workflow decisions do not create duplicate event notifications.
14. Sensitive document content and internal storage paths are not exposed.
15. Existing workflow history and cancellation behavior remain unchanged.
16. All existing regression tests continue to pass.
"""
import uuid
from unittest.mock import patch
import pytest
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus, ExtractionStatus
from app.models.workflow import ReviewWorkflow, ReviewAssignment, WorkflowState, ReviewDecision
from app.models.notification import Notification, NotificationType
from app.jwt import create_access_token
from app.services.audit import AuditWriteError


@pytest.fixture(autouse=True)
def cleanup_notification_test_data(db_session: Session):
    """Clean up notifications, workflows, assignments, and documents created during tests."""
    yield
    try:
        db_session.rollback()
        db_session.query(Notification).delete()
        db_session.query(ReviewAssignment).delete()
        db_session.query(ReviewWorkflow).delete()
        test_docs = db_session.query(DigitalDocument).filter(
            DigitalDocument.title.like("Task55 Test Doc%")
        ).all()
        for doc in test_docs:
            db_session.delete(doc)
        db_session.commit()
    except Exception:
        db_session.rollback()


def setup_test_document(
    db: Session,
    creator: User,
    department: str = "Legal",
    status: DocumentStatus = DocumentStatus.DRAFT,
) -> DigitalDocument:
    """Helper to create a test document with a registered version."""
    suffix = uuid.uuid4().hex[:6]
    doc = DigitalDocument(
        document_reference=f"DOC-T55-{suffix.upper()}",
        title=f"Task55 Test Doc {suffix}",
        subject="Task 5.5 notification testing",
        department=department,
        classification="Internal",
        mime_type="application/pdf",
        status=status,
        created_by_id=creator.id,
    )
    db.add(doc)
    db.flush()

    v = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=f"legal/2026/DOC-T55-{suffix}/v1.pdf",
        original_filename="sample.pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        file_hash_sha256="abc1234567890123456789012345678901234567890123456789012345678901",
        extracted_text="Safe body text",
        extraction_status=ExtractionStatus.COMPLETED,
        created_by_id=creator.id,
    )
    db.add(v)
    db.commit()
    db.refresh(doc)
    return doc


def test_submission_creates_notification_for_approver(client, db_session, role_user_factory):
    """
    1. Document submission creates a notification for the assigned approver.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")

    token_sub = create_access_token(user_id=submitter.id)
    response = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Please review"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert response.status_code == 201

    # Check notification for approver
    token_appr = create_access_token(user_id=approver.id)
    notif_res = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert notif_res.status_code == 200
    data = notif_res.json()
    assert data["total"] == 1
    assert data["unread_count"] == 1

    item = data["items"][0]
    assert item["notification_type"] == NotificationType.WORKFLOW_SUBMITTED.value
    assert item["recipient_id"] == str(approver.id)
    assert doc.document_reference in item["title"]
    assert doc.document_reference in item["message"]
    assert item["document_id"] == str(doc.id)
    assert item["is_read"] is False


def test_approval_creates_notification_for_submitter(client, db_session, role_user_factory):
    """
    2. Workflow approval creates a notification for the submitter indicating approval & activation.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")

    # Submit
    token_sub = create_access_token(user_id=submitter.id)
    sub_res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Initial submission"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert sub_res.status_code == 201
    wf_id = sub_res.json()["workflow_id"]

    # Approver approves
    token_appr = create_access_token(user_id=approver.id)
    dec_res = client.post(
        f"/api/v1/workflows/{wf_id}/decision",
        json={"decision": "approved", "comments": "Looks good"},
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert dec_res.status_code == 200

    # Submitter receives notification
    notif_res = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert notif_res.status_code == 200
    data = notif_res.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["notification_type"] == NotificationType.WORKFLOW_APPROVED.value
    assert item["recipient_id"] == str(submitter.id)
    assert "approved and activated" in item["message"].lower()


def test_rejection_creates_notification_for_submitter(client, db_session, role_user_factory):
    """
    3. Workflow rejection creates a notification for the submitter without exposing long comments.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")

    # Submit
    token_sub = create_access_token(user_id=submitter.id)
    sub_res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Initial submission"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    wf_id = sub_res.json()["workflow_id"]

    # Approver rejects
    token_appr = create_access_token(user_id=approver.id)
    dec_res = client.post(
        f"/api/v1/workflows/{wf_id}/decision",
        json={"decision": "rejected", "comments": "Confidential internal rejection rationale 12345"},
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert dec_res.status_code == 200

    # Submitter receives safe rejection notification
    notif_res = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert notif_res.status_code == 200
    item = notif_res.json()["items"][0]
    assert item["notification_type"] == NotificationType.WORKFLOW_REJECTED.value
    assert item["recipient_id"] == str(submitter.id)
    assert "rejected" in item["message"].lower()
    # Ensure confidential comments are NOT leaked into notification message
    assert "12345" not in item["message"]


def test_cancellation_creates_notification_for_assigned_approver(client, db_session, role_user_factory):
    """
    4. Workflow cancellation creates a notification for assigned approvers indicating withdrawal.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")

    # Submit
    token_sub = create_access_token(user_id=submitter.id)
    sub_res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Initial submission"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    wf_id = sub_res.json()["workflow_id"]

    # Cancel
    cancel_res = client.post(
        f"/api/v1/workflows/{wf_id}/cancel",
        json={"comments": "Withdrawing submission for correction"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert cancel_res.status_code == 200

    # Approver receives withdrawal notification (in addition to the earlier submitted notification)
    token_appr = create_access_token(user_id=approver.id)
    notif_res = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert notif_res.status_code == 200
    data = notif_res.json()
    assert data["total"] == 2  # 1 submission + 1 cancellation

    latest_notif = data["items"][0]  # newest first
    assert latest_notif["notification_type"] == NotificationType.WORKFLOW_CANCELLED.value
    assert "withdrawn" in latest_notif["message"].lower()


def test_failed_workflow_transitions_do_not_create_notifications(client, db_session, role_user_factory):
    """
    5. Failed workflow transitions (e.g. cross-dept submission, duplicate rejection) do not create notifications.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Finance"  # Different department!
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")

    token_sub = create_access_token(user_id=submitter.id)
    res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Invalid cross-dept"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    assert res.status_code == 400

    # Verify no notifications exist in DB
    total_notifs = db_session.query(Notification).count()
    assert total_notifs == 0


def test_audit_failure_and_rollback_leaves_no_orphan_notifications(client, db_session, role_user_factory):
    """
    6. Audit failure and transaction rollback do not leave orphan notification records.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")
    token_sub = create_access_token(user_id=submitter.id)

    with patch("app.api.v1.documents.audit_service.log_from_request", side_effect=AuditWriteError("Simulated audit write failure")):
        res = client.post(
            f"/api/v1/documents/{doc.id}/submit-for-review",
            json={"approver_id": str(approver.id), "comments": "Submission with failing audit"},
            headers={"Authorization": f"Bearer {token_sub}"},
        )
        assert res.status_code == 500

    # Verify atomic rollback left no notification
    total_notifs = db_session.query(Notification).count()
    assert total_notifs == 0


def test_notifications_visible_only_to_intended_recipient(client, db_session, role_user_factory):
    """
    7. Notifications are visible only to their intended recipients.
    """
    user_a = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    user_b = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    approver = role_user_factory(UserRole.APPROVER)["user"]
    user_a.department = "Legal"
    user_b.department = "Legal"
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=user_a, department="Legal")

    # User A submits to approver
    token_a = create_access_token(user_id=user_a.id)
    client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "User A submission"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # User B queries notifications -> should see 0
    token_b = create_access_token(user_id=user_b.id)
    res_b = client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 200
    assert res_b.json()["total"] == 0
    assert len(res_b.json()["items"]) == 0


def test_user_cannot_read_or_modify_another_users_notification(client, db_session, role_user_factory):
    """
    8. A user cannot read or mark another user's notification as read (non-disclosing 404).
    """
    user_a = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    user_b = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    approver = role_user_factory(UserRole.APPROVER)["user"]
    user_a.department = "Legal"
    user_b.department = "Legal"
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=user_a, department="Legal")

    token_a = create_access_token(user_id=user_a.id)
    client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "User A submission"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Approver has notification
    notif = db_session.query(Notification).filter(Notification.recipient_id == approver.id).first()
    assert notif is not None

    # User B tries to mark Approver's notification as read
    token_b = create_access_token(user_id=user_b.id)
    res = client.post(
        f"/api/v1/notifications/{notif.id}/read",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 404
    db_session.refresh(notif)
    assert notif.is_read is False


def test_pagination_and_deterministic_ordering(client, db_session, role_user_factory):
    """
    9. Pagination and deterministic newest-first ordering work correctly.
    """
    user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    db_session.commit()

    # Manually create 5 notifications
    created_ids = []
    for i in range(5):
        n = Notification(
            recipient_id=user.id,
            notification_type=NotificationType.WORKFLOW_SUBMITTED,
            title=f"Notification #{i}",
            message=f"Message #{i}",
            is_read=False,
        )
        db_session.add(n)
        db_session.flush()
        created_ids.append(n.id)
    db_session.commit()

    token = create_access_token(user_id=user.id)
    res_p1 = client.get(
        "/api/v1/notifications?page=1&page_size=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_p1.status_code == 200
    p1 = res_p1.json()
    assert p1["total"] == 5
    assert p1["unread_count"] == 5
    assert p1["total_pages"] == 3
    assert len(p1["items"]) == 2
    # Newest created is Notification #4
    assert p1["items"][0]["title"] == "Notification #4"
    assert p1["items"][1]["title"] == "Notification #3"

    res_p2 = client.get(
        "/api/v1/notifications?page=2&page_size=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_p2.status_code == 200
    p2 = res_p2.json()
    assert len(p2["items"]) == 2
    assert p2["items"][0]["title"] == "Notification #2"
    assert p2["items"][1]["title"] == "Notification #1"


def test_unread_only_filtering(client, db_session, role_user_factory):
    """
    10. Unread-only filtering works correctly.
    """
    user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    db_session.commit()

    # 1 unread, 1 read
    n_unread = Notification(
        recipient_id=user.id,
        notification_type=NotificationType.WORKFLOW_SUBMITTED,
        title="Unread Notification",
        message="Message unread",
        is_read=False,
    )
    n_read = Notification(
        recipient_id=user.id,
        notification_type=NotificationType.WORKFLOW_APPROVED,
        title="Read Notification",
        message="Message read",
        is_read=True,
    )
    db_session.add_all([n_unread, n_read])
    db_session.commit()

    token = create_access_token(user_id=user.id)

    # Without filter -> 2 total
    res_all = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token}"})
    assert res_all.json()["total"] == 2
    assert res_all.json()["unread_count"] == 1

    # With unread_only=true -> 1 total
    res_unread = client.get("/api/v1/notifications?unread_only=true", headers={"Authorization": f"Bearer {token}"})
    assert res_unread.json()["total"] == 1
    assert res_unread.json()["items"][0]["id"] == str(n_unread.id)


def test_unread_count_endpoint_and_read_update(client, db_session, role_user_factory):
    """
    11. Unread count updates correctly when a notification is marked as read.
    """
    user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    db_session.commit()

    n = Notification(
        recipient_id=user.id,
        notification_type=NotificationType.WORKFLOW_SUBMITTED,
        title="Action required",
        message="Review waiting",
        is_read=False,
    )
    db_session.add(n)
    db_session.commit()

    token = create_access_token(user_id=user.id)

    # Initial count
    c_res1 = client.get("/api/v1/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert c_res1.status_code == 200
    assert c_res1.json()["unread_count"] == 1

    # Mark as read
    read_res = client.post(f"/api/v1/notifications/{n.id}/read", headers={"Authorization": f"Bearer {token}"})
    assert read_res.status_code == 200
    assert read_res.json()["is_read"] is True
    assert read_res.json()["read_at"] is not None

    # Count is now 0
    c_res2 = client.get("/api/v1/notifications/unread-count", headers={"Authorization": f"Bearer {token}"})
    assert c_res2.status_code == 200
    assert c_res2.json()["unread_count"] == 0


def test_repeated_marking_as_read_is_idempotent(client, db_session, role_user_factory):
    """
    12. Repeated marking-as-read requests are safe and idempotent.
    """
    user = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    db_session.commit()

    n = Notification(
        recipient_id=user.id,
        notification_type=NotificationType.WORKFLOW_SUBMITTED,
        title="Action required",
        message="Review waiting",
        is_read=False,
    )
    db_session.add(n)
    db_session.commit()

    token = create_access_token(user_id=user.id)

    res1 = client.post(f"/api/v1/notifications/{n.id}/read", headers={"Authorization": f"Bearer {token}"})
    assert res1.status_code == 200
    read_at_1 = res1.json()["read_at"]

    res2 = client.post(f"/api/v1/notifications/{n.id}/read", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    read_at_2 = res2.json()["read_at"]

    # read_at is preserved
    assert read_at_1 == read_at_2


def test_conflicting_workflow_decisions_do_not_duplicate_notifications(client, db_session, role_user_factory):
    """
    13. Once a workflow decision is made, repeated or conflicting decisions fail (409) and do not create duplicate notifications.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")

    token_sub = create_access_token(user_id=submitter.id)
    sub_res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "First submission"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    wf_id = sub_res.json()["workflow_id"]

    token_appr = create_access_token(user_id=approver.id)
    # First decision succeeds
    dec1 = client.post(
        f"/api/v1/workflows/{wf_id}/decision",
        json={"decision": "approved", "comments": "First decision"},
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert dec1.status_code == 200

    # Second decision fails with 409
    dec2 = client.post(
        f"/api/v1/workflows/{wf_id}/decision",
        json={"decision": "approved", "comments": "Second duplicate decision"},
        headers={"Authorization": f"Bearer {token_appr}"},
    )
    assert dec2.status_code == 409

    # Exactly one approved notification exists for submitter
    notif_res = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token_sub}"})
    assert notif_res.json()["total"] == 1


def test_notifications_contain_no_sensitive_paths_or_ocr_text(client, db_session, role_user_factory):
    """
    14. Notification titles and messages do not contain internal storage paths, file hashes, or OCR text.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")
    token_sub = create_access_token(user_id=submitter.id)
    client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "Safe comments"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )

    token_appr = create_access_token(user_id=approver.id)
    res = client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {token_appr}"})
    item = res.json()["items"][0]

    forbidden_strings = ["/var/edrms", "storage_key", "file_hash", "extracted_text", "Safe body text", "abc12345"]
    for s in forbidden_strings:
        assert s not in item["title"]
        assert s not in item["message"]


def test_existing_workflow_history_and_cancellation_remain_intact(client, db_session, role_user_factory):
    """
    15. Existing workflow history retrieval works and reflects cancelled status alongside notification generation.
    """
    submitter = role_user_factory(UserRole.DEPARTMENT_USER)["user"]
    submitter.department = "Legal"
    approver = role_user_factory(UserRole.APPROVER)["user"]
    approver.department = "Legal"
    db_session.commit()

    doc = setup_test_document(db_session, creator=submitter, department="Legal")
    token_sub = create_access_token(user_id=submitter.id)

    # Submit
    sub_res = client.post(
        f"/api/v1/documents/{doc.id}/submit-for-review",
        json={"approver_id": str(approver.id), "comments": "History test"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )
    wf_id = sub_res.json()["workflow_id"]

    # Cancel
    client.post(
        f"/api/v1/workflows/{wf_id}/cancel",
        json={"comments": "Cancelled with comment"},
        headers={"Authorization": f"Bearer {token_sub}"},
    )

    # Check workflow history
    hist_res = client.get(f"/api/v1/documents/{doc.id}/workflow-history", headers={"Authorization": f"Bearer {token_sub}"})
    assert hist_res.status_code == 200
    hist = hist_res.json()
    assert hist["total_attempts"] == 1
    assert hist["attempts"][0]["state"] == "cancelled"
    assert hist["attempts"][0]["cancellation_comments"] == "Cancelled with comment"


def test_unauthenticated_requests_to_notifications_rejected(client):
    """
    16. Unauthenticated requests to notification endpoints return 401 Unauthorized.
    """
    res1 = client.get("/api/v1/notifications")
    assert res1.status_code == 401

    res2 = client.get("/api/v1/notifications/unread-count")
    assert res2.status_code == 401

    res3 = client.post(f"/api/v1/notifications/{uuid.uuid4()}/read")
    assert res3.status_code == 401
