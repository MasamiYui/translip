from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, SQLModel, create_engine

from ..config import CACHE_ROOT
from ..utils.io import now_iso

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
    """Create tables if they don't exist, then apply versioned migrations.

    Call at app startup.
    """
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    SQLModel.metadata.create_all(engine)
    run_migrations()


# ---------------------------------------------------------------------------
# Versioned migrations (ARCH-11)
#
# `create_all` only creates missing *tables*; it never alters an existing table,
# so column additions to already-deployed databases need explicit migrations.
# Each migration runs in its own transaction and records its version in the
# `schema_version` table only on success — a partial failure rolls back and
# raises, so a half-applied schema is detectable rather than silent. Migration
# bodies must be idempotent (guard with PRAGMA table_info) so that a database
# which already has the columns from an older runtime patch records the version
# without erroring.
# ---------------------------------------------------------------------------


def _ensure_schema_version_table(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "version INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "applied_at TEXT NOT NULL)"
        )
    )


def _add_missing_columns(conn: Connection, additions: list[tuple[str, str, str]]) -> None:
    """Idempotently ALTER ADD COLUMN — skips columns that already exist."""
    for table, column, ddl in additions:
        existing = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        cols = {row[1] for row in existing}
        if column in cols:
            continue
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def _migration_0001_runtime_columns(conn: Connection) -> None:
    _add_missing_columns(
        conn,
        [
            ("tasks", "work_id", "VARCHAR"),
            ("tasks", "episode_label", "VARCHAR"),
            ("analyses", "progress", "JSON"),
        ],
    )


# (version, name, fn) — keep ordered by ascending version; never renumber an
# already-released migration.
_MIGRATIONS: list[tuple[int, str, Callable[[Connection], None]]] = [
    (1, "runtime_columns", _migration_0001_runtime_columns),
]


def applied_versions(target_engine: Engine | None = None) -> set[int]:
    target = target_engine or engine
    with target.begin() as conn:
        _ensure_schema_version_table(conn)
        rows = conn.execute(text("SELECT version FROM schema_version")).fetchall()
    return {int(row[0]) for row in rows}


def run_migrations(target_engine: Engine | None = None) -> list[int]:
    """Apply pending migrations in version order; return the versions applied now.

    Idempotent: already-applied versions are skipped, so it is safe to call on
    every startup. Each migration is atomic — on failure it rolls back and the
    exception propagates, leaving the recorded version unchanged.
    """
    target = target_engine or engine
    done = applied_versions(target)
    newly_applied: list[int] = []
    for version, name, migrate in sorted(_MIGRATIONS, key=lambda item: item[0]):
        if version in done:
            continue
        with target.begin() as conn:  # one transaction per migration
            migrate(conn)
            conn.execute(
                text(
                    "INSERT INTO schema_version (version, name, applied_at) "
                    "VALUES (:version, :name, :applied_at)"
                ),
                {"version": version, "name": name, "applied_at": now_iso()},
            )
        newly_applied.append(version)
    return newly_applied


def get_session():
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session
