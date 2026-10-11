import uuid
from datetime import datetime, timezone
import enum
from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, validates
from app.database import Base

class UserRole(str, enum.Enum):
    """
    Supported user roles across the EDRMS platform.
    Stored as snake_case strings for database portability and consistency.
    """
    ADMIN = "admin"                          # Administrator
    RECORDS_OFFICER = "records_officer"      # Records Officer
    DEPARTMENT_USER = "department_user"      # Department User
    APPROVER = "approver"                    # Approver
    AUDITOR = "auditor"                      # Auditor
    READ_ONLY = "read_only"                  # Read-Only User

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    # UUID primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Unique and indexed email address
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    # Full display name
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Argon2id password hash (never stores plaintext)
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Optional department assignment
    department: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
    )

    # Role using native Enum / string type
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.DEPARTMENT_USER,
    )

    # Active status flag
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # Timezone-aware audit timestamps
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

    def __init__(self, **kwargs):
        # Ensure default values are populated on Python instance creation
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "is_active" not in kwargs:
            kwargs["is_active"] = True
        if "role" not in kwargs:
            kwargs["role"] = UserRole.DEPARTMENT_USER
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = utc_now()
        super().__init__(**kwargs)

    @validates("email")
    def validate_and_normalize_email(self, key: str, email_val: str) -> str:
        """Normalizes email to lower-case and stripped whitespace."""
        if not email_val or not isinstance(email_val, str):
            raise ValueError("Email is required and must be a valid string")
        normalized = email_val.strip().lower()
        if "@" not in normalized or len(normalized) < 3:
            raise ValueError("Invalid email address format")
        return normalized

    def __repr__(self) -> str:
        # Exclude hashed_password and sensitive attributes from repr
        role_val = self.role.value if isinstance(self.role, UserRole) else self.role
        return f"<User id={self.id} email={self.email} role={role_val} is_active={self.is_active}>"
