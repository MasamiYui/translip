from __future__ import annotations

import re


def build_qa_flags(
    *,
    source_text: str,
    target_text: str,
    glossary_matches: list[dict[str, object]],
    duration_budget: dict[str, object],
) -> list[str]:
    flags: list[str] = []
    if _has_mixed_language(source_text):
        flags.append("mixed_language")
    if len(source_text.strip()) <= 2:
        flags.append("too_short_source")
    if re.search(r"\d", source_text):
        flags.append("contains_number")
    if glossary_matches:
        flags.append("contains_protected_term")
    if _source_maybe_asr_error(source_text):
        flags.append("source_maybe_asr_error")
    fit_level = str(duration_budget.get("fit_level", "fit"))
    if fit_level == "review":
        flags.append("duration_may_overrun")
    elif fit_level == "risky":
        flags.append("duration_risky")
    if not target_text.strip():
        flags.append("empty_target")
    return flags


def _has_mixed_language(text: str) -> bool:
    has_ascii = bool(re.search(r"[A-Za-z]", text))
    has_cjk = bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))
    return has_ascii and has_cjk


def _source_maybe_asr_error(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if re.search(r"(.)\1{4,}", stripped):
        return True
    return False
