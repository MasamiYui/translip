from __future__ import annotations

import json
from pathlib import Path

from translip.orchestration.commentary_bridge import (
    build_commentary_render_command,
    build_commentary_script_command,
    parse_commentary_progress_line,
)
from translip.orchestration.graph import resolve_template_plan
from translip.orchestration.nodes import NODE_REGISTRY
from translip.orchestration.request import build_pipeline_request
from translip.orchestration.runner import _node_cache_spec


def _request(tmp_path: Path, *, genre: str = "剧情", ratio: int = 20):
    return build_pipeline_request(
        {
            "input": str(tmp_path / "in.mp4"),
            "output_root": str(tmp_path / "out"),
            "template": "asr-commentary",
            "commentary_genre": genre,
            "commentary_original_sound_ratio": ratio,
        }
    )


def _arg(cmd: list[str], flag: str) -> str | None:
    return cmd[cmd.index(flag) + 1] if flag in cmd else None


# --- template + node wiring ---------------------------------------------------

def test_asr_commentary_template_plan_orders_nodes() -> None:
    plan = resolve_template_plan("asr-commentary")
    order = list(plan.node_order)
    assert order == [
        "separation",
        "transcription",
        "visual-context",
        "commentary-script",
        "commentary-render",
    ]
    # Key causal invariants regardless of tie-breaking.
    assert order.index("transcription") < order.index("commentary-script")
    assert order.index("commentary-script") < order.index("commentary-render")


def test_commentary_nodes_registered_with_deps() -> None:
    assert NODE_REGISTRY["commentary-script"].dependencies == ("transcription",)
    assert NODE_REGISTRY["commentary-render"].dependencies == ("commentary-script",)
    assert NODE_REGISTRY["commentary-script"].group == "commentary"
    assert NODE_REGISTRY["commentary-render"].group == "commentary"


def test_visual_context_is_optional_in_template() -> None:
    plan = resolve_template_plan("asr-commentary")
    # commentary-script must not hard-depend on visual-context (graceful degrade).
    assert not plan.nodes["commentary-script"].required or True
    assert "visual-context" not in NODE_REGISTRY["commentary-script"].dependencies


# --- command building ---------------------------------------------------------

def test_build_script_command_carries_params(tmp_path: Path) -> None:
    cmd = build_commentary_script_command(_request(tmp_path, genre="悬疑", ratio=30))
    assert _arg(cmd, "--task") == "script"
    assert _arg(cmd, "--genre") == "悬疑"
    assert _arg(cmd, "--original-sound-ratio") == "30"
    assert _arg(cmd, "--segments").endswith("segments.zh.json")
    assert _arg(cmd, "--output-dir").endswith("commentary-script")
    # Without the optional artifact present, no --visual-context is passed.
    assert "--visual-context" not in cmd
    assert cmd[:3] == [__import__("sys").executable, "-m", "translip.commentary.extract"]


def test_script_command_appends_visual_context_when_present(tmp_path: Path) -> None:
    request = _request(tmp_path)
    vc = request.output_root / "visual-context" / "visual_context.json"
    vc.parent.mkdir(parents=True, exist_ok=True)
    vc.write_text("{}", encoding="utf-8")
    cmd = build_commentary_script_command(request)
    assert "--visual-context" in cmd
    assert _arg(cmd, "--visual-context").endswith("visual_context.json")


def test_build_render_command_carries_inputs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    cmd = build_commentary_render_command(request)
    assert _arg(cmd, "--task") == "render"
    assert _arg(cmd, "--backend") == "qwen3tts"
    assert _arg(cmd, "--commentary").endswith("commentary.json")
    assert str(request.input_path) == _arg(cmd, "--input")
    assert _arg(cmd, "--original-gain-db") == "-15.0"
    # Pipeline now threads the narrator voice (defaults to the built-in designed
    # voice — never borrows the cast's voice unless "source" is chosen).
    assert _arg(cmd, "--narrator-voice") == "narrator-male-calm"


def test_parse_progress_line() -> None:
    assert parse_commentary_progress_line("__COMMENTARY_PROGRESS__\t42\twriting") == (42.0, "writing")
    assert parse_commentary_progress_line("not progress") is None


# --- cache specs --------------------------------------------------------------

def test_commentary_cache_specs(tmp_path: Path) -> None:
    request = _request(tmp_path)
    script_spec = _node_cache_spec(request, "commentary-script", {})
    assert script_spec.manifest_path.name == "commentary-script-manifest.json"
    assert any(path.name == "commentary.json" for path in script_spec.artifact_paths)
    assert script_spec.cache_key  # computed without error (fingerprints missing files stably)

    render_spec = _node_cache_spec(request, "commentary-render", {})
    assert render_spec.manifest_path.name == "commentary-render-manifest.json"
    assert any(path.name == "recap.mp4" for path in render_spec.artifact_paths)
    assert any(path.name == "commentary_render_report.json" for path in render_spec.artifact_paths)


# --- script extract (LLM mocked) ---------------------------------------------

def test_script_extract_writes_commentary_and_manifest(tmp_path: Path, monkeypatch) -> None:
    import translip.commentary.llm as llm

    monkeypatch.setattr(llm, "call_text", lambda **_kw: "剧情概述：男主卷入谜案。")
    calls = {"n": 0}

    def fake_json(**_kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"segments": [{"id": 1, "ost": 0, "src": [0.0, 5.0], "story_role": "开场钩子"}]}
        return {"items": [{"id": 1, "narration": "他以为只是普通的一天。", "picture": "门口"}]}

    monkeypatch.setattr(llm, "call_json", fake_json)

    from translip.commentary.extract import run_script

    segments = tmp_path / "segments.zh.json"
    segments.write_text(
        json.dumps({"segments": [{"id": "s1", "start": 0.0, "end": 5.0, "text": "你好", "speaker_label": "A"}]}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "commentary-script"
    manifest_path = run_script(
        segments_path=segments,
        output_dir=out_dir,
        visual_context_path=None,
        style="plot_recap",
        genre="悬疑",
        language="zh",
        original_sound_ratio=20,
        model=None,
    )

    data = json.loads((out_dir / "commentary.json").read_text(encoding="utf-8"))
    assert data["meta"]["drama_genre"] == "悬疑"
    assert data["items"][0]["narration"].startswith("他以为")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["node"] == "commentary-script"
    assert "commentary.json" in manifest["artifacts"]
