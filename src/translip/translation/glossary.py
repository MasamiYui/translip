from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backend import canonical_language_code, output_tag_for_language

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GlossaryEntry:
    entry_id: str
    source_variants: tuple[str, ...]
    targets: dict[str, str]
    normalized_source: str | None = None


# The built-in glossary is intentionally EMPTY (TRA-2). Film-specific proper
# nouns (e.g. 《哪吒》 character names) used to be hardcoded here and force-applied
# to every zh->en job, which corrupted unrelated content. Ship such terms as a
# loadable asset instead — see `examples/glossary.zh-en.sample.json` — and pass
# them via `--glossary`, or set TRANSLIP_DEFAULT_GLOSSARY to a glossary JSON to
# apply a default to every job.
BUILTIN_DUBBING_GLOSSARY: tuple[GlossaryEntry, ...] = ()

# Env var pointing at a glossary JSON applied as the default for every job.
DEFAULT_GLOSSARY_ENV = "TRANSLIP_DEFAULT_GLOSSARY"


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
    """Default glossary applied to every job.

    The hardcoded tuple is empty (TRA-2); the only default terms come from a
    glossary JSON pointed to by ``TRANSLIP_DEFAULT_GLOSSARY`` (if set), so no
    film-specific names are forced onto unrelated content by default.
    """
    entries: list[GlossaryEntry] = []
    if canonical_language_code(source_lang) == "zh" and canonical_language_code(target_lang) == "en":
        entries.extend(BUILTIN_DUBBING_GLOSSARY)

    default_path = os.environ.get(DEFAULT_GLOSSARY_ENV, "").strip()
    if default_path:
        try:
            entries.extend(load_glossary(Path(default_path).expanduser()))
        except Exception:
            logger.warning(
                "Failed to load default glossary from %s=%s; ignoring.",
                DEFAULT_GLOSSARY_ENV,
                default_path,
                exc_info=True,
            )
    return entries


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
