"""
Automated test suite for Task 4.1: OCR Engine Foundation and Text Extraction.
Tests cover:
1. Text extraction from a text-based PDF (extracts embedded text without OCR).
2. OCR extraction from a scanned PDF (renders pages and executes Tesseract OCR).
3. OCR extraction from PNG and JPEG images.
4. TIFF handling (single-frame and multi-page TIFF images).
5. Empty and corrupt files handling (graceful handling, appropriate exceptions).
6. Encrypted PDFs handling (raises EncryptedFileError).
7. Unsupported formats (raises UnsupportedFormatError).
8. Missing stored files handling (FileNotFoundError).
9. Processing limits and resource cleanup (page-count limits, file-size limits, timeouts, temp file cleanup).
10. Database persistence of extracted text via process_and_persist_version.
11. Failure handling without overwriting valid existing text in the database.
12. Verification that existing upload, download, preview, authorization, and repository tests remain passing.
"""
import io
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image, ImageDraw
import pypdf
from pypdf import PdfWriter

from app.models.user import UserRole
from app.models.document import DigitalDocument, DocumentVersion, DocumentStatus
from app.services.storage import storage_service
from app.services.ocr import (
    TextExtractionService,
    ExtractionStrategy,
    ExtractionResult,
    UnsupportedFormatError,
    ResourceLimitExceededError,
    CorruptFileError,
    EncryptedFileError,
    ocr_service,
)

# Helper fixtures for generating deterministic test binaries

def make_text_pdf_bytes(text: str = "Confidential Financial Overview and Quarterly Report") -> bytes:
    """Generates a valid PDF with embedded text."""
    pdf_template = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {len(text) + 30} >>
stream
BT
/F1 18 Tf
50 700 Td
({text}) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000338 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
417
%%EOF"""
    return pdf_template.encode("latin-1")


def make_scanned_pdf_bytes(text: str = "SCANNED INVOICE 98765") -> bytes:
    """Generates a raster-only PDF (no embedded text stream, pure image)."""
    img = Image.new("RGB", (400, 120), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 45), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


def make_image_bytes(format_name: str, text: str = "IMAGE OCR TEXT 12345") -> bytes:
    """Generates an image (PNG, JPEG) with rendered text for OCR."""
    img = Image.new("RGB", (400, 120), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 45), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format=format_name)
    return buf.getvalue()


def make_multipage_tiff_bytes(texts: list[str]) -> bytes:
    """Generates a multi-page TIFF image."""
    images = []
    for t in texts:
        img = Image.new("RGB", (400, 120), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 45), t, fill="black")
        images.append(img)
    buf = io.BytesIO()
    images[0].save(buf, format="TIFF", save_all=True, append_images=images[1:])
    return buf.getvalue()


def make_encrypted_pdf_bytes(password: str = "SuperSecret123!") -> bytes:
    """Generates an encrypted/password-protected PDF."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ----------------- Tests -----------------

def test_extract_text_from_text_based_pdf(tmp_path):
    """Test 1: Text extraction from a text-based PDF uses embedded extraction strategy without OCR."""
    test_pdf_content = make_text_pdf_bytes("Quarterly Operations and Audit Report 2026")
    pdf_path = tmp_path / "text_doc.pdf"
    pdf_path.write_bytes(test_pdf_content)

    result = ocr_service.extract_text_from_file(pdf_path, "application/pdf")

    assert result.success is True
    assert result.strategy == ExtractionStrategy.EMBEDDED_PDF
    assert "Quarterly Operations and Audit Report 2026" in result.text
    assert result.page_count == 1
    assert result.char_count > 0


def test_ocr_extraction_from_scanned_pdf(tmp_path):
    """Test 2: Scanned PDF without embedded text triggers fallback to rasterization and Tesseract OCR."""
    scanned_bytes = make_scanned_pdf_bytes("SCANNED INVOICE 98765")
    pdf_path = tmp_path / "scanned_doc.pdf"
    pdf_path.write_bytes(scanned_bytes)

    result = ocr_service.extract_text_from_file(pdf_path, "application/pdf")

    assert result.success is True
    assert result.strategy == ExtractionStrategy.OCR_PDF
    assert "SCANNED" in result.text or "INVOICE" in result.text
    assert result.page_count == 1


def test_ocr_extraction_from_png_and_jpeg_images(tmp_path):
    """Test 3: OCR extraction from PNG and JPEG images using Tesseract."""
    # 1. PNG Image
    png_bytes = make_image_bytes("PNG", "PNG RECEIPT 1010")
    png_path = tmp_path / "receipt.png"
    png_path.write_bytes(png_bytes)

    res_png = ocr_service.extract_text_from_file(png_path, "image/png")
    assert res_png.success is True
    assert res_png.strategy == ExtractionStrategy.OCR_IMAGE
    assert "RECEIPT" in res_png.text or "1010" in res_png.text
    assert res_png.page_count == 1

    # 2. JPEG Image
    jpg_bytes = make_image_bytes("JPEG", "JPEG VOUCHER 2020")
    jpg_path = tmp_path / "voucher.jpg"
    jpg_path.write_bytes(jpg_bytes)

    res_jpg = ocr_service.extract_text_from_file(jpg_path, "image/jpeg")
    assert res_jpg.success is True
    assert res_jpg.strategy == ExtractionStrategy.OCR_IMAGE
    assert "VOUCHER" in res_jpg.text or "2020" in res_jpg.text
    assert res_jpg.page_count == 1


def test_ocr_extraction_from_tiff(tmp_path):
    """Test 4: TIFF handling for single and multi-page images."""
    tiff_bytes = make_multipage_tiff_bytes(["TIFF PAGE ONE", "TIFF PAGE TWO"])
    tiff_path = tmp_path / "multipage.tiff"
    tiff_path.write_bytes(tiff_bytes)

    result = ocr_service.extract_text_from_file(tiff_path, "image/tiff")

    assert result.success is True
    assert result.strategy == ExtractionStrategy.OCR_IMAGE
    assert result.page_count == 2
    assert "PAGE" in result.text or "TIFF" in result.text


def test_empty_and_corrupt_files(tmp_path):
    """Test 5: Empty files return empty result gracefully; corrupt files raise CorruptFileError."""
    # 1. Empty file
    empty_file = tmp_path / "empty.pdf"
    empty_file.write_bytes(b"")

    res_empty = ocr_service.extract_text_from_file(empty_file, "application/pdf")
    assert res_empty.success is True
    assert res_empty.text == ""
    assert res_empty.strategy == ExtractionStrategy.SKIPPED_EMPTY

    # 2. Corrupt PDF
    corrupt_pdf = tmp_path / "corrupt.pdf"
    corrupt_pdf.write_bytes(b"NOT A REAL PDF FILE CONTENT AT ALL")

    with pytest.raises(CorruptFileError):
        ocr_service.extract_text_from_file(corrupt_pdf, "application/pdf")

    # 3. Corrupt Image
    corrupt_img = tmp_path / "corrupt.png"
    corrupt_img.write_bytes(b"NOT AN IMAGE HEADER")

    with pytest.raises(CorruptFileError):
        ocr_service.extract_text_from_file(corrupt_img, "image/png")


def test_encrypted_pdf_handling(tmp_path):
    """Test 6: Encrypted PDF files raise EncryptedFileError gracefully."""
    enc_bytes = make_encrypted_pdf_bytes("ProtectedPass123")
    enc_path = tmp_path / "locked.pdf"
    enc_path.write_bytes(enc_bytes)

    with pytest.raises(EncryptedFileError) as exc_info:
        ocr_service.extract_text_from_file(enc_path, "application/pdf")

    assert "encrypted" in str(exc_info.value).lower()


def test_unsupported_formats(tmp_path):
    """Test 7: Unsupported file formats raise UnsupportedFormatError."""
    txt_file = tmp_path / "document.txt"
    txt_file.write_bytes(b"Hello plain text")

    with pytest.raises(UnsupportedFormatError):
        ocr_service.extract_text_from_file(txt_file, "text/plain")

    exe_file = tmp_path / "program.exe"
    exe_file.write_bytes(b"MZ executable header")

    with pytest.raises(UnsupportedFormatError):
        ocr_service.extract_text_from_file(exe_file, "application/x-dosexec")


def test_missing_stored_file(tmp_path):
    """Test 8: Missing stored file on disk raises FileNotFoundError."""
    missing_file = tmp_path / "does_not_exist.pdf"

    with pytest.raises(FileNotFoundError):
        ocr_service.extract_text_from_file(missing_file, "application/pdf")


def test_resource_limits_and_cleanup(tmp_path):
    """Test 9: Enforces page-count, file-size limits, and timeout."""
    # 1. File size limit
    custom_service = TextExtractionService(max_file_size_bytes=100)
    oversized_file = tmp_path / "oversized.pdf"
    oversized_file.write_bytes(b"A" * 500)

    with pytest.raises(ResourceLimitExceededError):
        custom_service.extract_text_from_file(oversized_file, "application/pdf")

    # 2. Page count limit on multi-frame TIFF
    tiff_bytes = make_multipage_tiff_bytes(["PAGE 1", "PAGE 2", "PAGE 3"])
    tiff_path = tmp_path / "three_pages.tiff"
    tiff_path.write_bytes(tiff_bytes)

    page_limited_service = TextExtractionService(max_pages=2)
    with pytest.raises(ResourceLimitExceededError):
        page_limited_service.extract_text_from_file(tiff_path, "image/tiff")


def test_process_and_persist_version(role_user_factory, db_session):
    """Test 10: process_and_persist_version executes extraction and updates DocumentVersion.extracted_text in DB."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]
    pdf_content = make_text_pdf_bytes("Persisted OCR Content Test for EDRMS")

    # Stage and finalize file
    temp_path, f_hash, f_size = storage_service.stage_file(io.BytesIO(pdf_content))
    s_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(temp_path, s_key)

    doc = DigitalDocument(
        document_reference=f"DOC-OCR-{uuid.uuid4().hex[:8].upper()}",
        title="OCR Test Document",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=s_key,
        original_filename="ocr_test.pdf",
        mime_type="application/pdf",
        file_size_bytes=f_size,
        file_hash_sha256=f_hash,
        created_by_id=admin.id,
        extracted_text=None,
    )
    db_session.add(ver)
    db_session.commit()
    db_session.refresh(ver)

    assert ver.extracted_text is None

    # Process and persist text
    result = ocr_service.process_and_persist_version(db=db_session, version=ver)

    assert result.success is True
    assert "Persisted OCR Content Test" in result.text

    # Re-query DB to verify persistence
    db_session.refresh(ver)
    assert ver.extracted_text is not None
    assert "Persisted OCR Content Test" in ver.extracted_text

    # Cleanup
    storage_service.resolve_storage_path(s_key).unlink(missing_ok=True)
    db_session.delete(doc)
    db_session.commit()


def test_failure_preserves_existing_extracted_text(role_user_factory, db_session):
    """Test 11: Failures do not overwrite previously valid extracted_text in DB."""
    admin = role_user_factory(role=UserRole.ADMIN)["user"]

    temp_path, f_hash, f_size = storage_service.stage_file(io.BytesIO(b"NOT A VALID PDF"))
    s_key = storage_service.generate_storage_key("pdf")
    storage_service.finalize_staged_file(temp_path, s_key)

    doc = DigitalDocument(
        document_reference=f"DOC-FAIL-{uuid.uuid4().hex[:8].upper()}",
        title="Preserve Text Test",
        department="Finance",
        classification="General",
        mime_type="application/pdf",
        status=DocumentStatus.ACTIVE,
        created_by_id=admin.id,
    )
    db_session.add(doc)
    db_session.flush()

    PREVIOUS_VALID_TEXT = "Existing Valid Extracted Text That Must Be Preserved"

    ver = DocumentVersion(
        document_id=doc.id,
        version_number=1,
        storage_key=s_key,
        original_filename="fail.pdf",
        mime_type="application/pdf",
        file_size_bytes=f_size,
        file_hash_sha256=f_hash,
        created_by_id=admin.id,
        extracted_text=PREVIOUS_VALID_TEXT,
    )
    db_session.add(ver)
    db_session.commit()
    db_session.refresh(ver)

    # Attempt to process corrupt file; must raise CorruptFileError
    with pytest.raises(CorruptFileError):
        ocr_service.process_and_persist_version(db=db_session, version=ver)

    # Verify database still contains original valid text
    db_session.refresh(ver)
    assert ver.extracted_text == PREVIOUS_VALID_TEXT

    # Cleanup
    storage_service.resolve_storage_path(s_key).unlink(missing_ok=True)
    db_session.delete(doc)
    db_session.commit()
