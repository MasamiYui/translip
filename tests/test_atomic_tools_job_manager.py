from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

from fastapi import UploadFile
from sqlmodel import SQLModel, create_engine


def _isolated_engine(tmp_path: Path):
    """Per-test SQLite DB so atomic-tools tests never touch the real CACHE_ROOT DB
    (which otherwise accumulates stale jobs and makes the concurrency count flaky)."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'atomic-test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


class FakeAdapter:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        input_file = next(path for path in input_dir.rglob("*") if path.is_file())
        on_progress(35.0, "fake-running")
        if self.should_fail:
            raise RuntimeError("adapter boom")
        output_path = output_dir / "result.txt"
        output_path.write_text(input_file.read_text(encoding="utf-8").upper(), encoding="utf-8")
        return {
            "echo_file": output_path.name,
            "input_name": input_file.name,
        }


class WaitingAdapter:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        self.started.set()
        on_progress(40.0, "waiting")
        self.release.wait(timeout=2)
        on_progress(80.0, "after-cancel")
        output_path = output_dir / "result.txt"
        output_path.write_text("done", encoding="utf-8")
        return {"echo_file": output_path.name}


def test_job_manager_executes_job_and_registers_artifacts(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    manager.register_adapter("probe", FakeAdapter())

    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="sample.wav",
                file=io.BytesIO(b"hello atomic tools"),
                headers={"content-type": "audio/wav"},
            )
        )
    )

    job = manager.create_job("probe", {"file_id": upload.file_id})
    asyncio.run(manager.execute_job(job.job_id))

    stored_job = manager.get_job(job.job_id)
    artifacts = manager.list_artifacts(job.job_id)

    assert stored_job.status == "completed"
    assert stored_job.progress_percent == 100.0
    assert stored_job.result == {
        "echo_file": "result.txt",
        "input_name": "sample.wav",
    }
    assert len(artifacts) == 1
    assert artifacts[0].filename == "result.txt"
    assert artifacts[0].file_id is not None
    artifact_path = manager.get_artifact_path(job.job_id, "result.txt")
    assert artifact_path is not None
    assert artifact_path.read_text(encoding="utf-8") == "HELLO ATOMIC TOOLS"


def test_job_manager_marks_job_failed_when_adapter_raises(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    manager.register_adapter("probe", FakeAdapter(should_fail=True))

    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="sample.wav",
                file=io.BytesIO(b"broken"),
                headers={"content-type": "audio/wav"},
            )
        )
    )

    job = manager.create_job("probe", {"file_id": upload.file_id})
    asyncio.run(manager.execute_job(job.job_id))

    stored_job = manager.get_job(job.job_id)
    assert stored_job.status == "failed"
    assert stored_job.error_message == "adapter boom"


def test_job_manager_rejects_unknown_file_references(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    manager.register_adapter("probe", FakeAdapter())

    try:
        manager.create_job("probe", {"file_id": "missing-file"})
    except ValueError as exc:
        assert "Unknown file reference" in str(exc)
    else:
        raise AssertionError("expected create_job() to reject an unknown file reference")


def test_job_manager_counts_pending_jobs_against_concurrency_limit(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(
        root=tmp_path / "atomic-tools", max_concurrent_jobs=1, db_engine=_isolated_engine(tmp_path)
    )
    manager.register_adapter("probe", FakeAdapter())

    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="sample.wav",
                file=io.BytesIO(b"hello atomic tools"),
                headers={"content-type": "audio/wav"},
            )
        )
    )

    manager.create_job("probe", {"file_id": upload.file_id})

    try:
        manager.create_job("probe", {"file_id": upload.file_id})
    except RuntimeError as exc:
        assert "Too many atomic tool jobs" in str(exc)
    else:
        raise AssertionError("expected create_job() to enforce the pending/running concurrency limit")


def test_job_manager_cancels_running_job_before_it_completes(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    adapter = WaitingAdapter()
    manager.register_adapter("probe", adapter)

    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="sample.wav",
                file=io.BytesIO(b"hello atomic tools"),
                headers={"content-type": "audio/wav"},
            )
        )
    )

    job = manager.create_job("probe", {"file_id": upload.file_id})
    thread = threading.Thread(target=lambda: asyncio.run(manager.execute_job(job.job_id)))
    thread.start()
    assert adapter.started.wait(timeout=2)

    assert manager.cancel_job(job.job_id) is True
    adapter.release.set()
    thread.join(timeout=2)

    stored_job = manager.get_job(job.job_id)
    assert stored_job.status == "cancelled"
    assert stored_job.error_message == "Cancelled by user"
    assert stored_job.progress_percent == 40.0
    assert manager.list_artifacts(job.job_id) == []


def _run_probe_job(manager, *, tool_id: str = "probe", content: bytes = b"hello") -> str:
    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="sample.wav",
                file=io.BytesIO(content),
                headers={"content-type": "audio/wav"},
            )
        )
    )
    job = manager.create_job(tool_id, {"file_id": upload.file_id})
    asyncio.run(manager.execute_job(job.job_id))
    return job.job_id


def test_list_jobs_paginates_and_counts_artifacts_in_sql(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    manager.register_adapter("probe", FakeAdapter())

    ids = {_run_probe_job(manager) for _ in range(5)}

    p1 = manager.list_jobs(page=1, size=2)
    p2 = manager.list_jobs(page=2, size=2)
    p3 = manager.list_jobs(page=3, size=2)

    assert p1.total == p2.total == p3.total == 5
    assert (len(p1.items), len(p2.items), len(p3.items)) == (2, 2, 1)
    assert {item.job_id for item in p1.items + p2.items + p3.items} == ids
    # artifact_count comes from the batched grouped query (FakeAdapter writes one).
    assert all(item.artifact_count == 1 for item in p1.items)


def test_list_jobs_filters_status_tool_and_search(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    manager.register_adapter("probe", FakeAdapter())
    manager.register_adapter("transcription", FakeAdapter(should_fail=True))

    ok = _run_probe_job(manager)
    bad = _run_probe_job(manager, tool_id="transcription")

    assert {i.job_id for i in manager.list_jobs(status="completed").items} == {ok}
    assert {i.job_id for i in manager.list_jobs(status="failed").items} == {bad}
    assert {i.job_id for i in manager.list_jobs(tool_id="transcription").items} == {bad}
    assert {i.job_id for i in manager.list_jobs(search="transcription").items} == {bad}
    assert manager.list_jobs(search="zzz-no-such-job").total == 0
    assert manager.list_jobs(status="all", tool_id="all").total == 2


class CancelProbeAdapter:
    """Records whether the unified cancel checker reached the adapter (ATOM-3)."""

    def __init__(self) -> None:
        self.checker_callable = False

    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        from translip.server.atomic_tools.cancellation import cancel_checker

        checker = cancel_checker(on_progress)
        self.checker_callable = callable(checker) and checker() is False
        output_path = output_dir / "ok.txt"
        output_path.write_text("ok", encoding="utf-8")
        return {"echo_file": output_path.name}


def test_job_manager_wires_unified_cancel_checker_to_adapters(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=_isolated_engine(tmp_path))
    adapter = CancelProbeAdapter()
    manager.register_adapter("probe", adapter)

    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="s.wav",
                file=io.BytesIO(b"x"),
                headers={"content-type": "audio/wav"},
            )
        )
    )
    job = manager.create_job("probe", {"file_id": upload.file_id})
    asyncio.run(manager.execute_job(job.job_id))

    assert manager.get_job(job.job_id).status == "completed"
    # The adapter received a callable cancel predicate via the unified contract.
    assert adapter.checker_callable is True


def test_list_jobs_excludes_foreign_job_roots(tmp_path: Path) -> None:
    from sqlmodel import Session

    from translip.server.atomic_tools.job_manager import JobManager
    from translip.server.models import AtomicToolJob

    engine = _isolated_engine(tmp_path)
    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=engine)
    manager.register_adapter("probe", FakeAdapter())
    owned = _run_probe_job(manager)

    # A sibling dir shares the textual prefix "…/jobs" but not the "/" boundary,
    # so the ownership LIKE (…/jobs/%) must exclude it — same boundary as
    # _owns_job's is_relative_to.
    with Session(engine) as session:
        session.add(
            AtomicToolJob(
                id="evil-1",
                tool_id="probe",
                tool_name="Probe",
                status="completed",
                job_root=str(tmp_path / "atomic-tools" / "jobs-evil" / "evil-1"),
            )
        )
        session.commit()

    resp = manager.list_jobs(page=1, size=50)
    ids = {item.job_id for item in resp.items}
    assert owned in ids
    assert "evil-1" not in ids
    assert resp.total == 1
