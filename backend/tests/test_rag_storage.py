from uuid import uuid4

import httpx
import pytest

from app.rag.storage import PrivateStorage, StorageError, object_key


def test_private_storage_requests_are_bounded_and_authenticated():
    key = object_key(uuid4(), uuid4(), uuid4())
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=b"source")
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        storage = PrivateStorage(
            "https://example-project.supabase.co", "test-service-key", "rag-private", client=client
        )
        storage.put(key, b"source", "text/plain")
        assert storage.get(key) == b"source"
        storage.delete(key)
    assert [request.method for request in requests] == ["POST", "GET", "DELETE"]
    assert requests[0].url.path == f"/storage/v1/object/rag-private/{key}"
    assert requests[1].url.path == f"/storage/v1/object/authenticated/rag-private/{key}"
    assert all(
        request.headers["authorization"] == "Bearer test-service-key" for request in requests
    )


def test_storage_rejects_invalid_config_paths_and_oversize():
    with pytest.raises(ValueError):
        PrivateStorage("http://localhost", "secret", "rag-private")
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        storage = PrivateStorage(
            "https://example-project.supabase.co", "secret", "rag-private", client=client
        )
        with pytest.raises(ValueError):
            storage.get("../other-bucket/file")
        with pytest.raises(StorageError):
            storage.put(
                object_key(uuid4(), uuid4(), uuid4()), b"x" * (2 * 1024 * 1024 + 1), "text/plain"
            )


def test_missing_private_object_can_be_deleted_again():
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(404))) as client:
        storage = PrivateStorage(
            "https://example-project.supabase.co", "secret", "rag-private", client=client
        )
        storage.delete(object_key(uuid4(), uuid4(), uuid4()))
