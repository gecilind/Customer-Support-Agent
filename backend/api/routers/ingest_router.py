from fastapi import APIRouter, Depends, File, UploadFile

from api.controllers.ingest_controller import IngestController
from api.dependencies import get_ingest_controller
from schemas.ingestion import IngestManualResponse


router = APIRouter(tags=["ingestion"])


@router.post("/ingest-manual", response_model=IngestManualResponse)
async def ingest_manual(
    file: UploadFile = File(...),
    controller: IngestController = Depends(get_ingest_controller),
) -> IngestManualResponse:
    return await controller.ingest_manual(file)
