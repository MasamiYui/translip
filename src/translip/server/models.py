from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Column
from sqlmodel import JSON, Field, SQLModel


class Task(SQLModel, table=True):
    """Task table — one record per pipeline execution."""

    __tablename__ = "tasks"

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    status: str = Field(index=True, default="pending")
    input_path: str
    output_root: str
    source_lang: str = Field(default="zh")
    target_lang: str = Field(default="en", index=True)
    config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    overall_progress: float = Field(default=0.0)
    current_stage: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    elapsed_sec: Optional[float] = Field(default=None)

    error_message: Optional[str] = Field(default=None)
    manifest_path: Optional[str] = Field(default=None)
    parent_task_id: Optional[str] = Field(default=None, index=True)

    work_id: Optional[str] = Field(default=None, index=True)
    episode_label: Optional[str] = Field(default=None)


class TaskStage(SQLModel, table=True):
    """Stage table — records status of each pipeline stage."""

    __tablename__ = "task_stages"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    stage_name: str
    status: str = Field(default="pending")
    progress_percent: float = Field(default=0.0)
    current_step: Optional[str] = Field(default=None)
    cache_hit: bool = Field(default=False)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    elapsed_sec: Optional[float] = Field(default=None)
    manifest_path: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


class ConfigPreset(SQLModel, table=True):
    """Config presets table — user-saved reusable config templates."""

    __tablename__ = "config_presets"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: Optional[str] = Field(default=None)
    source_lang: str = Field(default="zh")
    target_lang: str = Field(default="en")
    config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class TaskLog(SQLModel, table=True):
    """Audit log table."""

    __tablename__ = "task_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    action: str
    stage_name: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)


class AtomicToolFile(SQLModel, table=True):
    """Stored file metadata for atomic tool uploads and generated artifacts."""

    __tablename__ = "atomic_tool_files"

    id: str = Field(primary_key=True)
    kind: str = Field(index=True)
    filename: str = Field(index=True)
    path: str
    size_bytes: int = Field(default=0)
    content_type: str = Field(default="application/octet-stream")
    source_job_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)


class AtomicToolJob(SQLModel, table=True):
    """Atomic tool job table — one record per standalone tool execution."""

    __tablename__ = "atomic_tool_jobs"

    id: str = Field(primary_key=True)
    tool_id: str = Field(index=True)
    tool_name: str
    status: str = Field(index=True, default="pending")
    params: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    normalized_params: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    input_files: list[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    result: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    progress_percent: float = Field(default=0.0)
    current_step: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    job_root: str
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    elapsed_sec: Optional[float] = Field(default=None)


class AtomicToolArtifact(SQLModel, table=True):
    """Downloadable artifact metadata for atomic tool jobs."""

    __tablename__ = "atomic_tool_artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    file_id: str = Field(index=True)
    filename: str
    path: str
    size_bytes: int = Field(default=0)
    content_type: str = Field(default="application/octet-stream")
    download_url: str
    created_at: datetime = Field(default_factory=datetime.now)
