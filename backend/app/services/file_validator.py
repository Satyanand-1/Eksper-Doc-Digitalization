import re
from pathlib import Path
from typing import BinaryIO

class FileValidationError(Exception):
    """Raised when an uploaded file violates format, magic-byte, or integrity constraints."""
    pass

# Supported file extensions, MIME types, and signature validators
# PDF: %PDF- (0x25, 0x50, 0x44, 0x46, 0x2D)
# JPEG: 0xFF, 0xD8, 0xFF
# PNG: 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A
# TIFF (Little Endian): 0x49, 0x49, 0x2A, 0x00
# TIFF (Big Endian): 0x4D, 0x4D, 0x00, 0x2A

SUPPORTED_TYPES = {
    "pdf": {
        "mime": "application/pdf",
        "extensions": [".pdf"],
        "magic_check": lambda b: b.startswith(b"%PDF-"),
    },
    "jpeg": {
        "mime": "image/jpeg",
        "extensions": [".jpg", ".jpeg"],
        "magic_check": lambda b: b.startswith(b"\xff\xd8\xff"),
    },
    "png": {
        "mime": "image/png",
        "extensions": [".png"],
        "magic_check": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    },
    "tiff": {
        "mime": "image/tiff",
        "extensions": [".tif", ".tiff"],
        "magic_check": lambda b: b.startswith(b"II*\x00") or b.startswith(b"MM\x00*"),
    },
}

def sanitize_filename(filename: str) -> str:
    """
    Sanitizes user-supplied filename for display and download metadata.
    Removes directory path separators and dangerous characters while preserving base name and extension.
    """
    if not filename:
        return "unnamed_document"
    # Remove directory traversal and leading paths
    clean = Path(filename).name.strip()
    # Replace non-alphanumeric (except dot, underscore, hyphen, space)
    clean = re.sub(r"[^\w\s\.-]", "_", clean)
    return clean[:200] or "unnamed_document"

def inspect_file_content(file_path: Path) -> tuple[str, str]:
    """
    Validates file content by inspecting magic bytes directly from disk.
    Returns: (canonical_extension, canonical_mime_type)
    Raises FileValidationError if magic bytes don't match any supported format.
    """
    with open(file_path, "rb") as f:
        header = f.read(32)

    if not header:
        raise FileValidationError("Uploaded file is empty (0 bytes).")

    for type_name, spec in SUPPORTED_TYPES.items():
        if spec["magic_check"](header):
            return spec["extensions"][0].lstrip("."), spec["mime"]

    raise FileValidationError(
        "Unsupported or invalid file content. Supported formats are PDF, JPEG, PNG, and TIFF."
    )

def validate_filename_and_content_match(filename: str, canonical_ext: str) -> None:
    """
    Verifies that the original filename extension does not mismatch the inspected magic-byte format
    (e.g., rejecting an executable or script disguised with a .pdf extension, or a PNG file named .pdf).
    """
    file_ext = Path(filename).suffix.lower()
    
    # Check if the filename extension is valid for the detected type
    allowed_exts = []
    for spec in SUPPORTED_TYPES.values():
        if canonical_ext in [ext.lstrip(".") for ext in spec["extensions"]]:
            allowed_exts = spec["extensions"]
            break

    if file_ext not in allowed_exts:
        raise FileValidationError(
            f"File extension '{file_ext}' does not match detected file content format (expected {allowed_exts})."
        )
