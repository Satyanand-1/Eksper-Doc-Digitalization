"""
Local disk storage service module.
Provides secure staging, hashing, and finalization of stored files.
Enforces strict storage-root path containment, prevents directory traversal,
and maintains relative server-controlled storage keys.
"""
import os
import uuid
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO
from app.config import settings

class StorageSecurityError(Exception):
    """Raised when an operation attempts path traversal or violates storage-root boundaries."""
    pass

class StorageFileExistsError(Exception):
    """Raised when an operation attempts to silently overwrite an existing persistent file."""
    pass

class StorageFileNotFoundError(Exception):
    """Raised when a requested storage key cannot be found on disk."""
    pass

class LocalStorageService:
    """
    Manages persistent and staging storage on local disk outside public web roots.
    All public methods operate with sanitized server-controlled storage keys.
    """

    def __init__(self, root_dir: str | None = None):
        raw_root = root_dir or settings.STORAGE_ROOT
        self.root_path = Path(raw_root).resolve()
        self.uploads_dir = (self.root_path / "uploads").resolve()
        self.temp_dir = (self.root_path / "temp").resolve()

        # Ensure base directories exist
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def _validate_path_containment(self, target_path: Path, expected_parent: Path) -> Path:
        """
        Validates that target_path strictly resolves within expected_parent.
        Rejects path traversal (e.g. '../', absolute escaped paths).
        """
        resolved_target = target_path.resolve()
        resolved_parent = expected_parent.resolve()

        try:
            resolved_target.relative_to(resolved_parent)
        except ValueError:
            raise StorageSecurityError(
                f"Security violation: Path '{target_path}' traverses outside authorized directory '{expected_parent}'"
            )

        return resolved_target

    def generate_storage_key(self, extension: str = "") -> str:
        """
        Generates a random, structured, date-partitioned storage key.
        Format: uploads/YYYY/MM/<uuid>.<ext>
        Guarantees that user-supplied filenames never dictate filesystem layout.
        """
        now = datetime.now(timezone.utc)
        clean_ext = extension.lstrip(".").lower()
        # Sanitize extension (alphanumeric only, max 10 chars)
        clean_ext = "".join(ch for ch in clean_ext if ch.isalnum())[:10]
        ext_suffix = f".{clean_ext}" if clean_ext else ""

        file_id = uuid.uuid4()
        storage_key = f"uploads/{now.year:04d}/{now.month:02d}/{file_id}{ext_suffix}"
        return storage_key

    def resolve_storage_path(self, storage_key: str) -> Path:
        """
        Resolves a relative storage key to an absolute path.
        Validates that the resulting path remains within the storage root.
        """
        if not storage_key or not isinstance(storage_key, str):
            raise StorageSecurityError("Storage key must be a non-empty string")

        # Normalize slashes and reject drive letters or leading slashes
        clean_key = storage_key.strip().replace("\\", "/")
        if clean_key.startswith("/") or ":" in clean_key:
            raise StorageSecurityError(f"Absolute or drive-qualified storage key rejected: '{storage_key}'")

        target_path = self.root_path / clean_key
        return self._validate_path_containment(target_path, self.root_path)

    def stage_file(self, content_stream: BinaryIO) -> tuple[Path, str, int]:
        """
        Safely streams incoming data to a temporary staging file in `temp/`.
        Computes SHA-256 checksum and total byte size on-the-fly.
        Returns: (temp_file_path, sha256_hash, file_size_bytes)
        """
        temp_id = uuid.uuid4()
        temp_path = self.temp_dir / f"stage_{temp_id}.tmp"
        self._validate_path_containment(temp_path, self.temp_dir)

        sha256 = hashlib.sha256()
        total_bytes = 0

        try:
            with open(temp_path, "wb") as f_out:
                while chunk := content_stream.read(64 * 1024):
                    sha256.update(chunk)
                    total_bytes += len(chunk)
                    f_out.write(chunk)
        except Exception:
            # Clean up partial temp file immediately on stream failure
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

        return temp_path, sha256.hexdigest(), total_bytes

    def finalize_staged_file(self, temp_path: Path, storage_key: str) -> Path:
        """
        Atomically moves a staged temporary file to its permanent destination in `uploads/`.
        Ensures destination directories are created.
        Guarantees that an existing file is not silently overwritten.
        """
        self._validate_path_containment(temp_path, self.temp_dir)
        if not temp_path.exists():
            raise StorageFileNotFoundError(f"Temporary file '{temp_path}' does not exist")

        dest_path = self.resolve_storage_path(storage_key)
        if dest_path.exists():
            raise StorageFileExistsError(f"Destination file already exists for key: '{storage_key}'")

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(temp_path), str(dest_path))
        except Exception:
            # Clean up on failure
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise

        return dest_path

    def cleanup_temp_file(self, temp_path: Path) -> None:
        """Safely removes a temporary file if it exists."""
        try:
            self._validate_path_containment(temp_path, self.temp_dir)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        except Exception:
            pass

    def file_exists(self, storage_key: str) -> bool:
        """Checks if a finalized file exists on disk."""
        try:
            path = self.resolve_storage_path(storage_key)
            return path.is_file()
        except StorageSecurityError:
            return False

    def compute_sha256(self, file_path: Path) -> str:
        """Computes SHA-256 checksum of an existing file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                sha256.update(chunk)
        return sha256.hexdigest()

    def persist_binary_to_db(self, db, version_id: uuid.UUID, file_bytes: bytes) -> None:
        """
        Saves or updates the persistent file binary in PostgreSQL.
        Ensures the document content survives ephemeral cloud container restarts.
        """
        try:
            from app.models.document_content import DocumentFileContent
            existing = db.query(DocumentFileContent).filter(DocumentFileContent.version_id == version_id).first()
            if existing:
                existing.file_bytes = file_bytes
            else:
                db.add(DocumentFileContent(version_id=version_id, file_bytes=file_bytes))
        except Exception:
            pass

    def ensure_file_on_disk(self, db, version, doc=None) -> Path:
        """
        Guarantees that the file binary exists on disk at its storage_key.
        If container local storage was purged (ephemeral container sleep / restart / redeployment),
        it automatically re-hydrates the file binary from PostgreSQL.
        """
        file_path = self.resolve_storage_path(version.storage_key)
        if file_path.is_file() and file_path.stat().st_size > 0:
            return file_path

        # 1. Restore from PostgreSQL document_file_contents table
        try:
            from app.models.document_content import DocumentFileContent
            row = db.query(DocumentFileContent).filter(DocumentFileContent.version_id == version.id).first()
            if row and row.file_bytes:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "wb") as f_out:
                    f_out.write(row.file_bytes)
                return file_path
        except Exception:
            pass

        return file_path

# Singleton storage service instance configured with application settings
storage_service = LocalStorageService()
