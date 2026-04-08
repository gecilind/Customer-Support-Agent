import logging
import time

from repositories.kb_repository import KBRepository
from schemas.kb import KBSearchResult
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class KBService:
    def __init__(self, embedding_service: EmbeddingService, kb_repository: KBRepository) -> None:
        self.embedding_service = embedding_service
        self.kb_repository = kb_repository

    async def search(self, query: str, *, limit: int = 5) -> list[KBSearchResult]:
        emb_t0 = time.perf_counter()
        vectors = await self.embedding_service.generate([query])
        emb_elapsed = time.perf_counter() - emb_t0
        logger.info("[KB] Embedding time: %.2fs", emb_elapsed)

        if not vectors:
            return []
        embedding = vectors[0]

        pg_t0 = time.perf_counter()
        rows = await self.kb_repository.search(embedding, limit=limit)
        pg_elapsed = time.perf_counter() - pg_t0
        logger.info("[KB] pgvector query time: %.2fs", pg_elapsed)
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
