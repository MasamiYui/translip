from __future__ import annotations

import json
import time
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
    def __init__(
        self,
        *,
        job_id: str,
        status_path: Path,
        write_status: bool = True,
        item_order: list[str] | None = None,
        item_weights: dict[str, float] | None = None,
        status_update_interval_sec: float = 0.0,
    ) -> None:
        self.job_id = job_id
        self.status_path = status_path
        self.write_status = write_status
        # Throttle intermediate "running" progress writes to at most one per
        # interval to cut disk churn; 0 disables throttling. Status transitions
        # (start/complete/fail/finalize) always force a write, so the terminal
        # state is never lost (ARCH-10 / wires the previously dead field).
        self._status_update_interval_sec = max(0.0, float(status_update_interval_sec))
        self._last_write_monotonic = 0.0
        self._write_count = 0
        self._stages: dict[str, _StageState] = {}
        self._pipeline_status = "pending"
        self._current_stage: str | None = None
        self._item_order = list(item_order) if item_order is not None else list(STAGE_ORDER)
        self._item_weights = dict(item_weights) if item_weights is not None else dict(STAGE_WEIGHTS)

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
        self._write(force=True)

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
        # Terminal stage states always persist; only intermediate progress throttles.
        self._write(force=status != "running")

    def complete_stage(self, stage_name: str, *, status: str = "succeeded", current_step: str = "completed") -> None:
        self.update_stage_progress(stage_name, 100.0, current_step, status=status)

    def fail_stage(
        self,
        stage_name: str,
        *,
        error: str,
        pipeline_status: str = "failed",
    ) -> None:
        state = self._stages.get(stage_name)
        progress_percent = state.progress_percent if state is not None else 0.0
        self.update_stage_progress(stage_name, progress_percent, error, status="failed")
        self._pipeline_status = pipeline_status
        self._current_stage = stage_name
        self._write(force=True)

    def finalize(self, *, status: str) -> None:
        self._pipeline_status = status
        self._write(force=True)

    def _overall_progress(self) -> float:
        total = 0.0
        for stage_name in self._item_order:
            state = self._stages.get(stage_name)
            if state is None:
                continue
            total += self._item_weights.get(stage_name, 0.0) * (state.progress_percent / 100.0)
        return total * 100.0

    def payload(self) -> dict[str, Any]:
        stages = [self._stages[stage_name].to_payload() for stage_name in self._item_order if stage_name in self._stages]
        nodes = [{**stage, "node_name": stage["stage_name"]} for stage in stages]
        return {
            "job_id": self.job_id,
            "status": self._pipeline_status,
            "overall_progress_percent": round(self._overall_progress(), 2),
            "current_stage": self._current_stage,
            "updated_at": _now_iso(),
            "stages": stages,
            "nodes": nodes,
        }

    def _write(self, *, force: bool = False) -> None:
        if not self.write_status:
            return
        now = time.monotonic()
        if not force and self._status_update_interval_sec > 0:
            if now - self._last_write_monotonic < self._status_update_interval_sec:
                return  # throttled — a later forced/timed write will catch up
        self._last_write_monotonic = now
        ensure_directory(self.status_path.parent)
        self.status_path.write_text(
            json.dumps(self.payload(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._write_count += 1


__all__ = ["PipelineMonitor"]
