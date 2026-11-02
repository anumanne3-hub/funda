import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.providers.llm import MockProvider


@pytest.fixture
def client() -> Generator[TestClient]:
    url = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    if url != "sqlite://" and "funda_test_" not in url.rsplit("/", 1)[-1]:
        raise RuntimeError("Tests require a dedicated database named funda_test_*")
    engine = create_engine(
        url,
        **(
            {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
            if url == "sqlite://"
            else {}
        ),
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def test_db() -> Generator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = test_db
    app.state.session_factory = factory
    app.state.llm_provider = MockProvider()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
