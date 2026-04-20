from __future__ import annotations

import json
from pathlib import Path

from translip.transcription.ocr_correction import (
    CorrectionConfig,
    correct_asr_segments_with_ocr,
)


def _segments_payload() -> dict:
    return {
        "input": {"path": "voice.mp3"},
        "model": {"asr_backend": "faster-whisper"},
        "stats": {"segment_count": 4, "speaker_count": 2},
        "segments": [
            {
                "id": "seg-0001",
                "start": 0.21,
                "end": 2.81,
                "duration": 2.6,
                "speaker_label": "SPEAKER_00",
                "text": "虽扛下了天洁",
                "language": "zh",
            },
            {
                "id": "seg-0002",
                "start": 5.01,
                "end": 10.01,
                "duration": 5.0,
                "speaker_label": "SPEAKER_00",
                "text": "为师现在就为你们重塑肉身",
                "language": "zh",
            },
            {
                "id": "seg-0003",
                "start": 18.11,
                "end": 20.11,
                "duration": 2.0,
                "speaker_label": "SPEAKER_00",
                "text": "头发龙祖",
                "language": "zh",
            },
            {
                "id": "seg-0004",
                "start": 87.88,
                "end": 93.05,
                "duration": 5.17,
                "speaker_label": "SPEAKER_01",
                "text": "小燕拭摩",
                "language": "zh",
            },
        ],
    }


def _ocr_payload() -> dict:
    return {
        "events": [
            {"event_id": "evt-0001", "start": 0.75, "end": 2.50, "text": "虽扛下了天劫", "confidence": 0.996},
            {"event_id": "evt-0002", "start": 5.25, "end": 6.75, "text": "为师现在就为你们", "confidence": 0.999},
            {"event_id": "evt-0003", "start": 7.25, "end": 8.00, "text": "重塑", "confidence": 0.999},
            {"event_id": "evt-0004", "start": 8.75, "end": 9.50, "text": "肉身", "confidence": 0.999},
            {"event_id": "evt-0005", "start": 18.50, "end": 19.75, "text": "讨伐龙族", "confidence": 0.999},
            {"event_id": "evt-0006", "start": 91.75, "end": 92.25, "text": "小爷是魔", "confidence": 0.999},
            {"event_id": "evt-0007", "start": 93.25, "end": 94.00, "text": "那又如何", "confidence": 0.999},
        ]
    }


def test_correct_asr_segments_uses_single_and_merged_ocr_text() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    texts = [row["text"] for row in result.corrected_payload["segments"]]
    assert texts == ["虽扛下了天劫", "为师现在就为你们重塑肉身", "讨伐龙族", "小爷是魔"]
    decisions = {row["segment_id"]: row["decision"] for row in result.report["segments"]}
    assert decisions["seg-0001"] == "use_ocr"
    assert decisions["seg-0002"] == "merge_ocr"
    assert decisions["seg-0003"] == "use_ocr"
    assert decisions["seg-0004"] == "use_ocr"
    assert result.report["summary"]["corrected_count"] == 4
    assert result.report["summary"]["algorithm_version"] == "ocr-guided-asr-correction-v1"


def test_ocr_only_event_is_reported_without_inserting_segment() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    assert len(result.corrected_payload["segments"]) == 4
    assert result.report["ocr_only_events"] == [
        {
            "event_id": "evt-0007",
            "start": 93.25,
            "end": 94.0,
            "text": "那又如何",
            "decision": "ocr_only",
            "action": "reported_only",
            "needs_review": True,
        }
    ]


def test_low_confidence_ocr_keeps_asr() -> None:
    payload = _ocr_payload()
    payload["events"][0]["confidence"] = 0.1

    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=payload,
        config=CorrectionConfig.standard(),
    )

    assert result.corrected_payload["segments"][0]["text"] == "虽扛下了天洁"
    assert result.report["segments"][0]["decision"] == "use_asr"
    assert result.report["segments"][0]["needs_review"] is False


def test_write_correction_artifacts(tmp_path: Path) -> None:
    from translip.transcription.ocr_correction import write_correction_artifacts

    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    artifacts = write_correction_artifacts(result, output_dir=tmp_path / "asr-ocr-correct" / "voice")

    assert artifacts.corrected_segments_path.exists()
    assert artifacts.corrected_srt_path.exists()
    assert artifacts.report_path.exists()
    assert artifacts.manifest_path.exists()
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["config"]["preset"] == "standard"
