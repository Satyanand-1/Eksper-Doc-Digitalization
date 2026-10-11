"""
Audit log model for tracking operational, access, security, and governance actions.
Guarantees audit traceability for document access, permission evaluations, and record actions.
"""
import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, DateTime, Enum as SAEnum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class AuditOutcome(str, enum.Enum):
    """Outcome of the audited action."""
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"

class AuditLog(Base):
    """
    Immutable audit log table capturing security and document access events.
    Records actor, resource, action, outcome, client context, and optional metadata.
    """
    __tablename__ = "audit_logs"

    # UUID primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Actor user ID (nullable if unauthenticated / system action)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Action performed (e.g., 'document.download', 'document.upload', 'document.access_denied')
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Target resource type ('document', 'document_version', 'user', etc.)
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Target resource ID (e.g. document UUID)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Outcome of action ('success', 'denied', 'failed')
    outcome: Mapped[AuditOutcome] = mapped_column(
        SAEnum(AuditOutcome, name="audit_outcome", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    # Client IP address or request correlation identifier
    client_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )

    # Correlation or request ID if supplied
    correlation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Structured context (e.g., version_number, department, classification, reason for denial)
    # Excludes passwords, tokens, or file binary data
    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Audit event timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Optional relationship to actor user
    actor = relationship("User", foreign_keys=[actor_id])

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        outcome_val = self.outcome.value if isinstance(self.outcome, AuditOutcome) else self.outcome
        return (
            f"<AuditLog id={self.id} action={self.action} actor={self.actor_id} "
            f"outcome={outcome_val} resource={self.resource_type}:{self.resource_id}>"
        )
