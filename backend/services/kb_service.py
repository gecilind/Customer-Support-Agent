from repositories.kb_repository import KBRepository
from schemas.kb import KBSearchResult
from services.embedding_service import EmbeddingService


class KBService:
    def __init__(self, embedding_service: EmbeddingService, kb_repository: KBRepository) -> None:
        self.embedding_service = embedding_service
        self.kb_repository = kb_repository

    async def search(self, query: str, *, limit: int = 5) -> list[KBSearchResult]:
        vectors = await self.embedding_service.generate([query])
        if not vectors:
            return []
        embedding = vectors[0]
        rows = await self.kb_repository.search(embedding, limit=limit)
        return [
            KBSearchResult(
                content=r["content"],
                source=r["source"],
                section=r["section"],
                similarity=r["similarity"],
                chunk_index=r["chunk_index"],
            )
            for r in rows
        ]
