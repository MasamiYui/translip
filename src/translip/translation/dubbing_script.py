from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .backend import canonical_language_code


@dataclass(slots=True)
class DubbingScriptDecision:
    target_text: str
    dubbing_text: str
    script_status: str
    risk_flags: list[str]
    notes: list[str]


_PHRASE_OVERRIDES_ZH_EN = {
    "报": "Report.",
    "敖丙": "Ao Bing.",
    "哪吒": "Ne Zha.",
    "吒儿": "Ne Zha.",
    "你是妖": "You are a demon.",
    "我是魔": "I am a demon.",
    "讨伐龙族": "Attack the dragons.",
    "召集全体成员": "Gather everyone.",
    "陈塘关全军戒备": "Chentang Pass, stand ready.",
    "在外遇事要冷静": "Stay calm out there.",
    "爹娘为我操碎了心": "Mom and Dad worry so much about me.",
}


def polish_dubbing_script(
    *,
    source_text: str,
    target_text: str,
    source_lang: str,
    target_lang: str,
    source_duration_sec: float,
    glossary_matches: list[dict[str, Any]],
) -> DubbingScriptDecision:
    normalized = _normalize_spaces(target_text)
    risk_flags: list[str] = []
    notes: list[str] = []

    source_key = _normalize_source(source_text)
    if canonical_language_code(source_lang) == "zh" and canonical_language_code(target_lang) == "en":
        override = _PHRASE_OVERRIDES_ZH_EN.get(source_key)
        if override:
            normalized = override
            notes.append("builtin_phrase_override")

    missing_terms = _missing_glossary_terms(normalized, glossary_matches)
    if missing_terms:
        risk_flags.append("protected_term_missing")
        notes.extend(f"missing_protected_term:{term}" for term in missing_terms)

    if source_duration_sec < 1.4 or len(source_key) <= 2:
        risk_flags.append("needs_dubbing_unit")
    if _looks_like_fragment(normalized):
        risk_flags.append("target_fragment")

    dubbing_text = _punctuate_for_tts(normalized, target_lang=target_lang)
    script_status = "review" if risk_flags else "ready"
    return DubbingScriptDecision(
        target_text=normalized,
        dubbing_text=dubbing_text,
        script_status=script_status,
        risk_flags=_dedupe(risk_flags),
        notes=_dedupe(notes),
    )


def _missing_glossary_terms(target_text: str, matches: list[dict[str, Any]]) -> list[str]:
    lowered = target_text.lower()
    missing: list[str] = []
    for match in matches:
        replacement = str(match.get("replacement_text") or "").strip()
        if replacement and replacement.lower() not in lowered:
            missing.append(replacement)
    return _dedupe(missing)


def _looks_like_fragment(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped.split()) <= 1 and not re.search(r"[.!?。！？]$", stripped):
        return True
    return False


# Contrastive/causal conjunctions that reliably take a preceding comma when they
# join clauses (excludes "and"/"or"/"so" which are often non-clausal and would
# produce spurious commas).
_EN_PAUSE_CONJUNCTIONS = frozenset({"but", "because", "though", "however", "while"})


def _insert_breath_pause_en(text: str) -> str:
    """Insert a single breath comma before a clause-joining conjunction in a long
    English line that has no internal punctuation, so the TTS phrases it instead
    of running it together. Conservative: long lines only, never near the ends."""
    if "," in text:
        return text
    words = text.split()
    if len(words) < 12:
        return text
    for index in range(2, len(words) - 2):
        bare = words[index].lower().strip(".,!?;:")
        if bare in _EN_PAUSE_CONJUNCTIONS:
            words[index - 1] = words[index - 1] + ","
            return " ".join(words)
    return text


def _punctuate_for_tts(text: str, *, target_lang: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    if re.search(r"[.!?。！？]$", stripped):
        return stripped
    lang = canonical_language_code(target_lang)
    if lang == "en":
        stripped = _insert_breath_pause_en(stripped)
    # Terminal punctuation for every language (was English-only) so the TTS applies
    # final intonation instead of trailing off.
    return f"{stripped}。" if lang in ("zh", "ja") else f"{stripped}."


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_source(text: str) -> str:
    return re.sub(r"[\s，。！？；：,.!?;:]+", "", text).strip()


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
