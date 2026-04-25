"""Tests for the BUILTIN_DUBBING_GLOSSARY expansion (Sprint 1).

Regression guard: the new Dubai/UAE travel entries must be applied automatically
for zh->en dubbing jobs so that mistranslations seen in task-20260425-023015
("Halifa Tower", "Alibaba Tower", etc.) cannot reappear.
"""

from __future__ import annotations

import json
from pathlib import Path

from translip.translation.glossary import (
    BUILTIN_DUBBING_GLOSSARY,
    apply_glossary,
    built_in_dubbing_glossary,
    load_glossary,
    merge_glossaries,
)


def _entry_ids() -> set[str]:
    return {entry.entry_id for entry in BUILTIN_DUBBING_GLOSSARY}


def test_travel_entries_present_in_builtin_list() -> None:
    ids = _entry_ids()
    for required in (
        "builtin-burj-khalifa",
        "builtin-uae",
        "builtin-abu-dhabi",
        "builtin-palm-jumeirah",
        "builtin-dubai-mall",
        "builtin-burj-al-arab",
    ):
        assert required in ids, f"Missing builtin glossary entry: {required}"


def test_burj_khalifa_variants_translate_to_burj_khalifa() -> None:
    glossary = built_in_dubbing_glossary(source_lang="zh", target_lang="en")
    for variant in ("哈利法塔", "哈里法塔", "哈利发塔", "哈里巴塔"):
        processed, matches = apply_glossary(
            f"我们今天去{variant}观光",
            target_lang="en",
            glossary=glossary,
        )
        assert "Burj Khalifa" in processed, f"variant {variant!r} did not resolve to Burj Khalifa"
        assert any(match["entry_id"] == "builtin-burj-khalifa" for match in matches)


def test_dubai_translation_still_works() -> None:
    glossary = built_in_dubbing_glossary(source_lang="zh", target_lang="en")
    processed, matches = apply_glossary(
        "我在迪拜等你",
        target_lang="en",
        glossary=glossary,
    )
    assert "Dubai" in processed
    assert any(match["entry_id"] == "builtin-dubai" for match in matches)


def test_builtin_glossary_only_activates_for_zh_to_en() -> None:
    assert built_in_dubbing_glossary(source_lang="en", target_lang="zh") == []
    assert built_in_dubbing_glossary(source_lang="zh", target_lang="ja") == []


def test_travel_glossary_file_is_valid_and_loadable() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "config" / "glossary.travel.json"
    assert path.exists(), "glossary.travel.json must ship in the repo under config/"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "entries" in payload and payload["entries"], "entries list must be present"

    glossary = load_glossary(path)
    assert glossary, "glossary loader should return non-empty list"
    entry_ids = {entry.entry_id for entry in glossary}
    assert "landmark-burj-khalifa" in entry_ids
    assert "name-harry-potter" in entry_ids

    processed, _ = apply_glossary(
        "上次去哈利法塔,然后跟哈利波特合影",
        target_lang="en",
        glossary=glossary,
    )
    assert "Burj Khalifa" in processed
    assert "Harry Potter" in processed


def test_merge_glossaries_prefers_user_entries() -> None:
    user = load_glossary(
        Path(__file__).resolve().parents[1] / "config" / "glossary.example.json"
    )
    built_in = built_in_dubbing_glossary(source_lang="zh", target_lang="en")
    merged = merge_glossaries(user_glossary=user, built_in_glossary=built_in)
    user_ids = {entry.entry_id for entry in user}
    # User-provided IDs must be preserved as-is
    for user_id in user_ids:
        assert user_id in {entry.entry_id for entry in merged}
    # Built-in entries not shadowed by user glossary must still appear
    assert any(entry.entry_id == "builtin-uae" for entry in merged)


if __name__ == "__main__":  # pragma: no cover
    import pytest

    pytest.main([__file__, "-v"])
