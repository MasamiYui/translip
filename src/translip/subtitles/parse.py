"""Parse SRT / WebVTT subtitle files into a normalized list of cues.

Handles the differences between the two formats in one place:
- millisecond separator ``,`` (SRT) and ``.`` (VTT)
- optional hours component (``MM:SS.mmm``)
- VTT ``WEBVTT`` header, ``NOTE`` / ``STYLE`` blocks, cue identifier lines, and
  trailing cue settings on the timestamp line
- speaker prefixes, both the ``[LABEL] text`` form this project writes and the
  VTT ``<v LABEL>text</v>`` voice tag

The output is intentionally minimal (start/end/text/speaker); callers map it onto
their own payload shapes (ASR segments, OCR events, …).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

_BOM = "﻿"
_SPEAKER_PREFIX_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\s*(?P<rest>.*)$", re.DOTALL)
_VTT_VOICE_RE = re.compile(r"^<v\s+(?P<label>[^>]+)>(?P<rest>.*?)(?:</v>)?$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    index: int
    start: float
    end: float
    text: str
    speaker_label: str | None


def parse_timestamp(value: str) -> float:
    """Parse an SRT/VTT timestamp into seconds. Tolerates ``,`` or ``.`` and missing hours."""
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = "0", parts[0], parts[1]
    else:
        return 0.0
    try:
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return 0.0


def _extract_speaker(text: str) -> tuple[str | None, str]:
    prefix = _SPEAKER_PREFIX_RE.match(text)
    if prefix:
        return prefix.group("label").strip(), prefix.group("rest").strip()
    voice = _VTT_VOICE_RE.match(text)
    if voice:
        return voice.group("label").strip(), voice.group("rest").strip()
    return None, text.strip()


def parse_subtitles(text: str) -> list[SubtitleCue]:
    """Parse raw SRT or WebVTT text into ordered cues. Non-cue blocks are skipped."""
    blocks = re.split(r"\r?\n\s*\r?\n", text.lstrip(_BOM).strip())
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [line.strip().strip(_BOM) for line in block.splitlines()]
        lines = [line for line in lines if line]
        timestamp_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timestamp_index is None:
            continue  # WEBVTT header / NOTE / STYLE / stray block
        start_raw, _, end_raw = lines[timestamp_index].partition("-->")
        end_tokens = end_raw.split()
        start = parse_timestamp(start_raw)
        end = parse_timestamp(end_tokens[0]) if end_tokens else start
        body_lines = lines[timestamp_index + 1 :]
        raw_text = " ".join(body_lines).strip()
        if not raw_text:
            continue
        speaker_label, body = _extract_speaker(raw_text)
        if not body:
            continue
        cues.append(
            SubtitleCue(
                index=len(cues) + 1,
                start=start,
                end=max(end, start),
                text=body,
                speaker_label=speaker_label,
            )
        )
    return cues


def parse_subtitle_file(path: Path) -> list[SubtitleCue]:
    return parse_subtitles(Path(path).read_text(encoding="utf-8"))


__all__ = ["SubtitleCue", "parse_subtitles", "parse_subtitle_file", "parse_timestamp"]
