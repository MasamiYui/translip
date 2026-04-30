import json
from pathlib import Path

from translip.quality.dub_benchmark import DubBenchmarkRequest, build_dub_benchmark


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_dub_benchmark_blocks_when_subtitle_audio_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    _write_json(
        root / "task-e" / "voice" / "mix_report.en.json",
        {
            "stats": {
                "placed_count": 9,
                "skipped_count": 1,
                "quality_summary": {
                    "total_count": 10,
                    "overall_status_counts": {"passed": 10},
                    "speaker_status_counts": {"passed": 10},
                    "intelligibility_status_counts": {"passed": 10},
                },
                "audible_coverage": {
                    "failed_count": 1,
                    "failed_segment_ids": ["seg-0007"],
                    "min_coverage_ratio": 0.0,
                    "average_coverage_ratio": 0.9,
                },
            }
        },
    )

    result = build_dub_benchmark(
        DubBenchmarkRequest(
            pipeline_root=root,
            output_dir=root / "benchmark" / "voice",
            target_lang="en",
        )
    )

    payload = json.loads(result.artifacts.benchmark_path.read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert "audible_coverage_failed" in payload["reasons"]
    assert payload["metrics"]["coverage_ratio"] == 0.9
    assert payload["metrics"]["audible_failed_count"] == 1
    assert result.artifacts.report_path.exists()
    assert result.artifacts.manifest_path.exists()


def test_dub_benchmark_marks_review_for_character_and_repair_risks(tmp_path: Path) -> None:
    root = tmp_path / "pipeline"
    _write_json(
        root / "task-e" / "voice" / "mix_report.en.json",
        {
            "stats": {
                "placed_count": 20,
                "skipped_count": 0,
                "quality_summary": {
                    "total_count": 20,
                    "overall_status_counts": {"passed": 19, "review": 1},
                    "speaker_status_counts": {"passed": 18, "failed": 2},
                    "intelligibility_status_counts": {"passed": 20},
                },
                "audible_coverage": {"failed_count": 0, "failed_segment_ids": []},
            }
        },
    )
    _write_json(
        root / "task-d" / "voice" / "character-ledger" / "character_ledger.en.json",
        {
            "stats": {
                "character_count": 2,
                "review_count": 1,
                "blocked_count": 0,
                "voice_mismatch_count": 1,
            },
            "characters": [
                {"character_id": "char_0001", "review_status": "passed", "risk_flags": []},
                {"character_id": "char_0002", "review_status": "review", "risk_flags": ["pitch_class_drift"]},
            ],
        },
    )
    _write_json(
        root / "task-d" / "voice" / "repair-run" / "repair-run-manifest.json",
        {
            "stats": {
                "attempt_count": 8,
                "selected_count": 3,
                "manual_required_count": 1,
            }
        },
    )

    result = build_dub_benchmark(
        DubBenchmarkRequest(
            pipeline_root=root,
            output_dir=root / "benchmark" / "voice",
            target_lang="en",
        )
    )

    payload = json.loads(result.artifacts.benchmark_path.read_text(encoding="utf-8"))
    assert payload["status"] == "review_required"
    assert "character_voice_review_required" in payload["reasons"]
    assert "repair_manual_required" in payload["reasons"]
    assert payload["metrics"]["character_review_count"] == 1
    assert payload["metrics"]["repair_manual_required_count"] == 1
    assert 80.0 <= payload["score"] < 100.0
