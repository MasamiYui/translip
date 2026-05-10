from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from ..config import CACHE_ROOT

_DB_PATH = Path(
    os.environ.get(
        "TRANSLIP_DB_PATH",
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
    _ensure_columns()


def _ensure_columns() -> None:
    """Idempotent column additions for existing databases (runtime migration).

    Each entry: (table_name, column_name, ddl_fragment).
    """
    additions = [
        ("tasks", "work_id", "VARCHAR"),
        ("tasks", "episode_label", "VARCHAR"),
    ]
    with engine.connect() as conn:
        for table, column, ddl in additions:
            existing = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            cols = {row[1] for row in existing}
            if column in cols:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        conn.commit()


def get_session():
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
