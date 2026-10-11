import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, DateTime, Enum as SAEnum, ForeignKey, Text, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PhysicalRecordType(str, enum.Enum):
    """
    Standard physical record types.
    """
    CONTRACT = "contract"
    CASE_FILE = "case_file"
    CORRESPONDENCE = "correspondence"
    ARCHIVE_FOLDER = "archive_folder"
    FINANCIAL_RECORD = "financial_record"
    PERSONNEL_FILE = "personnel_file"
    POLICY_DOCUMENT = "policy_document"
    OTHER = "other"


class PhysicalFileStatus(str, enum.Enum):
    """
    Lifecycle status of a physical file registry record.
    Permitted transitions:
    - ACTIVE -> ARCHIVED, INACTIVE
    - ARCHIVED -> ACTIVE, INACTIVE
    - INACTIVE -> ACTIVE
    """
    ACTIVE = "active"
    ARCHIVED = "archived"
    INACTIVE = "inactive"


# Allowed lifecycle status transitions dictionary
VALID_STATUS_TRANSITIONS: dict[PhysicalFileStatus, set[PhysicalFileStatus]] = {
    PhysicalFileStatus.ACTIVE: {PhysicalFileStatus.ARCHIVED, PhysicalFileStatus.INACTIVE},
    PhysicalFileStatus.ARCHIVED: {PhysicalFileStatus.ACTIVE, PhysicalFileStatus.INACTIVE},
    PhysicalFileStatus.INACTIVE: {PhysicalFileStatus.ACTIVE},
}


class PhysicalFile(Base):
    """
    Physical File Registry model.
    Governs metadata, custody department, and tracking reference for physical records.
    Optionally links to an existing DigitalDocument record without storing file contents.
    """
    __tablename__ = "physical_files"

    __table_args__ = (
        Index("ix_physical_files_department_status", "department", "status"),
        Index("ix_physical_files_created_at", "created_at"),
    )

    # Unique internal physical file ID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-readable physical file reference, e.g. PHY-2026-A1B2C3D4
    file_reference: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # File title
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Description or summary
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Physical record type (contract, case file, correspondence, etc.)
    record_type: Mapped[PhysicalRecordType] = mapped_column(
        SAEnum(
            PhysicalRecordType,
            name="physical_record_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )

    # Owning department
    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Optional classification (e.g. Confidential, Public, Internal, Restricted)
    classification: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Optional relationship to an existing digital document
    # Set to SET NULL on delete so physical registry record is preserved if digital record is purged
    digital_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("digital_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional current storage location assignment
    # SET NULL on delete to prevent cascading deletion of physical files if location is cleaned up
    storage_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # External reference number, where applicable
    external_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Date received or registered
    date_received: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Lifecycle status: active, archived, inactive
    status: Mapped[PhysicalFileStatus] = mapped_column(
        SAEnum(
            PhysicalFileStatus,
            name="physical_file_status",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PhysicalFileStatus.ACTIVE,
        index=True,
    )

    # User who registered the file
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Circulation & Custody state: whether currently checked out
    is_checked_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    # User who last modified the file
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Record creation and modification timestamps
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
    digital_document = relationship("DigitalDocument", foreign_keys=[digital_document_id])
    storage_location = relationship("StorageLocation", foreign_keys=[storage_location_id], back_populates="physical_files")
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    custody_records = relationship("FileCustodyRecord", back_populates="physical_file", cascade="all, delete-orphan", order_by="desc(FileCustodyRecord.created_at)")
    movement_history = relationship("FileMovementHistory", back_populates="physical_file", cascade="all, delete-orphan", order_by="desc(FileMovementHistory.event_at)")
