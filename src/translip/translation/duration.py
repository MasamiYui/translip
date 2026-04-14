from __future__ import annotations

import math
import re

from .backend import canonical_language_code


def estimate_tts_duration(text: str, *, target_lang: str) -> float:
    normalized = text.strip()
    if not normalized:
        return 0.0
    canonical = canonical_language_code(target_lang)
    punctuation_count = len(re.findall(r"[,.!?;:，。！？；：、]", normalized))
    if canonical == "en":
        unit_count = max(1, len(re.findall(r"[A-Za-z0-9']+", normalized)))
        base = unit_count * 0.34
    elif canonical == "ja":
        unit_count = max(1, len(re.findall(r"[\u3040-\u30ff\u3400-\u9fffA-Za-z0-9]", normalized)))
        base = unit_count * 0.16
    elif canonical == "zh":
        unit_count = max(1, len(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", normalized)))
        base = unit_count * 0.22
    else:
        unit_count = max(1, len(re.findall(r"\S+", normalized)))
        base = unit_count * 0.28
    estimate = base + punctuation_count * 0.12
    return round(max(0.35, estimate), 3)


def build_duration_budget(
    *,
    source_duration_sec: float,
    target_text: str,
    target_lang: str,
) -> dict[str, float | str]:
    estimated = estimate_tts_duration(target_text, target_lang=target_lang)
    source_duration = max(0.001, source_duration_sec)
    ratio = estimated / source_duration
    if ratio <= 1.10:
        fit_level = "fit"
    elif ratio <= 1.30:
        fit_level = "review"
    else:
        fit_level = "risky"
    return {
        "source_duration_sec": round(source_duration_sec, 3),
        "target_lang": canonical_language_code(target_lang),
        "estimated_tts_duration_sec": round(estimated, 3),
        "duration_ratio": round(ratio, 3),
        "fit_level": fit_level,
    }


def summarize_duration_budgets(budgets: list[dict[str, float | str]]) -> dict[str, float | str]:
    if not budgets:
        return {
            "source_duration_sec": 0.0,
            "estimated_tts_duration_sec": 0.0,
            "duration_ratio": 0.0,
            "fit_level": "fit",
        }
    source_total = sum(float(item["source_duration_sec"]) for item in budgets)
    target_total = sum(float(item["estimated_tts_duration_sec"]) for item in budgets)
    ratio = target_total / max(0.001, source_total)
    if any(item["fit_level"] == "risky" for item in budgets):
        fit_level = "risky"
    elif any(item["fit_level"] == "review" for item in budgets):
        fit_level = "review"
    else:
        fit_level = "fit"
    return {
        "source_duration_sec": round(source_total, 3),
        "estimated_tts_duration_sec": round(target_total, 3),
        "duration_ratio": round(ratio, 3),
        "fit_level": fit_level,
    }
