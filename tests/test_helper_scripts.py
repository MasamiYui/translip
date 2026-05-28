from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    script_path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_task_a_to_d_accepts_voxcpm2_tts_backend() -> None:
    module = _load_script("run_task_a_to_d.py")

    args = module.build_parser().parse_args(
        [
            "--input",
            "input.mp4",
            "--tts-backend",
            "voxcpm2",
        ]
    )

    assert args.tts_backend == "voxcpm2"

def test_run_task_a_to_e_accepts_voxcpm2_tts_backend() -> None:
    module = _load_script("run_task_a_to_e.py")

    args = module.build_parser().parse_args(
        [
            "--input",
            "input.mp4",
            "--tts-backend",
            "voxcpm2",
        ]
    )

    assert args.tts_backend == "voxcpm2"
