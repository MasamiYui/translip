from __future__ import annotations

import json
from pathlib import Path

from translip.orchestration.monitor import PipelineMonitor


def _monitor(tmp_path: Path, interval: float) -> PipelineMonitor:
    return PipelineMonitor(
        job_id="job-1",
        status_path=tmp_path / "pipeline-status.json",
        write_status=True,
        item_order=["separation"],
        item_weights={"separation": 1.0},
        status_update_interval_sec=interval,
    )


def test_no_throttle_writes_every_update(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, 0.0)
    monitor.start_stage("separation")
    monitor.update_stage_progress("separation", 10.0)
    monitor.update_stage_progress("separation", 20.0)
    assert monitor._write_count == 3


def test_throttle_skips_intermediate_running_writes(tmp_path: Path) -> None:
    # A large interval means rapid running-progress updates are throttled, but the
    # forced start still writes.
    monitor = _monitor(tmp_path, 100.0)
    monitor.start_stage("separation")  # forced
    monitor.update_stage_progress("separation", 10.0)  # throttled
    monitor.update_stage_progress("separation", 20.0)  # throttled
    assert monitor._write_count == 1


def test_terminal_transitions_always_write(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, 100.0)
    monitor.start_stage("separation")  # forced (count 1)
    monitor.update_stage_progress("separation", 50.0)  # throttled
    monitor.complete_stage("separation")  # terminal -> forced (count 2)
    assert monitor._write_count == 2

    # The persisted file reflects the final (forced) state, not the throttled 50%.
    payload = json.loads((tmp_path / "pipeline-status.json").read_text(encoding="utf-8"))
    stage = next(s for s in payload["stages"] if s["stage_name"] == "separation")
    assert stage["status"] == "succeeded"
    assert stage["progress_percent"] == 100.0


def test_fail_and_finalize_force_writes(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, 100.0)
    monitor.start_stage("separation")
    monitor.update_stage_progress("separation", 30.0)  # throttled
    before = monitor._write_count
    monitor.fail_stage("separation", error="boom")
    monitor.finalize(status="failed")
    assert monitor._write_count > before
    payload = json.loads((tmp_path / "pipeline-status.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
