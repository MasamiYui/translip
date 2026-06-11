"""ocr-classify closed loop (Phase 3): cache linkage + downstream consumers."""
from __future__ import annotations

import json
from pathlib import Path

from translip.orchestration.cache import compute_cache_key
from translip.orchestration.ocr_bridge import (
    build_ocr_classify_command,
    effective_ocr_events_path,
    ocr_classified_events_path,
    ocr_events_path,
)
from translip.orchestration.runner import _stage_cache_payload
from translip.orchestration.subtitle_erase_detection import (
    filter_detection_by_classification,
    prepare_subtitle_erase_detection,
)
from translip.types import PipelineRequest


def _request(tmp_path: Path, **overrides) -> PipelineRequest:
    defaults = dict(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        template_id="asr-dub+ocr-subs+erase",
    )
    defaults.update(overrides)
    return PipelineRequest(**defaults)


def _write_classified(request: PipelineRequest, events: list[dict]) -> Path:
    path = ocr_classified_events_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"events": events}, ensure_ascii=False), encoding="utf-8")
    return path


def test_effective_events_path_requires_flag_and_file(tmp_path: Path) -> None:
    # Flag off -> always the raw events file, even if a stale classified file exists.
    request_off = _request(tmp_path, ocr_classify_text=False)
    _write_classified(request_off, [])
    assert effective_ocr_events_path(request_off) == ocr_events_path(request_off)

    # Flag on but file missing -> raw events file (classification not run yet).
    request_on = _request(tmp_path / "b", ocr_classify_text=True)
    assert effective_ocr_events_path(request_on) == ocr_events_path(request_on)

    # Flag on and file present -> classified variant.
    _write_classified(request_on, [])
    assert effective_ocr_events_path(request_on) == ocr_classified_events_path(request_on)


def test_build_ocr_classify_command_shape(tmp_path: Path) -> None:
    request = _request(tmp_path, ocr_classify_text=True, vision_backend="mlx", vision_lang="en")
    command = build_ocr_classify_command(request)
    assert "translip.vision.extract" in command
    assert command[command.index("--task") + 1] == "ocr-classify"
    assert command[command.index("--detection") + 1] == str(ocr_events_path(request))
    assert command[command.index("--backend") + 1] == "mlx"
    assert command[command.index("--lang") + 1] == "en"


def test_cache_keys_react_to_classification(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration import runner as runner_module

    monkeypatch.setattr(
        runner_module,
        "_resolved_vision_backend",
        lambda _request: {"backend": "mlx", "model": "m"},
    )
    base = _request(tmp_path, ocr_classify_text=False)
    flagged = _request(tmp_path, ocr_classify_text=True)

    # Toggling the flag changes every consumer's key.
    for stage in ("ocr-detect", "subtitle-erase"):
        assert compute_cache_key(_stage_cache_payload(base, stage)) != compute_cache_key(
            _stage_cache_payload(flagged, stage)
        )

    # Classified file content cascades into ocr-translate / asr-ocr-correct keys.
    keys_before = {
        stage: compute_cache_key(_stage_cache_payload(flagged, stage))
        for stage in ("ocr-translate", "asr-ocr-correct", "subtitle-erase")
    }
    _write_classified(flagged, [{"index": 1, "kind": "subtitle"}])
    keys_after = {
        stage: compute_cache_key(_stage_cache_payload(flagged, stage))
        for stage in ("ocr-translate", "asr-ocr-correct", "subtitle-erase")
    }
    assert all(keys_before[stage] != keys_after[stage] for stage in keys_before)

    # Flag-off keys ignore the classified file entirely.
    key_off_before = compute_cache_key(_stage_cache_payload(base, "ocr-translate"))
    assert key_off_before == compute_cache_key(_stage_cache_payload(base, "ocr-translate"))


def test_filter_detection_drops_scene_text_only(tmp_path: Path) -> None:
    detection = {
        "video": {"fps": 25},
        "events": [
            {"index": 1, "start_frame": 0, "end_frame": 10, "text": "你好", "box": [1, 2, 3, 4]},
            {"index": 2, "start_frame": 20, "end_frame": 30, "text": "EXIT", "box": [5, 6, 7, 8]},
            {"index": 3, "start_frame": 40, "end_frame": 50, "text": "芒果tv", "box": [9, 9, 9, 9]},
        ],
    }
    classified = tmp_path / "classified.json"
    classified.write_text(
        json.dumps(
            {
                "events": [
                    {"index": 1, "kind": "subtitle"},
                    {"index": 2, "kind": "scene_text"},
                    {"index": 3, "kind": "watermark"},
                ]
            }
        ),
        encoding="utf-8",
    )
    filtered = filter_detection_by_classification(detection, classified)
    indexes = [event["index"] for event in filtered["events"]]
    # scene_text dropped from masks; watermark stays erasable (wiping a logo is fine).
    assert indexes == [1, 3]
    assert filtered["subtitle_erase_preprocess"]["classification_dropped_events"] == 1
    # Original payload untouched.
    assert len(detection["events"]) == 3


def test_filter_detection_keeps_unclassified_and_tolerates_garbage(tmp_path: Path) -> None:
    detection = {"events": [{"index": 1, "text": "a"}, {"index": 2, "text": "b"}]}
    missing = tmp_path / "missing.json"
    assert filter_detection_by_classification(detection, missing) is detection

    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json", encoding="utf-8")
    assert filter_detection_by_classification(detection, garbage) is detection

    # Classified file without matching indexes -> unchanged payload object.
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"events": [{"index": 99, "kind": "scene_text"}]}), encoding="utf-8")
    assert filter_detection_by_classification(detection, partial) is detection


def test_prepare_detection_applies_classification_filter(tmp_path: Path) -> None:
    source = tmp_path / "detection.json"
    source.write_text(
        json.dumps(
            {
                "video": {"fps": 25, "total_frames": 100},
                "events": [
                    {"index": 1, "start_frame": 10, "end_frame": 20, "text": "你好", "box": [1, 2, 3, 4]},
                    {"index": 2, "start_frame": 30, "end_frame": 40, "text": "路牌", "box": [5, 6, 7, 8]},
                ],
            }
        ),
        encoding="utf-8",
    )
    classified = tmp_path / "classified.json"
    classified.write_text(
        json.dumps({"events": [{"index": 2, "kind": "scene_text"}]}), encoding="utf-8"
    )
    output = prepare_subtitle_erase_detection(
        source,
        tmp_path / "expanded.json",
        lead_frames=2,
        trail_frames=3,
        classified_events_path=classified,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [event["index"] for event in payload["events"]] == [1]
    # Lead/trail expansion still applied after filtering.
    assert payload["events"][0]["start_frame"] == 8
    assert payload["events"][0]["end_frame"] == 23


def test_ocr_translate_skips_non_dialogue_kinds(tmp_path: Path) -> None:
    from translip.subtitles.runner import translate_ocr_events
    from translip.translation.backend import BackendSegmentOutput

    events_path = tmp_path / "events.json"
    events_path.write_text(
        json.dumps(
            {
                "source_language": "zh",
                "events": [
                    {"event_id": "evt-0001", "start": 1.0, "end": 2.0, "text": "你好", "kind": "subtitle"},
                    {"event_id": "evt-0002", "start": 3.0, "end": 4.0, "text": "出口", "kind": "scene_text"},
                    {"event_id": "evt-0003", "start": 5.0, "end": 6.0, "text": "芒果tv", "kind": "watermark"},
                    {"event_id": "evt-0004", "start": 7.0, "end": 8.0, "text": "再见"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class FakeBackend:
        backend_name = "fake"

        def translate_batch(self, *, items, source_lang, target_lang):
            return [
                BackendSegmentOutput(segment_id=item.segment_id, target_text=f"T:{item.source_text}")
                for item in items
            ]

    result = translate_ocr_events(
        events_path=events_path,
        output_dir=tmp_path / "out",
        target_lang="en",
        backend_name="fake",
        backend_override=FakeBackend(),
    )
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    translated_ids = [event["event_id"] for event in payload["events"]]
    # subtitle + unclassified translated; scene_text/watermark skipped.
    assert translated_ids == ["evt-0001", "evt-0004"]


def test_correction_loader_skips_non_dialogue_kinds() -> None:
    from translip.transcription.ocr_correction import _load_events

    payload = {
        "events": [
            {"event_id": "evt-0001", "start": 1.0, "end": 2.0, "text": "你好", "kind": "subtitle"},
            {"event_id": "evt-0002", "start": 3.0, "end": 4.0, "text": "出口", "kind": "scene_text"},
            {"event_id": "evt-0003", "start": 5.0, "end": 6.0, "text": "标题", "kind": "title_card"},
            {"event_id": "evt-0004", "start": 7.0, "end": 8.0, "text": "再见"},
        ]
    }
    events = _load_events(payload)
    assert [event.event_id for event in events] == ["evt-0001", "evt-0004"]
