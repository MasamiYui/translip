from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_translation_adapter_builds_temp_payloads_and_outputs_translated_text(
    tmp_path: Path, monkeypatch
) -> None:
    from translip.server.atomic_tools.adapters.translation import TranslationAdapter

    output_dir = tmp_path / "output"
    captured: dict[str, object] = {}

    def fake_translate_script(request):
        captured["request"] = request
        bundle_dir = tmp_path / "runner-output" / "translation"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        translation_json = bundle_dir / "translation.en.json"
        translation_json.write_text(
            json.dumps(
                {
                    "segments": [
                        {"segment_id": "seg-1", "target_text": "Hello Dubai"},
                        {"segment_id": "seg-2", "target_text": "Welcome back"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        srt_path = bundle_dir / "translation.en.srt"
        srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello Dubai\n", encoding="utf-8")
        editable_json = bundle_dir / "translation.en.editable.json"
        editable_json.write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            artifacts=SimpleNamespace(
                translation_json_path=translation_json,
                editable_json_path=editable_json,
                srt_path=srt_path,
                manifest_path=bundle_dir / "task-c-manifest.json",
            )
        )

    monkeypatch.setattr(
        "translip.server.atomic_tools.adapters.translation.translate_script",
        fake_translate_script,
    )

    result = TranslationAdapter().run(
        {
            "text": "我在迪拜\n欢迎回来",
            "source_lang": "zh",
            "target_lang": "en",
            "backend": "local-m2m100",
        },
        tmp_path / "input",
        output_dir,
        lambda *_args, **_kwargs: None,
    )

    request = captured["request"]
    assert Path(request.segments_path).exists()
    assert Path(request.profiles_path).exists()
    assert json.loads(Path(request.segments_path).read_text(encoding="utf-8"))["segments"][0]["text"] == "我在迪拜"
    assert (output_dir / "translation.en.json").exists()
    assert (output_dir / "translation.en.srt").exists()
    assert (output_dir / "translation.en.txt").read_text(encoding="utf-8") == "Hello Dubai\nWelcome back"
    assert result["translated_text"] == "Hello Dubai\nWelcome back"
    assert result["translation_file"] == "translation.en.txt"
