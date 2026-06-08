from __future__ import annotations

import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import translip.server.models  # noqa: F401  (registers tables)
from translip.server.cache_manager import (
    PipelineOutputInfo,
    gc_pipeline_outputs,
    select_evictable_pipeline_outputs,
)
from translip.server.models import Task


def _info(name: str, size: int, mtime: float, referenced: bool) -> PipelineOutputInfo:
    return PipelineOutputInfo(path=Path(name), size_bytes=size, mtime=mtime, referenced=referenced)


def test_select_evicts_unreferenced_lru_first_under_count_limit() -> None:
    infos = [
        _info("a", 10, mtime=1.0, referenced=False),  # oldest
        _info("b", 10, mtime=2.0, referenced=False),
        _info("c", 10, mtime=3.0, referenced=True),  # newest, referenced
    ]
    evict = select_evictable_pipeline_outputs(infos, max_count=2)
    # 3 dirs, limit 2 -> evict the single oldest unreferenced.
    assert [str(i.path) for i in evict] == ["a"]


def test_select_never_evicts_referenced_even_when_over_limit() -> None:
    infos = [
        _info("a", 10, mtime=1.0, referenced=True),
        _info("b", 10, mtime=2.0, referenced=True),
    ]
    # Over the count limit, but everything is referenced -> nothing evicted.
    assert select_evictable_pipeline_outputs(infos, max_count=1) == []


def test_select_evicts_by_byte_budget() -> None:
    infos = [
        _info("a", 100, mtime=1.0, referenced=False),
        _info("b", 100, mtime=2.0, referenced=False),
        _info("c", 100, mtime=3.0, referenced=False),
    ]
    # 300 total, cap 150 -> evict oldest two (a, b) to get under.
    evict = select_evictable_pipeline_outputs(infos, max_bytes=150)
    assert [str(i.path) for i in evict] == ["a", "b"]


def test_select_noop_when_no_limits_or_under_limit() -> None:
    infos = [_info("a", 10, mtime=1.0, referenced=False)]
    assert select_evictable_pipeline_outputs(infos) == []
    assert select_evictable_pipeline_outputs(infos, max_count=5, max_bytes=1000) == []


def _engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'gc-test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _make_output_dir(root: Path, name: str, *, mtime: float) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "artifact.bin").write_bytes(b"\x00" * 256)
    os.utime(d, (mtime, mtime))
    return d


def test_gc_pipeline_outputs_evicts_orphans_and_keeps_referenced(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    out_root = cache_root / "output-pipeline"
    out_root.mkdir(parents=True)
    kept = _make_output_dir(out_root, "task-kept", mtime=3000)
    orphan_old = _make_output_dir(out_root, "task-orphan-old", mtime=1000)
    orphan_new = _make_output_dir(out_root, "task-orphan-new", mtime=2000)

    engine = _engine(tmp_path)
    with Session(engine) as session:
        session.add(
            Task(id="kept", name="kept", input_path="x.mp4", output_root=str(kept.resolve()))
        )
        session.commit()

    # Limit to 1 dir: only the referenced one may remain -> both orphans evicted,
    # oldest first.
    report = gc_pipeline_outputs(max_count=1, cache_root=cache_root, db_engine=engine)

    assert report["referenced"] == 1
    assert set(report["evicted"]) == {str(orphan_old), str(orphan_new)}
    assert report["freed_bytes"] > 0
    assert kept.exists()
    assert not orphan_old.exists()
    assert not orphan_new.exists()


def test_gc_pipeline_outputs_dry_run_deletes_nothing(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    out_root = cache_root / "output-pipeline"
    out_root.mkdir(parents=True)
    orphan = _make_output_dir(out_root, "task-orphan", mtime=1000)
    engine = _engine(tmp_path)

    report = gc_pipeline_outputs(max_count=0, cache_root=cache_root, db_engine=engine, dry_run=True)

    assert report["dry_run"] is True
    assert report["evicted"] == [str(orphan)]
    assert orphan.exists()  # dry run -> not actually deleted
