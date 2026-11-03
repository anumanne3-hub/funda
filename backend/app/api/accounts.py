from datetime import UTC, datetime
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    ACCOUNT_COOKIE,
    CSRF_COOKIE,
    account_identity,
    find_account_session,
    find_session,
    hash_token,
    new_session_token,
    session_expiry,
)
from app.db.session import get_db
from app.models import AccountSession, Conversation, Project, User

router = APIRouter()
hasher = PasswordHasher()


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise HTTPException(status_code=422, detail="Invalid email")
    return value


def issue_session(response: Response, db: Session, user: User) -> None:
    token, csrf = new_session_token(), new_session_token()
    db.add(
        AccountSession(
            user_id=user.id,
            token_hash=hash_token(token),
            csrf_hash=hash_token(csrf),
            expires_at=session_expiry(),
        )
    )
    db.commit()
    settings = get_settings()
    response.set_cookie(
        ACCOUNT_COOKIE,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=settings.session_ttl_days * 86400,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


@router.post("/auth/register", response_model=AccountRead, status_code=201)
def register(payload: Credentials, response: Response, db: Session = Depends(get_db)) -> User:
    user = User(email=normalize_email(payload.email), password_hash=hasher.hash(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Account already exists") from None
    issue_session(response, db, user)
    return user


@router.post("/auth/login", response_model=AccountRead)
def login(payload: Credentials, response: Response, db: Session = Depends(get_db)) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(payload.email)))
    try:
        if user is None or not hasher.verify(user.password_hash, payload.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(status_code=401, detail="Invalid credentials") from None
    issue_session(response, db, user)
    return user


@router.get("/auth/me", response_model=AccountRead)
def me(request: Request, db: Session = Depends(get_db)) -> User:
    return account_identity(request, db)


@router.get("/auth/csrf")
def csrf_token(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    account_identity(request, db)
    token = request.cookies.get(CSRF_COOKIE, "")
    session = find_account_session(db, request.cookies.get(ACCOUNT_COOKIE))
    if session is None or not token or hash_token(token) != session.csrf_hash:
        raise HTTPException(status_code=403, detail="CSRF token invalid")
    return {"csrf_token": token}


@router.post("/auth/refresh", response_model=AccountRead)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(ACCOUNT_COOKIE)
    if token:
        prior = db.scalar(
            select(AccountSession).where(AccountSession.token_hash == hash_token(token))
        )
        if prior is not None and prior.revoked_at is not None:
            db.execute(
                update(AccountSession)
                .where(AccountSession.user_id == prior.user_id, AccountSession.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
            db.commit()
            raise HTTPException(status_code=401, detail="Session reuse detected")
    user = account_identity(request, db, csrf=True)
    session = find_account_session(db, request.cookies.get(ACCOUNT_COOKIE))
    assert session is not None
    session.revoked_at = datetime.now(UTC)
    db.flush()
    issue_session(response, db, user)
    return user


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    account_identity(request, db, csrf=True)
    session = find_account_session(db, request.cookies.get(ACCOUNT_COOKIE))
    assert session is not None
    session.revoked_at = datetime.now(UTC)
    db.commit()
    response.delete_cookie(ACCOUNT_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


@router.post("/auth/logout-all", status_code=204)
def logout_all(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    user = account_identity(request, db, csrf=True)
    db.execute(
        update(AccountSession)
        .where(AccountSession.user_id == user.id, AccountSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    db.commit()
    response.delete_cookie(ACCOUNT_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectInput, request: Request, db: Session = Depends(get_db)
) -> Project:
    user = account_identity(request, db, csrf=True)
    project = Project(user_id=user.id, name=payload.name.strip())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(request: Request, db: Session = Depends(get_db)) -> list[Project]:
    user = account_identity(request, db)
    return list(
        db.scalars(
            select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
        )
    )


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def rename_project(
    project_id: UUID, payload: ProjectInput, request: Request, db: Session = Depends(get_db)
) -> Project:
    user = account_identity(request, db, csrf=True)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.name = payload.name.strip()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: UUID, request: Request, db: Session = Depends(get_db)) -> None:
    user = account_identity(request, db, csrf=True)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()


@router.post("/auth/claim-anonymous")
def claim_anonymous(request: Request, db: Session = Depends(get_db)) -> dict[str, int]:
    user = account_identity(request, db, csrf=True)
    anonymous = find_session(db, request.cookies.get(get_settings().session_cookie_name))
    if anonymous is None:
        raise HTTPException(status_code=404, detail="Anonymous session not found")
    conversations = list(
        db.scalars(select(Conversation.id).where(Conversation.anonymous_session_id == anonymous.id))
    )
    db.execute(
        update(Conversation)
        .where(Conversation.anonymous_session_id == anonymous.id)
        .values(anonymous_session_id=None, user_id=user.id)
    )
    db.commit()
    return {"claimed": len(conversations)}


@router.post("/auth/discard-anonymous", status_code=204)
def discard_anonymous(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    account_identity(request, db, csrf=True)
    anonymous = find_session(db, request.cookies.get(get_settings().session_cookie_name))
    if anonymous is None:
        raise HTTPException(status_code=404, detail="Anonymous session not found")
    db.delete(anonymous)
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name)


@router.delete("/auth/account", status_code=204)
def delete_account(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    user = account_identity(request, db, csrf=True)
    db.delete(user)
    db.commit()
    response.delete_cookie(ACCOUNT_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
