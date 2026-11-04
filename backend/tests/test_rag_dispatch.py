from uuid import uuid4

import httpx

from app.core.config import Settings, get_settings
from app.rag.dispatch import dispatch_job


def test_dispatch_uses_fixed_github_endpoint_and_keeps_failures_queued():
    job_id = uuid4()
    settings = Settings(
        rag_dispatch_repository="owner/repo",
        rag_dispatch_ref="main",
        rag_dispatch_token="test-token",
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert not dispatch_job(job_id, settings, client=client)
        assert requests[0].url == httpx.URL(
            "https://api.github.com/repos/owner/repo/actions/workflows/rag-ingest.yml/dispatches"
        )
        assert requests[0].headers["authorization"] == "Bearer test-token"
        assert requests[0].read() == (
            b'{"ref":"main","inputs":{"job_id":"' + str(job_id).encode() + b'"}}'
        )
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(204))) as client:
        assert dispatch_job(job_id, settings, client=client)
    settings.rag_dispatch_repository = "other/../path"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert not dispatch_job(job_id, settings, client=client)
    assert len(requests) == 1


def test_sync_replay_can_redispatch_queued_job(client, monkeypatch):
    from app.api import documents

    url = "https://example.com/dispatch-test"
    monkeypatch.setattr(get_settings(), "rag_allowed_source_urls", [url])
    calls = []
    monkeypatch.setattr(documents, "dispatch_job", lambda job_id, _settings: calls.append(job_id))
    client.post(
        "/api/v1/auth/register",
        json={"email": "dispatch@example.com", "password": "a-long-test-password"},
    ).raise_for_status()
    headers = {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}
    project_id = client.post("/api/v1/projects", json={"name": "P"}, headers=headers).json()["id"]
    document_id = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"url": url, "title": "Source"},
        headers=headers,
    ).json()["id"]
    sync_headers = {**headers, "Idempotency-Key": str(uuid4())}
    first = client.post(f"/api/v1/documents/{document_id}/sync", headers=sync_headers)
    replay = client.post(f"/api/v1/documents/{document_id}/sync", headers=sync_headers)
    assert first.json()["id"] == replay.json()["id"]
    assert len(calls) == 2
