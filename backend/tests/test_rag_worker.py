from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.main import app
from app.rag.embeddings import EmbeddingError
from app.rag.storage import StorageError
from app.rag.worker import ProcessingError, run_job


@pytest.mark.parametrize(
    ("failure", "code", "status"),
    [
        (ProcessingError("EXTRACT_FAILED"), "EXTRACT_FAILED", "failed"),
        (EmbeddingError("provider error"), "EMBEDDING_FAILED", "queued"),
        (StorageError("storage error"), "STORAGE_FAILED", "queued"),
        (SQLAlchemyError("database error"), "DATABASE_FAILED", "queued"),
    ],
)
@pytest.mark.asyncio
async def test_worker_runs_requested_job_and_persists_failure(
    client, monkeypatch, failure, code, status
):
    url = "https://example.com/worker"
    monkeypatch.setattr(get_settings(), "rag_allowed_source_urls", [url])
    client.post(
        "/api/v1/auth/register",
        json={"email": "worker-run@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    project_id = client.post("/api/v1/projects", json={"name": "P"}, headers=headers).json()["id"]
    document_id = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"url": url, "title": "Source"},
        headers=headers,
    ).json()["id"]
    job_id = UUID(
        client.post(
            f"/api/v1/documents/{document_id}/sync",
            headers={**headers, "Idempotency-Key": str(uuid4())},
        ).json()["id"]
    )
    seen = []

    async def fail(job):
        seen.append(job.id)
        raise failure

    assert not await run_job(uuid4(), app.state.session_factory, fail)
    assert await run_job(job_id, app.state.session_factory, fail)
    assert seen == [job_id]
    result = client.get(f"/api/v1/ingestion-jobs/{job_id}").json()
    assert result["status"] == status
    assert result["error_code"] == code
