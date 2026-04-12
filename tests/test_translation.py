import json
from pathlib import Path

from video_voice_separate.translation.backend import BackendSegmentOutput
from video_voice_separate.translation.duration import build_duration_budget
from video_voice_separate.translation.glossary import (
    apply_glossary,
    load_glossary,
    normalize_target_with_glossary,
)
from video_voice_separate.translation.runner import translate_script
from video_voice_separate.translation.siliconflow_backend import _extract_message_content, _parse_json_payload
from video_voice_separate.translation.units import SegmentRecord, build_context_units
from video_voice_separate.types import TranslationRequest


class FakeBackend:
    backend_name = "fake-backend"
    resolved_model = "fake-model"
    resolved_device = "cpu"

    def translate_batch(self, *, items, source_lang, target_lang):
        return [
            BackendSegmentOutput(
                segment_id=item.segment_id,
                target_text=f"{target_lang}:{item.source_text}",
            )
            for item in items
        ]


def test_build_context_units_merges_same_speaker_with_small_gap() -> None:
    segments = [
        SegmentRecord(
            segment_id="seg-0001",
            start=0.0,
            end=1.0,
            duration=1.0,
            speaker_label="SPEAKER_00",
            speaker_id="spk_0000",
            text="你好",
            language="zh",
        ),
        SegmentRecord(
            segment_id="seg-0002",
            start=1.4,
            end=2.2,
            duration=0.8,
            speaker_label="SPEAKER_00",
            speaker_id="spk_0000",
            text="迪拜",
            language="zh",
        ),
        SegmentRecord(
            segment_id="seg-0003",
            start=4.0,
            end=5.0,
            duration=1.0,
            speaker_label="SPEAKER_01",
            speaker_id="spk_0001",
            text="再见",
            language="zh",
        ),
    ]
    units = build_context_units(segments)
    assert len(units) == 2
    assert [segment.segment_id for segment in units[0].segments] == ["seg-0001", "seg-0002"]
    assert units[1].speaker_label == "SPEAKER_01"


def test_apply_glossary_replaces_target_terms(tmp_path: Path) -> None:
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "entry_id": "dubai",
                        "source_variants": ["迪拜"],
                        "targets": {"en": "Dubai"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    glossary = load_glossary(glossary_path)
    processed, matches = apply_glossary("我在迪拜", target_lang="en", glossary=glossary)
    assert processed == "我在Dubai"
    assert matches[0]["replacement_text"] == "Dubai"


def test_normalize_target_with_glossary_forces_single_term_segments() -> None:
    normalized = normalize_target_with_glossary(
        source_text="迪拜",
        target_text="The Dubai",
        glossary_matches=[
            {"entry_id": "dubai", "matched_text": "迪拜", "replacement_text": "Dubai"}
        ],
    )
    assert normalized == "Dubai"


def test_duration_budget_marks_risky_when_target_is_much_longer() -> None:
    budget = build_duration_budget(
        source_duration_sec=1.0,
        target_text="This is a very long translated sentence for a one second slot.",
        target_lang="en",
    )
    assert budget["fit_level"] == "risky"
    assert float(budget["duration_ratio"]) > 1.3


def test_siliconflow_response_helpers_parse_json_content() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": '```json\n{"segments":[{"segment_id":"seg-0001","target_text":"Hello"}]}\n```'
                }
            }
        ]
    }
    content = _extract_message_content(response)
    parsed = _parse_json_payload(content)
    assert parsed["segments"][0]["target_text"] == "Hello"


def test_translate_script_writes_expected_artifacts(tmp_path: Path) -> None:
    segments_path = tmp_path / "segments.zh.json"
    segments_path.write_text(
        json.dumps(
            {
                "input": {"path": "/tmp/voice.wav"},
                "segments": [
                    {
                        "id": "seg-0001",
                        "start": 0.0,
                        "end": 1.0,
                        "duration": 1.0,
                        "speaker_label": "SPEAKER_00",
                        "text": "迪拜",
                        "language": "zh",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profiles_path = tmp_path / "speaker_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "source_label": "SPEAKER_00",
                        "speaker_id": "spk_0000",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    glossary_path = tmp_path / "glossary.json"
    glossary_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "entry_id": "dubai",
                        "source_variants": ["迪拜"],
                        "targets": {"en": "Dubai"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            glossary_path=glossary_path,
            batch_size=1,
        ),
        backend_override=FakeBackend(),
    )

    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    editable = json.loads(result.artifacts.editable_json_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.artifacts.manifest_path.read_text(encoding="utf-8"))
    assert payload["backend"]["translation_backend"] == "fake-backend"
    assert payload["segments"][0]["target_text"] == "Dubai"
    assert payload["segments"][0]["glossary_matches"][0]["entry_id"] == "dubai"
    assert editable["units"][0]["segments"][0]["segment_id"] == "seg-0001"
    assert manifest["status"] == "succeeded"
