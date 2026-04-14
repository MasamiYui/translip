from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol


_LANGUAGE_ALIASES = {
    "zh": "zh",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "zho_hans": "zh",
    "cmn_hans": "zh",
    "en": "en",
    "eng_latn": "en",
    "english": "en",
    "ja": "ja",
    "jpn_jpan": "ja",
    "japanese": "ja",
}

_OUTPUT_TAGS = {
    "zh": "zh-Hans",
    "en": "en",
    "ja": "ja",
}


def canonical_language_code(language: str) -> str:
    key = language.strip().lower().replace(" ", "").replace("-", "_")
    return _LANGUAGE_ALIASES.get(key, language.strip())


def output_tag_for_language(language: str) -> str:
    canonical = canonical_language_code(language)
    if canonical in _OUTPUT_TAGS:
        return _OUTPUT_TAGS[canonical]
    sanitized = re.sub(r"[^A-Za-z0-9.-]+", "-", canonical).strip("-")
    return sanitized or "target"


def m2m100_language_code(language: str) -> str:
    canonical = canonical_language_code(language)
    if canonical not in {"zh", "en", "ja"}:
        raise ValueError(f"Unsupported M2M100 language code: {language}")
    return canonical


@dataclass(slots=True)
class BackendSegmentInput:
    segment_id: str
    source_text: str
    context_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BackendSegmentOutput:
    segment_id: str
    target_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TranslationBackend(Protocol):
    backend_name: str
    resolved_model: str
    resolved_device: str | None

    def translate_batch(
        self,
        *,
        items: list[BackendSegmentInput],
        source_lang: str,
        target_lang: str,
    ) -> list[BackendSegmentOutput]:
        ...
