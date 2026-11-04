"""Server-side GitHub Actions dispatch. A failed request leaves the durable job queued."""

import logging
import re
from uuid import UUID

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)
WORKFLOW = "rag-ingest.yml"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def dispatch_job(job_id: UUID, settings: Settings, *, client: httpx.Client | None = None) -> bool:
    repository = settings.rag_dispatch_repository
    token = settings.rag_dispatch_token
    if not repository or not token:
        return False
    if not REPOSITORY_PATTERN.fullmatch(repository):
        logger.error(
            "invalid RAG dispatch repository", extra={"event": "rag.dispatch.config_error"}
        )
        return False
    owned_client = client is None
    if client is None:
        client = httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False)
    try:
        response = client.post(
            f"https://api.github.com/repos/{repository}/actions/workflows/{WORKFLOW}/dispatches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"ref": settings.rag_dispatch_ref, "inputs": {"job_id": str(job_id)}},
        )
        if response.status_code == 204:
            return True
        logger.warning(
            "RAG dispatch rejected",
            extra={"event": "rag.dispatch.rejected", "status_code": response.status_code},
        )
        return False
    except httpx.HTTPError:
        logger.warning("RAG dispatch unavailable", extra={"event": "rag.dispatch.unavailable"})
        return False
    finally:
        if owned_client:
            client.close()
