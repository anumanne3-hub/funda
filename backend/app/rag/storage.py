"""Private Supabase Storage access for trusted API and worker processes only."""

import re
from uuid import UUID

import httpx

MAX_OBJECT_BYTES = 2 * 1024 * 1024
PROJECT_URL = re.compile(r"^https://[a-z0-9-]+\.supabase\.co$")
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class StorageError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def object_key(user_id: UUID, document_id: UUID, version_id: UUID) -> str:
    return f"{user_id}/{document_id}/{version_id}"


class PrivateStorage:
    def __init__(
        self,
        project_url: str,
        service_key: str,
        bucket: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not PROJECT_URL.fullmatch(project_url) or not BUCKET_NAME.fullmatch(bucket):
            raise ValueError("Invalid Supabase Storage configuration")
        if not service_key:
            raise ValueError("Storage service key is required")
        self.base_url = f"{project_url}/storage/v1/object"
        self.bucket = bucket
        # Current Supabase secret keys are not JWTs and belong only in the apikey header.
        self.headers = {"apikey": service_key}
        if not service_key.startswith("sb_secret_"):
            self.headers["Authorization"] = f"Bearer {service_key}"
        self.client = client or httpx.Client(timeout=15.0, follow_redirects=False, trust_env=False)
        self.owned_client = client is None

    def close(self) -> None:
        if self.owned_client:
            self.client.close()

    def __enter__(self) -> "PrivateStorage":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _path(self, key: str) -> str:
        if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f-]{36}/[0-9a-f-]{36}", key):
            raise ValueError("Invalid object key")
        return f"{self.bucket}/{key}"

    def put(self, key: str, content: bytes, media_type: str) -> None:
        if len(content) > MAX_OBJECT_BYTES:
            raise StorageError("Object exceeds size limit")
        if media_type not in {"text/plain", "text/markdown", "text/html", "application/pdf"}:
            raise StorageError("Unsupported object type")
        try:
            response = self.client.post(
                f"{self.base_url}/{self._path(key)}",
                headers={**self.headers, "Content-Type": media_type},
                content=content,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            raise StorageError("Private object upload failed", status_code=status) from exc

    def get(self, key: str) -> bytes:
        try:
            with self.client.stream(
                "GET", f"{self.base_url}/authenticated/{self._path(key)}", headers=self.headers
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_OBJECT_BYTES:
                        raise StorageError("Object exceeds size limit")
                return bytes(body)
        except httpx.HTTPError as exc:
            raise StorageError("Private object download failed") from exc

    def delete(self, key: str) -> None:
        try:
            response = self.client.delete(
                f"{self.base_url}/{self._path(key)}", headers=self.headers
            )
            if response.status_code == 404:
                return  # Retry after an earlier deletion or interrupted database commit.
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError("Private object deletion failed") from exc
