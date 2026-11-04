import json

import httpx
import pytest

from app.rag.embeddings import EmbeddingError, NvidiaEmbeddings


@pytest.mark.asyncio
async def test_embedding_modes_order_and_shape():
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [float(index), 1.0]}
                    for index in reversed(range(len(payload["input"])))
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = NvidiaEmbeddings("test-key", dimensions=2, client=client)
        assert await provider.embed_documents(["first", "second"]) == [[0.0, 1.0], [1.0, 1.0]]
        assert await provider.embed_query("question") == [0.0, 1.0]
    assert [request["input_type"] for request in requests] == ["passage", "query"]
    assert all(request["truncate"] == "NONE" for request in requests)


@pytest.mark.asyncio
async def test_embedding_rejects_bad_response():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})
        )
    ) as client:
        provider = NvidiaEmbeddings("test-key", dimensions=2, client=client)
        with pytest.raises(EmbeddingError):
            await provider.embed_query("question")
        with pytest.raises(EmbeddingError):
            await provider.embed_query(" ")
