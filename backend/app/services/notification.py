import uuid
import logging
from sqlalchemy.orm import Session
from app.models.notification import Notification, NotificationType
from app.models.workflow import ReviewWorkflow
from app.models.document import DigitalDocument

logger = logging.getLogger("edrms.notifications")


class NotificationService:
    """
    Transactional domain service for creating workflow notifications.
    Operates within the caller's database transaction to ensure atomicity.
    Never stores file paths, raw text, or secrets in notification records.
    """

    @classmethod
    def create_notification(
        cls,
        db: Session,
        recipient_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        document_id: uuid.UUID | None = None,
        workflow_id: uuid.UUID | None = None,
    ) -> Notification:
        notification = Notification(
            recipient_id=recipient_id,
            notification_type=notification_type,
            title=title,
            message=message,
            document_id=document_id,
            workflow_id=workflow_id,
            is_read=False,
        )
        db.add(notification)
        return notification

    @classmethod
    def notify_workflow_submitted(
        cls,
        db: Session,
        workflow: ReviewWorkflow,
        document: DigitalDocument,
        approver_id: uuid.UUID,
    ) -> Notification:
        """
        Notify assigned approver that a document review is awaiting their attention.
        """
        title = f"Document review required: {document.document_reference}"
        message = (
            f"Document '{document.title}' ({document.document_reference}) "
            f"has been submitted for your review."
        )
        notification = cls.create_notification(
            db=db,
            recipient_id=approver_id,
            notification_type=NotificationType.WORKFLOW_SUBMITTED,
            title=title,
            message=message,
            document_id=document.id,
            workflow_id=workflow.id,
        )
        logger.info(
            f"Created workflow_submitted notification for approver {approver_id} on workflow {workflow.id}"
        )
        return notification

    @classmethod
    def notify_workflow_approved(
        cls,
        db: Session,
        workflow: ReviewWorkflow,
        document: DigitalDocument,
    ) -> Notification:
        """
        Notify original submitter that their submitted document was approved and activated.
        """
        title = f"Document approved: {document.document_reference}"
        message = (
            f"Document '{document.title}' ({document.document_reference}) "
            f"has been approved and activated."
        )
        notification = cls.create_notification(
            db=db,
            recipient_id=workflow.submitter_id,
            notification_type=NotificationType.WORKFLOW_APPROVED,
            title=title,
            message=message,
            document_id=document.id,
            workflow_id=workflow.id,
        )
        logger.info(
            f"Created workflow_approved notification for submitter {workflow.submitter_id} on workflow {workflow.id}"
        )
        return notification

    @classmethod
    def notify_workflow_rejected(
        cls,
        db: Session,
        workflow: ReviewWorkflow,
        document: DigitalDocument,
    ) -> Notification:
        """
        Notify original submitter that their submitted document was rejected and returned to draft.
        Safe message indicating feedback is available without leaking confidential comments.
        """
        title = f"Document review rejected: {document.document_reference}"
        message = (
            f"Document '{document.title}' ({document.document_reference}) "
            f"was rejected during review and returned to draft. Review feedback is available in the workflow history."
        )
        notification = cls.create_notification(
            db=db,
            recipient_id=workflow.submitter_id,
            notification_type=NotificationType.WORKFLOW_REJECTED,
            title=title,
            message=message,
            document_id=document.id,
            workflow_id=workflow.id,
        )
        logger.info(
            f"Created workflow_rejected notification for submitter {workflow.submitter_id} on workflow {workflow.id}"
        )
        return notification

    @classmethod
    def notify_workflow_cancelled(
        cls,
        db: Session,
        workflow: ReviewWorkflow,
        document: DigitalDocument,
        assigned_approver_ids: list[uuid.UUID],
    ) -> list[Notification]:
        """
        Notify assigned approvers that the pending document review has been withdrawn/cancelled.
        """
        title = f"Review withdrawn: {document.document_reference}"
        message = (
            f"The pending review for document '{document.title}' ({document.document_reference}) "
            f"has been withdrawn."
        )
        notifications = []
        for approver_id in assigned_approver_ids:
            n = cls.create_notification(
                db=db,
                recipient_id=approver_id,
                notification_type=NotificationType.WORKFLOW_CANCELLED,
                title=title,
                message=message,
                document_id=document.id,
                workflow_id=workflow.id,
            )
            notifications.append(n)
            logger.info(
                f"Created workflow_cancelled notification for approver {approver_id} on workflow {workflow.id}"
            )
        return notifications


notification_service = NotificationService()
