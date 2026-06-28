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
    """User-facing knobs for one commentary-script run.

    Phase-1 style customization adds five orthogonal axes on top of ``style``
    (the original "mode" knob, kept under that name for backwards compatibility
    with persisted commentary.json files):

    * ``style`` (alias: mode) — script structure: plot_recap / plot_tease /
      analysis / roast / reaction / tutorial. Drives prompt template selection.
    * ``tone_preset`` — narrator persona: objective / passionate / humorous /
      sarcastic / suspenseful / chill / dramatic / professional. Drives
      writing-stage voice.
    * ``pacing_preset`` — segment density: sparse / balanced / dense. Drives
      avg segment seconds + chars-per-second + sentence style.
    * ``perspective`` — narrative person: third_person / first_person_narrator
      / first_person_protagonist / second_person / god_view.
    * ``audience`` — platform tone: bilibili / douyin / xiaohongshu /
      youtube_long / wechat_video / generic.
    * ``style_intensity`` — 0.0..1.0 slider, how strongly the tone overrides
      the neutral baseline.
    """

    style: str = "plot_recap"
    genre: str = "剧情"
    language: str = "zh"
    original_sound_ratio: int = 20
    model: str | None = None
    # --- Phase-1 style customization ---
    tone_preset: str = "objective"
    pacing_preset: str = "balanced"
    perspective: str = "third_person"
    audience: str = "generic"
    style_intensity: float = 0.6

    def normalized(self) -> "CommentaryOptions":
        """Clamp ``style_intensity`` and lower-case enum-like fields."""
        clamped = max(0.0, min(1.0, float(self.style_intensity)))
        return CommentaryOptions(
            style=str(self.style or "plot_recap").strip() or "plot_recap",
            genre=str(self.genre or "剧情").strip() or "剧情",
            language=str(self.language or "zh").strip() or "zh",
            original_sound_ratio=int(self.original_sound_ratio),
            model=self.model,
            tone_preset=str(self.tone_preset or "objective").strip() or "objective",
            pacing_preset=str(self.pacing_preset or "balanced").strip() or "balanced",
            perspective=str(self.perspective or "third_person").strip() or "third_person",
            audience=str(self.audience or "generic").strip() or "generic",
            style_intensity=clamped,
        )


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
    # Phase-1 style customization echoed into the artifact for traceability.
    tone_preset: str = "objective"
    pacing_preset: str = "balanced"
    perspective: str = "third_person"
    audience: str = "generic"
    style_intensity: float = 0.6

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
                # Phase-1: persist the chosen style profile so commentary.json
                # round-trips through review/edit without losing user intent.
                "style_profile": {
                    "tone_preset": self.tone_preset,
                    "pacing_preset": self.pacing_preset,
                    "perspective": self.perspective,
                    "audience": self.audience,
                    "style_intensity": round(float(self.style_intensity), 2),
                },
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
