import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, Integer, BigInteger, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class DocumentStatus(str, enum.Enum):
    """
    Lifecycle status of a digital record.
    Initial states allow transition from draft through review, activation, and archiving.
    """
    DRAFT = "draft"                          # Editable draft document
    UNDER_REVIEW = "under_review"            # Submitted for review or approval
    ACTIVE = "active"                        # Approved, official record in active custody
    ARCHIVED = "archived"                    # Archived record according to retention policy
    DISPOSED = "disposed"                    # Destroyed or legally disposed record

class ExtractionStatus(str, enum.Enum):
    """
    OCR and text-extraction lifecycle status for a document version.
    """
    PENDING = "pending"                      # Scheduled / queued for extraction
    PROCESSING = "processing"                # Extraction currently in progress
    COMPLETED = "completed"                  # Successfully extracted and persisted
    FAILED = "failed"                        # Extraction failed

class DigitalDocument(Base):
    """
    Represents a logical digital record in the repository.
    Holds governance metadata, title, reference number, status, and department.
    File binaries are NOT stored in this row; they are tracked through DocumentVersion.
    """
    __tablename__ = "digital_documents"

    # UUID primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Human-readable, application-generated unique document reference (e.g. DOC-2026-0001)
    document_reference: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # Document title
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # Subject or descriptive abstract
    subject: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Responsible department
    department: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Document category / classification (e.g., Contract, Invoice, Policy, Memo)
    classification: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    # Expected or primary MIME type (e.g. application/pdf, image/png)
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Lifecycle status
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=DocumentStatus.DRAFT,
        index=True,
    )

    # Creator user reference (no cascade delete on user delete to preserve record provenance)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Audit timestamps
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

    # Archival audit timestamp
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Retention governance fields
    retention_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retention_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    retention_trigger_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    retention_start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    retention_end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    retention_assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    retention_assigned_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    retention_rule = relationship("RetentionRule", back_populates="documents")
    retention_assigned_by = relationship("User", foreign_keys=[retention_assigned_by_id])
    legal_holds = relationship("LegalHold", back_populates="document", cascade="all, delete-orphan", order_by="desc(LegalHold.placed_at)")

    # Relationship to immutable document versions (ordered by version number)
    # Does NOT cascade delete files physically from disk on metadata delete
    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "status" not in kwargs:
            kwargs["status"] = DocumentStatus.DRAFT
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = utc_now()
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        status_val = self.status.value if isinstance(self.status, DocumentStatus) else self.status
        return f"<DigitalDocument id={self.id} ref={self.document_reference} title='{self.title}' status={status_val}>"

class DocumentVersion(Base):
    """
    Represents an immutable revision/version of a DigitalDocument.
    Holds metadata regarding physical disk storage key, original filename,
    file size, SHA-256 hash, and OCR extracted text.
    """
    __tablename__ = "document_versions"
    __table_args__ = (
        # Ensure version numbers are strictly unique within their parent document
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
    )

    # UUID primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign key to parent DigitalDocument
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("digital_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Version sequence number (1, 2, 3...)
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Server-generated relative storage key on disk (never client-supplied)
    # e.g., "uploads/2026/10/a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"
    storage_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )

    # Original filename retained solely as metadata for presentation/download
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Concrete MIME type of this version
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # File size in bytes
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Cryptographic SHA-256 checksum for file integrity verification
    file_hash_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # Extracted plain text (from Tesseract OCR or native embedded streams)
    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    # OCR and text extraction tracking fields
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus, name="extraction_status", native_enum=False),
        nullable=False,
        default=ExtractionStatus.PENDING,
        index=True,
    )

    extraction_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    extraction_error: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
    )

    # Creator user reference for this version
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Timestamp when version was uploaded/created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    document = relationship("DigitalDocument", back_populates="versions")
    created_by = relationship("User", foreign_keys=[created_by_id])

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        if "extraction_status" not in kwargs:
            kwargs["extraction_status"] = ExtractionStatus.PENDING
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion id={self.id} doc_id={self.document_id} "
            f"ver={self.version_number} size={self.file_size_bytes} hash={self.file_hash_sha256[:8]}...>"
        )
