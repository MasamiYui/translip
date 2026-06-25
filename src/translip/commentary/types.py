"""Types for the commentary-script stage (movie-recap narration generation).

The output data model is **OST-interleaved**: a recap is an ordered list of items
that are either narration-over-picture (``ost=0``) or original-sound passthrough
(``ost=1``, a kept clip of the source with its own audio). Every item anchors to a
source window ``[src_start, src_end]`` in SECONDS — the same float timeline the
``transcription`` and ``video-analyze`` artifacts use — so downstream planning can
cut it with ``video-trim`` directly (no HH:MM:SS string parsing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CommentaryOptions:
    """User-facing knobs for one commentary-script run."""

    style: str = "plot_recap"
    genre: str = "剧情"
    language: str = "zh"
    original_sound_ratio: int = 20
    model: str | None = None


@dataclass(slots=True)
class CommentaryItem:
    """One beat of the recap timeline.

    ``ost=0`` items carry narration spoken over the picture; ``ost=1`` items keep
    the original audio of ``[src_start, src_end]`` untouched (no narration). The
    final ``id`` is 1-based and contiguous after merge.
    """

    id: int
    ost: int
    src_start: float
    src_end: float
    narration: str
    picture: str
    story_role: str
    est_duration_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ost": self.ost,
            "src": [round(self.src_start, 3), round(self.src_end, 3)],
            "narration": self.narration,
            "picture": self.picture,
            "story_role": self.story_role,
            "est_duration_sec": round(self.est_duration_sec, 2),
        }


@dataclass(slots=True)
class CommentaryScript:
    """The full reviewable artifact written as ``commentary.json``."""

    items: list[CommentaryItem]
    plot_analysis: str
    style: str
    genre: str
    language: str
    original_sound_ratio: int
    model: str

    @property
    def ost0_count(self) -> int:
        return sum(1 for item in self.items if item.ost == 0)

    @property
    def ost1_count(self) -> int:
        return sum(1 for item in self.items if item.ost == 1)

    def realized_ost1_ratio(self) -> float:
        """OST=1 share of total estimated runtime (0–100), for sanity-checking the knob."""
        total = sum(item.est_duration_sec for item in self.items)
        if total <= 0:
            return 0.0
        ost1 = sum(item.est_duration_sec for item in self.items if item.ost == 1)
        return round(100.0 * ost1 / total, 1)

    def to_payload(self, *, source: dict[str, Any]) -> dict[str, Any]:
        return {
            "meta": {
                "commentary_style": self.style,
                "drama_genre": self.genre,
                "narration_language": self.language,
                "original_sound_ratio": self.original_sound_ratio,
                "model": {"backend": "deepseek", "model": self.model},
                "source": source,
                "stats": {
                    "item_count": len(self.items),
                    "ost0_count": self.ost0_count,
                    "ost1_count": self.ost1_count,
                    "realized_ost1_ratio": self.realized_ost1_ratio(),
                },
            },
            # Kept verbatim for human review / transparency (it grounds the script).
            "plot_analysis": self.plot_analysis,
            "items": [item.to_dict() for item in self.items],
        }
