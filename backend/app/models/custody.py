import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, DateTime, Enum as SAEnum, ForeignKey, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CustodyStatus(str, enum.Enum):
    """
    Status of an individual custody checkout record.
    ACTIVE = Currently checked out to custodian.
    RETURNED = Checked back in / returned.
    """
    ACTIVE = "active"
    RETURNED = "returned"


class PhysicalMovementType(str, enum.Enum):
    """
    Type of physical file movement event in the movement history.
    """
    CHECKOUT = "checkout"
    CHECKIN = "checkin"
    TRANSFER = "transfer"


class FileCustodyRecord(Base):
    """
    Durable custody record for physical files.
    Tracks checkouts to custodians, expected and actual returns, issuing and receiving users.
    """
    __tablename__ = "file_custody_records"

    __table_args__ = (
        Index("ix_file_custody_physical_file_status", "physical_file_id", "status"),
        Index("ix_file_custody_custodian_user_id", "custodian_user_id"),
        Index("ix_file_custody_checked_out_at", "checked_out_at"),
        Index("ix_file_custody_expected_return_at", "expected_return_at"),
        Index(
            "uq_file_custody_single_active",
            "physical_file_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Associated physical file
    physical_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("physical_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Custodian: either an EDRMS user or external recipient
    custodian_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Custodian name and contact (captures full identity or external recipient details)
    custodian_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    custodian_department: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    custodian_contact: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Current custody status: active or returned
    status: Mapped[CustodyStatus] = mapped_column(
        SAEnum(
            CustodyStatus,
            name="custody_status",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=CustodyStatus.ACTIVE,
        index=True,
    )

    # Timestamps
    checked_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    expected_return_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    checked_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Checkout reason / purpose
    purpose: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Checkin notes / remarks
    checkin_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Issuing user who dispatched the physical record
    issued_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Receiving user who verified and checked the physical record back in
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Record timestamps
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
    physical_file = relationship("PhysicalFile", foreign_keys=[physical_file_id], back_populates="custody_records")
    custodian_user = relationship("User", foreign_keys=[custodian_user_id])
    issued_by = relationship("User", foreign_keys=[issued_by_id])
    received_by = relationship("User", foreign_keys=[received_by_id])
    movement_events = relationship("FileMovementHistory", back_populates="custody_record", cascade="all, delete-orphan")


class FileMovementHistory(Base):
    """
    Chronological, immutable business log of physical file movement events
    (checkouts, check-ins, transfers).
    """
    __tablename__ = "file_movement_history"

    __table_args__ = (
        Index("ix_file_movement_file_event", "physical_file_id", "event_at"),
        Index("ix_file_movement_actor_id", "actor_id"),
        Index("ix_file_movement_type", "movement_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Associated physical file
    physical_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("physical_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Movement type: checkout, checkin, transfer
    movement_type: Mapped[PhysicalMovementType] = mapped_column(
        SAEnum(
            PhysicalMovementType,
            name="physical_movement_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    # Source storage location (where it came from)
    source_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Destination storage location (where it went or was returned to)
    destination_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Previous custody description (e.g. "Stored in HQ-CAB-01" or "Checked out to Jane Doe")
    from_custody_state: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Resulting custody description (e.g. "Checked out to Jane Doe" or "Stored in HQ-CAB-02")
    to_custody_state: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Actor performing the operation
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Timestamp of the physical event
    event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Explanatory notes or reason
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Associated custody record UUID, where applicable
    custody_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_custody_records.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Record creation timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    physical_file = relationship("PhysicalFile", foreign_keys=[physical_file_id], back_populates="movement_history")
    source_location = relationship("StorageLocation", foreign_keys=[source_location_id])
    destination_location = relationship("StorageLocation", foreign_keys=[destination_location_id])
    actor = relationship("User", foreign_keys=[actor_id])
    custody_record = relationship("FileCustodyRecord", foreign_keys=[custody_record_id], back_populates="movement_events")
