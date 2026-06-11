from __future__ import annotations

import json
from pathlib import Path

from translip.orchestration.graph import resolve_template_plan
from translip.orchestration.vision_bridge import (
    build_visual_context_command,
    parse_vision_progress_line,
    visual_context_path,
)
from translip.types import PipelineRequest
from translip.translation.visual_context import best_visual_scene, load_visual_units


def _request(tmp_path: Path, **overrides) -> PipelineRequest:
    defaults = dict(
        input_path=tmp_path / "input.mp4",
        output_root=tmp_path / "out",
        template_id="asr-dub+visual",
    )
    defaults.update(overrides)
    return PipelineRequest(**defaults)


def test_visual_template_resolves_with_optional_visual_node() -> None:
    plan = resolve_template_plan("asr-dub+visual")
    assert plan.node_order == [
        "stage1",
        "task-a",
        "task-b",
        "visual-context",
        "task-c",
        "task-d",
        "task-e",
        "task-g",
    ]
    # Optional: a missing vision backend must not fail the whole pipeline.
    assert plan.nodes["visual-context"].required is False
    assert plan.nodes["visual-context"].group == "visual-perception"
    assert plan.dependencies_for("visual-context") == ("task-a",)


def test_other_templates_unchanged() -> None:
    for template_id in ("asr-dub-basic", "asr-dub+ocr-subs", "asr-dub+ocr-subs+erase"):
        plan = resolve_template_plan(template_id)
        assert "visual-context" not in plan.node_order


def test_build_visual_context_command_uses_effective_segments(tmp_path: Path) -> None:
    request = _request(tmp_path, vision_backend="mlx", vision_frames_per_unit=2, vision_lang="en")
    command = build_visual_context_command(request)
    assert command[1:4] == ["-m", "translip.vision.extract", "--input"]
    assert "--task" in command and "scene-context" in command
    # Effective segments path (corrected fallback chain), not the raw one only.
    segments_arg = command[command.index("--segments") + 1]
    assert segments_arg.endswith("segments.zh.json")
    assert command[command.index("--backend") + 1] == "mlx"
    assert command[command.index("--frames-per-unit") + 1] == "2"
    assert command[command.index("--lang") + 1] == "en"

    # When asr-ocr-correct produced a corrected file, the command must use it.
    corrected = (
        tmp_path / "out" / "task-a" / "correction" / "input" / "segments.zh.corrected.json"
    )
    corrected.parent.mkdir(parents=True, exist_ok=True)
    corrected.write_text("{}", encoding="utf-8")
    from translip.orchestration.commands import effective_task_a_segments_path

    effective = effective_task_a_segments_path(request)
    if str(effective).endswith("corrected.json"):
        command2 = build_visual_context_command(request)
        assert command2[command2.index("--segments") + 1] == str(effective)


def test_parse_vision_progress_line_matches_extractor_prefix() -> None:
    assert parse_vision_progress_line("__VISION_PROGRESS__\t33\tanalyzing unit 2/6") == (
        33.0,
        "analyzing unit 2/6",
    )
    assert parse_vision_progress_line("__ERASE_PROGRESS__\t33\tx") is None


def test_task_c_command_includes_visual_context_only_when_present(tmp_path: Path) -> None:
    from translip.orchestration.commands import build_task_c_command

    request = _request(tmp_path)
    command = build_task_c_command(request)
    assert "--visual-context" not in command

    vc = visual_context_path(request)
    vc.parent.mkdir(parents=True, exist_ok=True)
    vc.write_text('{"units": []}', encoding="utf-8")
    command_with = build_task_c_command(request)
    assert "--visual-context" in command_with
    assert command_with[command_with.index("--visual-context") + 1] == str(vc)


def test_visual_context_cache_payload_uses_resolved_backend(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration import runner as runner_module

    request = _request(tmp_path)
    monkeypatch.setattr(
        runner_module,
        "_resolved_vision_backend",
        lambda _request: {"backend": "mlx", "model": "test-model"},
    )
    payload = runner_module._stage_cache_payload(request, "visual-context")
    assert payload["vision_backend_resolved"] == {"backend": "mlx", "model": "test-model"}
    assert payload["vision_frames_per_unit"] == 4
    assert payload["segments"]["exists"] is False  # no segments yet -> stable miss value


def test_task_c_cache_payload_tracks_visual_context_fingerprint(tmp_path: Path) -> None:
    from translip.orchestration.cache import compute_cache_key
    from translip.orchestration.runner import _stage_cache_payload

    request = _request(tmp_path)
    key_without = compute_cache_key(_stage_cache_payload(request, "task-c"))

    vc = visual_context_path(request)
    vc.parent.mkdir(parents=True, exist_ok=True)
    vc.write_text('{"units": [{"start": 0, "end": 1, "scene": "x"}]}', encoding="utf-8")
    key_with = compute_cache_key(_stage_cache_payload(request, "task-c"))
    assert key_with != key_without

    vc.write_text('{"units": [{"start": 0, "end": 1, "scene": "y"}]}', encoding="utf-8")
    key_changed = compute_cache_key(_stage_cache_payload(request, "task-c"))
    assert key_changed != key_with


def test_resolved_vision_backend_unavailable_is_stable(tmp_path: Path, monkeypatch) -> None:
    from translip.orchestration.runner import _resolved_vision_backend
    from translip.vision.backends import VisionDependencyError

    def boom(_settings=None):
        raise VisionDependencyError("nope")

    monkeypatch.setattr("translip.vision.backends.resolve_backend_name", boom)
    request = _request(tmp_path, vision_backend="ollama")
    assert _resolved_vision_backend(request) == {"backend": "unavailable", "model": ""}


def test_load_visual_units_tolerates_missing_and_garbage(tmp_path: Path) -> None:
    assert load_visual_units(None) == []
    assert load_visual_units(tmp_path / "missing.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert load_visual_units(bad) == []
    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        json.dumps(
            {
                "units": [
                    {"start": 0.0, "end": 5.0, "scene": "车内对话"},
                    {"start": 5.0, "end": 4.0, "scene": "inverted"},  # dropped
                    {"start": 6.0, "end": 9.0, "error": "parse failed"},  # no scene -> dropped
                    "garbage",
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    units = load_visual_units(mixed)
    assert units == [{"start": 0.0, "end": 5.0, "scene": "车内对话"}]


def test_best_visual_scene_picks_largest_overlap() -> None:
    visual_units = [
        {"start": 0.0, "end": 10.0, "scene": "A"},
        {"start": 10.0, "end": 20.0, "scene": "B"},
    ]
    # Translation unit 8-14s overlaps A by 2s and B by 4s -> B wins.
    assert best_visual_scene(8.0, 14.0, visual_units) == "B"
    # Zero overlap -> None (no stale context injected).
    assert best_visual_scene(30.0, 35.0, visual_units) is None
    assert best_visual_scene(0.0, 1.0, []) is None


def test_translate_units_injects_scene_into_context(tmp_path: Path) -> None:
    from translip.translation.runner import _translate_units
    from translip.translation.units import ContextUnit, SegmentRecord
    from translip.types import TranslationRequest

    captured: list = []

    class FakeBackend:
        backend_name = "fake"
        resolved_model = "fake"
        resolved_device = "cpu"

        def translate_batch(self, *, items, source_lang, target_lang):
            captured.extend(items)
            from translip.translation.backend import BackendSegmentOutput

            return [
                BackendSegmentOutput(segment_id=item.segment_id, target_text="hello")
                for item in items
            ]

    segment = SegmentRecord(
        segment_id="seg-0001",
        start=1.0,
        end=3.0,
        duration=2.0,
        speaker_label="S0",
        speaker_id=None,
        text="你好",
        language="zh",
    )
    unit = ContextUnit(
        unit_id="unit-0001", speaker_label="S0", speaker_id=None, start=1.0, end=3.0, segments=[segment]
    )
    request = TranslationRequest(
        segments_path=tmp_path / "s.json", profiles_path=tmp_path / "p.json", batch_size=4
    )

    _translate_units(
        units=[unit],
        glossary=[],
        request=request,
        backend=FakeBackend(),
        visual_units=[{"start": 0.0, "end": 5.0, "scene": "车内，两人对话"}],
    )
    assert captured[0].context_text.startswith("[画面] 车内，两人对话\n")

    captured.clear()
    _translate_units(
        units=[unit], glossary=[], request=request, backend=FakeBackend(), visual_units=[]
    )
    assert not captured[0].context_text.startswith("[画面]")
