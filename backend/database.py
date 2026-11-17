from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'campaigns.db').as_posix()}"


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return get_settings().database_url or DEFAULT_SQLITE_URL


@lru_cache
def get_engine() -> Engine:
    url = database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def reset_engine() -> None:
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def migrate_schema(engine: Engine) -> None:
    if not database_url().startswith("sqlite"):
        return
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(stream_offers)")).fetchall()
        columns = {row[1] for row in rows}
        if columns and "offer_name" not in columns:
            conn.execute(text("ALTER TABLE stream_offers ADD COLUMN offer_name VARCHAR(200)"))
            conn.commit()


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
