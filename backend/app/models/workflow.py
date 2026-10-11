import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, DateTime, Enum as SAEnum, ForeignKey, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowState(str, enum.Enum):
    """
    Lifecycle state of a document review workflow.
    """
    PENDING = "pending"          # Submitted and awaiting review
    APPROVED = "approved"        # Reserved for approval decision task (Task 5.2)
    REJECTED = "rejected"        # Reserved for rejection decision task (Task 5.2)
    CANCELLED = "cancelled"      # Cancelled or withdrawn workflow


class ReviewDecision(str, enum.Enum):
    """
    Review decision outcomes (reserved for Task 5.2).
    """
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewWorkflow(Base):
    """
    Durable workflow record tracking the review-and-approval lifecycle of a digital document.
    """
    __tablename__ = "review_workflows"
    __table_args__ = (
        # Partial unique index: A document may have at most ONE active (pending) review workflow
        Index(
            "uq_active_review_workflow_per_document",
            "document_id",
            unique=True,
            postgresql_where=(text("state = 'pending'")),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("digital_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    state: Mapped[WorkflowState] = mapped_column(
        SAEnum(WorkflowState, name="workflow_state", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=WorkflowState.PENDING,
        index=True,
    )

    submitter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    submission_comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    cancelled_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancellation_comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    document = relationship("DigitalDocument", foreign_keys=[document_id])
    submitter = relationship("User", foreign_keys=[submitter_id])
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])
    assignments = relationship("ReviewAssignment", back_populates="workflow", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ReviewWorkflow id={self.id} doc_id={self.document_id} state={self.state.value}>"


class ReviewAssignment(Base):
    """
    Review assignment attaching an explicit approver to a review workflow.
    """
    __tablename__ = "review_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assigned_approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Reserved fields for review decision task (Task 5.2)
    decision: Mapped[ReviewDecision | None] = mapped_column(
        SAEnum(ReviewDecision, name="review_decision", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        default=None,
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    decision_comments: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    workflow = relationship("ReviewWorkflow", back_populates="assignments")
    assigned_approver = relationship("User", foreign_keys=[assigned_approver_id])

    def __repr__(self) -> str:
        return f"<ReviewAssignment id={self.id} workflow_id={self.workflow_id} approver_id={self.assigned_approver_id}>"
