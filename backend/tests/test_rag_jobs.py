from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.main import app
from app.rag.jobs import LEASE_SECONDS, MAX_ATTEMPTS, claim_job, finish_job, renew_lease


def test_claim_lease_retry_and_duplicate_delivery(client, monkeypatch):
    url = "https://example.com/worker-test"
    monkeypatch.setattr(get_settings(), "rag_allowed_source_urls", [url])
    client.post(
        "/api/v1/auth/register",
        json={"email": "worker-test@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
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
    start = datetime.now(UTC)
    factory = app.state.session_factory

    with factory() as db:
        first = claim_job(db, now=start)
        assert first is not None and first.id == job_id
        assert first.attempts == 1
        first_token = first.lease_token
        assert first_token is not None
    with factory() as db:
        assert claim_job(db, now=start + timedelta(seconds=1)) is None
    with factory() as db:
        assert renew_lease(db, job_id, first_token, now=start + timedelta(seconds=1))
    with factory() as db:
        assert claim_job(db, now=start + timedelta(seconds=LEASE_SECONDS)) is None
    with factory() as db:
        second = claim_job(db, now=start + timedelta(seconds=LEASE_SECONDS + 2))
        assert second is not None and second.attempts == 2
        second_token = second.lease_token
        assert second_token is not None and second_token != first_token
    with factory() as db:
        assert not finish_job(
            db, job_id, first_token, now=start + timedelta(seconds=LEASE_SECONDS + 3)
        )
    with factory() as db:
        assert finish_job(
            db,
            job_id,
            second_token,
            error_code="TEMPORARY",
            retryable=True,
            now=start + timedelta(seconds=LEASE_SECONDS + 3),
        )
    with factory() as db:
        third = claim_job(db, now=start + timedelta(seconds=LEASE_SECONDS + 4))
        assert third is not None and third.attempts == MAX_ATTEMPTS
        third_token = third.lease_token
        assert third_token is not None
    with factory() as db:
        assert claim_job(db, now=start + timedelta(seconds=LEASE_SECONDS * 2 + 5)) is None
    status = client.get(f"/api/v1/ingestion-jobs/{job_id}").json()
    assert status["status"] == "failed"
    assert status["error_code"] == "LEASE_EXPIRED"
    with factory() as db:
        assert not finish_job(db, job_id, third_token)
