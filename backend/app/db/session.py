from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine_options: dict[str, object] = {"pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    engine_options["pool_size"] = settings.database_pool_size
    engine_options["max_overflow"] = 0
    engine_options["pool_timeout"] = 10

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session]:
    with SessionLocal() as session:
        yield session
