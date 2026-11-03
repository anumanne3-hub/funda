import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AccountSession, AnonymousSession, User

ACCOUNT_COOKIE = "genai_account"
CSRF_COOKIE = "genai_csrf"


def find_account_session(db: Session, token: str | None) -> AccountSession | None:
    if not token:
        return None
    record = db.scalar(select(AccountSession).where(AccountSession.token_hash == hash_token(token)))
    if record is None or record.revoked_at is not None:
        return None
    expiry = record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return record if expiry > datetime.now(UTC) else None


def account_identity(request: Request, db: Session, *, csrf: bool = False) -> User:
    session = find_account_session(db, request.cookies.get(ACCOUNT_COOKIE))
    if session is None:
        raise HTTPException(status_code=401, detail="Account session required")
    if csrf:
        supplied = request.headers.get("X-CSRF-Token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if (
            not supplied
            or not cookie
            or not hmac.compare_digest(supplied, cookie)
            or not hmac.compare_digest(hash_token(supplied), session.csrf_hash)
        ):
            raise HTTPException(status_code=403, detail="CSRF token invalid")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account session required")
    return user


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


def owner_identity(request: Request, db: Session, *, csrf: bool = False) -> tuple[str, UUID]:
    account = find_account_session(db, request.cookies.get(ACCOUNT_COOKIE))
    if account is not None:
        user = account_identity(request, db, csrf=csrf)
        return "user_id", user.id
    anonymous = require_http_session(request, db)
    return "anonymous_session_id", anonymous.id


def websocket_owner(websocket: WebSocket, db: Session) -> tuple[str, UUID] | None:
    account = find_account_session(db, websocket.cookies.get(ACCOUNT_COOKIE))
    if account is not None:
        return "user_id", account.user_id
    anonymous = websocket_session(websocket, db)
    return ("anonymous_session_id", anonymous.id) if anonymous else None
