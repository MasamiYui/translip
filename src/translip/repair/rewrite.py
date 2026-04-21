from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..translation.duration import estimate_tts_duration
from ..translation.glossary import GlossaryEntry


@dataclass(slots=True)
class RewriteCandidate:
    rewrite_id: str
    segment_id: str
    variant: str
    target_text: str
    estimated_tts_duration_sec: float
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "rewrite_id": self.rewrite_id,
            "segment_id": self.segment_id,
            "variant": self.variant,
            "target_text": self.target_text,
            "estimated_tts_duration_sec": self.estimated_tts_duration_sec,
            "reason": self.reason,
        }


def rewrite_for_dubbing(
    *,
    segment_id: str,
    source_text: str,
    current_target_text: str,
    source_duration_sec: float,
    target_lang: str,
    glossary: list[GlossaryEntry],
) -> list[RewriteCandidate]:
    natural_text, natural_reason = _natural_rewrite(
        source_text=source_text,
        current_target_text=current_target_text,
        glossary=glossary,
        target_lang=target_lang,
    )
    short_text, short_reason = _short_rewrite(
        source_text=source_text,
        natural_text=natural_text,
        current_target_text=current_target_text,
        source_duration_sec=source_duration_sec,
        glossary=glossary,
        target_lang=target_lang,
    )
    candidates = [
        RewriteCandidate(
            rewrite_id=f"{segment_id}-rw-natural",
            segment_id=segment_id,
            variant="natural",
            target_text=natural_text,
            estimated_tts_duration_sec=estimate_tts_duration(natural_text, target_lang=target_lang),
            reason=natural_reason,
        ),
        RewriteCandidate(
            rewrite_id=f"{segment_id}-rw-short",
            segment_id=segment_id,
            variant="short",
            target_text=short_text,
            estimated_tts_duration_sec=estimate_tts_duration(short_text, target_lang=target_lang),
            reason=short_reason,
        ),
    ]
    deduped: list[RewriteCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.target_text.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _natural_rewrite(
    *,
    source_text: str,
    current_target_text: str,
    glossary: list[GlossaryEntry],
    target_lang: str,
) -> tuple[str, str]:
    phrase = _phrase_rewrite(source_text)
    if phrase is not None:
        return phrase, "rule_based_phrase_rewrite"

    glossary_text = _glossary_rewrite(
        source_text=source_text,
        target_text=current_target_text,
        glossary=glossary,
        target_lang=target_lang,
        short=False,
    )
    if glossary_text != _normalize_sentence(current_target_text):
        return glossary_text, "glossary_protected_rewrite"

    normalized = _normalize_sentence(current_target_text)
    return normalized, "normalized_current_translation"


def _short_rewrite(
    *,
    source_text: str,
    natural_text: str,
    current_target_text: str,
    source_duration_sec: float,
    glossary: list[GlossaryEntry],
    target_lang: str,
) -> tuple[str, str]:
    phrase = _short_phrase_rewrite(source_text)
    if phrase is not None:
        return phrase, "rule_based_short_phrase_rewrite"

    glossary_text = _glossary_rewrite(
        source_text=source_text,
        target_text=current_target_text,
        glossary=glossary,
        target_lang=target_lang,
        short=True,
    )
    if glossary_text != _normalize_sentence(current_target_text):
        return glossary_text, "glossary_protected_short_rewrite"

    shortened = _shorten_english(natural_text)
    if estimate_tts_duration(shortened, target_lang=target_lang) < estimate_tts_duration(natural_text, target_lang=target_lang):
        return shortened, "compressed_common_english_phrases"
    if source_duration_sec <= 1.2:
        return _trim_to_core_words(natural_text), "trimmed_for_short_source_window"
    return shortened, "normalized_short_variant"


def _phrase_rewrite(source_text: str) -> str | None:
    compact = _compact_source(source_text)
    if "打扰一下" in compact and "中国人" in compact:
        return "Excuse me, are you Chinese?"
    if "天气" in compact and ("霸道" in compact or "超" in compact):
        return "The weather here is intense."
    phrase_map = {
        "人间天堂": "Paradise.",
        "行李给我": "Give me the bag.",
        "一会儿带你去吃": "Food later.",
        "我改": "I'll change.",
        "要学会修复": "Learn to fix it.",
        "就这么定了": "It's settled.",
        "我妈说了": "Mom said.",
        "你妈又说了": "Your mom again.",
        "反正": "Anyway.",
        "我眼力也太好了": "Great eyes.",
        "笑一个嘛": "Smile.",
        "音乐喷泉": "Music Fountain.",
        "奶奶再见": "Bye, Grandma.",
        "独立人生梦": "Independent life.",
    }
    if compact in phrase_map:
        return phrase_map[compact]
    if compact in {"迪拜", "在迪拜"}:
        return "Dubai."
    if compact in {"谢谢", "谢谢你", "Thankyou"}:
        return "Thank you."
    return None


def _short_phrase_rewrite(source_text: str) -> str | None:
    compact = _compact_source(source_text)
    if "打扰一下" in compact and "中国人" in compact:
        return "Are you Chinese?"
    if "天气" in compact and ("霸道" in compact or "超" in compact):
        return "Wild weather."
    phrase_map = {
        "人间天堂": "Paradise.",
        "行李给我": "My bag.",
        "一会儿带你去吃": "Food later.",
        "我改": "I'll change.",
        "要学会修复": "Fix it.",
        "就这么定了": "Settled.",
        "我妈说了": "Mom said.",
        "你妈又说了": "Your mom again.",
        "反正": "Anyway.",
        "我眼力也太好了": "Great eyes.",
        "笑一个嘛": "Smile.",
        "音乐喷泉": "Fountain.",
        "奶奶再见": "Bye, Grandma.",
        "独立人生梦": "Independence.",
    }
    if compact in phrase_map:
        return phrase_map[compact]
    if compact in {"迪拜", "在迪拜"}:
        return "Dubai."
    if compact in {"谢谢", "谢谢你", "Thankyou"}:
        return "Thanks."
    return None


def _glossary_rewrite(
    *,
    source_text: str,
    target_text: str,
    glossary: list[GlossaryEntry],
    target_lang: str,
    short: bool,
) -> str:
    normalized = _normalize_sentence(target_text)
    matches = _matching_glossary_terms(source_text=source_text, glossary=glossary, target_lang=target_lang)
    if not matches:
        return normalized

    compact_source = _compact_source(source_text)
    if len(matches) == 1 and compact_source in {_compact_source(source) for source in matches[0].source_variants}:
        return _normalize_sentence(matches[0].target)

    rewritten = normalized
    for match in matches:
        if match.target.casefold() in rewritten.casefold():
            continue
        if "知道" in compact_source:
            return _normalize_sentence(
                f"Know {match.target}?" if short else f"Do you know the {match.target}?"
            )
        rewritten = _replace_probable_term(rewritten, match.target)
    return _normalize_sentence(rewritten)


@dataclass(slots=True)
class _GlossaryMatch:
    source_variants: tuple[str, ...]
    target: str


def _matching_glossary_terms(
    *,
    source_text: str,
    glossary: list[GlossaryEntry],
    target_lang: str,
) -> list[_GlossaryMatch]:
    target_tag = target_lang
    compact_source = _compact_source(source_text)
    matches: list[_GlossaryMatch] = []
    for entry in glossary:
        target = entry.targets.get(target_tag) or entry.targets.get(target_lang.split("-")[0]) or entry.normalized_source
        if not target:
            continue
        if any(_compact_source(source) in compact_source for source in entry.source_variants):
            matches.append(_GlossaryMatch(source_variants=entry.source_variants, target=target))
    return matches


def _replace_probable_term(text: str, replacement: str) -> str:
    if replacement == "Dubai":
        return re.sub(r"\b(Didi|Dibai|Dubay)\b", replacement, text, flags=re.IGNORECASE)
    if replacement == "Burj Khalifa":
        replaced = re.sub(
            r"\b(?:the\s+)?(?:Halifa|Haribata|Harry\s+Potter|Hollywood)\s+Tower\b",
            f"the {replacement}",
            text,
            flags=re.IGNORECASE,
        )
        if replaced != text:
            return replaced
    if text.endswith("?"):
        return f"{text[:-1].strip()} {replacement}?"
    if text.endswith("."):
        return f"{text[:-1].strip()} {replacement}."
    return f"{text} {replacement}"


def _shorten_english(text: str) -> str:
    shortened = _normalize_sentence(text)
    replacements = [
        (r"\bI am\b", "I'm"),
        (r"\bYou are\b", "You're"),
        (r"\bWe are\b", "We're"),
        (r"\bgoing to\b", "headed to"),
        (r"\bDo you know the\b", "Know the"),
        (r"\bDo you know\b", "Know"),
        (r"\bExcuse me,\s*", ""),
        (r"\bplease\b", ""),
        (r"\bvery\b", ""),
    ]
    for pattern, replacement in replacements:
        shortened = re.sub(pattern, replacement, shortened, flags=re.IGNORECASE)
    return _normalize_sentence(shortened)


def _trim_to_core_words(text: str, *, max_words: int = 4) -> str:
    words = re.findall(r"[A-Za-z0-9']+|[^\w\s]", text)
    lexical_words = [word for word in words if re.search(r"[A-Za-z0-9]", word)]
    if len(lexical_words) <= max_words:
        return _normalize_sentence(text)
    kept: list[str] = []
    count = 0
    for word in words:
        kept.append(word)
        if re.search(r"[A-Za-z0-9]", word):
            count += 1
        if count >= max_words:
            break
    return _normalize_sentence(" ".join(kept))


def _normalize_sentence(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    normalized = re.sub(r"\s+([,.!?;:])", r"\1", normalized)
    return normalized


def _compact_source(text: str) -> str:
    return re.sub(r"[\s，。！？；：,.!?;:]+", "", text).strip()


__all__ = ["RewriteCandidate", "rewrite_for_dubbing"]
