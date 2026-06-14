from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import translip.server.task_manager as tm
from translip.server.models import Task


def _engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'sse.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _add_task(engine, *, task_id: str, output_root: Path, status: str) -> None:
    with Session(engine) as session:
        session.add(
            Task(
                id=task_id,
                name=task_id,
                input_path="in.mp4",
                output_root=str(output_root),
                status=status,
                overall_progress=100.0 if status != "running" else 10.0,
            )
        )
        session.commit()


async def _collect(gen, *, max_events: int, timeout: float = 5.0) -> list[str]:
    events: list[str] = []

    async def _run() -> None:
        async for chunk in gen:
            events.append(chunk)
            if len(events) >= max_events:
                break

    try:
        await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        await gen.aclose()
    return events


def test_stream_exits_on_terminal_db_status_without_timeout(tmp_path: Path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    monkeypatch.setattr(tm, "engine", engine)
    out = tmp_path / "out"
    out.mkdir()
    _add_task(engine, task_id="t1", output_root=out, status="succeeded")

    # No status JSON -> the DB row is authoritative -> a 'done' event, not a timeout.
    gen = tm.task_manager.stream_progress("t1", interval=0.01, heartbeat_sec=0.05)
    events = asyncio.run(_collect(gen, max_events=2))

    joined = "".join(events)
    assert "event: done" in joined
    assert "succeeded" in joined
    assert "timeout" not in joined


def test_stream_emits_progress_and_done_from_json(tmp_path: Path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    monkeypatch.setattr(tm, "engine", engine)
    out = tmp_path / "out"
    out.mkdir()
    _add_task(engine, task_id="t2", output_root=out, status="running")
    (out / "pipeline-status.json").write_text(
        json.dumps(
            {
                "current_stage": "synthesis",
                "overall_progress_percent": 100,
                "status": "succeeded",
                "stages": [{"name": "synthesis", "status": "succeeded"}],
            }
        ),
        encoding="utf-8",
    )

    gen = tm.task_manager.stream_progress("t2", interval=0.01, heartbeat_sec=0.05)
    events = asyncio.run(_collect(gen, max_events=3))

    joined = "".join(events)
    assert "event: progress" in joined
    assert "event: done" in joined
    assert "synthesis" in joined


def test_stream_emits_heartbeat_while_running(tmp_path: Path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    monkeypatch.setattr(tm, "engine", engine)
    out = tmp_path / "out"
    out.mkdir()
    _add_task(engine, task_id="t3", output_root=out, status="running")

    # Running, no status JSON, no change -> keepalive comments keep the stream warm.
    gen = tm.task_manager.stream_progress("t3", interval=0.01, heartbeat_sec=0.02)
    events = asyncio.run(_collect(gen, max_events=2))

    assert any(chunk.startswith(": keepalive") for chunk in events)


def test_stream_reports_task_not_found(tmp_path: Path, monkeypatch) -> None:
    engine = _engine(tmp_path)
    monkeypatch.setattr(tm, "engine", engine)

    gen = tm.task_manager.stream_progress("missing", interval=0.01)
    events = asyncio.run(_collect(gen, max_events=1))

    assert any("Task not found" in chunk for chunk in events)
