"""Extract plain text from uploaded manual files (.txt, .pdf)."""

from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader

from core.exceptions import IngestionError


def _normalize_extracted_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Detect type from filename extension and return UTF-8 text ready for chunking.
    Raises IngestionError on unsupported types or extraction failure.
    """
    if not filename or not filename.strip():
        raise IngestionError("Filename is required.")

    name = filename.strip()
    lower = name.lower()
    if lower.endswith(".txt"):
        try:
            raw = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionError("Uploaded file must be UTF-8 text.") from exc
        return _normalize_extracted_text(raw)

    if lower.endswith(".pdf"):
        if not file_bytes:
            raise IngestionError(
                "PDF appears to be scanned/image-based. Text extraction failed."
            )
        try:
            reader = PdfReader(BytesIO(file_bytes))
        except Exception as exc:  # noqa: BLE001 — surface as ingestion error
            raise IngestionError("Failed to read PDF file.") from exc

        page_texts: list[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text()
            except Exception as exc:  # noqa: BLE001
                raise IngestionError("Failed to extract text from PDF.") from exc
            page_texts.append(t or "")

        combined = "\n\n".join(page_texts)
        normalized = _normalize_extracted_text(combined)
        if not normalized:
            raise IngestionError(
                "PDF appears to be scanned/image-based. Text extraction failed."
            )
        return normalized

    raise IngestionError("Unsupported file type. Accepted: .txt, .pdf")
