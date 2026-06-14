from __future__ import annotations

import json
from pathlib import Path

from translip.orchestration.commands import build_task_a_command, glossary_hotwords
from translip.types import PipelineRequest


def _glossary_file(tmp_path: Path) -> Path:
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {"source_variants": ["哪吒", "吒儿"], "targets": {"en": "Ne Zha"}},
                    {"source_variants": ["敖丙"], "targets": {"en": "Ao Bing"}},
                    {"source_variants": ["哪吒"], "targets": {"en": "dup"}},  # deduped
                    {"source_variants": ["bad,term"], "targets": {"en": "x"}},  # comma -> skipped
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _request(tmp_path: Path, *, glossary: Path | None = None) -> PipelineRequest:
    return PipelineRequest(
        input_path=tmp_path / "in.mp4",
        output_root=tmp_path / "out",
        glossary_path=glossary,
    )


def test_glossary_hotwords_extracts_dedups_and_skips_commas(tmp_path: Path) -> None:
    request = _request(tmp_path, glossary=_glossary_file(tmp_path))
    assert glossary_hotwords(request) == ["哪吒", "吒儿", "敖丙"]


def test_glossary_hotwords_empty_without_glossary(tmp_path: Path) -> None:
    assert glossary_hotwords(_request(tmp_path)) == []


def test_glossary_hotwords_tolerates_missing_file(tmp_path: Path) -> None:
    request = _request(tmp_path, glossary=tmp_path / "does-not-exist.json")
    assert glossary_hotwords(request) == []


def test_build_task_a_command_feeds_glossary_hotwords(tmp_path: Path) -> None:
    request = _request(tmp_path, glossary=_glossary_file(tmp_path))
    command = build_task_a_command(request)
    assert "--hotwords" in command
    assert command[command.index("--hotwords") + 1] == "哪吒,吒儿,敖丙"


def test_build_task_a_command_omits_hotwords_without_glossary(tmp_path: Path) -> None:
    assert "--hotwords" not in build_task_a_command(_request(tmp_path))


def test_task_a_cache_key_tracks_glossary_hotwords(tmp_path: Path) -> None:
    # ARCH-4: changing the glossary changes the transcription hotwords, so the cache key
    # must change too (otherwise stale ASR would be reused).
    from translip.orchestration.cache import compute_cache_key
    from translip.orchestration.runner import _stage_cache_payload

    request = _request(tmp_path)
    key_without = compute_cache_key(_stage_cache_payload(request, "transcription"))

    request.glossary_path = _glossary_file(tmp_path)
    key_with = compute_cache_key(_stage_cache_payload(request, "transcription"))

    assert key_without != key_with
