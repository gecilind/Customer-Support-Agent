from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.manual import Manual


class ManualSourceRow:
    """Lightweight container for a grouped source row."""

    def __init__(self, source: str, category: str, chunk_count: int, ingested_at: datetime) -> None:
        self.source = source
        self.category = category
        self.chunk_count = chunk_count
        self.ingested_at = ingested_at


class ManualRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sources(self) -> list[ManualSourceRow]:
        stmt = (
            select(
                Manual.source,
                Manual.category,
                func.count(Manual.id).label("chunk_count"),
                func.min(Manual.created_at).label("ingested_at"),
            )
            .group_by(Manual.source, Manual.category)
            .order_by(func.min(Manual.created_at).desc())
        )
        result = await self.session.execute(stmt)
        return [
            ManualSourceRow(
                source=row.source,
                category=row.category,
                chunk_count=row.chunk_count,
                ingested_at=row.ingested_at,
            )
            for row in result.all()
        ]

    async def save_chunks(
        self,
        *,
        source: str,
        category: str,
        sections_and_chunks: list[tuple[str, int, str, list[float]]],
    ) -> int:
        rows = [
            Manual(
                source=source,
                section=section,
                content=content,
                category=category,
                chunk_index=chunk_index,
                embedding=embedding,
            )
            for section, chunk_index, content, embedding in sections_and_chunks
        ]

        self.session.add_all(rows)
        await self.session.commit()
        return len(rows)

    async def delete_by_source(self, *, source: str) -> int:
        stmt = delete(Manual).where(Manual.source == source)
        result = await self.session.execute(stmt)
        await self.session.commit()
        # SQLAlchemy may not populate rowcount for all DB drivers, but asyncpg typically does.
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_by_source_prefix(self, *, prefix: str) -> int:
        stmt = delete(Manual).where(Manual.source.like(f"{prefix}%"))
        result = await self.session.execute(stmt)
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
