from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

from fastapi import UploadFile


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

    manager = JobManager(root=tmp_path / "atomic-tools")
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

    manager = JobManager(root=tmp_path / "atomic-tools")
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

    manager = JobManager(root=tmp_path / "atomic-tools")
    manager.register_adapter("probe", FakeAdapter())

    try:
        manager.create_job("probe", {"file_id": "missing-file"})
    except ValueError as exc:
        assert "Unknown file reference" in str(exc)
    else:
        raise AssertionError("expected create_job() to reject an unknown file reference")


def test_job_manager_counts_pending_jobs_against_concurrency_limit(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    manager = JobManager(root=tmp_path / "atomic-tools", max_concurrent_jobs=1)
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

    manager = JobManager(root=tmp_path / "atomic-tools")
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
