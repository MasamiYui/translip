from __future__ import annotations

import asyncio
import mimetypes
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, select

from ...config import CACHE_ROOT
from ...orchestration.subprocess_runner import StageSubprocessCancelled
from ..database import engine as default_engine
from ..models import AtomicToolArtifact, AtomicToolFile, AtomicToolJob
from .registry import create_adapter, get_tool_spec
from .schemas import (
    ArtifactInfo,
    AtomicJobDetail,
    AtomicJobListResponse,
    AtomicJobRead,
    AtomicStoredFileInfo,
    FileUploadResponse,
    JobResponse,
)


@dataclass(slots=True)
class StoredFile:
    file_id: str
    filename: str
    path: Path
    size_bytes: int
    content_type: str
    created_at: datetime


class AtomicJobCancelled(RuntimeError):
    """Raised inside a running adapter when the user cancels the job."""


class JobManager:
    def __init__(
        self,
        *,
        root: Path | None = None,
        max_concurrent_jobs: int = 2,
        db_engine: Engine | None = None,
    ) -> None:
        self.root = (root or (CACHE_ROOT / "atomic-tools")).resolve()
        self.upload_root = self.root / "uploads"
        self.jobs_root = self.root / "jobs"
        self.max_concurrent_jobs = max_concurrent_jobs
        self.db_engine = db_engine or default_engine
        SQLModel.metadata.create_all(self.db_engine)
        self._adapter_overrides: dict[str, Any] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_events_lock = threading.Lock()

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
        with self._session() as session:
            session.add(
                AtomicToolFile(
                    id=stored.file_id,
                    kind="upload",
                    filename=stored.filename,
                    path=str(stored.path),
                    size_bytes=stored.size_bytes,
                    content_type=stored.content_type,
                    created_at=stored.created_at,
                )
            )
            session.commit()
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
        now = datetime.now()
        model = AtomicToolJob(
            id=job_id,
            tool_id=tool_id,
            tool_name=spec.name_zh,
            status="pending",
            params=dict(params),
            normalized_params=normalized,
            input_files=self._input_file_infos(normalized),
            progress_percent=0.0,
            job_root=str(self.jobs_root / job_id),
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            return self._job_to_response(model)

    async def execute_job(self, job_id: str) -> None:
        await asyncio.to_thread(self._execute_job_sync, job_id)

    def _execute_job_sync(self, job_id: str) -> None:
        cancel_event = self._cancel_event_for(job_id)
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status == "cancelled" or cancel_event.is_set():
                self._mark_job_cancelled(job_id)
                self._drop_cancel_event(job_id)
                return
            params = dict(job.normalized_params)
            tool_id = job.tool_id
        try:
            adapter = self._get_adapter(tool_id)
            job_dir = self.jobs_root / job_id
            input_dir = job_dir / "input"
            output_dir = job_dir / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._materialize_inputs(params, input_dir)

            started_at = datetime.now()
            self._update_job(
                job_id,
                status="running",
                started_at=started_at,
                progress_percent=1.0,
                current_step="starting",
                error_message=None,
            )

            def on_progress(percent: float, step: str | None = None) -> None:
                if cancel_event.is_set():
                    raise AtomicJobCancelled()
                self._update_job(
                    job_id,
                    progress_percent=max(0.0, min(99.0, float(percent))),
                    current_step=step,
                )
                if cancel_event.is_set():
                    raise AtomicJobCancelled()

            setattr(on_progress, "is_cancelled", cancel_event.is_set)

            try:
                result = adapter.run(params, input_dir, output_dir, on_progress)
            except (AtomicJobCancelled, StageSubprocessCancelled):
                self._mark_job_cancelled(job_id, started_at=started_at)
                return
            except Exception as exc:
                finished_at = datetime.now()
                with self._session() as session:
                    job = session.get(AtomicToolJob, job_id)
                    current_progress = job.progress_percent if job else 0.0
                self._update_job(
                    job_id,
                    status="failed",
                    error_message=str(exc),
                    finished_at=finished_at,
                    elapsed_sec=round((finished_at - started_at).total_seconds(), 3),
                    progress_percent=min(current_progress or 0.0, 99.0),
                )
                return

            if cancel_event.is_set():
                self._mark_job_cancelled(job_id, started_at=started_at)
                return

            finished_at = datetime.now()
            self._update_job(
                job_id,
                status="completed",
                result=result,
                finished_at=finished_at,
                elapsed_sec=round((finished_at - started_at).total_seconds(), 3),
                progress_percent=100.0,
                current_step="completed",
            )
            self._register_artifacts(job_id, tool_id)
        finally:
            self._drop_cancel_event(job_id)

    def get_job(self, job_id: str) -> JobResponse:
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            return self._job_to_response(job)

    def get_job_detail(self, job_id: str) -> AtomicJobDetail:
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            return self._job_to_detail(job)

    def get_job_result(self, job_id: str) -> dict[str, Any] | None:
        return self.get_job(job_id).result

    def list_artifacts(self, job_id: str) -> list[ArtifactInfo]:
        self.get_job(job_id)
        with self._session() as session:
            artifacts = list(
                session.exec(
                    select(AtomicToolArtifact).where(AtomicToolArtifact.job_id == job_id)
                ).all()
            )
            return [self._artifact_to_info(artifact) for artifact in artifacts]

    def get_artifact_path(self, job_id: str, filename: str) -> Path | None:
        with self._session() as session:
            artifact = session.exec(
                select(AtomicToolArtifact).where(
                    AtomicToolArtifact.job_id == job_id,
                    AtomicToolArtifact.filename == filename,
                )
            ).first()
            if artifact is not None:
                path = Path(artifact.path)
                if path.exists():
                    return path
        return None

    def list_jobs(
        self,
        *,
        status: str | None = None,
        tool_id: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> AtomicJobListResponse:
        with self._session() as session:
            jobs = list(session.exec(select(AtomicToolJob)).all())
        jobs = [job for job in jobs if self._owns_job(job)]

        if status and status != "all":
            jobs = [job for job in jobs if job.status == status]
        if tool_id and tool_id != "all":
            jobs = [job for job in jobs if job.tool_id == tool_id]
        if search:
            needle = search.lower()
            jobs = [
                job
                for job in jobs
                if needle in job.id.lower()
                or needle in job.tool_id.lower()
                or needle in job.tool_name.lower()
                or any(needle in str(item.get("filename", "")).lower() for item in job.input_files)
            ]

        jobs.sort(key=lambda item: item.created_at, reverse=True)
        total = len(jobs)
        offset = (page - 1) * size
        page_items = jobs[offset : offset + size]
        return AtomicJobListResponse(
            items=[self._job_to_read(job) for job in page_items],
            total=total,
            page=page,
            size=size,
        )

    def list_recent_jobs(self, *, limit: int = 5) -> list[AtomicJobRead]:
        return self.list_jobs(page=1, size=limit).items

    def rerun_job(self, job_id: str) -> JobResponse:
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            tool_id = job.tool_id
            params = dict(job.params or job.normalized_params)
        return self.create_job(tool_id, params)

    def delete_job(self, job_id: str, *, delete_artifacts: bool = True) -> None:
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            artifacts = list(
                session.exec(
                    select(AtomicToolArtifact).where(AtomicToolArtifact.job_id == job_id)
                ).all()
            )
            for artifact in artifacts:
                stored_file = session.get(AtomicToolFile, artifact.file_id)
                if stored_file is not None:
                    session.delete(stored_file)
                session.delete(artifact)
            session.delete(job)
            session.commit()
        if delete_artifacts:
            shutil.rmtree(self.jobs_root / job_id, ignore_errors=True)

    def cancel_job(self, job_id: str) -> bool:
        cancel_event = self._cancel_event_for(job_id)
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            if not self._owns_job(job) or job.status not in ("pending", "running"):
                self._drop_cancel_event(job_id)
                return False
            cancel_event.set()
            now = datetime.now()
            job.status = "cancelled"
            job.error_message = "Cancelled by user"
            job.finished_at = now
            job.updated_at = now
            job.current_step = "cancelled"
            if job.started_at:
                job.elapsed_sec = round((now - job.started_at).total_seconds(), 3)
            session.add(job)
            session.commit()
        return True

    def mark_interrupted_jobs(self) -> int:
        count = 0
        now = datetime.now()
        with self._session() as session:
            jobs = list(
                session.exec(
                    select(AtomicToolJob).where(AtomicToolJob.status.in_(["pending", "running"]))
                ).all()
            )
            jobs = [job for job in jobs if self._owns_job(job)]
            for job in jobs:
                job.status = "interrupted"
                job.error_message = "Interrupted by service restart"
                job.finished_at = now
                job.updated_at = now
                if job.started_at:
                    job.elapsed_sec = round((now - job.started_at).total_seconds(), 3)
                session.add(job)
                count += 1
            session.commit()
        return count

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        threshold = datetime.now() - timedelta(hours=max_age_hours)
        removed = 0
        with self._session() as session:
            files = list(
                session.exec(
                    select(AtomicToolFile).where(AtomicToolFile.created_at < threshold)
                ).all()
            )
            for stored in files:
                path = Path(stored.path)
                if stored.kind == "upload" and path.parent.exists():
                    shutil.rmtree(path.parent, ignore_errors=True)
                session.delete(stored)
                removed += 1

            jobs = list(
                session.exec(
                    select(AtomicToolJob).where(AtomicToolJob.created_at < threshold)
                ).all()
            )
            jobs = [job for job in jobs if self._owns_job(job)]
            for job in jobs:
                shutil.rmtree(self.jobs_root / job.id, ignore_errors=True)
                session.delete(job)
                removed += 1
            session.commit()
        return removed

    def _get_adapter(self, tool_id: str):
        return self._adapter_overrides.get(tool_id) or create_adapter(tool_id)

    def _cancel_event_for(self, job_id: str) -> threading.Event:
        with self._cancel_events_lock:
            event = self._cancel_events.get(job_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[job_id] = event
            return event

    def _drop_cancel_event(self, job_id: str) -> None:
        with self._cancel_events_lock:
            self._cancel_events.pop(job_id, None)

    def _mark_job_cancelled(
        self,
        job_id: str,
        *,
        started_at: datetime | None = None,
    ) -> None:
        finished_at = datetime.now()
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            start = job.started_at or started_at
            job.status = "cancelled"
            job.error_message = "Cancelled by user"
            job.finished_at = finished_at
            job.current_step = "cancelled"
            job.updated_at = finished_at
            if start:
                job.elapsed_sec = round((finished_at - start).total_seconds(), 3)
            session.add(job)
            session.commit()

    def _active_job_count(self) -> int:
        with self._session() as session:
            jobs = session.exec(
                select(AtomicToolJob).where(AtomicToolJob.status.in_(["pending", "running"]))
            ).all()
            return len([job for job in jobs if self._owns_job(job)])

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
        stored = self._get_stored_file(file_id)
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
        stored = self._require_stored_file(file_id)
        target_dir = input_dir / stem
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stored.path, target_dir / stored.filename)

    def _register_artifacts(self, job_id: str, tool_id: str) -> list[ArtifactInfo]:
        output_dir = self.jobs_root / job_id / "output"
        artifacts: list[ArtifactInfo] = []
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            file_id = uuid4().hex
            content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            relative_name = path.relative_to(output_dir).as_posix()
            now = datetime.now()
            with self._session() as session:
                session.add(
                    AtomicToolFile(
                        id=file_id,
                        kind="artifact",
                        filename=path.name,
                        path=str(path),
                        size_bytes=path.stat().st_size,
                        content_type=content_type,
                        source_job_id=job_id,
                        created_at=now,
                    )
                )
                artifact = AtomicToolArtifact(
                    job_id=job_id,
                    file_id=file_id,
                    filename=relative_name,
                    path=str(path),
                    size_bytes=path.stat().st_size,
                    content_type=content_type,
                    download_url=f"/api/atomic-tools/{tool_id}/jobs/{job_id}/artifacts/{relative_name}",
                    created_at=now,
                )
                session.add(artifact)
                session.commit()
                session.refresh(artifact)
                artifacts.append(self._artifact_to_info(artifact))
        return artifacts

    def _session(self) -> Session:
        return Session(self.db_engine)

    def _owns_job(self, job: AtomicToolJob) -> bool:
        try:
            return Path(job.job_root).resolve().is_relative_to(self.jobs_root)
        except Exception:
            return str(job.job_root).startswith(str(self.jobs_root))

    def _get_stored_file(self, file_id: str) -> StoredFile | None:
        with self._session() as session:
            stored = session.get(AtomicToolFile, file_id)
            if stored is None:
                return None
            return self._stored_file_from_model(stored)

    def _require_stored_file(self, file_id: str) -> StoredFile:
        stored = self._get_stored_file(file_id)
        if stored is None:
            raise KeyError(file_id)
        return stored

    def _input_file_infos(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        file_ids: list[str] = []
        for key, value in params.items():
            if key == "file_id" and isinstance(value, str):
                file_ids.append(value)
            elif key.endswith("_file_id") and isinstance(value, str):
                file_ids.append(value)
            elif key.endswith("_file_ids") and isinstance(value, list):
                file_ids.extend(item for item in value if isinstance(item, str))

        items: list[dict[str, Any]] = []
        for file_id in file_ids:
            stored = self._require_stored_file(file_id)
            items.append(
                AtomicStoredFileInfo(
                    file_id=stored.file_id,
                    filename=stored.filename,
                    size_bytes=stored.size_bytes,
                    content_type=stored.content_type,
                ).model_dump()
            )
        return items

    def _stored_file_from_model(self, stored: AtomicToolFile) -> StoredFile:
        return StoredFile(
            file_id=stored.id,
            filename=stored.filename,
            path=Path(stored.path),
            size_bytes=stored.size_bytes,
            content_type=stored.content_type,
            created_at=stored.created_at,
        )

    def _artifact_to_info(self, artifact: AtomicToolArtifact) -> ArtifactInfo:
        return ArtifactInfo(
            filename=artifact.filename,
            size_bytes=artifact.size_bytes,
            content_type=artifact.content_type,
            download_url=artifact.download_url,
            file_id=artifact.file_id,
        )

    def _job_to_response(self, job: AtomicToolJob) -> JobResponse:
        return JobResponse(
            job_id=job.id,
            tool_id=job.tool_id,
            status=job.status,
            progress_percent=job.progress_percent,
            current_step=job.current_step,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            elapsed_sec=job.elapsed_sec,
            error_message=job.error_message,
            result=job.result,
        )

    def _job_to_read(self, job: AtomicToolJob) -> AtomicJobRead:
        return AtomicJobRead(
            **self._job_to_response(job).model_dump(),
            tool_name=job.tool_name,
            input_files=[AtomicStoredFileInfo(**item) for item in job.input_files],
            artifact_count=len(self.list_artifacts(job.id)),
            updated_at=job.updated_at,
        )

    def _job_to_detail(self, job: AtomicToolJob) -> AtomicJobDetail:
        return AtomicJobDetail(
            **self._job_to_read(job).model_dump(),
            params=job.params,
            artifacts=self.list_artifacts(job.id),
        )

    def _update_job(self, job_id: str, **values: Any) -> None:
        with self._session() as session:
            job = session.get(AtomicToolJob, job_id)
            if job is None:
                raise KeyError(job_id)
            for key, value in values.items():
                setattr(job, key, value)
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()


job_manager = JobManager()
