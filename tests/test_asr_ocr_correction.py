from __future__ import annotations

import json
from pathlib import Path

from translip.transcription.ocr_correction import (
    ArbitrationVerdict,
    CorrectionConfig,
    correct_asr_segments_with_ocr,
    load_ocr_payload,
    load_segments_payload,
    write_correction_artifacts,
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


def test_late_ocr_match_persists_dubbing_and_subtitle_windows() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload={
            "segments": [
                {
                    "id": "seg-late",
                    "start": 13.35,
                    "end": 18.11,
                    "duration": 4.76,
                    "speaker_label": "SPEAKER_00",
                    "text": "召集全体成员",
                    "language": "zh",
                }
            ]
        },
        ocr_payload={
            "events": [
                {
                    "event_id": "evt-late",
                    "start": 16.25,
                    "end": 17.75,
                    "text": "召集全体成员",
                    "confidence": 0.999,
                }
            ]
        },
        config=CorrectionConfig.standard(),
    )

    segment = result.corrected_payload["segments"][0]
    assert segment["text"] == "召集全体成员"
    assert segment["timing"]["asr_window"] == {"start": 13.35, "end": 18.11, "duration": 4.76}
    assert segment["timing"]["ocr_window"] == {
        "start": 16.25,
        "end": 17.75,
        "duration": 1.5,
        "event_ids": ["evt-late"],
        "confidence": 0.999,
    }
    assert segment["timing"]["subtitle_window"] == {"start": 16.25, "end": 17.75, "duration": 1.5}
    assert segment["timing"]["dubbing_window"] == {
        "start": 15.65,
        "end": 18.11,
        "duration": 2.46,
        "policy": "late_ocr_anchor",
    }
    assert "asr_start_precedes_ocr_window" in segment["timing"]["warnings"]

    report_row = result.report["segments"][0]
    assert report_row["timing"]["dubbing_window"]["start"] == 15.65
    assert report_row["timing"]["subtitle_window"]["start"] == 16.25


def test_review_decision_does_not_claim_ocr_timing_window() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload={
            "segments": [
                {
                    "id": "seg-review",
                    "start": 71.38,
                    "end": 72.62,
                    "duration": 1.24,
                    "speaker_label": "SPEAKER_00",
                    "text": "要恨就恨",
                    "language": "zh",
                },
                {
                    "id": "seg-full",
                    "start": 72.62,
                    "end": 75.86,
                    "duration": 3.24,
                    "speaker_label": "SPEAKER_00",
                    "text": "要恨就恨你们为什么生来就是妖",
                    "language": "zh",
                },
            ]
        },
        ocr_payload={
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
        config=CorrectionConfig.standard(),
    )

    review_segment, full_segment = result.corrected_payload["segments"]
    assert result.report["segments"][0]["decision"] == "review"
    assert "timing" not in review_segment
    assert result.report["segments"][1]["decision"] == "use_ocr"
    assert full_segment["timing"]["ocr_window"]["event_ids"] == ["evt-full"]


def _detection_style_payload() -> dict:
    """The subtitle-detect 'detection.json' schema: start_time/end_time, no event_id."""
    events = []
    for event in _ocr_payload()["events"]:
        events.append(
            {
                "start_time": event["start"],
                "end_time": event["end"],
                "text": event["text"],
                "confidence": event["confidence"],
            }
        )
    return {"events": events}


def test_detection_style_ocr_events_are_normalized() -> None:
    # Feeding the detection.json schema (start_time/end_time) must yield the same corrections
    # as the ocr_events.json schema — guards against the silent zero-correction trap.
    detection_result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_detection_style_payload(),
        config=CorrectionConfig.standard(),
    )
    reference_result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )

    detection_texts = [row["text"] for row in detection_result.corrected_payload["segments"]]
    reference_texts = [row["text"] for row in reference_result.corrected_payload["segments"]]
    assert detection_texts == reference_texts == [
        "虽扛下了天劫",
        "为师现在就为你们重塑肉身",
        "讨伐龙族",
        "小爷是魔",
    ]
    assert detection_result.report["summary"]["corrected_count"] == 4


def test_correction_block_has_no_embedded_report_path() -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )
    assert "report_path" not in result.corrected_payload["correction"]


def _fmt_srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_to_srt(payload: dict) -> str:
    lines: list[str] = []
    for index, segment in enumerate(payload["segments"], start=1):
        lines += [
            str(index),
            f"{_fmt_srt_time(segment['start'])} --> {_fmt_srt_time(segment['end'])}",
            f"[{segment['speaker_label']}] {segment['text']}",
            "",
        ]
    return "\n".join(lines)


def _events_to_srt(payload: dict) -> str:
    lines: list[str] = []
    for index, event in enumerate(payload["events"], start=1):
        lines += [
            str(index),
            f"{_fmt_srt_time(event['start'])} --> {_fmt_srt_time(event['end'])}",
            event["text"],
            "",
        ]
    return "\n".join(lines)


def test_subtitle_inputs_yield_same_corrections_as_json(tmp_path: Path) -> None:
    asr_srt = tmp_path / "asr.srt"
    ocr_srt = tmp_path / "ocr.srt"
    asr_srt.write_text(_segments_to_srt(_segments_payload()), encoding="utf-8")
    ocr_srt.write_text(_events_to_srt(_ocr_payload()), encoding="utf-8")

    seg_payload = load_segments_payload(asr_srt)
    ocr_payload = load_ocr_payload(ocr_srt)

    # Speaker prefix round-trips from the ASR subtitle; OCR confidence defaults to 1.0.
    assert seg_payload["segments"][0]["speaker_label"] == "SPEAKER_00"
    assert seg_payload["segments"][3]["speaker_label"] == "SPEAKER_01"
    assert ocr_payload["events"][0]["confidence"] == 1.0

    srt_result = correct_asr_segments_with_ocr(
        segments_payload=seg_payload,
        ocr_payload=ocr_payload,
        config=CorrectionConfig.standard(),
    )
    json_result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )
    assert [s["text"] for s in srt_result.corrected_payload["segments"]] == [
        s["text"] for s in json_result.corrected_payload["segments"]
    ]


def test_load_segments_payload_passes_json_through(tmp_path: Path) -> None:
    path = tmp_path / "segments.json"
    path.write_text(json.dumps(_segments_payload(), ensure_ascii=False), encoding="utf-8")
    assert load_segments_payload(path) == _segments_payload()


def test_clean_srt_drops_speaker_prefix(tmp_path: Path) -> None:
    result = correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
    )
    artifacts = write_correction_artifacts(result, output_dir=tmp_path)

    assert artifacts.clean_srt_path.exists()
    speaker_srt = artifacts.corrected_srt_path.read_text(encoding="utf-8")
    clean_srt = artifacts.clean_srt_path.read_text(encoding="utf-8")
    assert "[SPEAKER_00]" in speaker_srt
    assert "[SPEAKER_" not in clean_srt
    assert "虽扛下了天劫" in clean_srt  # corrected text still present


class _StubArbitrator:
    def __init__(self, verdict: ArbitrationVerdict | None) -> None:
        self.verdict = verdict
        self.calls: list = []

    def __call__(self, request) -> ArbitrationVerdict | None:
        self.calls.append(request)
        return self.verdict


def _review_payloads() -> tuple[dict, dict]:
    # "要恨就恨" (4 chars) overlaps the long OCR line (13 chars): alignment passes but the
    # length ratio (3.25) blows past the standard gate (2.2) → deterministic "review".
    segments = {
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
    }
    ocr = {
        "events": [
            {
                "event_id": "evt-full",
                "start": 71.749,
                "end": 74.999,
                "text": "要恨就恨你们为什么生来就是妖",
                "confidence": 0.998,
            }
        ]
    }
    return segments, ocr


def test_arbitrator_only_called_for_review_segments() -> None:
    # The standard fixture has no review segment (all four are clear corrections).
    stub = _StubArbitrator(ArbitrationVerdict("use_ocr", "x", "y"))
    correct_asr_segments_with_ocr(
        segments_payload=_segments_payload(),
        ocr_payload=_ocr_payload(),
        config=CorrectionConfig.standard(),
        arbitrator=stub,
    )
    assert stub.calls == []


def test_arbitration_resolves_review_to_use_ocr() -> None:
    segments, ocr = _review_payloads()
    stub = _StubArbitrator(ArbitrationVerdict("use_ocr", "", "ocr is the full on-screen line"))
    result = correct_asr_segments_with_ocr(
        segments_payload=segments, ocr_payload=ocr, config=CorrectionConfig.standard(), arbitrator=stub
    )
    row = result.report["segments"][0]
    assert row["decision"] == "llm_use_ocr"
    assert result.corrected_payload["segments"][0]["text"] == "要恨就恨你们为什么生来就是妖"
    assert row["arbitration"] == {
        "decision": "use_ocr",
        "reason": "ocr is the full on-screen line",
        "applied": True,
    }
    assert result.report["summary"]["arbitrated_count"] == 1
    assert result.report["summary"]["review_count"] == 0
    assert len(stub.calls) == 1
    assert stub.calls[0].asr_text == "要恨就恨"
    assert stub.calls[0].ocr_text == "要恨就恨你们为什么生来就是妖"


def test_arbitration_merge_must_pass_faithfulness() -> None:
    segments, ocr = _review_payloads()
    # 'X' appears in neither source → faithfulness rejects → fall back to deterministic review.
    stub = _StubArbitrator(ArbitrationVerdict("merge", "要恨就恨X", "invented a character"))
    result = correct_asr_segments_with_ocr(
        segments_payload=segments, ocr_payload=ocr, config=CorrectionConfig.standard(), arbitrator=stub
    )
    row = result.report["segments"][0]
    assert row["decision"] == "review"
    assert row["arbitration"]["applied"] is False
    assert result.corrected_payload["segments"][0]["text"] == "要恨就恨"  # ASR kept
    assert result.report["summary"]["review_count"] == 1
    assert result.report["summary"]["arbitrated_count"] == 0


def test_arbitration_accepts_faithful_merge() -> None:
    segments, ocr = _review_payloads()
    stub = _StubArbitrator(ArbitrationVerdict("merge", "要恨就恨你们", "trim to the spoken span"))
    result = correct_asr_segments_with_ocr(
        segments_payload=segments, ocr_payload=ocr, config=CorrectionConfig.standard(), arbitrator=stub
    )
    row = result.report["segments"][0]
    assert row["decision"] == "llm_merge"
    assert result.corrected_payload["segments"][0]["text"] == "要恨就恨你们"
    assert result.report["summary"]["arbitrated_count"] == 1


def test_arbitration_none_falls_back_to_review() -> None:
    segments, ocr = _review_payloads()
    stub = _StubArbitrator(None)
    result = correct_asr_segments_with_ocr(
        segments_payload=segments, ocr_payload=ocr, config=CorrectionConfig.standard(), arbitrator=stub
    )
    row = result.report["segments"][0]
    assert row["decision"] == "review"
    assert "arbitration" not in row
    assert result.report["summary"]["review_count"] == 1


def test_write_correction_artifacts(tmp_path: Path) -> None:
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
