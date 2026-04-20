from __future__ import annotations

import json
from pathlib import Path


def test_transcript_correction_adapter_writes_artifacts_and_summary(tmp_path: Path) -> None:
    from translip.server.atomic_tools.adapters.transcript_correction import TranscriptCorrectionAdapter

    input_dir = tmp_path / "input"
    segments_file = input_dir / "segments_file" / "segments.zh.json"
    ocr_file = input_dir / "ocr_events_file" / "ocr_events.json"
    segments_file.parent.mkdir(parents=True)
    ocr_file.parent.mkdir(parents=True)
    segments_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "id": "seg-0001",
                        "start": 0.0,
                        "end": 2.0,
                        "duration": 2.0,
                        "speaker_label": "SPEAKER_00",
                        "text": "虽扛下了天洁",
                        "language": "zh",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ocr_file.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "event_id": "evt-0001",
                        "start": 0.1,
                        "end": 1.8,
                        "text": "虽扛下了天劫",
                        "confidence": 0.99,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "output"
    progress: list[tuple[float, str | None]] = []

    result = TranscriptCorrectionAdapter().run(
        {
            "segments_file_id": "segments-file-id",
            "ocr_events_file_id": "ocr-events-file-id",
            "enabled": True,
            "preset": "standard",
            "ocr_only_policy": "report_only",
        },
        input_dir,
        output_dir,
        lambda pct, step=None: progress.append((pct, step)),
    )

    assert (output_dir / "segments.zh.corrected.json").exists()
    assert (output_dir / "segments.zh.corrected.srt").exists()
    assert (output_dir / "correction-report.json").exists()
    assert (output_dir / "correction-manifest.json").exists()
    corrected = json.loads((output_dir / "segments.zh.corrected.json").read_text(encoding="utf-8"))
    assert corrected["segments"][0]["text"] == "虽扛下了天劫"
    assert result["segment_count"] == 1
    assert result["corrected_count"] == 1
    assert result["ocr_only_count"] == 0
    assert result["algorithm_version"] == "ocr-guided-asr-correction-v1"
    assert result["corrected_segments_file"] == "segments.zh.corrected.json"
    assert progress[0] == (5.0, "loading_inputs")


def test_transcript_correction_adapter_validates_default_params() -> None:
    from translip.server.atomic_tools.adapters.transcript_correction import TranscriptCorrectionAdapter

    params = TranscriptCorrectionAdapter().validate_params(
        {
            "segments_file_id": "segments-file-id",
            "ocr_events_file_id": "ocr-events-file-id",
        }
    )

    assert params["enabled"] is True
    assert params["preset"] == "standard"
    assert params["ocr_only_policy"] == "report_only"
