import re
import secrets
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.document import DigitalDocument

def generate_document_reference(db: Session, prefix: str = "DOC") -> str:
    """
    Generates a unique, human-readable document reference format:
    e.g. DOC-2026-A1B2C3D4

    Uniqueness is guaranteed by:
    1. Combining year with a cryptographically secure random 8-character uppercase hex suffix.
    2. Enforcing uniqueness at the database level with a unique index.
    3. Retrying on the rare occasion of a collision.
    """
    year = datetime.now(timezone.utc).year
    max_attempts = 10

    for _ in range(max_attempts):
        suffix = secrets.token_hex(4).upper()
        candidate = f"{prefix}-{year}-{suffix}"

        # Preliminary check within current transaction
        existing = db.query(DigitalDocument.id).filter(
            DigitalDocument.document_reference == candidate
        ).first()

        if not existing:
            return candidate

    raise RuntimeError("Failed to generate a unique document reference after multiple attempts.")


def generate_physical_file_reference(db: Session, prefix: str = "PHY") -> str:
    """
    Generates a unique, human-readable physical file reference format:
    e.g. PHY-2026-A1B2C3D4

    Uniqueness is guaranteed by:
    1. Combining year with a cryptographically secure random 8-character uppercase hex suffix.
    2. Enforcing uniqueness at the database level with a unique index.
    3. Retrying on the rare occasion of a collision.
    """
    from app.models.physical_file import PhysicalFile

    year = datetime.now(timezone.utc).year
    max_attempts = 10

    for _ in range(max_attempts):
        suffix = secrets.token_hex(4).upper()
        candidate = f"{prefix}-{year}-{suffix}"

        # Preliminary check within current transaction
        existing = db.query(PhysicalFile.id).filter(
            PhysicalFile.file_reference == candidate
        ).first()

        if not existing:
            return candidate

    raise RuntimeError("Failed to generate a unique physical file reference after multiple attempts.")
