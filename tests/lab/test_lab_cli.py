"""CLI plumbing (no ML): listing, dry-run, report/compare round-trip."""
from __future__ import annotations

import json
import subprocess
import sys

from translip_lab import cli


def test_scenarios_register_in_fresh_process():
    # A fresh interpreter must see all scenarios (cli imports the scenarios package).
    out = subprocess.run([sys.executable, "-m", "translip_lab", "scenarios"],
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert "asr" in out.stdout and "ocr-detect" in out.stdout and "subtitle-erase" in out.stdout


def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSLIP_LAB_HOME", str(tmp_path))


def test_doctor_runs(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    rc = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "ffmpeg" in out
    assert rc == 0  # ffmpeg is on PATH in the test env


def test_evaluate_gates():
    manifest = {"aggregates": {
        "asr": {"primary_metric": "cer", "higher_is_better": False, "mean": 0.3},
        "sep": {"primary_metric": "si_sdr", "higher_is_better": True, "mean": 8.0},
    }}
    ok, _ = cli._evaluate_gates("asr=0.4,sep=5", manifest)   # 0.3<=0.4 and 8>=5
    assert ok is True
    fail, _ = cli._evaluate_gates("asr=0.2", manifest)       # 0.3<=0.2 → FAIL
    assert fail is False
    unknown, _ = cli._evaluate_gates("nope=1", manifest)     # missing key → FAIL
    assert unknown is False


def test_scenarios_and_datasets(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    assert cli.main(["scenarios"]) == 0
    out = capsys.readouterr().out
    assert "asr" in out and "ocr-detect" in out
    assert cli.main(["datasets"]) == 0
    assert "synthetic-subtitle" in capsys.readouterr().out


def test_run_dry_run_via_suite(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    rc = cli.main(["run", "--suite", "separation-synthetic", "--dry-run"])
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out


def test_run_dry_run_ad_hoc(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    rc = cli.main(["run", "--dataset", "synthetic-mix", "--scenario", "separation",
                   "--dataset-param", "clips=1", "--dry-run"])
    assert rc == 0


def test_report_and_compare_roundtrip(monkeypatch, tmp_path, capsys):
    _home(monkeypatch, tmp_path)
    runs = tmp_path / "runs"
    for rid, mean in (("runA", 0.2), ("runB", 0.3)):
        d = runs / rid
        d.mkdir(parents=True)
        (d / "run-manifest.json").write_text(json.dumps({
            "run_id": rid, "suite": "s", "dataset": "d", "scenarios": ["asr"],
            "aggregates": {"asr": {"primary_metric": "cer", "higher_is_better": False, "mean": mean}},
            "results": [],
        }), encoding="utf-8")

    assert cli.main(["list-runs"]) == 0
    assert cli.main(["report", "--run", "runA"]) == 0
    # candidate cer 0.3 > baseline 0.2 with lower-is-better → regression → exit 1
    assert cli.main(["compare", "--baseline", "runA", "--candidate", "runB"]) == 1
    assert "regressed" in capsys.readouterr().out
