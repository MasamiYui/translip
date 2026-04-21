from __future__ import annotations

import json
from pathlib import Path

from translip.speaker_review.decisions import apply_speaker_decisions, write_speaker_corrected_artifacts
from translip.speaker_review.diagnostics import build_speaker_diagnostics, build_speaker_review_plan


def test_speaker_diagnostics_flags_short_island_and_low_sample_speaker() -> None:
    diagnostics = build_speaker_diagnostics(_segments_payload())

    speakers = {row["speaker_label"]: row for row in diagnostics["speakers"]}
    assert "low_sample_speaker" in speakers["SPEAKER_01"]["risk_flags"]

    sandwiched_runs = [
        row for row in diagnostics["speaker_runs"] if "sandwiched_run" in row["risk_flags"]
    ]
    assert sandwiched_runs
    assert sandwiched_runs[0]["speaker_label"] == "SPEAKER_01"

    review_plan = build_speaker_review_plan(diagnostics)
    assert review_plan["summary"]["review_item_count"] > 0
    assert any(item["item_type"] == "speaker_run" for item in review_plan["items"])


def test_apply_speaker_decisions_relabels_segments_and_tracks_non_cloneable() -> None:
    corrected, meta = apply_speaker_decisions(
        _segments_payload(),
        {
            "decisions": [
                {
                    "item_id": "run-0002",
                    "item_type": "speaker_run",
                    "decision": "merge_to_surrounding_speaker",
                    "source_speaker_label": "SPEAKER_01",
                    "segment_ids": ["seg-0002"],
                },
                {
                    "item_id": "speaker:SPEAKER_02",
                    "item_type": "speaker_profile",
                    "decision": "mark_non_cloneable",
                    "source_speaker_label": "SPEAKER_02",
                },
            ]
        },
    )

    rows = {row["id"]: row for row in corrected["segments"]}
    assert rows["seg-0002"]["speaker_label"] == "SPEAKER_00"
    assert rows["seg-0002"]["original_speaker_label"] == "SPEAKER_01"
    assert rows["seg-0002"]["speaker_correction"]["decision"] == "merge_to_surrounding_speaker"
    assert meta["changed_segment_count"] == 1
    assert meta["non_cloneable_speakers"] == ["SPEAKER_02"]


def test_write_speaker_corrected_artifacts_outputs_json_srt_and_manifest(tmp_path: Path) -> None:
    segments_path = tmp_path / "segments.zh.corrected.json"
    decisions_path = tmp_path / "manual_speaker_decisions.zh.json"
    output_path = tmp_path / "segments.zh.speaker-corrected.json"
    srt_path = tmp_path / "segments.zh.speaker-corrected.srt"
    manifest_path = tmp_path / "speaker-review-manifest.json"
    _write_json(segments_path, _segments_payload())
    _write_json(
        decisions_path,
        {
            "decisions": [
                {
                    "item_id": "segment:seg-0002",
                    "item_type": "segment",
                    "decision": "relabel_to_previous_speaker",
                    "source_speaker_label": "SPEAKER_01",
                    "segment_ids": ["seg-0002"],
                }
            ]
        },
    )

    manifest = write_speaker_corrected_artifacts(
        source_segments_path=segments_path,
        decisions_path=decisions_path,
        output_segments_path=output_path,
        output_srt_path=srt_path,
        manifest_path=manifest_path,
    )

    assert manifest["summary"]["changed_segment_count"] == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["segments"][1]["speaker_label"] == "SPEAKER_00"
    assert "[SPEAKER_00] 插一句" in srt_path.read_text(encoding="utf-8")


def _segments_payload() -> dict:
    return {
        "segments": [
            {"id": "seg-0001", "start": 0.0, "end": 1.8, "duration": 1.8, "text": "第一句", "speaker_label": "SPEAKER_00", "language": "zh"},
            {"id": "seg-0002", "start": 1.86, "end": 2.46, "duration": 0.6, "text": "插一句", "speaker_label": "SPEAKER_01", "language": "zh"},
            {"id": "seg-0003", "start": 2.5, "end": 4.0, "duration": 1.5, "text": "继续说话", "speaker_label": "SPEAKER_00", "language": "zh"},
            {"id": "seg-0004", "start": 4.6, "end": 24.8, "duration": 20.2, "text": "您好", "speaker_label": "SPEAKER_02", "language": "zh"},
        ]
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
