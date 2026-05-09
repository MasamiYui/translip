from __future__ import annotations

import asyncio
import io
from pathlib import Path

from fastapi import UploadFile
from sqlmodel import SQLModel, create_engine


class PersistentFakeAdapter:
    def validate_params(self, params: dict) -> dict:
        return dict(params)

    def run(self, params: dict, input_dir: Path, output_dir: Path, on_progress) -> dict:
        input_file = next(path for path in input_dir.rglob("*") if path.is_file())
        on_progress(42.0, "persisting")
        output_path = output_dir / "result.txt"
        output_path.write_text(input_file.read_text(encoding="utf-8").upper(), encoding="utf-8")
        return {
            "echo_file": output_path.name,
            "input_name": input_file.name,
        }


def _engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'atomic-jobs.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_job_manager_persists_jobs_files_and_artifacts_across_instances(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    engine = _engine(tmp_path)
    root = tmp_path / "atomic-tools"

    manager = JobManager(root=root, db_engine=engine)
    manager.register_adapter("probe", PersistentFakeAdapter())

    upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="sample.wav",
                file=io.BytesIO(b"hello atomic jobs"),
                headers={"content-type": "audio/wav"},
            )
        )
    )
    job = manager.create_job("probe", {"file_id": upload.file_id})
    asyncio.run(manager.execute_job(job.job_id))

    restored = JobManager(root=root, db_engine=engine)
    restored.register_adapter("probe", PersistentFakeAdapter())

    restored_job = restored.get_job(job.job_id)
    restored_artifacts = restored.list_artifacts(job.job_id)
    page = restored.list_jobs(size=10)

    assert restored_job.status == "completed"
    assert restored_job.progress_percent == 100.0
    assert restored_job.result == {
        "echo_file": "result.txt",
        "input_name": "sample.wav",
    }
    assert [artifact.filename for artifact in restored_artifacts] == ["result.txt"]
    assert restored.get_artifact_path(job.job_id, "result.txt").read_text(encoding="utf-8") == "HELLO ATOMIC JOBS"
    assert page.total == 1
    assert page.items[0].job_id == job.job_id
    assert page.items[0].input_files[0].filename == "sample.wav"
    assert page.items[0].artifact_count == 1


def test_job_manager_lists_jobs_with_status_tool_and_search_filters(tmp_path: Path) -> None:
    from translip.server.atomic_tools.job_manager import JobManager

    engine = _engine(tmp_path)
    manager = JobManager(root=tmp_path / "atomic-tools", db_engine=engine)
    manager.register_adapter("probe", PersistentFakeAdapter())

    first_upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="alpha.wav",
                file=io.BytesIO(b"alpha"),
                headers={"content-type": "audio/wav"},
            )
        )
    )
    second_upload = asyncio.run(
        manager.save_upload(
            UploadFile(
                filename="beta.wav",
                file=io.BytesIO(b"beta"),
                headers={"content-type": "audio/wav"},
            )
        )
    )

    first_job = manager.create_job("probe", {"file_id": first_upload.file_id})
    asyncio.run(manager.execute_job(first_job.job_id))
    second_job = manager.create_job("probe", {"file_id": second_upload.file_id})

    completed = manager.list_jobs(status="completed")
    pending = manager.list_jobs(status="pending")
    searched = manager.list_jobs(search="alpha")

    assert [job.job_id for job in completed.items] == [first_job.job_id]
    assert [job.job_id for job in pending.items] == [second_job.job_id]
    assert [job.job_id for job in searched.items] == [first_job.job_id]
