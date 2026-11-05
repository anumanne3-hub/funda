from uuid import uuid4

from app.core.config import get_settings


def _register(client, email):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-test-password"},
    ).raise_for_status()
    return {"X-CSRF-Token": client.get("/api/v1/auth/csrf").json()["csrf_token"]}


def test_source_and_job_are_owner_scoped(client, monkeypatch):
    url = "https://example.com/allowed"
    monkeypatch.setattr(get_settings(), "rag_allowed_source_urls", [url])
    alice_headers = _register(client, "alice-rag@example.com")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Research"}, headers=alice_headers
    ).json()["id"]
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/sources",
            json={"url": "https://example.com/other", "title": "Other"},
            headers=alice_headers,
        ).status_code
        == 422
    )
    created = client.post(
        f"/api/v1/projects/{project_id}/sources",
        json={"url": url, "title": "Allowed"},
        headers=alice_headers,
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    assert len(client.get(f"/api/v1/projects/{project_id}/sources").json()) == 1
    key = str(uuid4())
    sync_headers = {**alice_headers, "Idempotency-Key": key}
    assert (
        client.post(f"/api/v1/documents/{document_id}/sync", headers=alice_headers).status_code
        == 422
    )
    first = client.post(f"/api/v1/documents/{document_id}/sync", headers=sync_headers)
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "queued"
    assert (
        client.post(f"/api/v1/documents/{document_id}/sync", headers=sync_headers).json()["id"]
        == first.json()["id"]
    )
    job_id = first.json()["id"]
    jobs = client.get(f"/api/v1/projects/{project_id}/ingestion-jobs")
    assert jobs.status_code == 200
    assert [row["id"] for row in jobs.json()] == [job_id]

    client.post("/api/v1/auth/logout", headers=alice_headers).raise_for_status()
    bob_headers = _register(client, "bob-rag@example.com")
    assert client.get(f"/api/v1/projects/{project_id}/sources").status_code == 404
    assert client.get(f"/api/v1/projects/{project_id}/ingestion-jobs").status_code == 404
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert client.get(f"/api/v1/ingestion-jobs/{job_id}").status_code == 404
    assert (
        client.post(f"/api/v1/documents/{document_id}/sync", headers=bob_headers).status_code == 404
    )
    assert client.delete(f"/api/v1/documents/{document_id}", headers=bob_headers).status_code == 404

    client.post("/api/v1/auth/logout", headers=bob_headers).raise_for_status()
    alice_headers = _register(client, "alice-rag-new@example.com")
    assert client.get(f"/api/v1/ingestion-jobs/{job_id}").status_code == 404


def test_same_website_can_be_added_to_another_project_or_after_deletion(client, monkeypatch):
    url = "https://example.com/shared"
    monkeypatch.setattr(get_settings(), "rag_allowed_source_urls", [url])
    headers = _register(client, "source-scope@example.com")
    first_project = client.post("/api/v1/projects", json={"name": "First"}, headers=headers).json()[
        "id"
    ]
    second_project = client.post(
        "/api/v1/projects", json={"name": "Second"}, headers=headers
    ).json()["id"]
    payload = {"url": url, "title": "Shared page"}
    first = client.post(f"/api/v1/projects/{first_project}/sources", json=payload, headers=headers)
    assert first.status_code == 201
    assert (
        client.post(
            f"/api/v1/projects/{first_project}/sources", json=payload, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/projects/{second_project}/sources", json=payload, headers=headers
        ).status_code
        == 201
    )
    client.delete(f"/api/v1/documents/{first.json()['id']}", headers=headers).raise_for_status()
    assert (
        client.post(
            f"/api/v1/projects/{first_project}/sources", json=payload, headers=headers
        ).status_code
        == 201
    )
