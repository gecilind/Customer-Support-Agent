from sqlalchemy.ext.asyncio import AsyncSession

from models.manual import Manual


class ManualRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
