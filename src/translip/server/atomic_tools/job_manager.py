from __future__ import annotations

import asyncio
import mimetypes
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile

from ...config import CACHE_ROOT
from .registry import create_adapter, get_tool_spec
from .schemas import ArtifactInfo, FileUploadResponse, JobResponse


@dataclass(slots=True)
class StoredFile:
    file_id: str
    filename: str
    path: Path
    size_bytes: int
    content_type: str
    created_at: datetime


class JobManager:
    def __init__(self, *, root: Path | None = None, max_concurrent_jobs: int = 2) -> None:
        self.root = (root or (CACHE_ROOT / "atomic-tools")).resolve()
        self.upload_root = self.root / "uploads"
        self.jobs_root = self.root / "jobs"
        self.max_concurrent_jobs = max_concurrent_jobs
        self._jobs: dict[str, JobResponse] = {}
        self._files: dict[str, StoredFile] = {}
        self._job_artifacts: dict[str, list[ArtifactInfo]] = {}
        self._adapter_overrides: dict[str, Any] = {}

    def register_adapter(self, tool_id: str, adapter: Any) -> None:
        self._adapter_overrides[tool_id] = adapter

    async def save_upload(self, file: UploadFile) -> FileUploadResponse:
        file_id = uuid4().hex
        filename = Path(file.filename or "upload.bin").name
        target_dir = self.upload_root / file_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        chunk_size = 4 * 1024 * 1024
        size_bytes = 0
        with target_path.open("wb") as dst:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                dst.write(chunk)
                size_bytes += len(chunk)
        content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        stored = StoredFile(
            file_id=file_id,
            filename=filename,
            path=target_path,
            size_bytes=size_bytes,
            content_type=content_type,
            created_at=datetime.now(),
        )
        self._files[file_id] = stored
        return FileUploadResponse(
            file_id=file_id,
            filename=filename,
            size_bytes=stored.size_bytes,
            content_type=stored.content_type,
        )

    def create_job(self, tool_id: str, params: dict) -> JobResponse:
        spec = get_tool_spec(tool_id)
        if self._active_job_count() >= self.max_concurrent_jobs:
            raise RuntimeError("Too many atomic tool jobs are already running")
        adapter = self._get_adapter(tool_id)
        normalized = adapter.validate_params(params)
        self._validate_file_references(spec.accept_formats, spec.max_file_size_mb, normalized)
        job_id = uuid4().hex
        job = JobResponse(
            job_id=job_id,
            tool_id=tool_id,
            status="pending",
            progress_percent=0.0,
            created_at=datetime.now(),
            result=None,
        )
        self._jobs[job_id] = job
        setattr(job, "_normalized_params", normalized)
        return job

    async def execute_job(self, job_id: str) -> None:
        await asyncio.to_thread(self._execute_job_sync, job_id)

    def _execute_job_sync(self, job_id: str) -> None:
        job = self._jobs[job_id]
        params = getattr(job, "_normalized_params")
        adapter = self._get_adapter(job.tool_id)
        job_dir = self.jobs_root / job_id
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._materialize_inputs(params, input_dir)

        started_at = datetime.now()
        job.status = "running"
        job.started_at = started_at
        job.progress_percent = 1.0
        job.current_step = "starting"

        def on_progress(percent: float, step: str | None = None) -> None:
            job.progress_percent = max(0.0, min(99.0, float(percent)))
            job.current_step = step

        try:
            result = adapter.run(params, input_dir, output_dir, on_progress)
        except Exception as exc:
            finished_at = datetime.now()
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = finished_at
            job.elapsed_sec = round((finished_at - started_at).total_seconds(), 3)
            job.progress_percent = min(job.progress_percent or 0.0, 99.0)
            return

        finished_at = datetime.now()
        job.status = "completed"
        job.result = result
        job.finished_at = finished_at
        job.elapsed_sec = round((finished_at - started_at).total_seconds(), 3)
        job.progress_percent = 100.0
        job.current_step = "completed"
        self._job_artifacts[job_id] = self._register_artifacts(job)

    def get_job(self, job_id: str) -> JobResponse:
        return self._jobs[job_id]

    def get_job_result(self, job_id: str) -> dict[str, Any] | None:
        return self.get_job(job_id).result

    def list_artifacts(self, job_id: str) -> list[ArtifactInfo]:
        self.get_job(job_id)
        return list(self._job_artifacts.get(job_id, []))

    def get_artifact_path(self, job_id: str, filename: str) -> Path | None:
        for artifact in self._job_artifacts.get(job_id, []):
            if artifact.filename == filename:
                path = self.jobs_root / job_id / "output" / filename
                if path.exists():
                    return path
        return None

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        threshold = datetime.now() - timedelta(hours=max_age_hours)
        removed = 0
        for file_id, stored in list(self._files.items()):
            if stored.created_at < threshold:
                if stored.path.parent.exists():
                    shutil.rmtree(stored.path.parent, ignore_errors=True)
                self._files.pop(file_id, None)
                removed += 1

        for job_id, job in list(self._jobs.items()):
            if job.created_at < threshold:
                shutil.rmtree(self.jobs_root / job_id, ignore_errors=True)
                self._jobs.pop(job_id, None)
                self._job_artifacts.pop(job_id, None)
                removed += 1
        return removed

    def _get_adapter(self, tool_id: str):
        return self._adapter_overrides.get(tool_id) or create_adapter(tool_id)

    def _active_job_count(self) -> int:
        return sum(1 for job in self._jobs.values() if job.status in {"pending", "running"})

    def _validate_file_references(
        self,
        accepted_formats: list[str],
        max_file_size_mb: int,
        params: dict[str, Any],
    ) -> None:
        for key, value in params.items():
            if key == "file_id" and isinstance(value, str):
                self._validate_stored_file(value, accepted_formats, max_file_size_mb, param_name=key)
            elif key.endswith("_file_id") and isinstance(value, str):
                self._validate_stored_file(value, accepted_formats, max_file_size_mb, param_name=key)
            elif key.endswith("_file_ids") and isinstance(value, list):
                for index, file_id in enumerate(value):
                    self._validate_stored_file(
                        file_id,
                        accepted_formats,
                        max_file_size_mb,
                        param_name=f"{key}[{index}]",
                    )

    def _validate_stored_file(
        self,
        file_id: str,
        accepted_formats: list[str],
        max_file_size_mb: int,
        *,
        param_name: str,
    ) -> None:
        stored = self._files.get(file_id)
        if stored is None:
            raise ValueError(f"Unknown file reference for {param_name}: {file_id}")
        if stored.size_bytes > (max_file_size_mb * 1024 * 1024):
            raise ValueError(
                f"File '{stored.filename}' exceeds the {max_file_size_mb} MB limit for this tool"
            )
        suffix = Path(stored.filename).suffix.lower()
        normalized_formats = {item.lower() for item in accepted_formats}
        if suffix and normalized_formats and suffix not in normalized_formats:
            raise ValueError(
                f"File '{stored.filename}' is not supported for this tool. "
                f"Accepted formats: {', '.join(sorted(normalized_formats))}"
            )

    def _materialize_inputs(self, params: dict[str, Any], input_dir: Path) -> None:
        for key, value in params.items():
            if key == "file_id":
                self._copy_file_to_input("file", value, input_dir)
            elif key.endswith("_file_id") and isinstance(value, str):
                self._copy_file_to_input(key.removesuffix("_id"), value, input_dir)
            elif key.endswith("_file_ids") and isinstance(value, list):
                stem = key.removesuffix("_ids")
                for index, file_id in enumerate(value):
                    self._copy_file_to_input(f"{stem}_{index}", file_id, input_dir)

    def _copy_file_to_input(self, stem: str, file_id: str, input_dir: Path) -> None:
        stored = self._files[file_id]
        target_dir = input_dir / stem
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stored.path, target_dir / stored.filename)

    def _register_artifacts(self, job: JobResponse) -> list[ArtifactInfo]:
        output_dir = self.jobs_root / job.job_id / "output"
        artifacts: list[ArtifactInfo] = []
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            file_id = uuid4().hex
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            stored = StoredFile(
                file_id=file_id,
                filename=path.name,
                path=path,
                size_bytes=path.stat().st_size,
                content_type=content_type,
                created_at=datetime.now(),
            )
            self._files[file_id] = stored
            artifacts.append(
                ArtifactInfo(
                    filename=path.relative_to(output_dir).as_posix(),
                    size_bytes=stored.size_bytes,
                    content_type=stored.content_type,
                    download_url=f"/api/atomic-tools/{job.tool_id}/jobs/{job.job_id}/artifacts/{path.relative_to(output_dir).as_posix()}",
                    file_id=file_id,
                )
            )
        return artifacts


job_manager = JobManager()
