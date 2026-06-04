"""Tests for the iterative auto-fix loop (server/routes/autofix.py).

The loop's decision logic is exercised as pure functions; the multi-round
worker is driven end-to-end with the CLI subprocesses and the dub-qa
re-evaluation stubbed, so we can assert iteration / accept / rollback /
convergence behaviour without any TTS models or real rendering.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from sqlmodel import Session, SQLModel, create_engine, select

import translip.server.routes.autofix as autofix
from translip.server.models import Analysis, Task


# --------------------------------------------------------------------------- #
# Pure decision helpers
# --------------------------------------------------------------------------- #


def test_auto_fix_targets_filters_attempted_dedups_and_caps() -> None:
    report = {"remediation": {"repair_directive": {"segment_ids": ["s1", "s2", "s2", "s3", "s4"]}}}
    # s2 already attempted → dropped; duplicates collapsed; capped at max_items.
    assert autofix._auto_fix_targets(report, {"s2"}, 10) == ["s1", "s3", "s4"]
    assert autofix._auto_fix_targets(report, set(), 2) == ["s1", "s2"]
    # No remediation / directive → empty (loop converges).
    assert autofix._auto_fix_targets({}, set(), 10) == []
    assert autofix._auto_fix_targets({"remediation": {"repair_directive": None}}, set(), 10) == []


def test_round_accepted_gate() -> None:
    # Clear score gain wins.
    assert autofix._round_accepted(70.0, 70.6, 10, 10) is True
    # Below the epsilon and no fewer problems → reject (noise).
    assert autofix._round_accepted(70.0, 70.2, 10, 10) is False
    # Near-tie on score but strictly fewer problems → accept.
    assert autofix._round_accepted(70.0, 70.1, 10, 8) is True
    # Regression → reject even if problems dropped.
    assert autofix._round_accepted(70.0, 69.0, 10, 5) is False
    # No scores → fall back to problem count.
    assert autofix._round_accepted(None, None, 10, 8) is True
    assert autofix._round_accepted(None, None, 10, 10) is False


def test_merge_selected_segments_unions_by_id(tmp_path: Path) -> None:
    base = [{"segment_id": "s1", "selected_audio_path": "a.wav"}]
    round_path = tmp_path / "selected_segments.en.json"
    round_path.write_text(
        json.dumps({"segments": [{"segment_id": "s2", "selected_audio_path": "b.wav"}]}),
        encoding="utf-8",
    )
    merged = autofix._merge_selected_segments(base, round_path)
    ids = sorted(s["segment_id"] for s in merged)
    assert ids == ["s1", "s2"]  # earlier accepted fix (s1) preserved alongside the new one
    # Missing round file → base unchanged.
    assert autofix._merge_selected_segments(base, tmp_path / "missing.json") == base


# --------------------------------------------------------------------------- #
# End-to-end worker (CLI + re-evaluation stubbed)
# --------------------------------------------------------------------------- #


def _make_pipeline(output_root: Path) -> None:
    """Lay out the minimal artifacts the worker checks for existence."""
    (output_root / "task-c" / "voice").mkdir(parents=True, exist_ok=True)
    (output_root / "task-c" / "voice" / "translation.en.json").write_text("{}", encoding="utf-8")
    (output_root / "task-b" / "voice").mkdir(parents=True, exist_ok=True)
    (output_root / "task-b" / "voice" / "speaker_profiles.json").write_text("{}", encoding="utf-8")
    (output_root / "task-a" / "voice").mkdir(parents=True, exist_ok=True)
    (output_root / "task-a" / "voice" / "segments.zh.json").write_text("{}", encoding="utf-8")
    td = output_root / "task-d" / "voice" / "spk_0001"
    td.mkdir(parents=True, exist_ok=True)
    (td / "speaker_segments.en.json").write_text("{}", encoding="utf-8")
    stage1 = output_root / "stage1" / "clip"
    stage1.mkdir(parents=True, exist_ok=True)
    (stage1 / "background.mp3").write_text("x", encoding="utf-8")
    # Pre-existing task-e mix so snapshot/restore has something to copy.
    voice = output_root / "task-e" / "voice"
    voice.mkdir(parents=True, exist_ok=True)
    (voice / "mix_report.en.json").write_text(json.dumps({"marker": "original"}), encoding="utf-8")
    (voice / "task-e-manifest.json").write_text("{}", encoding="utf-8")
    # Keep moss out of the picture; pin a non-moss backend + cpu device.
    (output_root / "request.json").write_text(
        json.dumps({"tts_backend": "qwen3tts", "device": "cpu"}), encoding="utf-8"
    )


def _seed_task_and_baseline(engine, output_root: Path, *, score: float, problems: int, targets: list[str]) -> None:
    """Insert the task and a succeeded baseline dub-qa whose report carries the
    auto-fixable targets the loop will pull from."""
    report = {
        "scorecard": {"score": score},
        "qa_summary": {"problem_segment_count": problems},
        "remediation": {"repair_directive": {"segment_ids": targets}},
    }
    rel = "analysis/baseline/dub_qa_report.en.json"
    report_path = output_root / rel
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with Session(engine) as session:
        session.add(
            Task(
                id="task-fix",
                name="fixture",
                status="succeeded",
                input_path=str(output_root / "in.mp4"),
                output_root=str(output_root),
                source_lang="zh",
                target_lang="en",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
        )
        session.add(
            Analysis(
                id="ana-baseline",
                task_id="task-fix",
                analysis_type="dub-qa",
                status="succeeded",
                target_lang="en",
                source_lang="zh",
                params={},
                result={"score": score, "problem_segment_count": problems},
                report_path=rel,
                created_at=datetime.now(),
            )
        )
        session.commit()


def _install_stubs(monkeypatch, engine, output_root: Path, eval_queue: list[dict]):
    """Stub the CLI runner (writes the per-round selected_segments) and dub-qa
    re-evaluation (pops a scripted result per round)."""
    monkeypatch.setattr(autofix, "engine", engine)

    def fake_run_cli(args, log_path):
        head = str(args[0])
        if head == "run-dub-repair":
            seg_ids = [str(args[i + 1]) for i, a in enumerate(args) if a == "--segment-id"]
            run_dir = output_root / "task-d" / "voice" / "repair-run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "selected_segments.en.json").write_text(
                json.dumps(
                    {
                        "stats": {"selected_count": len(seg_ids)},
                        "segments": [
                            {"segment_id": s, "selected_audio_path": f"{s}.wav"} for s in seg_ids
                        ],
                    }
                ),
                encoding="utf-8",
            )
        elif head == "render-dub":
            # Simulate the render mutating task-e so rollback is observable.
            (output_root / "task-e" / "voice" / "mix_report.en.json").write_text(
                json.dumps({"marker": "rendered"}), encoding="utf-8"
            )

    monkeypatch.setattr(autofix, "_run_cli", fake_run_cli)

    calls = {"n": 0}

    def fake_build_dub_qa(request):
        spec = eval_queue[calls["n"]]
        calls["n"] += 1
        out_dir = Path(request.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "scorecard": {"score": spec["score"]},
            "qa_summary": {"problem_segment_count": spec["problems"]},
            "remediation": {"repair_directive": {"segment_ids": spec.get("targets", [])}},
        }
        report_path = out_dir / "dub_qa_report.en.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        manifest = {"summary": {"score": spec["score"], "problem_segment_count": spec["problems"]}}
        return SimpleNamespace(
            report=report,
            manifest=manifest,
            artifacts=SimpleNamespace(report_path=report_path),
        )

    monkeypatch.setattr(autofix, "build_dub_qa", fake_build_dub_qa)
    return calls


def _run_job(engine, params: dict) -> Analysis:
    with Session(engine) as session:
        job = Analysis(
            id="fix-job",
            task_id="task-fix",
            analysis_type="auto-fix",
            status="pending",
            target_lang="en",
            source_lang="zh",
            params=params,
        )
        session.add(job)
        session.commit()
    autofix._run_auto_fix_in_thread("fix-job")
    with Session(engine) as session:
        return session.get(Analysis, "fix-job")


def test_auto_fix_iterates_until_converged(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fix.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    output_root = tmp_path / "out"
    _make_pipeline(output_root)
    _seed_task_and_baseline(engine, output_root, score=60.0, problems=6, targets=["s1", "s2"])

    # Round 1: 60 -> 72 (accept), still 2 problems left to chase.
    # Round 2: 72 -> 80 (accept), no targets left -> converge before round 3.
    eval_queue = [
        {"score": 72.0, "problems": 4, "targets": ["s3", "s4"]},
        {"score": 80.0, "problems": 2, "targets": []},
    ]
    _install_stubs(monkeypatch, engine, output_root, eval_queue)

    job = _run_job(engine, {"max_rounds": 3, "max_items": 20, "segment_ids": ["s1", "s2"]})

    assert job.status == "succeeded", job.error_message
    result = job.result
    assert result["before_score"] == 60.0
    assert result["after_score"] == 80.0
    assert result["rounds_run"] == 2  # third round had no targets → stopped
    assert [r["accepted"] for r in result["rounds"]] == [True, True]
    assert result["rolled_back"] is False
    assert result["new_analysis_id"] is not None
    assert result["repaired_count"] == 4  # 2 segments each accepted round

    # Each accepted round promoted a fresh dub-qa analysis (baseline + 2).
    with Session(engine) as session:
        dubqa = session.exec(
            select(Analysis).where(Analysis.task_id == "task-fix").where(Analysis.analysis_type == "dub-qa")
        ).all()
    assert len(dubqa) == 3

    # The cumulative selected set accumulated both rounds' repairs (s1..s4),
    # so the final render kept earlier fixes.
    cumulative = json.loads(
        (output_root / "task-d" / "voice" / "repair-run" / "selected_segments.cumulative.en.json").read_text(
            encoding="utf-8"
        )
    )
    assert sorted(s["segment_id"] for s in cumulative["segments"]) == ["s1", "s2", "s3", "s4"]


def test_auto_fix_rolls_back_a_regressing_round(tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'fix.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    output_root = tmp_path / "out"
    _make_pipeline(output_root)
    _seed_task_and_baseline(engine, output_root, score=70.0, problems=5, targets=["s1"])

    # The only round makes it worse (70 -> 64): must roll back, keep nothing.
    eval_queue = [{"score": 64.0, "problems": 7, "targets": []}]
    _install_stubs(monkeypatch, engine, output_root, eval_queue)

    job = _run_job(engine, {"max_rounds": 3, "segment_ids": ["s1"]})

    assert job.status == "succeeded", job.error_message
    result = job.result
    assert result["after_score"] == 70.0  # stayed at the baseline (best) score
    assert result["rounds_run"] == 1
    assert result["rounds"][0]["accepted"] is False
    assert result["rolled_back"] is True
    assert result["new_analysis_id"] is None
    assert job.report_path is None

    # task-e was restored to the pre-round snapshot (render's mutation undone).
    mix = json.loads((output_root / "task-e" / "voice" / "mix_report.en.json").read_text(encoding="utf-8"))
    assert mix["marker"] == "original"

    # No extra dub-qa analysis was promoted (only the baseline remains).
    with Session(engine) as session:
        dubqa = session.exec(
            select(Analysis).where(Analysis.task_id == "task-fix").where(Analysis.analysis_type == "dub-qa")
        ).all()
    assert len(dubqa) == 1
