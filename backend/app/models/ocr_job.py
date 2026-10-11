import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, Integer, DateTime, Enum as SAEnum, ForeignKey, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class OCRJobStatus(str, enum.Enum):
    """
    Lifecycle status of an asynchronous durable OCR processing job.
    """
    QUEUED = "queued"          # Newly created, awaiting processing
    RUNNING = "running"        # Claimed by an active worker under lease
    COMPLETED = "completed"    # Successfully extracted and persisted
    FAILED = "failed"          # Permanently failed or retry budget exhausted

class OCRJob(Base):
    """
    Durable OCR processing job queue record.
    Survives application server and worker container restarts.
    """
    __tablename__ = "ocr_jobs"
    __table_args__ = (
        # Uniqueness rule: only one job record per document version
        UniqueConstraint("document_version_id", name="uq_ocr_jobs_document_version_id"),
    )

    # Job primary key UUID
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Document version foreign key
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Job status
    status: Mapped[OCRJobStatus] = mapped_column(
        SAEnum(OCRJobStatus, name="ocr_job_status", native_enum=False),
        nullable=False,
        default=OCRJobStatus.QUEUED,
        index=True,
    )

    # Retry count tracking
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    # Retry scheduling
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Lease expiry for crash/restart recovery
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    # Worker heartbeat / identification
    worker_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )

    # Execution timestamps
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Sanitized failure recording
    last_error: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
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

    # Relationship to version
    document_version = relationship("DocumentVersion", foreign_keys=[document_version_id])

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "status" not in kwargs:
            kwargs["status"] = OCRJobStatus.QUEUED
        if "attempt_count" not in kwargs:
            kwargs["attempt_count"] = 0
        if "max_attempts" not in kwargs:
            kwargs["max_attempts"] = 3
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = utc_now()
        if "next_retry_at" not in kwargs:
            kwargs["next_retry_at"] = utc_now()
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<OCRJob id={self.id} version_id={self.document_version_id} status={self.status.value} attempts={self.attempt_count}/{self.max_attempts}>"
