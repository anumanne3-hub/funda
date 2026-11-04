import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect

from app.db.base import Base
from app.models import chat  # noqa: F401


def test_postgres_sql_migrations_preserve_data_and_match_models():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("SQL migrations require disposable PostgreSQL TEST_DATABASE_URL")
    if not url.rsplit("/", 1)[-1].startswith("funda_test_"):
        raise RuntimeError("Use a dedicated funda_test_* database")
    migrations = sorted((Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql"))
    session_id = uuid4()
    conversation_id = uuid4()
    message_id = uuid4()
    engine = create_engine(url)
    with engine.connect() as connection:
        transaction = connection.begin()
        db = connection.connection.driver_connection
        try:
            db.execute(migrations[0].read_text(), prepare=False)
            db.execute(
                "INSERT INTO anonymous_sessions (id, token_hash, expires_at) "
                "VALUES (%s, %s, now() + interval '1 day')",
                (session_id, "migration-test"),
            )
            db.execute(
                "INSERT INTO conversations (id, anonymous_session_id, title) VALUES (%s, %s, %s)",
                (conversation_id, session_id, "Before accounts"),
            )
            db.execute(
                "INSERT INTO messages "
                "(id, conversation_id, sequence_number, role, content, status) "
                "VALUES (%s, %s, 1, 'user', 'Preserved text', 'completed')",
                (message_id, conversation_id),
            )
            for migration in migrations[1:]:
                db.execute(migration.read_text(), prepare=False)
            assert db.execute("SELECT id FROM anonymous_sessions").fetchone() == (session_id,)
            assert db.execute(
                "SELECT version_number, content FROM message_versions WHERE message_id = %s",
                (message_id,),
            ).fetchone() == (1, "Preserved text")
            schema = inspect(connection)
            for table in Base.metadata.sorted_tables:
                columns = {column["name"]: column for column in schema.get_columns(table.name)}
                expected_columns = set(table.columns.keys())
                if table.name == "document_chunks":
                    expected_columns.add("embedding")
                assert set(columns) == expected_columns
                for column in table.columns:
                    assert columns[column.name]["nullable"] == column.nullable
                    assert str(columns[column.name]["type"].compile(dialect=engine.dialect)) == str(
                        column.type.compile(dialect=engine.dialect)
                    )
                assert set(schema.get_pk_constraint(table.name)["constrained_columns"]) == {
                    column.name for column in table.primary_key
                }
                assert {index["name"] for index in schema.get_indexes(table.name)} >= {
                    index.name for index in table.indexes
                }
            assert db.execute(
                "SELECT count(*) FROM pg_class WHERE relname IN "
                "('anonymous_sessions','conversations','messages','chat_requests',"
                "'limit_buckets','users','account_sessions','projects',"
                "'message_versions','message_feedback','regeneration_requests',"
                "'documents','document_versions','document_chunks','ingestion_jobs',"
                "'message_citations','storage_deletions') "
                "AND relnamespace = 'public'::regnamespace "
                "AND relrowsecurity"
            ).fetchone() == (17,)
        finally:
            transaction.rollback()
    engine.dispose()


def test_first_session_against_sql_migrations(monkeypatch):
    """Exercise the actual HTTP path against SQL migrations, not create_all."""
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_settings
    from app.db.session import get_db
    from app.main import app
    from app.models import AnonymousSession
    from app.models.chat import LimitBucket

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("SQL migrations require disposable PostgreSQL TEST_DATABASE_URL")
    if not url.rsplit("/", 1)[-1].startswith("funda_test_"):
        raise RuntimeError("Use a dedicated funda_test_* database")
    migrations = sorted((Path(__file__).resolve().parents[2] / "supabase/migrations").glob("*.sql"))
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            connection.begin()  # Closing the connection rolls back migrations and writes.
            for migration in migrations:
                connection.connection.driver_connection.execute(
                    migration.read_text(), prepare=False
                )
            factory = sessionmaker(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )
            monkeypatch.setattr(app.state, "session_factory", factory)

            def migrated_db():
                with factory() as db:
                    yield db

            app.dependency_overrides[get_db] = migrated_db
            try:
                with TestClient(app, base_url="https://testserver") as client:
                    assert client.get("/ready").status_code == 200
                    with factory() as db:
                        assert db.scalar(select(func.count()).select_from(AnonymousSession)) == 0
                        assert db.scalar(select(func.count()).select_from(LimitBucket)) == 0
                    origin = get_settings().frontend_origins[0]
                    response = client.post("/api/v1/anonymous-session", headers={"origin": origin})
                    assert response.status_code == 200, response.text
                    assert response.headers["access-control-allow-origin"] == origin
                    assert client.cookies.get(get_settings().session_cookie_name)
                    second = client.post("/api/v1/anonymous-session", headers={"origin": origin})
                    assert second.json()["id"] == response.json()["id"]
                    with factory() as db:
                        assert db.scalar(select(func.count()).select_from(AnonymousSession)) == 1
            finally:
                app.dependency_overrides.pop(get_db, None)
    finally:
        engine.dispose()
