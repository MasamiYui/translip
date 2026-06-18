from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


TRANSLATION = {
    "backend": {"target_lang": "en"},
    "segments": [
        {"segment_id": "seg-0001", "speaker_id": "spk_0", "start": 0.0, "end": 1.5, "duration": 1.5, "target_text": "Hello there"},
        {"segment_id": "seg-0002", "speaker_id": "spk_1", "start": 2.0, "end": 3.0, "duration": 1.0, "target_text": "Goodbye"},
        {"segment_id": "seg-0003", "speaker_id": "spk_0", "start": 4.0, "end": 5.0, "duration": 1.0, "target_text": "   "},
    ],
}


def _make_inputs(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    (input_dir / "translation_file").mkdir(parents=True)
    (input_dir / "background_file").mkdir(parents=True)
    (input_dir / "translation_file" / "translation.en.json").write_text(
        json.dumps(TRANSLATION), encoding="utf-8"
    )
    (input_dir / "background_file" / "bg.wav").write_bytes(b"bg")
    return input_dir


def test_dub_render_synthesizes_per_segment_and_renders(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters import dub_render as mod

    input_dir = _make_inputs(tmp_path)
    output_dir = tmp_path / "output"

    synth_calls: list[str] = []

    def fake_generate_speech(*, text, language, backend, reference_audio_path, output_path):
        synth_calls.append(text)
        output_path.write_bytes(b"wav")
        return {"duration_sec": 1.2, "sample_rate": 24000}

    captured: dict = {}

    def fake_render_dub(request):
        captured["request"] = request
        # The renderer's report + anchor must already be on disk and parseable.
        report = json.loads(Path(request.task_d_report_paths[0]).read_text())
        captured["report"] = report
        captured["anchor"] = json.loads(Path(request.segments_path).read_text())
        mix = Path(request.output_dir) / "preview_mix.en.wav"
        mix.parent.mkdir(parents=True, exist_ok=True)
        mix.write_bytes(b"mix")
        artifacts = SimpleNamespace(preview_mix_wav_path=mix)
        return SimpleNamespace(artifacts=artifacts)

    monkeypatch.setattr(mod, "generate_speech", fake_generate_speech)
    monkeypatch.setattr(mod, "render_dub", fake_render_dub)

    result = mod.DubRenderAdapter().run(
        {"translation_file_id": "t", "background_file_id": "b", "backend": "qwen3tts", "target_lang": "auto"},
        input_dir,
        output_dir,
        lambda *_a, **_k: None,
    )

    # Empty/whitespace line (seg-0003) is skipped for synthesis...
    assert synth_calls == ["Hello there", "Goodbye"]
    # ...but still appears in the timing anchor so the timeline stays intact.
    assert [s["segment_id"] for s in captured["anchor"]["segments"]] == ["seg-0001", "seg-0002", "seg-0003"]
    assert len(captured["report"]["segments"]) == 2
    assert captured["report"]["backend"]["target_lang"] == "en"
    row = captured["report"]["segments"][0]
    assert row["generated_duration_sec"] == 1.2 and row["source_duration_sec"] == 1.5
    assert row["overall_status"] == "passed" and Path(row["audio_path"]).is_absolute()
    # Renderer params propagate; no video → audio-only result.
    assert captured["request"].target_lang == "en"
    assert result["mixed_audio_file"] == "dub_mix.en.wav"
    assert result["dubbed_segments"] == 2 and result["total_segments"] == 3
    assert "output_file" not in result
    assert (output_dir / "dub_mix.en.wav").read_bytes() == b"mix"


def test_dub_render_muxes_when_video_provided(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters import dub_render as mod

    input_dir = _make_inputs(tmp_path)
    (input_dir / "video_file").mkdir(parents=True)
    (input_dir / "video_file" / "clip.mp4").write_bytes(b"video")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        mod, "generate_speech",
        lambda **k: (k["output_path"].write_bytes(b"wav"), {"duration_sec": 1.0, "sample_rate": 24000})[1],
    )

    def fake_render_dub(request):
        mix = Path(request.output_dir) / "preview_mix.en.wav"
        mix.parent.mkdir(parents=True, exist_ok=True)
        mix.write_bytes(b"mix")
        return SimpleNamespace(artifacts=SimpleNamespace(preview_mix_wav_path=mix))

    monkeypatch.setattr(mod, "render_dub", fake_render_dub)
    mux_calls: dict = {}

    def fake_mux(**kwargs):
        kwargs["output_path"].write_bytes(b"dubbed")
        mux_calls.update(kwargs)
        return kwargs["output_path"]

    monkeypatch.setattr(mod, "mux_video_with_audio", fake_mux)

    result = mod.DubRenderAdapter().run(
        {"translation_file_id": "t", "background_file_id": "b", "video_file_id": "v"},
        input_dir,
        output_dir,
        lambda *_a, **_k: None,
    )

    assert result["output_file"] == "dubbed.mp4"
    assert (output_dir / "dubbed.mp4").read_bytes() == b"dubbed"
    assert mux_calls["input_audio_path"].name == "dub_mix.en.wav"
