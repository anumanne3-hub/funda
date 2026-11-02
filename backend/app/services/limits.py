"""Atomic, shared limits; reservations stay charged when provider usage is unknown."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.chat import LimitBucket


class RequestRejected(Exception):
    def __init__(self, code: str, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


def consume(db: Session, scope: str, amount: int, ceiling: int, seconds: int) -> None:
    now = datetime.now(UTC)
    window = int(now.timestamp()) // seconds
    key = f"{scope}:{window}"
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    db.execute(delete(LimitBucket).where(LimitBucket.expires_at < now))
    db.execute(
        insert(LimitBucket)
        .values(key=key, value=0, expires_at=now + timedelta(seconds=seconds * 2))
        .on_conflict_do_nothing(index_elements=["key"])
    )
    result = db.execute(
        update(LimitBucket)
        .where(LimitBucket.key == key, LimitBucket.value + amount <= ceiling)
        .values(value=LimitBucket.value + amount)
        .returning(LimitBucket.key)
    ).first()
    if result is None:
        raise RequestRejected("BUDGET_EXCEEDED" if scope == "budget" else "RATE_LIMITED", True)
