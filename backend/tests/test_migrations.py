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
            for migration in migrations[1:]:
                db.execute(migration.read_text(), prepare=False)
            assert db.execute("SELECT id FROM anonymous_sessions").fetchone() == (session_id,)
            schema = inspect(connection)
            for table in Base.metadata.sorted_tables:
                columns = {column["name"]: column for column in schema.get_columns(table.name)}
                assert set(columns) == set(table.columns.keys())
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
                "'limit_buckets') AND relnamespace = 'public'::regnamespace "
                "AND relrowsecurity"
            ).fetchone() == (5,)
        finally:
            transaction.rollback()
    engine.dispose()
