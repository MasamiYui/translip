"""Heuristic inference of which Work a task belongs to.

Algorithm (top-3 by confidence):

1. Substring match: task name / source filename contains an existing Work title or alias  → 0.9
2. Edit distance / fuzzy substring vs existing Work titles                                → 0.6
3. Filename pattern extraction (`<title>.S01E01.*`, `<title>.<year>.*` etc.)              → 0.5

For unmatched filename-pattern hits we additionally suggest creating a new Work
with the extracted title.
"""

from __future__ import annotations

import os
import re
from typing import Any

# Common patterns extracted from media filenames
_SE_PATTERN = re.compile(r"(?P<title>.+?)[._\s-]+S(?P<season>\d{1,2})E(?P<ep>\d{1,3})", re.IGNORECASE)
_EP_PATTERN = re.compile(r"(?P<title>.+?)[._\s-]+(?:EP?|第)\s*(?P<ep>\d{1,3})", re.IGNORECASE)
_YEAR_PATTERN = re.compile(r"(?P<title>.+?)[._\s-]+(?P<year>(19|20)\d{2})\b")


def _split_camel_or_dot(text: str) -> str:
    """Friends.S01E01 -> 'Friends S01E01'."""
    return re.sub(r"[._\-]+", " ", text).strip()


def _basename_without_ext(path: str) -> str:
    base = os.path.basename(path or "")
    name, _ = os.path.splitext(base)
    return name


def _normalize(text: str) -> str:
    return _split_camel_or_dot((text or "").strip()).lower()


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _extract_episode_label(text: str) -> str | None:
    m = _SE_PATTERN.search(text)
    if m:
        season = int(m.group("season"))
        ep = int(m.group("ep"))
        return f"S{season:02d}E{ep:02d}"
    m = _EP_PATTERN.search(text)
    if m:
        return f"E{int(m.group('ep')):02d}"
    return None


def _extract_pattern_title(text: str) -> str | None:
    """Try to pull a leading 'title' part out of common media filename patterns."""
    for pattern in (_SE_PATTERN, _EP_PATTERN, _YEAR_PATTERN):
        m = pattern.search(text)
        if m:
            raw = m.group("title")
            cleaned = _split_camel_or_dot(raw).strip()
            if cleaned:
                return cleaned
    return None


def infer_work_from_task(
    *,
    task_name: str,
    input_path: str | None,
    works: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return up to 3 candidate works ranked by confidence.

    Each candidate is one of:
      { "work_id": str, "title": str, "score": float, "reason": str, "episode_label": str | None }
      { "work_id": None, "suggest_create": { "title": str, "year": int|None }, "score": float, "reason": str, "episode_label": str | None }
    """
    sources = [task_name or "", _basename_without_ext(input_path or "")]
    haystacks = [_normalize(s) for s in sources if s]
    if not haystacks:
        return []

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_create_titles: set[str] = set()

    episode_label = None
    for s in sources:
        episode_label = _extract_episode_label(s)
        if episode_label:
            break

    # Pass 1: substring containment by alias/title
    for w in works:
        wid = str(w.get("id") or "")
        if not wid or wid in seen_ids:
            continue
        title = (w.get("title") or "").strip()
        names = [title, *(w.get("aliases") or [])]
        names = [n for n in names if n]
        for name in names:
            needle = name.strip().lower()
            for hay in haystacks:
                if needle and (needle in hay or hay in needle):
                    candidates.append(
                        {
                            "work_id": wid,
                            "title": title,
                            "score": 0.9,
                            "reason": f"contains alias '{name}'",
                            "episode_label": episode_label,
                        }
                    )
                    seen_ids.add(wid)
                    break
            if wid in seen_ids:
                break

    # Pass 2: fuzzy edit-distance against title
    for w in works:
        wid = str(w.get("id") or "")
        if not wid or wid in seen_ids:
            continue
        title_norm = _normalize(w.get("title") or "")
        if not title_norm:
            continue
        best = 0.0
        for hay in haystacks:
            for token in re.split(r"\s+", hay):
                if not token:
                    continue
                if abs(len(token) - len(title_norm)) > 4:
                    continue
                d = _levenshtein(token, title_norm)
                tolerance = max(1, len(title_norm) // 4)
                if d <= tolerance:
                    score = 0.6 + max(0.0, 0.1 * (1 - d / max(1, len(title_norm))))
                    if score > best:
                        best = score
        if best > 0:
            candidates.append(
                {
                    "work_id": wid,
                    "title": w.get("title"),
                    "score": round(best, 3),
                    "reason": "fuzzy match",
                    "episode_label": episode_label,
                }
            )
            seen_ids.add(wid)

    # Pass 3: pattern extraction → suggest_create when no Work matched
    for s in sources:
        title = _extract_pattern_title(s)
        if not title:
            continue
        norm = title.lower()
        if norm in seen_create_titles:
            continue
        if any(
            (c.get("title") or "").strip().lower() == norm
            for c in candidates
            if c.get("work_id")
        ):
            continue
        seen_create_titles.add(norm)
        year = None
        m = _YEAR_PATTERN.search(s)
        if m:
            try:
                year = int(m.group("year"))
            except ValueError:
                year = None
        candidates.append(
            {
                "work_id": None,
                "suggest_create": {"title": title, "year": year},
                "score": 0.5,
                "reason": "filename pattern",
                "episode_label": episode_label,
            }
        )

    candidates.sort(key=lambda c: -float(c.get("score") or 0))
    return candidates[:3]
