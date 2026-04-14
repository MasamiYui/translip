from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils.files import ensure_directory
from .stages import STAGE_ORDER, STAGE_WEIGHTS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class _StageState:
    stage_name: str
    status: str
    progress_percent: float
    current_step: str
    updated_at: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status,
            "progress_percent": round(self.progress_percent, 2),
            "current_step": self.current_step,
            "updated_at": self.updated_at,
        }


class PipelineMonitor:
    def __init__(self, *, job_id: str, status_path: Path, write_status: bool = True) -> None:
        self.job_id = job_id
        self.status_path = status_path
        self.write_status = write_status
        self._stages: dict[str, _StageState] = {}
        self._pipeline_status = "pending"
        self._current_stage: str | None = None

    def start_stage(self, stage_name: str, current_step: str = "starting") -> None:
        self._current_stage = stage_name
        self._pipeline_status = "running"
        self._stages[stage_name] = _StageState(
            stage_name=stage_name,
            status="running",
            progress_percent=0.0,
            current_step=current_step,
            updated_at=_now_iso(),
        )
        self._write()

    def update_stage_progress(
        self,
        stage_name: str,
        progress_percent: float,
        current_step: str | None = None,
        *,
        status: str = "running",
    ) -> None:
        state = self._stages.get(stage_name)
        if state is None:
            state = _StageState(
                stage_name=stage_name,
                status=status,
                progress_percent=0.0,
                current_step=current_step or "",
                updated_at=_now_iso(),
            )
            self._stages[stage_name] = state
        state.status = status
        state.progress_percent = max(0.0, min(100.0, progress_percent))
        if current_step is not None:
            state.current_step = current_step
        state.updated_at = _now_iso()
        if status == "running":
            self._current_stage = stage_name
            self._pipeline_status = "running"
        self._write()

    def complete_stage(self, stage_name: str, *, status: str = "succeeded", current_step: str = "completed") -> None:
        self.update_stage_progress(stage_name, 100.0, current_step, status=status)

    def fail_stage(self, stage_name: str, *, error: str) -> None:
        self.update_stage_progress(stage_name, self._stages.get(stage_name, _StageState(stage_name, "", 0.0, "", _now_iso())).progress_percent, error, status="failed")
        self._pipeline_status = "failed"
        self._current_stage = stage_name
        self._write()

    def finalize(self, *, status: str) -> None:
        self._pipeline_status = status
        self._write()

    def _overall_progress(self) -> float:
        total = 0.0
        for stage_name in STAGE_ORDER:
            state = self._stages.get(stage_name)
            if state is None:
                continue
            total += STAGE_WEIGHTS.get(stage_name, 0.0) * (state.progress_percent / 100.0)
        return total * 100.0

    def payload(self) -> dict[str, Any]:
        stages = [self._stages[stage_name].to_payload() for stage_name in STAGE_ORDER if stage_name in self._stages]
        return {
            "job_id": self.job_id,
            "status": self._pipeline_status,
            "overall_progress_percent": round(self._overall_progress(), 2),
            "current_stage": self._current_stage,
            "updated_at": _now_iso(),
            "stages": stages,
        }

    def _write(self) -> None:
        if not self.write_status:
            return
        ensure_directory(self.status_path.parent)
        self.status_path.write_text(
            json.dumps(self.payload(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


__all__ = ["PipelineMonitor"]
