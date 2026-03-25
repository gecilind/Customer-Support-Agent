from fastapi import HTTPException, UploadFile

from core.exceptions import IngestionError
from schemas.ingestion import IngestManualResponse
from services.file_extraction_service import extract_text
from services.ingestion_service import IngestionService


class IngestController:
    def __init__(self, ingestion_service: IngestionService) -> None:
        self.ingestion_service = ingestion_service

    async def ingest_manual(self, file: UploadFile) -> IngestManualResponse:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required.")

        raw_bytes = await file.read()
        try:
            raw_text = extract_text(raw_bytes, file.filename)
        except IngestionError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc

        lower = file.filename.lower()
        ext = lower.rsplit(".", 1)[-1] if "." in lower else ""
        file_type = "pdf" if ext == "pdf" else "txt"

        chunks_saved = await self.ingestion_service.ingest_text(
            source=file.filename,
            raw_text=raw_text,
            category="general",
            file_type=file_type,
        )
        return IngestManualResponse(source=file.filename, chunks_saved=chunks_saved, category="general")
