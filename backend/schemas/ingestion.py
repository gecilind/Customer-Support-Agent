from pydantic import BaseModel


class IngestManualResponse(BaseModel):
    source: str
    chunks_saved: int
    category: str
