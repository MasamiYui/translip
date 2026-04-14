from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from ..config import CACHE_ROOT

_DB_PATH = Path(
    os.environ.get(
        "VIDEO_VOICE_SEPARATE_DB_PATH",
        str(CACHE_ROOT / "data.db"),
    )
)

engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create tables if they don't exist. Call at app startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
