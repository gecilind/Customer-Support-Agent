from pydantic import BaseModel, Field


class KBSearchResult(BaseModel):
    content: str
    source: str
    section: str
    similarity: float
    chunk_index: int = Field(..., description="Chunk index within source document")
