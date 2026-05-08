import json
from pathlib import Path

from translip.translation.backend import BackendSegmentOutput, CondenseOutput
from translip.translation.duration import build_duration_budget
from translip.translation.glossary import (
    apply_glossary,
    load_glossary,
    normalize_target_with_glossary,
)
from translip.translation.runner import translate_script
from translip.translation.siliconflow_backend import _extract_message_content, _parse_json_payload
from translip.translation.units import SegmentRecord, build_context_units
from translip.types import TranslationRequest


class FakeBackend:
    backend_name = "fake-backend"
    resolved_model = "fake-model"
    resolved_device = "cpu"
    supports_condensation = False

    def translate_batch(self, *, items, source_lang, target_lang):
        return [
            BackendSegmentOutput(
                segment_id=item.segment_id,
                target_text=f"{target_lang}:{item.source_text}",
            )
            for item in items
        ]


class CapturingBackend(FakeBackend):
    def __init__(self) -> None:
        self.source_lang: str | None = None

    def translate_batch(self, *, items, source_lang, target_lang):
        self.source_lang = source_lang
        return super().translate_batch(items=items, source_lang=source_lang, target_lang=target_lang)


class FakeCondenseBackend(FakeBackend):
    supports_condensation = True

    def condense_batch(self, *, items, target_lang):
        return [
            CondenseOutput(
                segment_id=item.segment_id,
                target_text=item.current_target_text[:item.max_chars] if item.max_chars < len(item.current_target_text) else item.current_target_text,
            )
            for item in items
        ]


class LongEnglishBackend(FakeBackend):
    def translate_batch(self, *, items, source_lang, target_lang):
        return [
            BackendSegmentOutput(
                segment_id=item.segment_id,
                target_text="This is a very long translated sentence for a one second slot.",
            )
            for item in items
        ]


class TrimOnlyLongEnglishBackend(FakeBackend):
    def translate_batch(self, *, items, source_lang, target_lang):
        return [
            BackendSegmentOutput(
                segment_id=item.segment_id,
                target_text="Alpha beta gamma delta epsilon zeta eta theta.",
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


def test_translate_script_uses_builtin_dubbing_glossary_and_phrase_overrides(tmp_path: Path) -> None:
    segments_path = tmp_path / "segments.zh.json"
    segments_path.write_text(
        json.dumps(
            _make_segments_payload([
                {"id": "seg-0001", "start": 0.0, "end": 1.0, "duration": 1.0, "speaker_label": "SPEAKER_00", "text": "哪吒", "language": "zh"},
                {"id": "seg-0002", "start": 1.1, "end": 2.0, "duration": 0.9, "speaker_label": "SPEAKER_00", "text": "报", "language": "zh"},
            ]),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profiles_path = tmp_path / "speaker_profiles.json"
    profiles_path.write_text(
        json.dumps(_make_profiles_payload([("SPEAKER_00", "spk_0000")]), ensure_ascii=False),
        encoding="utf-8",
    )

    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            batch_size=1,
        ),
        backend_override=FakeBackend(),
    )

    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    by_id = {row["segment_id"]: row for row in payload["segments"]}
    assert by_id["seg-0001"]["target_text"] == "Ne Zha."
    assert by_id["seg-0001"]["glossary_matches"][0]["entry_id"] == "builtin-ne-zha"
    assert by_id["seg-0002"]["target_text"] == "Report."
    assert "needs_dubbing_unit" in by_id["seg-0002"]["script_risk_flags"]


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


def test_translate_script_auto_detects_japanese_source_language(tmp_path: Path) -> None:
    segments_path = tmp_path / "segments.auto.json"
    segments_path.write_text(
        json.dumps(
            _make_segments_payload([
                {
                    "id": "seg-0001",
                    "start": 0.0,
                    "end": 1.0,
                    "duration": 1.0,
                    "speaker_label": "SPEAKER_00",
                    "text": "こんにちは。今日は京都に行きます。",
                    "language": "auto",
                }
            ]),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profiles_path = tmp_path / "speaker_profiles.json"
    profiles_path.write_text(
        json.dumps(_make_profiles_payload([("SPEAKER_00", "spk_0000")]), ensure_ascii=False),
        encoding="utf-8",
    )
    backend = CapturingBackend()

    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            source_lang="auto",
            target_lang="en",
        ),
        backend_override=backend,
    )

    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    assert backend.source_lang == "ja"
    assert payload["backend"]["source_lang"] == "ja"


def _make_segments_payload(segments: list[dict]) -> dict:
    return {"input": {"path": "/tmp/voice.wav"}, "segments": segments}


def _make_profiles_payload(speakers: list[tuple[str, str]]) -> dict:
    return {"profiles": [{"source_label": label, "speaker_id": sid} for label, sid in speakers]}


def _write_fixtures(tmp_path: Path, *, segment_text: str = "这是一个非常非常长的句子用来测试精简功能", duration: float = 1.0):
    segments_path = tmp_path / "segments.zh.json"
    segments_path.write_text(
        json.dumps(
            _make_segments_payload([
                {"id": "seg-0001", "start": 0.0, "end": duration, "duration": duration, "speaker_label": "SPEAKER_00", "text": segment_text, "language": "zh"},
            ]),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    profiles_path = tmp_path / "speaker_profiles.json"
    profiles_path.write_text(
        json.dumps(_make_profiles_payload([("SPEAKER_00", "spk_0000")]), ensure_ascii=False),
        encoding="utf-8",
    )
    return segments_path, profiles_path


def test_condense_mode_off_skips_condensation(tmp_path: Path) -> None:
    segments_path, profiles_path = _write_fixtures(tmp_path)
    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            condense_mode="off",
        ),
        backend_override=FakeCondenseBackend(),
    )
    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    seg = payload["segments"][0]
    assert seg["condense_status"] == "skipped"
    assert seg["original_target_text"] == seg["target_text"]


def test_condense_mode_smart_processes_risky_segments(tmp_path: Path) -> None:
    segments_path, profiles_path = _write_fixtures(tmp_path, duration=1.0)
    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            condense_mode="smart",
        ),
        backend_override=FakeCondenseBackend(),
    )
    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    seg = payload["segments"][0]
    fit_level = seg["duration_budget"]["fit_level"]
    if fit_level == "risky":
        assert seg["condense_status"] in ("condensed", "still_risky", "condense_failed")
    else:
        assert seg["condense_status"] == "skipped"


def test_condense_unsupported_backend_falls_back_gracefully(tmp_path: Path) -> None:
    segments_path, profiles_path = _write_fixtures(tmp_path)
    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            condense_mode="smart",
        ),
        backend_override=FakeBackend(),
    )
    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    seg = payload["segments"][0]
    assert seg["condense_status"] == "skipped"


def test_condense_unsupported_backend_uses_rule_based_fallback(tmp_path: Path) -> None:
    segments_path, profiles_path = _write_fixtures(
        tmp_path,
        segment_text="人间天堂",
        duration=0.7,
    )
    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            condense_mode="smart",
        ),
        backend_override=LongEnglishBackend(),
    )
    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    editable = json.loads(result.artifacts.editable_json_path.read_text(encoding="utf-8"))
    seg = payload["segments"][0]
    assert seg["original_target_text"] == "This is a very long translated sentence for a one second slot."
    assert seg["target_text"] == "Paradise."
    assert seg["condense_status"] == "condensed"
    assert seg["condense_method"] == "rule_based"
    assert payload["stats"]["condense_counts"]["condensed"] == 1
    assert payload["stats"]["condense_method_counts"]["rule_based"] == 1
    assert editable["units"][0]["segments"][0]["condense_method"] == "rule_based"


def test_condense_rule_based_fallback_rejects_unsafe_word_trimming(tmp_path: Path) -> None:
    segments_path, profiles_path = _write_fixtures(
        tmp_path,
        segment_text="我先洗个澡",
        duration=0.7,
    )
    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            condense_mode="smart",
        ),
        backend_override=TrimOnlyLongEnglishBackend(),
    )
    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    seg = payload["segments"][0]
    assert seg["target_text"] == "Alpha beta gamma delta epsilon zeta eta theta."
    assert seg["condense_status"] == "condense_failed"
    assert seg["condense_method"] == "none"


def test_condense_payload_includes_condense_counts(tmp_path: Path) -> None:
    segments_path, profiles_path = _write_fixtures(tmp_path)
    result = translate_script(
        TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=tmp_path / "output",
            target_lang="en",
            condense_mode="off",
        ),
        backend_override=FakeBackend(),
    )
    payload = json.loads(result.artifacts.translation_json_path.read_text(encoding="utf-8"))
    assert "condense_counts" in payload["stats"]
    assert payload["stats"]["condense_method_counts"] == {"none": 1}
    assert payload["backend"]["condense_mode"] == "off"
