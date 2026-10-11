"""
OCR and Text Extraction Service module.
Provides secure, deterministic text extraction and OCR for stored documents:
- Text-based PDFs: Extracts embedded text directly using pypdf.
- Scanned PDFs: Renders PDF pages to images using pdf2image/poppler and runs Tesseract OCR.
- PNG and JPEG: Runs Tesseract OCR on images via Pillow.
- TIFF: Supports single and multi-page TIFF images via Pillow and Tesseract OCR.

Enforces strict safety boundaries:
- Resolves files strictly via trusted storage service (no arbitrary paths).
- Bounded processing: page-count limit, file-size limit, and execution timeout.
- Never logs sensitive document text.
- Cleans up temporary resources.
- Preserves existing extracted text on failure (never overwrites valid text with empty/null on error).
"""
import logging
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import uuid
from PIL import Image, ImageOps, UnidentifiedImageError
import pypdf
from pypdf.errors import PdfReadError
import pytesseract
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.document import DocumentVersion, ExtractionStatus, utc_now
from app.services.storage import LocalStorageService, storage_service, StorageSecurityError

logger = logging.getLogger(__name__)


class ExtractionStrategy(str, Enum):
    """Strategy employed to extract text."""
    EMBEDDED_PDF = "embedded_pdf"
    OCR_PDF = "ocr_pdf"
    OCR_IMAGE = "ocr_image"
    SKIPPED_EMPTY = "skipped_empty"


class OCRError(Exception):
    """Base exception for OCR and text extraction failures."""
    pass


class UnsupportedFormatError(OCRError):
    """Raised when file format is not supported for text extraction/OCR."""
    pass


class ResourceLimitExceededError(OCRError):
    """Raised when document exceeds allowed page count, file size, or execution time."""
    pass


class CorruptFileError(OCRError):
    """Raised when document binary is corrupt or cannot be decoded."""
    pass


class EncryptedFileError(OCRError):
    """Raised when document (e.g. PDF) is password-protected or encrypted."""
    pass


@dataclass
class ExtractionResult:
    """Result of text extraction process."""
    success: bool
    text: Optional[str]
    strategy: Optional[ExtractionStrategy]
    page_count: int
    char_count: int
    execution_time_seconds: float
    error_message: Optional[str] = None


class TextExtractionService:
    """
    Dedicated text extraction and OCR engine service for EDRMS documents.
    """

    def __init__(
        self,
        storage: Optional[LocalStorageService] = None,
        max_pages: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        max_file_size_bytes: Optional[int] = None,
        tesseract_cmd: Optional[str] = None,
    ):
        self.storage = storage or storage_service
        self.max_pages = max_pages or settings.OCR_MAX_PAGES
        self.timeout_seconds = timeout_seconds or settings.OCR_TIMEOUT_SECONDS
        self.max_file_size_bytes = max_file_size_bytes or settings.OCR_MAX_FILE_SIZE_BYTES
        self.tesseract_cmd = tesseract_cmd or settings.TESSERACT_CMD

        # Configure pytesseract binary if specified
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    def extract_text_from_file(self, file_path: Path, mime_type: str) -> ExtractionResult:
        """
        Extracts text from a local file path with format inspection and resource limits.
        """
        start_time = time.time()
        clean_mime = (mime_type or "").strip().lower()

        # 1. Basic filesystem verification
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"File not found on disk: {file_path.name}")

        file_size = file_path.stat().st_size
        if file_size == 0:
            return ExtractionResult(
                success=True,
                text="",
                strategy=ExtractionStrategy.SKIPPED_EMPTY,
                page_count=0,
                char_count=0,
                execution_time_seconds=round(time.time() - start_time, 4),
            )

        if file_size > self.max_file_size_bytes:
            raise ResourceLimitExceededError(
                f"File size {file_size} bytes exceeds maximum allowed {self.max_file_size_bytes} bytes"
            )

        # 2. Dispatch based on mime_type
        if clean_mime == "application/pdf":
            return self._extract_from_pdf(file_path, start_time)
        elif clean_mime in {"image/jpeg", "image/jpg", "image/png", "image/tiff", "image/tif"}:
            return self._extract_from_image(file_path, start_time)
        else:
            raise UnsupportedFormatError(f"Unsupported MIME type for text extraction/OCR: '{mime_type}'")

    def _extract_from_pdf(self, file_path: Path, start_time: float) -> ExtractionResult:
        """
        Two-stage PDF extraction:
        1. Fast embedded text extraction using pypdf.
        2. Fallback to rasterization + Tesseract OCR if embedded text is insufficient.
        """
        try:
            reader = pypdf.PdfReader(str(file_path))
        except PdfReadError as e:
            raise CorruptFileError(f"Corrupt or invalid PDF file: {e}")
        except Exception as e:
            raise CorruptFileError(f"Failed to parse PDF: {e}")

        if reader.is_encrypted:
            raise EncryptedFileError("PDF is password-protected or encrypted; cannot extract text")

        total_pages = len(reader.pages)
        if total_pages > self.max_pages:
            raise ResourceLimitExceededError(
                f"PDF has {total_pages} pages, which exceeds the allowed limit of {self.max_pages} pages"
            )

        # Stage 1: Attempt embedded text extraction
        embedded_text_parts: list[str] = []
        for page_idx, page in enumerate(reader.pages):
            if (time.time() - start_time) > self.timeout_seconds:
                raise ResourceLimitExceededError(f"Text extraction timed out after {self.timeout_seconds}s")
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    embedded_text_parts.append(page_text.strip())
            except Exception as e:
                logger.warning(f"Error extracting embedded text from page {page_idx + 1}: {e}")

        combined_embedded = "\n\n".join(embedded_text_parts).strip()

        # If substantial text is present (at least 30 characters on average across pages with text, or 50 chars total),
        # consider embedded extraction sufficient
        if len(combined_embedded) >= 50 or (total_pages > 0 and len(combined_embedded) >= 20 * total_pages):
            return ExtractionResult(
                success=True,
                text=combined_embedded,
                strategy=ExtractionStrategy.EMBEDDED_PDF,
                page_count=total_pages,
                char_count=len(combined_embedded),
                execution_time_seconds=round(time.time() - start_time, 4),
            )

        # Stage 2: Fallback to rendered OCR for scanned/raster PDFs
        logger.info(f"PDF has insufficient embedded text ({len(combined_embedded)} chars). Falling back to OCR.")
        ocr_text_parts: list[str] = []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Convert pages to images with DPI 200
                images = convert_from_path(
                    str(file_path),
                    dpi=200,
                    output_folder=temp_dir,
                    first_page=1,
                    last_page=self.max_pages,
                )

                for page_idx, image in enumerate(images):
                    if (time.time() - start_time) > self.timeout_seconds:
                        raise ResourceLimitExceededError(f"OCR processing timed out after {self.timeout_seconds}s")

                    # Run Tesseract OCR on rendered page image
                    page_ocr = pytesseract.image_to_string(image, timeout=self.timeout_seconds)
                    if page_ocr.strip():
                        ocr_text_parts.append(page_ocr.strip())

        except (PDFPageCountError, PDFSyntaxError) as e:
            raise CorruptFileError(f"Poppler rendering failed for PDF: {e}")
        except pytesseract.TesseractError as e:
            raise OCRError(f"Tesseract execution error: {e}")
        except ResourceLimitExceededError:
            raise
        except Exception as e:
            raise OCRError(f"Failed during PDF OCR rendering: {e}")

        final_ocr_text = "\n\n".join(ocr_text_parts).strip()
        # If OCR produced text, use it; otherwise retain whatever embedded text existed
        result_text = final_ocr_text if final_ocr_text else combined_embedded

        return ExtractionResult(
            success=True,
            text=result_text,
            strategy=ExtractionStrategy.OCR_PDF if final_ocr_text else ExtractionStrategy.EMBEDDED_PDF,
            page_count=total_pages,
            char_count=len(result_text),
            execution_time_seconds=round(time.time() - start_time, 4),
        )

    def _extract_from_image(self, file_path: Path, start_time: float) -> ExtractionResult:
        """
        Extract text from image files (PNG, JPEG, TIFF).
        Supports multi-frame TIFFs up to max_pages.
        """
        try:
            img = Image.open(str(file_path))
        except UnidentifiedImageError:
            raise CorruptFileError("Unrecognized or corrupted image format")
        except Exception as e:
            raise CorruptFileError(f"Failed to open image file: {e}")

        text_parts: list[str] = []
        page_count = 0

        try:
            # Handle multi-frame images (like multi-page TIFFs) or standard single-frame images
            n_frames = getattr(img, "n_frames", 1)
            if n_frames > self.max_pages:
                raise ResourceLimitExceededError(
                    f"Image contains {n_frames} frames, exceeding maximum limit of {self.max_pages}"
                )

            for frame_idx in range(n_frames):
                if (time.time() - start_time) > self.timeout_seconds:
                    raise ResourceLimitExceededError(f"OCR timed out after {self.timeout_seconds}s")

                img.seek(frame_idx)
                # Convert palette/RGBA to RGB or Grayscale for optimal OCR
                frame = img.copy()
                if frame.mode in ("RGBA", "LA", "P"):
                    frame = frame.convert("RGB")

                frame_text = pytesseract.image_to_string(frame, timeout=self.timeout_seconds)
                if frame_text.strip():
                    text_parts.append(frame_text.strip())
                page_count += 1

        except pytesseract.TesseractError as e:
            raise OCRError(f"Tesseract OCR error: {e}")
        except ResourceLimitExceededError:
            raise
        except Exception as e:
            raise CorruptFileError(f"Failed processing image frames: {e}")
        finally:
            try:
                img.close()
            except Exception:
                pass

        combined_text = "\n\n".join(text_parts).strip()

        return ExtractionResult(
            success=True,
            text=combined_text,
            strategy=ExtractionStrategy.OCR_IMAGE,
            page_count=page_count,
            char_count=len(combined_text),
            execution_time_seconds=round(time.time() - start_time, 4),
        )

    def process_and_persist_version(
        self,
        db: Session,
        version: DocumentVersion,
    ) -> ExtractionResult:
        """
        Safely processes text extraction for a stored DocumentVersion and persists results.
        Enforces:
        - Sets extraction_status to PROCESSING.
        - Resolves storage key via trusted storage service (security containment check).
        - On success: sets extraction_status to COMPLETED, updates extraction_completed_at, and saves extracted_text.
        - On failure: sets extraction_status to FAILED, records sanitized extraction_error,
          and PRESERVES existing valid version.extracted_text (never overwrites valid text with empty content).
        - Commits state changes to database.
        """
        if not version or not version.storage_key:
            raise ValueError("Invalid DocumentVersion: missing version or storage_key")

        # 1. Update status to PROCESSING
        version.extraction_status = ExtractionStatus.PROCESSING
        version.extraction_error = None
        db.commit()
        db.refresh(version)

        try:
            # 2. Resolve path through trusted storage containment
            try:
                resolved_path = self.storage.resolve_storage_path(version.storage_key)
            except StorageSecurityError as e:
                logger.critical(f"Storage path security containment violation: {e}")
                raise

            if not resolved_path.exists() or not resolved_path.is_file():
                logger.error(f"Stored binary missing from disk for version {version.id}")
                raise FileNotFoundError(f"File for version {version.id} does not exist on disk")

            # 3. Perform text extraction
            result = self.extract_text_from_file(resolved_path, version.mime_type)

            # 4. On success: update extracted_text, status, and completion timestamp
            if result.success and result.text is not None:
                version.extracted_text = result.text
                version.extraction_status = ExtractionStatus.COMPLETED
                version.extraction_completed_at = utc_now()
                version.extraction_error = None
                db.commit()
                db.refresh(version)
                logger.info(
                    f"Successfully extracted and persisted text for version {version.id} "
                    f"({result.char_count} chars, strategy={result.strategy.value})"
                )
            return result

        except Exception as exc:
            # 5. On failure: mark as FAILED, record sanitized error, preserve existing extracted_text
            db.rollback()
            # Re-fetch version to ensure clean session state
            current_ver = db.query(DocumentVersion).filter(DocumentVersion.id == version.id).first()
            if current_ver:
                current_ver.extraction_status = ExtractionStatus.FAILED
                # Truncate and sanitize error message to avoid leaking internals or stack traces
                raw_error = str(exc).strip()
                sanitized_error = raw_error[:250] if raw_error else exc.__class__.__name__
                current_ver.extraction_error = sanitized_error
                db.commit()
                db.refresh(current_ver)
            logger.error(f"Extraction failed for version {version.id}: {exc.__class__.__name__}")
            raise


# Singleton instance
ocr_service = TextExtractionService()


def process_version_background(version_id: uuid.UUID) -> None:
    """
    Background worker task for processing a document version's text extraction.
    Creates a fresh, isolated SQLAlchemy database session via SessionLocal.
    Guarantees session cleanup upon exit.
    Prevents duplicate concurrent processing if version is already processing or completed.
    """
    from app.database import SessionLocal

    db: Session = SessionLocal()
    try:
        version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not version:
            logger.error(f"Background OCR task aborted: DocumentVersion {version_id} not found in DB")
            return

        # Concurrency / idempotency guard: do not re-run if already completed or actively processing
        if version.extraction_status in (ExtractionStatus.COMPLETED, ExtractionStatus.PROCESSING):
            logger.info(
                f"Skipping background OCR for version {version_id}: already {version.extraction_status.value}"
            )
            return

        ocr_service.process_and_persist_version(db=db, version=version)

    except Exception as exc:
        logger.error(f"Background OCR processing completed with error for version {version_id}: {exc.__class__.__name__}")
    finally:
        db.close()

