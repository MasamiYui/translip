from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest


def test_run_stage_command_terminates_process_when_cancel_requested(tmp_path: Path) -> None:
    from translip.orchestration.subprocess_runner import (
        StageSubprocessCancelled,
        run_stage_command,
    )

    cancel = threading.Event()

    def request_cancel() -> None:
        time.sleep(0.4)
        cancel.set()

    threading.Thread(target=request_cancel, daemon=True).start()

    with pytest.raises(StageSubprocessCancelled):
        run_stage_command(
            [
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(30)",
            ],
            log_path=tmp_path / "stage.log",
            should_cancel=cancel.is_set,
        )

    assert "started" in (tmp_path / "stage.log").read_text(encoding="utf-8")
