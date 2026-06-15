"""Praat TextGrid (long form) parser + RTTM/SRT emitters.

AISHELL-4 and AliMeeting ship per-speaker IntervalTier TextGrids; this turns them
into the (start, end, speaker, text) intervals the lab needs, then into the RTTM
(diarization GT) and SRT (ASR GT) the scenarios consume.
"""
from __future__ import annotations

import re
from pathlib import Path

_ITEM_SPLIT = re.compile(r"item\s*\[\d+\]\s*:")
_NAME = re.compile(r'name\s*=\s*"([^"]*)"')
_INTERVAL = re.compile(
    r'intervals\s*\[\d+\]\s*:\s*'
    r'xmin\s*=\s*([0-9.]+)\s*'
    r'xmax\s*=\s*([0-9.]+)\s*'
    r'text\s*=\s*"((?:[^"\\]|\\.)*)"',
    re.DOTALL,
)


def parse_textgrid(path: str | Path) -> list[tuple[float, float, str, str]]:
    """Return [(start, end, speaker, text), ...] for non-empty intervals (long form)."""
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    intervals: list[tuple[float, float, str, str]] = []
    blocks = _ITEM_SPLIT.split(content)
    for block in blocks[1:]:
        name_m = _NAME.search(block)
        tier = name_m.group(1).strip() if name_m else "speaker"
        for m in _INTERVAL.finditer(block):
            start = float(m.group(1))
            end = float(m.group(2))
            text = m.group(3).replace('\\"', '"').strip()
            if text and end > start:
                intervals.append((start, end, tier, text))
    intervals.sort(key=lambda x: (x[0], x[1]))
    return intervals


def to_rttm(intervals: list[tuple[float, float, str, str]], file_id: str) -> str:
    lines = [
        f"SPEAKER {file_id} 1 {start:.3f} {(end - start):.3f} <NA> <NA> {speaker} <NA> <NA>"
        for start, end, speaker, _ in intervals
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def _srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(intervals: list[tuple[float, float, str, str]]) -> str:
    out: list[str] = []
    for i, (start, end, _speaker, text) in enumerate(intervals, start=1):
        out.append(f"{i}\n{_srt_ts(start)} --> {_srt_ts(end)}\n{text}\n")
    return "\n".join(out)
