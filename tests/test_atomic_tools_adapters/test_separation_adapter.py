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
        manifest_path = bundle_dir / "manifest.json"
        voice_path.write_bytes(b"voice")
        background_path.write_bytes(b"background")
        manifest_path.write_text('{"ok": true}', encoding="utf-8")
        return SimpleNamespace(
            route=SimpleNamespace(route="dialogue", reason="speech-heavy"),
            artifacts=SimpleNamespace(
                voice_path=voice_path,
                background_path=background_path,
                manifest_path=manifest_path,
                bundle_dir=bundle_dir,
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
    assert (output_dir / "manifest.json").read_text(encoding="utf-8") == '{"ok": true}'
    assert result["voice_file"] == "voice.wav"
    assert result["background_file"] == "background.wav"
    assert result["manifest_file"] == "manifest.json"
    assert result["route"] == "dialogue"
    assert result["route_reason"] == "speech-heavy"
    assert any(step == "separating" for _, step in progress)


def test_separation_adapter_removes_nested_runner_bundle_after_flattening(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.server.atomic_tools.adapters.separation import SeparationAdapter

    input_file = tmp_path / "input" / "file" / "demo.mp4"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"video")
    output_dir = tmp_path / "output"

    def fake_separate_file(request):
        bundle_dir = output_dir / "demo"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        voice_path = bundle_dir / "voice.wav"
        background_path = bundle_dir / "background.wav"
        manifest_path = bundle_dir / "manifest.json"
        voice_path.write_bytes(b"voice")
        background_path.write_bytes(b"background")
        manifest_path.write_text('{"ok": true}', encoding="utf-8")
        return SimpleNamespace(
            route=SimpleNamespace(route="music", reason="heuristic"),
            artifacts=SimpleNamespace(
                voice_path=voice_path,
                background_path=background_path,
                manifest_path=manifest_path,
                bundle_dir=bundle_dir,
            ),
            manifest={},
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.separation.separate_file",
        fake_separate_file,
    )

    SeparationAdapter().run(
        {"file_id": "fake", "mode": "auto", "quality": "balanced", "output_format": "wav"},
        input_file.parent.parent,
        output_dir,
        lambda percent, step=None: None,
    )

    assert (output_dir / "voice.wav").exists()
    assert (output_dir / "background.wav").exists()
    assert (output_dir / "manifest.json").exists()
    assert not (output_dir / "demo").exists()
