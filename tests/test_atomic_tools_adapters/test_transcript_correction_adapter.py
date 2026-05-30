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
    assert params["llm_arbitration"] == "off"


def _write_review_case(input_dir: Path) -> None:
    segments_file = input_dir / "segments_file" / "segments.zh.json"
    ocr_file = input_dir / "ocr_events_file" / "ocr_events.json"
    segments_file.parent.mkdir(parents=True)
    ocr_file.parent.mkdir(parents=True)
    segments_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "id": "seg-review",
                        "start": 71.38,
                        "end": 72.62,
                        "duration": 1.24,
                        "speaker_label": "SPEAKER_00",
                        "text": "要恨就恨",
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
                        "event_id": "evt-full",
                        "start": 71.749,
                        "end": 74.999,
                        "text": "要恨就恨你们为什么生来就是妖",
                        "confidence": 0.998,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_adapter_threads_arbitrator_when_enabled(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters import transcript_correction as adapter_mod
    from translip.transcription.ocr_correction import ArbitrationVerdict

    calls: list = []

    def fake_build(mode: str):
        assert mode == "deepseek"
        def arbitrator(request):
            calls.append(request)
            return ArbitrationVerdict("use_ocr", "", "ocr is the full line")
        return arbitrator

    monkeypatch.setattr(adapter_mod, "_build_arbitrator", fake_build)

    input_dir = tmp_path / "input"
    _write_review_case(input_dir)
    result = adapter_mod.TranscriptCorrectionAdapter().run(
        {
            "segments_file_id": "a",
            "ocr_events_file_id": "b",
            "preset": "standard",
            "llm_arbitration": "deepseek",
        },
        input_dir,
        tmp_path / "output",
        lambda pct, step=None: None,
    )
    assert result["llm_arbitration"] == "deepseek"
    assert result["arbitrated_count"] == 1
    assert len(calls) == 1


def test_adapter_off_keeps_review_without_arbitration(tmp_path: Path) -> None:
    from translip.server.atomic_tools.adapters import transcript_correction as adapter_mod

    # With arbitration off, the review segment stays a review — no backend constructed, no network.
    input_dir = tmp_path / "input"
    _write_review_case(input_dir)
    result = adapter_mod.TranscriptCorrectionAdapter().run(
        {"segments_file_id": "a", "ocr_events_file_id": "b", "llm_arbitration": "off"},
        input_dir,
        tmp_path / "output",
        lambda pct, step=None: None,
    )
    assert result["llm_arbitration"] == "off"
    assert result["arbitrated_count"] == 0
    assert result["review_count"] == 1  # the review segment stays a review with no arbitrator
