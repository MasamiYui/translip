"""Phase-1 commentary style customization — end-to-end coverage.

Covers the full data-flow seam introduced by Phase-1:

    NewTaskPage (TaskConfig) -> CreateTaskRequest (server.schemas)
        -> PipelineRequest (types.pipeline)
        -> commentary_bridge.build_commentary_script_command (CLI argv)
        -> extract.run_script (CLI parser + run_script)
        -> chain.generate_commentary_script (prompt injection)
        -> CommentaryScript.to_payload (meta.style_profile)

Every external dependency that is not part of the Phase-1 contract (the LLM)
is stubbed. The tests verify that each Phase-1 knob is honored at every
boundary and that the prompt that the LLM actually receives contains the
expected style brief.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from translip.commentary import build_story_document, generate_commentary_script
from translip.commentary import style_profiles
from translip.commentary.extract import _parse_args, run_script
from translip.commentary.types import CommentaryOptions
from translip.orchestration.commentary_bridge import build_commentary_script_command
from translip.orchestration.request import build_pipeline_request
from translip.server.atomic_tools.adapters.commentary_script import CommentaryScriptAdapter
from translip.server.atomic_tools.schemas import CommentaryScriptToolRequest
from translip.server.schemas import CreateTaskRequest
from translip.types.pipeline import PipelineRequest


# ---------------------------------------------------------------------------
# style_profiles registry
# ---------------------------------------------------------------------------

def test_mode_profiles_contain_phase1_set() -> None:
    expected = {"plot_recap", "plot_tease", "analysis", "roast", "reaction", "tutorial"}
    assert expected.issubset(set(style_profiles.MODE_PROFILES))


def test_tone_profiles_contain_phase1_set() -> None:
    expected = {
        "objective", "passionate", "humorous", "sarcastic",
        "suspenseful", "chill", "dramatic", "professional",
    }
    assert expected == set(style_profiles.TONE_PROFILES)


def test_pacing_profiles_have_three_bands() -> None:
    assert set(style_profiles.PACING_PROFILES) == {"sparse", "balanced", "dense"}
    sparse = style_profiles.PACING_PROFILES["sparse"]
    dense = style_profiles.PACING_PROFILES["dense"]
    # sparse must be slower than dense — invariant the chain.merge relies on.
    assert sparse.cps_zh < dense.cps_zh


def test_perspective_profiles_have_five_voices() -> None:
    assert set(style_profiles.PERSPECTIVE_PROFILES) == {
        "third_person", "first_person_narrator", "first_person_protagonist",
        "second_person", "god_view",
    }


def test_audience_profiles_cover_main_platforms() -> None:
    expected = {
        "generic", "bilibili", "douyin", "xiaohongshu",
        "youtube_long", "wechat_video", "professional_b2b",
    }
    assert expected == set(style_profiles.AUDIENCE_PROFILES)


def test_chars_per_second_language_aware() -> None:
    cn = style_profiles.chars_per_second(style_profiles.PACING_PROFILES["balanced"], "zh")
    jp = style_profiles.chars_per_second(style_profiles.PACING_PROFILES["balanced"], "ja")
    en = style_profiles.chars_per_second(style_profiles.PACING_PROFILES["balanced"], "en")
    assert cn == jp  # CJK shares the same cps
    assert en < cn   # Latin scripts are slower (chars-per-second is lower)
    assert en > 0


def test_resolve_helpers_fall_back_to_default() -> None:
    assert style_profiles.resolve_mode("bogus").id == style_profiles.DEFAULT_MODE_ID
    assert style_profiles.resolve_tone("").id == style_profiles.DEFAULT_TONE_ID
    assert style_profiles.resolve_pacing(None).id == style_profiles.DEFAULT_PACING_ID  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CommentaryOptions normalization
# ---------------------------------------------------------------------------

def test_options_normalized_clamps_intensity_and_fills_defaults() -> None:
    opt = CommentaryOptions(
        style="",
        tone_preset="",
        pacing_preset="",
        perspective="",
        audience="",
        style_intensity=5.0,  # out of range
    ).normalized()
    assert opt.style == "plot_recap"
    assert opt.tone_preset == "objective"
    assert opt.pacing_preset == "balanced"
    assert opt.perspective == "third_person"
    assert opt.audience == "generic"
    assert 0.0 <= opt.style_intensity <= 1.0


# ---------------------------------------------------------------------------
# Chain: stub LLM and verify prompts carry every Phase-1 knob
# ---------------------------------------------------------------------------

def _stub_llm(monkeypatch) -> dict:
    """Stub call_text + call_json. Captures the prompts seen by the LLM."""
    captured: dict = {"text_prompts": [], "json_prompts": []}

    import translip.commentary.llm as llm_mod

    def fake_text(*, system: str, user: str, **_kw) -> str:
        captured["text_prompts"].append({"system": system, "user": user})
        return "剧情概述：男主卷入谜案。"

    json_call = {"n": 0}

    def fake_json(*, system: str, user: str, **_kw):
        captured["json_prompts"].append({"system": system, "user": user})
        json_call["n"] += 1
        if json_call["n"] == 1:
            return {
                "segments": [
                    {"id": 1, "ost": 0, "src": [0.0, 6.0], "story_role": "开场钩子"},
                ]
            }
        return {"items": [{"id": 1, "narration": "他以为只是普通的一天。", "picture": "门口"}]}

    monkeypatch.setattr(llm_mod, "call_text", fake_text)
    monkeypatch.setattr(llm_mod, "call_json", fake_json)
    return captured


def _story() -> "object":
    return build_story_document(
        [{"id": "s1", "start": 0.0, "end": 6.0, "text": "对白", "speaker_label": "A"}], []
    )


def test_chain_injects_tone_and_audience_into_prompt(monkeypatch) -> None:
    captured = _stub_llm(monkeypatch)
    script = generate_commentary_script(
        story=_story(),
        options=CommentaryOptions(
            style="roast",
            tone_preset="sarcastic",
            pacing_preset="dense",
            perspective="second_person",
            audience="bilibili",
            style_intensity=0.9,
        ),
    )
    # Phase-1 fields are written back onto the script.
    assert script.style == "roast"
    assert script.tone_preset == "sarcastic"
    assert script.pacing_preset == "dense"
    assert script.perspective == "second_person"
    assert script.audience == "bilibili"
    assert script.style_intensity == pytest.approx(0.9)

    # The planning prompt must carry the persona + pacing brief.
    planning_user = captured["json_prompts"][0]["user"]
    writing_user = captured["json_prompts"][1]["user"]
    # Tone and pacing are global — they belong to both planning and writing.
    for blob in (planning_user, writing_user):
        assert "sarcastic" in blob or "毒舌" in blob
        assert "dense" in blob or "密集" in blob
    # Audience-specific allow/banned phrasing is a writing-stage concern.
    # The prompt renders the Chinese label "B 站" plus the language_brief.
    assert "B 站" in writing_user or "bilibili" in writing_user.lower() or "ACGN" in writing_user
    # Perspective only enters the writing stage (it's a sentence-level directive).
    assert "第二人称" in writing_user or "second_person" in writing_user


def test_chain_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        generate_commentary_script(
            story=_story(), options=CommentaryOptions(style="frame_riff")
        )


def test_chain_pacing_drives_est_duration(monkeypatch) -> None:
    """Sparse pacing must give a longer est_duration_sec than dense for the same narration."""
    narration = "他以为只是普通的一天，但是接下来的每一秒都让他后悔不已。"  # ~26 zh chars

    def _run(pacing: str) -> float:
        import translip.commentary.llm as llm_mod

        monkeypatch.setattr(llm_mod, "call_text", lambda **_kw: "概述")
        call = {"n": 0}

        def fake_json(**_kw):
            call["n"] += 1
            if call["n"] == 1:
                return {"segments": [{"id": 1, "ost": 0, "src": [0.0, 30.0], "story_role": "钩子"}]}
            return {"items": [{"id": 1, "narration": narration, "picture": "x"}]}

        monkeypatch.setattr(llm_mod, "call_json", fake_json)
        script = generate_commentary_script(
            story=build_story_document(
                [{"id": "s1", "start": 0.0, "end": 30.0, "text": "x", "speaker_label": ""}], []
            ),
            options=CommentaryOptions(pacing_preset=pacing),
        )
        return script.items[0].est_duration_sec

    sparse = _run("sparse")
    dense = _run("dense")
    # sparse → fewer chars per second → longer est_duration for the same text.
    assert sparse > dense


# ---------------------------------------------------------------------------
# Payload: meta.style_profile records every knob (commentary.json contract)
# ---------------------------------------------------------------------------

def test_to_payload_records_style_profile(monkeypatch) -> None:
    _stub_llm(monkeypatch)
    script = generate_commentary_script(
        story=_story(),
        options=CommentaryOptions(
            style="analysis",
            tone_preset="professional",
            pacing_preset="sparse",
            perspective="god_view",
            audience="professional_b2b",
            style_intensity=0.25,
        ),
    )
    payload = script.to_payload(source={"segment_count": 1, "visual_unit_count": 0, "duration_sec": 6.0, "truncated": False})
    meta = payload["meta"]
    assert meta["commentary_style"] == "analysis"
    profile = meta["style_profile"]
    assert profile["tone_preset"] == "professional"
    assert profile["pacing_preset"] == "sparse"
    assert profile["perspective"] == "god_view"
    assert profile["audience"] == "professional_b2b"
    assert profile["style_intensity"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# CLI: argparse round-trip every flag
# ---------------------------------------------------------------------------

def test_extract_cli_parses_phase1_flags() -> None:
    ns = _parse_args(
        [
            "--task", "script",
            "--segments", "seg.json",
            "--output-dir", "out",
            "--style", "tutorial",
            "--genre", "纪录片",
            "--language", "en",
            "--original-sound-ratio", "30",
            "--tone-preset", "humorous",
            "--pacing-preset", "dense",
            "--perspective", "first_person_narrator",
            "--audience", "douyin",
            "--style-intensity", "0.85",
        ]
    )
    assert ns.style == "tutorial"
    assert ns.tone_preset == "humorous"
    assert ns.pacing_preset == "dense"
    assert ns.perspective == "first_person_narrator"
    assert ns.audience == "douyin"
    assert ns.style_intensity == pytest.approx(0.85)


def test_run_script_records_phase1_params_in_manifest(tmp_path: Path, monkeypatch) -> None:
    _stub_llm(monkeypatch)
    segments = tmp_path / "segments.zh.json"
    segments.write_text(
        json.dumps({"segments": [{"id": "s1", "start": 0.0, "end": 6.0, "text": "x", "speaker_label": ""}]}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "script"
    manifest_path = run_script(
        segments_path=segments,
        output_dir=out_dir,
        visual_context_path=None,
        style="plot_tease",
        genre="悬疑",
        language="zh",
        original_sound_ratio=10,
        model=None,
        tone_preset="suspenseful",
        pacing_preset="sparse",
        perspective="second_person",
        audience="xiaohongshu",
        style_intensity=0.7,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    params = manifest["params"]
    assert params["style"] == "plot_tease"
    assert params["tone_preset"] == "suspenseful"
    assert params["pacing_preset"] == "sparse"
    assert params["perspective"] == "second_person"
    assert params["audience"] == "xiaohongshu"
    assert params["style_intensity"] == pytest.approx(0.7)
    payload = json.loads((out_dir / "commentary.json").read_text(encoding="utf-8"))
    assert payload["meta"]["style_profile"]["tone_preset"] == "suspenseful"


# ---------------------------------------------------------------------------
# commentary_bridge: PipelineRequest -> argv carries every Phase-1 flag
# ---------------------------------------------------------------------------

def _arg(cmd: list[str], flag: str) -> str | None:
    return cmd[cmd.index(flag) + 1] if flag in cmd else None


def test_bridge_threads_phase1_flags(tmp_path: Path) -> None:
    request = build_pipeline_request(
        {
            "input": str(tmp_path / "in.mp4"),
            "output_root": str(tmp_path / "out"),
            "template": "asr-commentary",
            "commentary_style": "roast",
            "commentary_tone_preset": "sarcastic",
            "commentary_pacing_preset": "dense",
            "commentary_perspective": "first_person_protagonist",
            "commentary_audience": "bilibili",
            "commentary_style_intensity": 0.85,
        }
    )
    cmd = build_commentary_script_command(request)
    assert _arg(cmd, "--style") == "roast"
    assert _arg(cmd, "--tone-preset") == "sarcastic"
    assert _arg(cmd, "--pacing-preset") == "dense"
    assert _arg(cmd, "--perspective") == "first_person_protagonist"
    assert _arg(cmd, "--audience") == "bilibili"
    assert _arg(cmd, "--style-intensity") == "0.850"


def test_bridge_defaults_match_pipeline_request_defaults(tmp_path: Path) -> None:
    """Even with no Phase-1 overrides, the bridge must still emit every flag."""
    request = build_pipeline_request(
        {
            "input": str(tmp_path / "in.mp4"),
            "output_root": str(tmp_path / "out"),
            "template": "asr-commentary",
        }
    )
    cmd = build_commentary_script_command(request)
    assert _arg(cmd, "--tone-preset") == "objective"
    assert _arg(cmd, "--pacing-preset") == "balanced"
    assert _arg(cmd, "--perspective") == "third_person"
    assert _arg(cmd, "--audience") == "generic"
    assert _arg(cmd, "--style-intensity") is not None


# ---------------------------------------------------------------------------
# server schemas: CreateTaskRequest + atomic-tool request carry the new fields
# ---------------------------------------------------------------------------

def test_create_task_request_has_phase1_defaults() -> None:
    body = CreateTaskRequest(
        name="t",
        input_path="/tmp/x.mp4",
        target_lang="zh",
        config={},
    )
    cfg = body.config
    assert cfg.commentary_tone_preset == "objective"
    assert cfg.commentary_pacing_preset == "balanced"
    assert cfg.commentary_perspective == "third_person"
    assert cfg.commentary_audience == "generic"
    assert cfg.commentary_style_intensity == pytest.approx(0.6)


def test_create_task_request_accepts_overrides() -> None:
    body = CreateTaskRequest(
        name="t",
        input_path="/tmp/x.mp4",
        target_lang="zh",
        config={
            "commentary_style": "analysis",
            "commentary_tone_preset": "professional",
            "commentary_pacing_preset": "sparse",
            "commentary_perspective": "god_view",
            "commentary_audience": "professional_b2b",
            "commentary_style_intensity": 0.2,
        },
    )
    cfg = body.config
    assert cfg.commentary_style == "analysis"
    assert cfg.commentary_tone_preset == "professional"
    assert cfg.commentary_style_intensity == pytest.approx(0.2)


def test_create_task_request_rejects_invalid_enum() -> None:
    with pytest.raises(ValueError):
        CreateTaskRequest(
            name="t",
            input_path="/tmp/x.mp4",
            target_lang="zh",
            config={"commentary_tone_preset": "not_a_persona"},
        )


def test_atomic_script_request_carries_phase1_fields() -> None:
    req = CommentaryScriptToolRequest(
        segments_file_id="s",
        commentary_style="reaction",
        tone_preset="passionate",
        pacing_preset="dense",
        perspective="first_person_narrator",
        audience="douyin",
        style_intensity=1.0,
    )
    dumped = req.model_dump()
    assert dumped["commentary_style"] == "reaction"
    assert dumped["tone_preset"] == "passionate"
    assert dumped["pacing_preset"] == "dense"
    assert dumped["perspective"] == "first_person_narrator"
    assert dumped["audience"] == "douyin"
    assert dumped["style_intensity"] == pytest.approx(1.0)


def test_atomic_script_request_rejects_out_of_range_intensity() -> None:
    with pytest.raises(ValueError):
        CommentaryScriptToolRequest(segments_file_id="s", style_intensity=2.0)


# ---------------------------------------------------------------------------
# commentary_script adapter: full path (params -> CommentaryOptions -> json)
# ---------------------------------------------------------------------------

def test_adapter_threads_phase1_params(tmp_path: Path, monkeypatch) -> None:
    _stub_llm(monkeypatch)
    seg_dir = tmp_path / "input" / "segments_file"
    seg_dir.mkdir(parents=True)
    (seg_dir / "seg.json").write_text(
        json.dumps({"segments": [{"id": "s1", "start": 0.0, "end": 6.0, "text": "x", "speaker_label": ""}]}),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    result = CommentaryScriptAdapter().run(
        {
            "segments_file_id": "seg",
            "commentary_style": "tutorial",
            "drama_genre": "纪录片",
            "narration_language": "zh",
            "original_sound_ratio": 25,
            "tone_preset": "professional",
            "pacing_preset": "sparse",
            "perspective": "first_person_narrator",
            "audience": "professional_b2b",
            "style_intensity": 0.35,
        },
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )
    assert result["commentary_style"] == "tutorial"
    assert result["tone_preset"] == "professional"
    assert result["pacing_preset"] == "sparse"
    assert result["perspective"] == "first_person_narrator"
    assert result["audience"] == "professional_b2b"
    assert result["style_intensity"] == pytest.approx(0.35)

    payload = json.loads((output_dir / "commentary.json").read_text(encoding="utf-8"))
    profile = payload["meta"]["style_profile"]
    assert profile["tone_preset"] == "professional"
    assert profile["audience"] == "professional_b2b"
