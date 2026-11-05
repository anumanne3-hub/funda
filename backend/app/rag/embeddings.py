"""NVIDIA hosted trial embedding adapter for development evaluation."""

import math

import httpx

from app.rag.contracts import EmbeddingProvider

ENDPOINT = "https://integrate.api.nvidia.com/v1/embeddings"
MAX_BATCH = 16


class EmbeddingError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NvidiaEmbeddings(EmbeddingProvider):
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "nvidia/nemotron-3.5-embed-1b",
        dimensions: int = 2048,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key or not model or dimensions < 1 or dimensions > 2048:
            raise ValueError("Invalid embedding configuration")
        self.model = model
        self.dimensions = dimensions
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=30.0, trust_env=False)
        self.owned_client = client is None

    async def close(self) -> None:
        if self.owned_client:
            await self.client.aclose()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            vectors.extend(await self._embed(texts[start : start + MAX_BATCH], "passage"))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "query"))[0]

    async def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if not texts or any(not text.strip() or len(text) > 1200 for text in texts):
            raise EmbeddingError("Embedding input is empty or too long")
        try:
            response = await self.client.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "input": texts,
                    "input_type": input_type,
                    "truncate": "NONE",
                },
            )
            response.raise_for_status()
            data = response.json()["data"]
            if not isinstance(data, list) or len(data) != len(texts):
                raise ValueError("Embedding count mismatch")
            ordered: list[list[float] | None] = [None] * len(texts)
            for item in data:
                index = item["index"]
                values = item["embedding"]
                if (
                    not isinstance(index, int)
                    or isinstance(index, bool)
                    or index < 0
                    or index >= len(texts)
                    or ordered[index] is not None
                    or not isinstance(values, list)
                    or len(values) != self.dimensions
                ):
                    raise ValueError("Invalid embedding response")
                vector = [float(value) for value in values]
                if not all(math.isfinite(value) for value in vector):
                    raise ValueError("Invalid embedding values")
                ordered[index] = vector
            if any(vector is None for vector in ordered):
                raise ValueError("Missing embedding")
            return [vector for vector in ordered if vector is not None]
        except httpx.HTTPStatusError as exc:
            raise EmbeddingError(
                "Embedding provider rejected request", status_code=exc.response.status_code
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError("Embedding provider unavailable") from exc
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise EmbeddingError("Embedding response invalid") from exc
