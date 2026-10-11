import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, DateTime, Enum as SAEnum, ForeignKey, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationType(str, enum.Enum):
    """
    Categorized workflow event notification types.
    """
    WORKFLOW_SUBMITTED = "workflow_submitted"
    WORKFLOW_APPROVED = "workflow_approved"
    WORKFLOW_REJECTED = "workflow_rejected"
    WORKFLOW_CANCELLED = "workflow_cancelled"


class Notification(Base):
    """
    Database-backed in-app notification tracking workflow lifecycle events for users.
    """
    __tablename__ = "notifications"

    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
        Index("ix_notifications_recipient_unread", "recipient_id", "is_read"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    notification_type: Mapped[NotificationType] = mapped_column(
        SAEnum(NotificationType, name="notification_type", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("digital_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_workflows.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Relationships
    recipient = relationship("User", foreign_keys=[recipient_id])
    document = relationship("DigitalDocument", foreign_keys=[document_id])
    workflow = relationship("ReviewWorkflow", foreign_keys=[workflow_id])

    def __repr__(self) -> str:
        return f"<Notification id={self.id} recipient_id={self.recipient_id} type={self.notification_type.value} read={self.is_read}>"
