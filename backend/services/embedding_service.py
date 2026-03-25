from openai import AsyncOpenAI

from core.exceptions import IngestionError


class EmbeddingService:
    def __init__(self, *, openai_api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=openai_api_key)

    async def generate(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
        except Exception as exc:  # noqa: BLE001
            raise IngestionError(f"Embedding generation failed: {exc}") from exc

        try:
            embeddings = [item.embedding for item in response.data]
        except Exception as exc:  # noqa: BLE001
            raise IngestionError(f"Embedding response parsing failed: {exc}") from exc

        if len(embeddings) != len(texts):
            raise IngestionError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(embeddings)}"
            )

        for i, emb in enumerate(embeddings):
            if len(emb) != 1536:
                raise IngestionError(
                    f"Embedding dimension mismatch at index {i}: expected 1536, got {len(emb)}"
                )

        return embeddings

