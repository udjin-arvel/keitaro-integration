from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("KEITARO_API_URL", "https://tracker.test")
    monkeypatch.setenv("KEITARO_API_KEY", "test-key")
    monkeypatch.setenv("KEITARO_DOMAIN_ID", "9")
    monkeypatch.setenv("KEITARO_GROUP_ID", "3")
    monkeypatch.setenv("KEITARO_SOURCE_ID", "7")

    from config import get_settings
    from database import Base, get_engine, reset_engine

    get_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(bind=get_engine())

    from main import app

    with TestClient(app) as test_client:
        yield test_client

    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def db_session(client: TestClient) -> Generator[Session, None, None]:
    from database import get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
