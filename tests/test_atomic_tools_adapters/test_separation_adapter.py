from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_separation_adapter_copies_runner_outputs(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.separation import SeparationAdapter

    input_file = tmp_path / "input" / "file" / "demo.mp4"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"video")
    output_dir = tmp_path / "output"
    progress: list[tuple[float, str | None]] = []

    def fake_separate_file(request):
        bundle_dir = tmp_path / "runner-output" / "demo"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        voice_path = bundle_dir / "voice.wav"
        background_path = bundle_dir / "background.wav"
        voice_path.write_bytes(b"voice")
        background_path.write_bytes(b"background")
        return SimpleNamespace(
            route=SimpleNamespace(route="dialogue", reason="speech-heavy"),
            artifacts=SimpleNamespace(
                voice_path=voice_path,
                background_path=background_path,
                manifest_path=bundle_dir / "manifest.json",
            ),
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.separation.separate_file",
        fake_separate_file,
    )

    result = SeparationAdapter().run(
        {"file_id": "fake", "mode": "auto", "quality": "balanced", "output_format": "wav"},
        input_file.parent.parent,
        output_dir,
        lambda percent, step=None: progress.append((percent, step)),
    )

    assert (output_dir / "voice.wav").read_bytes() == b"voice"
    assert (output_dir / "background.wav").read_bytes() == b"background"
    assert result["voice_file"] == "voice.wav"
    assert result["background_file"] == "background.wav"
    assert result["route"] == "dialogue"
    assert result["route_reason"] == "speech-heavy"
    assert any(step == "separating" for _, step in progress)
