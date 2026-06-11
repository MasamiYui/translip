from __future__ import annotations

import pytest

from translip.vision.prompts import render_prompt
from translip.vision.schema import extract_json, parse_unit_output


def test_extract_json_bare_object() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_code_fence() -> None:
    text = 'Here you go:\n```json\n{"scene": "车内"}\n```\nHope that helps!'
    assert extract_json(text) == {"scene": "车内"}


def test_extract_json_prose_wrapped_object() -> None:
    text = '好的，结果是 {"scene": "办公室", "people_visible": 2} 以上。'
    assert extract_json(text)["scene"] == "办公室"


def test_extract_json_array() -> None:
    assert extract_json('[{"kind": "subtitle"}]') == [{"kind": "subtitle"}]


def test_extract_json_no_json_raises() -> None:
    with pytest.raises(ValueError):
        extract_json("I cannot see any frames, sorry.")


def test_parse_scene_context_coerces_fields() -> None:
    payload = parse_unit_output(
        "scene-context",
        '{"scene": "车内对话", "people_visible": "2", "setting": "car_interior", "mood": "tense", "confidence": 1.7}',
    )
    assert payload == {
        "scene": "车内对话",
        "people_visible": 2,
        "setting": "car_interior",
        "mood": "tense",
        "confidence": 1.0,  # clamped
    }


def test_parse_scene_context_garbage_degrades_to_error() -> None:
    payload = parse_unit_output("scene-context", "the frames are blurry")
    assert "error" in payload
    assert payload["raw"] == "the frames are blurry"


def test_parse_scene_context_missing_confidence_defaults() -> None:
    payload = parse_unit_output("scene-context", '{"scene": "x"}')
    assert payload["confidence"] == 0.5
    assert payload["people_visible"] is None


def test_parse_ocr_classify_accepts_single_element_array() -> None:
    payload = parse_unit_output("ocr-classify", '[{"kind": "watermark", "confidence": 0.8}]')
    assert payload == {"kind": "watermark", "confidence": 0.8}


def test_parse_ocr_classify_rejects_unknown_kind() -> None:
    payload = parse_unit_output("ocr-classify", '{"kind": "advert", "confidence": 0.9}')
    assert "error" in payload


def test_parse_erase_qc_booleans() -> None:
    payload = parse_unit_output(
        "erase-qc", '{"residual_text": false, "artifact": null, "note": "clean", "confidence": 0.9}'
    )
    assert payload["residual_text"] is False
    assert payload["artifact"] is None


def test_parse_speaker_visual_null_speaking_face() -> None:
    payload = parse_unit_output(
        "speaker-visual", '{"people_visible": 2, "speaking_face": null, "speaker_hint": null}'
    )
    assert payload["speaking_face"] is None


def test_parse_freeform_plain_text_is_acceptable() -> None:
    payload = parse_unit_output("freeform", "出现了三次手机屏幕特写。")
    assert payload["answer"] == "出现了三次手机屏幕特写。"


def test_parse_freeform_json_answer() -> None:
    payload = parse_unit_output("freeform", '{"answer": "三次", "confidence": 0.7}')
    assert payload == {"answer": "三次", "confidence": 0.7}


def test_parse_unknown_task_raises() -> None:
    with pytest.raises(ValueError):
        parse_unit_output("nope", "{}")


def test_render_prompt_substitutes_and_falls_back() -> None:
    zh = render_prompt("ocr-classify", "zh", text="路牌文字")
    assert "路牌文字" in zh and "subtitle" in zh
    en = render_prompt("freeform", "en", question="how many cars?")
    assert "how many cars?" in en
    # unknown lang falls back to zh
    fallback = render_prompt("scene-context", "fr")
    assert fallback == render_prompt("scene-context", "zh")
    with pytest.raises(ValueError):
        render_prompt("nope", "zh")
