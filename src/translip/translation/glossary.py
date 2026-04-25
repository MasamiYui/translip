from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend import canonical_language_code, output_tag_for_language


@dataclass(slots=True)
class GlossaryEntry:
    entry_id: str
    source_variants: tuple[str, ...]
    targets: dict[str, str]
    normalized_source: str | None = None


BUILTIN_DUBBING_GLOSSARY: tuple[GlossaryEntry, ...] = (
    GlossaryEntry(
        entry_id="builtin-ne-zha",
        source_variants=("哪吒", "吒儿"),
        targets={"en": "Ne Zha"},
        normalized_source="哪吒",
    ),
    GlossaryEntry(
        entry_id="builtin-ao-bing",
        source_variants=("敖丙",),
        targets={"en": "Ao Bing"},
        normalized_source="敖丙",
    ),
    GlossaryEntry(
        entry_id="builtin-chentang-pass",
        source_variants=("陈塘关",),
        targets={"en": "Chentang Pass"},
        normalized_source="陈塘关",
    ),
    GlossaryEntry(
        entry_id="builtin-shen-gongbao",
        source_variants=("申公豹",),
        targets={"en": "Shen Gongbao"},
        normalized_source="申公豹",
    ),
    GlossaryEntry(
        entry_id="builtin-east-sea-dragon-clan",
        source_variants=("东海龙族", "龙族"),
        targets={"en": "East Sea Dragon Clan"},
        normalized_source="东海龙族",
    ),
    GlossaryEntry(
        entry_id="builtin-heavenly-tribulation",
        source_variants=("天劫",),
        targets={"en": "Heavenly Tribulation"},
        normalized_source="天劫",
    ),
    GlossaryEntry(
        entry_id="builtin-dubai",
        source_variants=("迪拜",),
        targets={"en": "Dubai"},
        normalized_source="迪拜",
    ),
    # --- Sprint 1 additions: travel / UAE landmarks commonly mis-translated by
    # local-m2m100 in task-20260425-023015 (Halifa Tower/Harry Potter/Alibaba).
    GlossaryEntry(
        entry_id="builtin-burj-khalifa",
        source_variants=("哈利法塔", "哈里法塔", "哈利发塔", "哈里巴塔", "哈里法大厦"),
        targets={"en": "Burj Khalifa"},
        normalized_source="哈利法塔",
    ),
    GlossaryEntry(
        entry_id="builtin-uae",
        source_variants=("阿联酋", "阿拉伯联合酋长国"),
        targets={"en": "the United Arab Emirates"},
        normalized_source="阿联酋",
    ),
    GlossaryEntry(
        entry_id="builtin-abu-dhabi",
        source_variants=("阿布扎比",),
        targets={"en": "Abu Dhabi"},
        normalized_source="阿布扎比",
    ),
    GlossaryEntry(
        entry_id="builtin-palm-jumeirah",
        source_variants=("棕榈岛", "朱美拉棕榈岛"),
        targets={"en": "Palm Jumeirah"},
        normalized_source="棕榈岛",
    ),
    GlossaryEntry(
        entry_id="builtin-dubai-mall",
        source_variants=("迪拜购物中心", "迪拜商场"),
        targets={"en": "The Dubai Mall"},
        normalized_source="迪拜购物中心",
    ),
    GlossaryEntry(
        entry_id="builtin-burj-al-arab",
        source_variants=("帆船酒店", "阿拉伯塔"),
        targets={"en": "Burj Al Arab"},
        normalized_source="帆船酒店",
    ),
)


def load_glossary(glossary_path: Path | None) -> list[GlossaryEntry]:
    if glossary_path is None:
        return []
    payload = json.loads(glossary_path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    glossary: list[GlossaryEntry] = []
    for index, raw_entry in enumerate(entries, start=1):
        source_variants = tuple(
            variant.strip() for variant in raw_entry.get("source_variants", []) if variant.strip()
        )
        if not source_variants:
            continue
        glossary.append(
            GlossaryEntry(
                entry_id=raw_entry.get("entry_id", f"term-{index:04d}"),
                source_variants=source_variants,
                targets={str(key): str(value) for key, value in raw_entry.get("targets", {}).items()},
                normalized_source=raw_entry.get("normalized_source"),
            )
        )
    return glossary


def built_in_dubbing_glossary(*, source_lang: str, target_lang: str) -> list[GlossaryEntry]:
    if canonical_language_code(source_lang) != "zh" or canonical_language_code(target_lang) != "en":
        return []
    return list(BUILTIN_DUBBING_GLOSSARY)


def merge_glossaries(
    *,
    user_glossary: list[GlossaryEntry],
    built_in_glossary: list[GlossaryEntry],
) -> list[GlossaryEntry]:
    if not built_in_glossary:
        return list(user_glossary)
    user_ids = {entry.entry_id for entry in user_glossary}
    user_sources = {
        _normalize_source_for_term_check(variant)
        for entry in user_glossary
        for variant in entry.source_variants
    }
    merged = list(user_glossary)
    for entry in built_in_glossary:
        if entry.entry_id in user_ids:
            continue
        normalized_sources = {
            _normalize_source_for_term_check(variant)
            for variant in entry.source_variants
        }
        if normalized_sources & user_sources:
            continue
        merged.append(entry)
    return merged


def apply_glossary(
    text: str,
    *,
    target_lang: str,
    glossary: list[GlossaryEntry],
) -> tuple[str, list[dict[str, Any]]]:
    if not glossary:
        return text, []

    target_tag = output_tag_for_language(target_lang)
    canonical_lang = canonical_language_code(target_lang)
    processed = text
    matches: list[dict[str, Any]] = []

    for entry in glossary:
        replacement = (
            entry.targets.get(target_tag)
            or entry.targets.get(canonical_lang)
            or entry.normalized_source
        )
        if not replacement:
            continue
        for source in sorted(entry.source_variants, key=len, reverse=True):
            if source not in processed:
                continue
            processed = processed.replace(source, replacement)
            matches.append(
                {
                    "entry_id": entry.entry_id,
                    "matched_text": source,
                    "replacement_text": replacement,
                }
            )
    return _normalize_spaces(processed), matches


def normalize_target_with_glossary(
    *,
    source_text: str,
    target_text: str,
    glossary_matches: list[dict[str, Any]],
) -> str:
    if len(glossary_matches) != 1:
        return _normalize_spaces(target_text)
    source_normalized = _normalize_source_for_term_check(source_text)
    matched = _normalize_source_for_term_check(str(glossary_matches[0]["matched_text"]))
    if not source_normalized or source_normalized != matched:
        return _normalize_spaces(target_text)
    return _normalize_spaces(str(glossary_matches[0]["replacement_text"]))


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_source_for_term_check(text: str) -> str:
    return re.sub(r"[\s，。！？；：,.!?;:]+", "", text).strip()
