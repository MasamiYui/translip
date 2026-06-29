from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from translip.commentary.render import (
    ClipSpec,
    build_clip_command,
    build_concat_command,
    db_to_linear,
    plan_render,
    write_concat_list,
)
from translip.server.atomic_tools.adapters.commentary_render import CommentaryRenderAdapter
from translip.server.atomic_tools.schemas import CommentaryRenderToolRequest

_MODULE = "translip.server.atomic_tools.adapters.commentary_render"


def _arg_value(args: list[str], flag: str) -> str | None:
    for i, tok in enumerate(args):
        if tok == flag and i + 1 < len(args):
            return args[i + 1]
    return None


# --- schema ------------------------------------------------------------------

def test_schema_defaults() -> None:
    dumped = CommentaryRenderToolRequest(commentary_file_id="c", video_file_id="v").model_dump()
    assert dumped["backend"] == "qwen3tts"
    assert dumped["original_gain_db"] == -15.0
    assert dumped["narration_language"] is None
    # BGM fields default to "no BGM" so the pre-BGM behaviour is preserved.
    assert dumped["bgm_preset"] is None
    assert dumped["bgm_file_id"] is None
    assert dumped["bgm_gain_db"] == -15.0
    assert dumped["bgm_duck_db"] == -9.0


def test_schema_rejects_positive_bgm_duck_db() -> None:
    # duck_db represents *attenuation* applied during narration → must be <= 0.
    with pytest.raises(ValueError, match="bgm_duck_db must be <= 0"):
        CommentaryRenderToolRequest(
            commentary_file_id="c",
            video_file_id="v",
            bgm_duck_db=3.0,
        )


def test_schema_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError):
        CommentaryRenderToolRequest(commentary_file_id="c", video_file_id="v", backend="nope")


def test_schema_clone_backend_no_longer_requires_upload() -> None:
    # A built-in narrator voice (or "source") resolves to a reference for the
    # clone-only backends, so a manual reference upload is no longer required.
    req = CommentaryRenderToolRequest(commentary_file_id="c", video_file_id="v", backend="voxcpm2")
    assert req.backend == "voxcpm2"


# --- plan_render -------------------------------------------------------------

def _items() -> list[dict]:
    return [
        {"id": 1, "ost": 0, "src": [0.5, 6.0]},
        {"id": 2, "ost": 1, "src": [6.0, 10.0]},
        {"id": 3, "ost": 0, "src": [11.0, 18.0]},
    ]


def test_plan_render_uses_narration_len_for_ost0_and_window_for_ost1() -> None:
    specs = plan_render(
        _items(), narration_durations={1: 2.0, 3: 2.5}, source_duration=30.0
    )
    assert [s.item_id for s in specs] == [1, 2, 3]
    assert [s.index for s in specs] == [0, 1, 2]  # contiguous
    # ost0 → av is the narration length; take is min(av, window)
    assert specs[0].ost == 0 and specs[0].av_duration == 2.0 and specs[0].take_duration == 2.0
    # ost1 → av == take == clamped window (6→10)
    assert specs[1].ost == 1 and specs[1].av_duration == 4.0 and specs[1].take_duration == 4.0
    assert specs[2].av_duration == 2.5


def test_plan_render_pads_when_source_shorter_than_narration() -> None:
    # ost0 window is only 1s (5→6) but narration is 3s → take 1s, pad 2s.
    specs = plan_render(
        [{"id": 1, "ost": 0, "src": [5.0, 6.0]}],
        narration_durations={1: 3.0},
        source_duration=6.0,
    )
    assert specs[0].take_duration == 1.0
    assert specs[0].av_duration == 3.0
    assert specs[0].pad_duration == 2.0


def test_plan_render_clamps_window_to_source_end() -> None:
    specs = plan_render(
        [{"id": 1, "ost": 1, "src": [5.0, 999.0]}],
        narration_durations={},
        source_duration=8.0,
    )
    assert specs[0].take_duration == 3.0  # 8 - 5


def test_plan_render_drops_unrenderable_items() -> None:
    specs = plan_render(
        [
            {"id": 1, "ost": 0, "src": [0.0, 5.0]},     # no narration → dropped
            {"id": 2, "ost": 1, "src": [40.0, 50.0]},   # starts past source end → dropped
            {"id": 3, "ost": 1, "src": [2.0, 6.0]},     # kept
        ],
        narration_durations={},
        source_duration=30.0,
    )
    assert [s.item_id for s in specs] == [3]
    assert specs[0].index == 0  # re-indexed


def test_db_to_linear() -> None:
    assert db_to_linear(0.0) == pytest.approx(1.0)
    assert db_to_linear(-20.0) == pytest.approx(0.1)


# --- command builders --------------------------------------------------------

def test_build_clip_command_ost0_mixes_ducked_original_with_narration() -> None:
    spec = ClipSpec(index=0, item_id=1, ost=0, src_start=1.5, take_duration=2.0, av_duration=2.0)
    cmd = build_clip_command(
        ffmpeg="ffmpeg",
        spec=spec,
        source_path=Path("src.mp4"),
        narration_path=Path("n.wav"),
        output_path=Path("clip.mp4"),
        width=641,  # odd → must be evened
        height=360,
        crf=20,
        preset="medium",
        original_gain_db=-20.0,
    )
    # Two inputs: source (seeked) + narration.
    assert cmd.index("-ss") < cmd.index("-i")
    assert _arg_value(cmd, "-ss") == "1.500"
    assert cmd.count("-i") == 2
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2" in fc
    assert "volume=0.1000" in fc          # -20 dB ducking on the original
    assert "scale=640:360" in fc          # 641 → 640 (even)
    assert "tpad" not in fc               # pad_duration 0 → no clone
    # Final length is the narration-driven av_duration.
    assert _arg_value(cmd, "-t") == "2.000"
    assert cmd[-1] == "clip.mp4"


def test_build_clip_command_ost0_clones_last_frame_when_padding() -> None:
    spec = ClipSpec(index=0, item_id=1, ost=0, src_start=0.0, take_duration=1.0, av_duration=3.0)
    cmd = build_clip_command(
        ffmpeg="ffmpeg", spec=spec, source_path=Path("s.mp4"), narration_path=Path("n.wav"),
        output_path=Path("c.mp4"), width=640, height=360, crf=20, preset="medium",
        original_gain_db=-15.0,
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "tpad=stop_mode=clone:stop_duration=2.000" in fc
    assert "-ss" not in cmd  # src_start 0 → no seek


def test_build_clip_command_ost1_passthrough_single_input() -> None:
    spec = ClipSpec(index=1, item_id=2, ost=1, src_start=6.0, take_duration=4.0, av_duration=4.0)
    cmd = build_clip_command(
        ffmpeg="ffmpeg", spec=spec, source_path=Path("s.mp4"), narration_path=None,
        output_path=Path("c.mp4"), width=1280, height=720, crf=20, preset="medium",
        original_gain_db=-15.0,
    )
    assert cmd.count("-i") == 1  # original only
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix" not in fc and "volume=" not in fc
    assert "[0:a]atrim=duration=4.000" in fc
    assert _arg_value(cmd, "-t") == "4.000"


def test_build_clip_command_ost0_with_bgm_adds_third_input_and_sidechain() -> None:
    spec = ClipSpec(index=0, item_id=1, ost=0, src_start=0.0, take_duration=2.0, av_duration=2.0)
    cmd = build_clip_command(
        ffmpeg="ffmpeg",
        spec=spec,
        source_path=Path("s.mp4"),
        narration_path=Path("n.wav"),
        output_path=Path("c.mp4"),
        width=640,
        height=360,
        crf=20,
        preset="medium",
        original_gain_db=-15.0,
        bgm_path=Path("bgm.wav"),
        bgm_gain_db=-15.0,
        bgm_duck_db=-9.0,
    )
    # Three inputs: source + narration + bgm (looped).
    assert cmd.count("-i") == 3
    # ``-stream_loop -1`` immediately precedes the BGM ``-i`` so the placeholder
    # loops indefinitely under the clip.
    assert "-stream_loop" in cmd
    sl_idx = cmd.index("-stream_loop")
    assert cmd[sl_idx + 1] == "-1"
    assert cmd[sl_idx + 2] == "-i" and cmd[sl_idx + 3] == "bgm.wav"

    fc = cmd[cmd.index("-filter_complex") + 1]
    # 3-input amix replaces the legacy 2-input mix, side-chain compressor
    # pinned by the narration label drives the duck.
    assert "amix=inputs=3" in fc
    assert "amix=inputs=2" not in fc
    assert "sidechaincompress" in fc
    assert "[bgm_raw][narr]sidechaincompress" in fc
    # Limiter caps the final bus so amix overshoots can't clip.
    assert "alimiter" in fc


def test_build_clip_command_ost0_without_bgm_keeps_legacy_two_input_mix() -> None:
    # Backwards-compat: omitting bgm_path keeps the original 2-input filtergraph
    # (source + narration), no sidechain, no third input — so existing tasks
    # render byte-identically to the pre-BGM behaviour.
    spec = ClipSpec(index=0, item_id=1, ost=0, src_start=0.0, take_duration=2.0, av_duration=2.0)
    cmd = build_clip_command(
        ffmpeg="ffmpeg", spec=spec, source_path=Path("s.mp4"), narration_path=Path("n.wav"),
        output_path=Path("c.mp4"), width=640, height=360, crf=20, preset="medium",
        original_gain_db=-15.0,
    )
    assert cmd.count("-i") == 2
    assert "-stream_loop" not in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2" in fc
    assert "sidechaincompress" not in fc


def test_build_clip_command_ost0_requires_narration() -> None:
    spec = ClipSpec(index=0, item_id=1, ost=0, src_start=0.0, take_duration=1.0, av_duration=1.0)
    with pytest.raises(ValueError, match="narration_path"):
        build_clip_command(
            ffmpeg="ffmpeg", spec=spec, source_path=Path("s.mp4"), narration_path=None,
            output_path=Path("c.mp4"), width=640, height=360, crf=20, preset="medium",
            original_gain_db=-15.0,
        )


def test_concat_list_and_command(tmp_path: Path) -> None:
    clips = [tmp_path / "clip_0000.mp4", tmp_path / "clip_0001.mp4"]
    for c in clips:
        c.write_bytes(b"x")
    list_path = write_concat_list(clips, tmp_path / "concat.txt")
    content = list_path.read_text(encoding="utf-8")
    assert content.startswith("file '") and "clip_0000.mp4'" in content
    cmd = build_concat_command(ffmpeg="ffmpeg", list_path=list_path, output_path=tmp_path / "out.mp4")
    assert _arg_value(cmd, "-f") == "concat"
    assert _arg_value(cmd, "-c") == "copy"
    assert cmd[-1].endswith("out.mp4")


# --- adapter.run (TTS + ffmpeg mocked) ---------------------------------------

def _write_commentary(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "meta": {"commentary_style": "plot_recap", "narration_language": "zh"},
                "items": [
                    {"id": 1, "ost": 0, "src": [0.5, 6.0], "narration": "开场钩子。", "picture": "p"},
                    {"id": 2, "ost": 1, "src": [6.0, 10.0], "narration": "", "picture": "q"},
                    {"id": 3, "ost": 0, "src": [11.0, 18.0], "narration": "结尾悬念。", "picture": "r"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _patch_render(monkeypatch, captured: dict, *, audio_streams: int = 1) -> None:
    def fake_speech(*, text, language, backend, reference_audio_path, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"wav")
        return {"duration_sec": 2.0, "sample_rate": 48000, "mode": "designed",
                "backend": backend, "reference_used": reference_audio_path is not None}

    def fake_run(command, **kwargs):
        captured.setdefault("commands", []).append(command)
        Path(command[-1]).write_bytes(b"video")

    def fake_resolve(voice, **kwargs):
        ref = Path(kwargs["work_dir"]) / "narrator_ref.wav"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_bytes(b"wav")
        captured["resolved_voice"] = voice
        return ref

    monkeypatch.setattr(f"{_MODULE}.generate_speech", fake_speech)
    monkeypatch.setattr(f"{_MODULE}.run_stage_command", fake_run)
    monkeypatch.setattr("translip.commentary.voices.resolve_narrator_reference", fake_resolve)
    monkeypatch.setattr(f"{_MODULE}.ffmpeg_binary", lambda: "ffmpeg")
    monkeypatch.setattr(
        f"{_MODULE}.probe_media",
        lambda _p: SimpleNamespace(audio_stream_count=audio_streams, duration_sec=30.0),
    )
    monkeypatch.setattr(f"{_MODULE}.probe_video_resolution", lambda _p: (640, 360))


def test_adapter_assembles_recap(tmp_path: Path, monkeypatch) -> None:
    commentary_dir = tmp_path / "input" / "commentary_file"
    video_dir = tmp_path / "input" / "video_file"
    commentary_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)
    _write_commentary(commentary_dir / "commentary.json")
    (video_dir / "src.mp4").write_bytes(b"video")

    captured: dict = {}
    _patch_render(monkeypatch, captured)
    output_dir = tmp_path / "output"

    result = CommentaryRenderAdapter().run(
        {"commentary_file_id": "c", "video_file_id": "v", "backend": "qwen3tts"},
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    assert result["recap_file"] == "recap.mp4"
    assert result["clip_count"] == 3
    assert result["ost0_count"] == 2 and result["ost1_count"] == 1
    assert result["timeline_duration_sec"] == pytest.approx(2.0 + 4.0 + 2.0)
    assert (output_dir / "recap.mp4").exists()

    report = json.loads((output_dir / "commentary_render_report.json").read_text(encoding="utf-8"))
    assert report["clip_count"] == 3
    assert report["clips"][1]["ost"] == 1
    # Narrator reference is resolved by the voice library (built-in designed voice,
    # mocked) — no ffmpeg borrow; so just 3 per-clip renders + 1 concat.
    assert len(captured["commands"]) == 4
    assert captured["resolved_voice"] is None  # default selector threaded through


def test_adapter_threads_narrator_voice(tmp_path: Path, monkeypatch) -> None:
    commentary_dir = tmp_path / "input" / "commentary_file"
    video_dir = tmp_path / "input" / "video_file"
    commentary_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)
    _write_commentary(commentary_dir / "commentary.json")
    (video_dir / "src.mp4").write_bytes(b"video")

    captured: dict = {}
    _patch_render(monkeypatch, captured)
    CommentaryRenderAdapter().run(
        {
            "commentary_file_id": "c",
            "video_file_id": "v",
            "backend": "qwen3tts",
            "narrator_voice": "narrator-female-bright",
        },
        tmp_path / "input",
        tmp_path / "output",
        lambda *_a, **_k: None,
    )
    assert captured["resolved_voice"] == "narrator-female-bright"


def test_adapter_raises_without_source_audio(tmp_path: Path, monkeypatch) -> None:
    commentary_dir = tmp_path / "input" / "commentary_file"
    video_dir = tmp_path / "input" / "video_file"
    commentary_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)
    _write_commentary(commentary_dir / "commentary.json")
    (video_dir / "src.mp4").write_bytes(b"video")

    _patch_render(monkeypatch, {}, audio_streams=0)
    with pytest.raises(RuntimeError, match="没有音频轨"):
        CommentaryRenderAdapter().run(
            {"commentary_file_id": "c", "video_file_id": "v"},
            tmp_path / "input",
            tmp_path / "output",
            lambda *_a, **_k: None,
        )


# --- real ffmpeg integration (skipped when ffmpeg is absent) -----------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_render_really_produces_playable_recap(tmp_path: Path, monkeypatch) -> None:
    import soundfile as sf
    import numpy as np

    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    # A 12s source with both video and audio (sine), so OST=1 passthrough + OST=0
    # ducking both have real source audio to work with.
    commentary_dir = tmp_path / "input" / "commentary_file"
    video_dir = tmp_path / "input" / "video_file"
    commentary_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True)
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=12:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=330:duration=12",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
            str(video_dir / "src.mp4"),
        ],
        check=True,
    )
    commentary_dir.joinpath("commentary.json").write_text(
        json.dumps(
            {
                "meta": {"narration_language": "zh"},
                "items": [
                    {"id": 1, "ost": 0, "src": [0.0, 4.0], "narration": "开场。", "picture": "p"},
                    {"id": 2, "ost": 1, "src": [4.0, 8.0], "narration": "", "picture": "q"},
                    {"id": 3, "ost": 0, "src": [8.0, 11.0], "narration": "结尾。", "picture": "r"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Stub only the TTS: write a real 1.5s sine wav instead of loading a model.
    def fake_speech(*, text, language, backend, reference_audio_path, output_path):
        sr = 48000
        t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
        sf.write(str(output_path), 0.2 * np.sin(2 * np.pi * 220 * t), sr)
        return {"duration_sec": 1.5, "sample_rate": sr, "mode": "designed",
                "backend": backend, "reference_used": False}

    monkeypatch.setattr(f"{_MODULE}.generate_speech", fake_speech)

    output_dir = tmp_path / "output"
    # Use the "source" narrator voice so the reference comes from the real source
    # audio via ffmpeg — this exercises the render pipeline without loading the
    # VoiceDesign model (which the built-in voices would otherwise require).
    result = CommentaryRenderAdapter().run(
        {"commentary_file_id": "c", "video_file_id": "v", "backend": "qwen3tts", "narrator_voice": "source"},
        tmp_path / "input",
        output_dir,
        lambda *_a, **_k: None,
    )

    recap = output_dir / "recap.mp4"
    assert recap.exists() and recap.stat().st_size > 0
    assert result["clip_count"] == 3 and result["ost1_count"] == 1
    # Timeline ≈ 1.5 (ost0) + 4.0 (ost1) + 1.5 (ost0) = 7.0s; probe the real file.
    from translip.utils.ffmpeg import probe_media

    assert abs(float(probe_media(recap).duration_sec) - 7.0) < 1.0
