import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AnonymousSession


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=get_settings().session_ttl_days)


def find_session(db: Session, token: str | None) -> AnonymousSession | None:
    if not token:
        return None
    record = db.scalar(
        select(AnonymousSession).where(AnonymousSession.token_hash == hash_token(token))
    )
    if record is None:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return record if expires_at > datetime.now(UTC) else None


def require_http_session(request: Request, db: Session) -> AnonymousSession:
    record = find_session(db, request.cookies.get(get_settings().session_cookie_name))
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Anonymous session required"
        )
    return record


def websocket_session(websocket: WebSocket, db: Session) -> AnonymousSession | None:
    return find_session(db, websocket.cookies.get(get_settings().session_cookie_name))
