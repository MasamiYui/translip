"""LabConfig env overrides."""
from __future__ import annotations

from translip_lab.config import load_config


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSLIP_LAB_HOME", str(tmp_path))
    monkeypatch.delenv("TRANSLIP_LAB_RUNS_DIR", raising=False)
    cfg = load_config()
    assert cfg.home == tmp_path
    assert cfg.datasets_dir == tmp_path / "datasets"
    assert cfg.runs_dir == tmp_path / "runs"


def test_translip_cmd_is_split(monkeypatch):
    monkeypatch.setenv("TRANSLIP_LAB_TRANSLIP_CMD", "uv run translip")
    assert load_config().translip_cmd == ("uv", "run", "translip")
