from fastapi import HTTPException, UploadFile

from core.exceptions import IngestionError
from schemas.ingestion import IngestManualResponse
from services.file_extraction_service import extract_text, is_pdf_bytes
from services.ingestion_service import IngestionService


class IngestController:
    def __init__(self, ingestion_service: IngestionService) -> None:
        self.ingestion_service = ingestion_service

    async def ingest_manual(self, file: UploadFile) -> IngestManualResponse:
        raw_bytes = await file.read()
        source_name = (file.filename or "").strip()
        if not source_name:
            source_name = "upload.pdf" if is_pdf_bytes(raw_bytes) else ""
        if not source_name:
            raise HTTPException(status_code=400, detail="Filename is required.")

        try:
            raw_text = extract_text(raw_bytes, source_name)
        except IngestionError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc

        lower = source_name.lower()
        ext = lower.rsplit(".", 1)[-1] if "." in lower else ""
        file_type = "pdf" if ext == "pdf" or is_pdf_bytes(raw_bytes) else "txt"

        chunks_saved = await self.ingestion_service.ingest_text(
            source=source_name,
            raw_text=raw_text,
            category="general",
            file_type=file_type,
        )
        return IngestManualResponse(source=source_name, chunks_saved=chunks_saved, category="general")
