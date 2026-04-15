from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_probe_adapter_writes_report_and_result_payload(tmp_path: Path, monkeypatch) -> None:
    from translip.server.atomic_tools.adapters.probe import ProbeAdapter

    input_file = tmp_path / "input" / "file" / "demo.mp4"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b"video")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.probe.probe_media",
        lambda path: SimpleNamespace(
            media_type="video",
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration_sec=15.2,
            audio_stream_count=1,
            sample_rate=48_000,
            channels=2,
        ),
    )

    result = ProbeAdapter().run(
        {"file_id": "fake"},
        input_file.parent.parent,
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    report = json.loads((output_dir / "probe.json").read_text(encoding="utf-8"))
    assert report["duration_sec"] == 15.2
    assert result["format_name"] == "mov,mp4,m4a,3gp,3g2,mj2"
    assert result["has_video"] is True
    assert result["audio_streams"] == 1
