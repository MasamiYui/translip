from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel, create_engine

import translip.server.database as db
import translip.server.models  # noqa: F401  (registers tables on SQLModel.metadata)
from translip.server.database import applied_versions, run_migrations


def _engine(tmp_path: Path):
    return create_engine(
        f"sqlite:///{tmp_path / 'migrations-test.db'}",
        connect_args={"check_same_thread": False},
    )


def _columns(engine, table: str) -> set[str]:
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def test_run_migrations_on_fresh_db_records_versions_and_is_idempotent(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)  # current schema (already has the columns)

    first = run_migrations(engine)
    assert first == [1]
    assert applied_versions(engine) == {1}

    # Re-running applies nothing new.
    second = run_migrations(engine)
    assert second == []
    assert applied_versions(engine) == {1}

    # schema_version row is recorded with a name + timestamp.
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT version, name, applied_at FROM schema_version")).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1 and rows[0][1] == "runtime_columns" and rows[0][2]


def test_run_migrations_adds_missing_columns_to_legacy_db(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    # Simulate an older database whose tables predate the column additions.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE tasks (id VARCHAR PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE analyses (id VARCHAR PRIMARY KEY)"))

    assert "work_id" not in _columns(engine, "tasks")

    applied = run_migrations(engine)
    assert applied == [1]
    assert {"work_id", "episode_label"} <= _columns(engine, "tasks")
    assert "progress" in _columns(engine, "analyses")
    assert applied_versions(engine) == {1}


def test_run_migrations_rolls_back_and_records_nothing_on_failure(tmp_path: Path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    SQLModel.metadata.create_all(engine)

    def boom(_conn):
        raise RuntimeError("migration boom")

    # Inject a failing migration with a higher version than the real ones.
    monkeypatch.setattr(db, "_MIGRATIONS", [*db._MIGRATIONS, (999, "boom", boom)])

    try:
        run_migrations(engine)
    except RuntimeError as exc:
        assert "migration boom" in str(exc)
    else:
        raise AssertionError("expected the failing migration to raise")

    # The real migration committed; the failing one recorded nothing.
    versions = applied_versions(engine)
    assert 1 in versions
    assert 999 not in versions
