from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.manual import Manual


class KBRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, embedding: list[float], limit: int = 5) -> list[dict]:
        """pgvector similarity via pgvector.sqlalchemy — order by cosine distance, similarity = 1 - distance."""
        distance_expr = Manual.embedding.cosine_distance(embedding)
        similarity_expr = (literal(1) - distance_expr).label("similarity")

        stmt = (
            select(Manual, similarity_expr)
            .order_by(distance_expr)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            {
                "content": m.content,
                "source": m.source,
                "section": m.section,
                "similarity": float(sim),
                "chunk_index": m.chunk_index,
            }
            for m, sim in result.all()
        ]
