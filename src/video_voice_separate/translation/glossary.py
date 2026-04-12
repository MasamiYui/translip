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
