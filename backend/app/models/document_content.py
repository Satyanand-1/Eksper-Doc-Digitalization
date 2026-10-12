"""
Database model for persistent document file content storage in PostgreSQL.
Protects uploaded binary contents across ephemeral container restarts, redeployments, and host spin-downs.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentFileContent(Base):
    """
    Persistent document binary store.
    Keeps binary copies in PostgreSQL to guarantee availability even if
    ephemeral container local storage is purged during sleep/redeployment.
    """
    __tablename__ = "document_file_contents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    file_bytes: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    version = relationship("DocumentVersion", backref="file_content")
