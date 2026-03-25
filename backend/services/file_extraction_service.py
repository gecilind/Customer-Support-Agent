"""Extract plain text from uploaded manual files (.txt, .pdf)."""

from __future__ import annotations

import re
from io import BytesIO

import fitz  # PyMuPDF — robust text extraction for diverse PDF generators (CVs, Word export, etc.)
from pypdf import PdfReader

from core.exceptions import IngestionError


def is_pdf_bytes(data: bytes) -> bool:
    """
    Detect PDF by signature. Header is usually at offset 0, but some files prepend bytes
    (e.g. web downloads, tools) so we scan the first chunk for %PDF-.
    """
    if len(data) < 5:
        return False
    if data[:5] == b"%PDF-":
        return True
    return b"%PDF-" in data[:16384]


def _normalize_extracted_text(text: str) -> str:
    # PostgreSQL rejects U+0000 in text; PDF extractors often emit NULs between glyphs/fields.
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text_pymupdf(file_bytes: bytes) -> str:
    """PyMuPDF usually extracts more reliably than pypdf (Word/Canva CVs, etc.)."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        parts: list[str] = []
        for i in range(len(doc)):
            parts.append(doc[i].get_text() or "")
    finally:
        doc.close()
    return "\n\n".join(parts)


def _extract_pdf_text_pypdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    page_texts: list[str] = []
    for page in reader.pages:
        page_texts.append(page.extract_text() or "")
    return "\n\n".join(page_texts)


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Detect type from filename extension and return UTF-8 text ready for chunking.
    Raises IngestionError on unsupported types or extraction failure.
    """
    name = (filename or "").strip()
    lower = name.lower()

    # Prefer file content: many clients send PDFs without a .pdf filename (blob, "CV", etc.).
    treat_as_pdf = is_pdf_bytes(file_bytes) or lower.endswith(".pdf")
    treat_as_txt = lower.endswith(".txt") and not is_pdf_bytes(file_bytes)

    if treat_as_txt:
        try:
            raw = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionError("Uploaded file must be UTF-8 text.") from exc
        return _normalize_extracted_text(raw)

    if treat_as_pdf:
        if not file_bytes:
            raise IngestionError(
                "PDF appears to be scanned/image-based. Text extraction failed."
            )

        last_exc: Exception | None = None
        saw_extractor_without_error = False
        for extractor in (_extract_pdf_text_pymupdf, _extract_pdf_text_pypdf):
            try:
                combined = extractor(file_bytes)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            saw_extractor_without_error = True
            normalized = _normalize_extracted_text(combined)
            if normalized:
                return normalized

        if last_exc is not None and not saw_extractor_without_error:
            raise IngestionError(
                "Failed to read PDF file. It may be corrupted, encrypted, or unsupported."
            ) from last_exc
        raise IngestionError(
            "No text could be extracted from this PDF. If it is image-only (scanned), "
            "export a searchable PDF or add OCR; otherwise try re-saving from Word/Google Docs."
        )

    raise IngestionError("Unsupported file type. Accepted: .txt, .pdf")
