from fastapi import HTTPException, UploadFile

from schemas.ingestion import IngestManualResponse
from services.ingestion_service import IngestionService


class IngestController:
    def __init__(self, ingestion_service: IngestionService) -> None:
        self.ingestion_service = ingestion_service

    async def ingest_manual(self, file: UploadFile) -> IngestManualResponse:
        if not file.filename or not file.filename.lower().endswith(".txt"):
            raise HTTPException(status_code=400, detail="Only .txt files are supported for now.")

        raw_bytes = await file.read()
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Uploaded file must be UTF-8 text.") from exc

        chunks_saved = await self.ingestion_service.ingest_text(
            source=file.filename,
            raw_text=raw_text,
            category="general",
        )
        return IngestManualResponse(source=file.filename, chunks_saved=chunks_saved, category="general")
