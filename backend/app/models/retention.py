import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, Integer, DateTime, Boolean, Enum as SAEnum, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RetentionPeriodUnit(str, enum.Enum):
    DAYS = "days"
    MONTHS = "months"
    YEARS = "years"


class RetentionTriggerEvent(str, enum.Enum):
    CREATION = "creation"
    APPROVAL = "approval"


class LegalHoldStatus(str, enum.Enum):
    ACTIVE = "active"
    RELEASED = "released"


class DisposalEligibilityStatus(str, enum.Enum):
    RETAINED = "retained"
    ELIGIBLE_FOR_REVIEW = "eligible_for_review"
    ON_HOLD = "on_hold"
    NEEDS_ATTENTION = "needs_attention"


class RetentionRule(Base):
    """
    Retention schedule policy governing minimum record custody period.
    Configurable business rule defining retention duration and triggering lifecycle event.
    """
    __tablename__ = "retention_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Optional classification/category targeting (e.g., Contract, Policy, Invoice)
    classification: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Duration unit: days, months, or years
    retention_period_unit: Mapped[RetentionPeriodUnit] = mapped_column(
        SAEnum(RetentionPeriodUnit, name="retention_period_unit", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Duration count (must be positive integer)
    retention_period_value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Triggering lifecycle event (creation or approval)
    trigger_event: Mapped[RetentionTriggerEvent] = mapped_column(
        SAEnum(RetentionTriggerEvent, name="retention_trigger_event", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    documents = relationship("DigitalDocument", back_populates="retention_rule")


class LegalHold(Base):
    """
    Legal hold placed on a digital record to suspend disposal eligibility.
    While active, the document can never be assessed as eligible for disposal review.
    """
    __tablename__ = "legal_holds"

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

    hold_reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[LegalHoldStatus] = mapped_column(
        SAEnum(LegalHoldStatus, name="legal_hold_status", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LegalHoldStatus.ACTIVE,
        index=True,
    )

    placed_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    released_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    release_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    document = relationship("DigitalDocument", back_populates="legal_holds")
    placed_by = relationship("User", foreign_keys=[placed_by_id])
    released_by = relationship("User", foreign_keys=[released_by_id])
