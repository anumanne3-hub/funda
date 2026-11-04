from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.rag.run_worker import run


@pytest.mark.asyncio
async def test_worker_keeps_job_queued_when_deployment_is_incomplete(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", "sqlite://")
    monkeypatch.setattr(settings, "rag_storage_url", None)
    monkeypatch.setattr(settings, "rag_embedding_api_key", None)
    assert await run(uuid4()) == 2
