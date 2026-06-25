from __future__ import annotations

import json
from pathlib import Path

import pytest

from translip.commentary import build_story_document, generate_commentary_script
from translip.commentary.types import CommentaryOptions
from translip.server.atomic_tools.adapters.commentary_script import CommentaryScriptAdapter
from translip.server.atomic_tools.schemas import CommentaryScriptToolRequest


# --- schema validation -------------------------------------------------------

def test_schema_defaults() -> None:
    dumped = CommentaryScriptToolRequest(segments_file_id="s").model_dump()
    assert dumped["commentary_style"] == "plot_recap"
    assert dumped["original_sound_ratio"] == 20
    assert dumped["drama_genre"] == "剧情"
    assert dumped["visual_context_file_id"] is None
    assert dumped["model"] is None


def test_schema_rejects_out_of_range_ratio() -> None:
    with pytest.raises(ValueError):
        CommentaryScriptToolRequest(segments_file_id="s", original_sound_ratio=120)


def test_schema_requires_segments() -> None:
    with pytest.raises(ValueError):
        CommentaryScriptToolRequest(visual_context_file_id="v")  # type: ignore[call-arg]


# --- story document ----------------------------------------------------------

def test_story_document_interleaves_subtitles_and_scenes() -> None:
    story = build_story_document(
        [{"id": "s1", "start": 1.0, "end": 3.0, "text": "你到底想干什么", "speaker_label": "A"}],
        [{"unit_id": "v1", "start": 0.0, "end": 5.0, "scene": "审讯室", "mood": "紧张", "people_visible": 2}],
    )
    assert "你到底想干什么" in story.text
    assert "审讯室" in story.text and "人数:2" in story.text
    assert story.segment_count == 1 and story.visual_unit_count == 1
    assert story.duration_sec == 3.0  # max segment end
    assert story.truncated is False


# --- chain merge (LLM mocked) ------------------------------------------------

def _fake_llm(monkeypatch, *, plot: str, plan: dict, items: dict) -> None:
    import translip.commentary.llm as llm_mod

    monkeypatch.setattr(llm_mod, "call_text", lambda **_kw: plot)
    calls = {"n": 0}

    def fake_json(**_kw):
        calls["n"] += 1
        return plan if calls["n"] == 1 else items

    monkeypatch.setattr(llm_mod, "call_json", fake_json)


def test_chain_merges_plan_and_narration(monkeypatch) -> None:
    _fake_llm(
        monkeypatch,
        plot="剧情概述：男主被卷入一桩谜案。",
        plan={
            "segments": [
                {"id": 1, "ost": 0, "src": [1.0, 6.0], "story_role": "开场钩子", "intent": "抓人"},
                {"id": 2, "ost": 1, "src": [6.0, 10.0], "story_role": "名场面", "intent": "保留原声"},
            ]
        },
        items={
            "items": [
                {"id": 1, "narration": "他以为只是普通的一天。", "picture": "男主站在门口"},
                {"id": 2, "narration": "播放原片2", "picture": "激烈对峙"},
            ]
        },
    )
    story = build_story_document(
        [{"id": "s1", "start": 1.0, "end": 10.0, "text": "对白", "speaker_label": "A"}], []
    )
    script = generate_commentary_script(story=story, options=CommentaryOptions())

    assert len(script.items) == 2
    first, second = script.items
    assert first.ost == 0 and first.narration.startswith("他以为")
    assert (first.src_start, first.src_end) == (1.0, 6.0)
    assert first.est_duration_sec > 0  # chars / 5
    # ost=1 is a passthrough: narration dropped, est = clip length.
    assert second.ost == 1 and second.narration == ""
    assert second.est_duration_sec == 4.0
    assert script.ost0_count == 1 and script.ost1_count == 1


def test_chain_clamps_and_drops_bad_windows(monkeypatch) -> None:
    _fake_llm(
        monkeypatch,
        plot="概述",
        plan={
            "segments": [
                {"id": 1, "ost": 0, "src": [0.0, 4.0], "story_role": "钩子"},
                {"id": 2, "ost": 0, "src": [4.0, 4.02], "story_role": "废片"},   # < min window → dropped
                {"id": 3, "ost": 0, "src": [5.0, 999.0], "story_role": "结尾"},   # end clamped to duration
            ]
        },
        items={"items": [{"id": 1, "narration": "开场。", "picture": "x"}, {"id": 3, "narration": "结尾。", "picture": "y"}]},
    )
    story = build_story_document(
        [{"id": "s1", "start": 0.0, "end": 8.0, "text": "x", "speaker_label": ""}], []
    )
    script = generate_commentary_script(story=story, options=CommentaryOptions())
    assert [i.id for i in script.items] == [1, 2]  # re-numbered contiguously, degenerate dropped
    assert script.items[-1].src_end == 8.0  # clamped to story duration


def test_chain_rejects_frame_riff() -> None:
    story = build_story_document(
        [{"id": "s1", "start": 0.0, "end": 2.0, "text": "x", "speaker_label": ""}], []
    )
    with pytest.raises(ValueError, match="frame_riff"):
        generate_commentary_script(story=story, options=CommentaryOptions(style="frame_riff"))


# --- adapter.run (LLM mocked) ------------------------------------------------

def test_adapter_writes_commentary_json(tmp_path: Path, monkeypatch) -> None:
    seg_dir = tmp_path / "input" / "segments_file"
    seg_dir.mkdir(parents=True)
    (seg_dir / "seg.json").write_text(
        json.dumps(
            {"segments": [{"id": "s1", "start": 1.0, "end": 6.0, "text": "你好", "speaker_label": "A"}]}
        ),
        encoding="utf-8",
    )

    _fake_llm(
        monkeypatch,
        plot="剧情概述。",
        plan={"segments": [{"id": 1, "ost": 0, "src": [1.0, 6.0], "story_role": "开场钩子"}]},
        items={"items": [{"id": 1, "narration": "开场解说。", "picture": "画面"}]},
    )

    output_dir = tmp_path / "output"
    result = CommentaryScriptAdapter().run(
        {
            "segments_file_id": "seg",
            "commentary_style": "plot_recap",
            "drama_genre": "悬疑",
            "narration_language": "zh",
            "original_sound_ratio": 20,
        },
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert result["item_count"] == 1
    assert result["commentary_file"] == "commentary.json"
    assert result["ost0_count"] == 1 and result["ost1_count"] == 0

    data = json.loads((output_dir / "commentary.json").read_text(encoding="utf-8"))
    assert data["meta"]["commentary_style"] == "plot_recap"
    assert data["meta"]["drama_genre"] == "悬疑"
    assert data["meta"]["source"]["segment_count"] == 1
    assert data["items"][0]["narration"] == "开场解说。"
    assert data["items"][0]["src"] == [1.0, 6.0]


def test_adapter_raises_on_empty_segments(tmp_path: Path, monkeypatch) -> None:
    seg_dir = tmp_path / "input" / "segments_file"
    seg_dir.mkdir(parents=True)
    (seg_dir / "seg.json").write_text(json.dumps({"segments": []}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="无法生成解说文案"):
        CommentaryScriptAdapter().run(
            {"segments_file_id": "seg"},
            tmp_path / "input",
            tmp_path / "output",
            lambda *_a, **_k: None,
        )
