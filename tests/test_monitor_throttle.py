from __future__ import annotations

import json
from pathlib import Path

from translip.orchestration.monitor import PipelineMonitor


def _monitor(tmp_path: Path, interval: float) -> PipelineMonitor:
    return PipelineMonitor(
        job_id="job-1",
        status_path=tmp_path / "pipeline-status.json",
        write_status=True,
        item_order=["stage1"],
        item_weights={"stage1": 1.0},
        status_update_interval_sec=interval,
    )


def test_no_throttle_writes_every_update(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, 0.0)
    monitor.start_stage("stage1")
    monitor.update_stage_progress("stage1", 10.0)
    monitor.update_stage_progress("stage1", 20.0)
    assert monitor._write_count == 3


def test_throttle_skips_intermediate_running_writes(tmp_path: Path) -> None:
    # A large interval means rapid running-progress updates are throttled, but the
    # forced start still writes.
    monitor = _monitor(tmp_path, 100.0)
    monitor.start_stage("stage1")  # forced
    monitor.update_stage_progress("stage1", 10.0)  # throttled
    monitor.update_stage_progress("stage1", 20.0)  # throttled
    assert monitor._write_count == 1


def test_terminal_transitions_always_write(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, 100.0)
    monitor.start_stage("stage1")  # forced (count 1)
    monitor.update_stage_progress("stage1", 50.0)  # throttled
    monitor.complete_stage("stage1")  # terminal -> forced (count 2)
    assert monitor._write_count == 2

    # The persisted file reflects the final (forced) state, not the throttled 50%.
    payload = json.loads((tmp_path / "pipeline-status.json").read_text(encoding="utf-8"))
    stage = next(s for s in payload["stages"] if s["stage_name"] == "stage1")
    assert stage["status"] == "succeeded"
    assert stage["progress_percent"] == 100.0


def test_fail_and_finalize_force_writes(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, 100.0)
    monitor.start_stage("stage1")
    monitor.update_stage_progress("stage1", 30.0)  # throttled
    before = monitor._write_count
    monitor.fail_stage("stage1", error="boom")
    monitor.finalize(status="failed")
    assert monitor._write_count > before
    payload = json.loads((tmp_path / "pipeline-status.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
