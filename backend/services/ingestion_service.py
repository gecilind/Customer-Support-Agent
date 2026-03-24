from repositories.manual_repository import ManualRepository


class IngestionService:
    def __init__(self, manual_repository: ManualRepository) -> None:
        self.manual_repository = manual_repository

    async def ingest_text(self, *, source: str, raw_text: str, category: str = "general") -> int:
        chunks = self._chunk_text(raw_text)
        sections_and_chunks = [(f"Section {index + 1}", index, chunk) for index, chunk in enumerate(chunks)]
        return await self.manual_repository.save_chunks(
            source=source,
            category=category,
            sections_and_chunks=sections_and_chunks,
        )

    def _chunk_text(self, text: str, max_chars: int = 1200) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []

        split_by_paragraph = [part.strip() for part in normalized.split("\n\n") if part.strip()]
        chunks: list[str] = []
        for para in split_by_paragraph:
            if len(para) <= max_chars:
                chunks.append(para)
                continue

            start = 0
            while start < len(para):
                chunks.append(para[start : start + max_chars].strip())
                start += max_chars
        return [chunk for chunk in chunks if chunk]
