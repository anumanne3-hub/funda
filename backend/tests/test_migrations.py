from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings


def test_upgrade_downgrade_and_reopen(tmp_path: Path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    monkeypatch.setattr(get_settings(), "database_url", url)
    monkeypatch.setattr(get_settings(), "migration_database_url", None)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO limit_buckets (key, value, expires_at) "
                        "VALUES ('restart-test', 7, '2027-01-01')"))
    engine.dispose()
    reopened = create_engine(url)
    with reopened.connect() as db:
        assert db.scalar(text("SELECT value FROM limit_buckets WHERE key='restart-test'")) == 7
    reopened.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert {"messages", "chat_requests", "anonymous_sessions", "limit_buckets"}.issubset(
        inspect(engine).get_table_names())
    engine.dispose()
