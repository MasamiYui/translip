"""Normalized sample + ground-truth records shared across datasets and scenarios.

A ``DatasetAdapter`` turns an external corpus into a ``SampleManifest`` (a list of
``Sample``). Each ``Sample`` points at the media translip will consume plus a
``GroundTruth`` describing *which* references are available — scenarios pick the
fields they need (e.g. the ASR scenario needs ``transcript_srt``; the erase
scenario needs ``clean_video``). Fields are optional precisely because no single
dataset has every kind of GT (see the dataset-landscape research).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _opt_str(p: Path | None) -> str | None:
    return str(p) if p is not None else None


@dataclass(slots=True)
class GroundTruth:
    """Available references for a sample. All optional; scenarios validate."""

    transcript_srt: Path | None = None  # reference subtitles → ASR CER
    rttm: Path | None = None  # reference diarization → DER
    clean_stems: dict[str, Any] = field(default_factory=dict)  # {"voice":path,"background":path} → SI-SDR
    subtitle_boxes: Path | None = None  # JSON {events:[{start,end,text,box}]} → OCR detection F1
    clean_video: Path | None = None  # subtitle-free reference video → erase PSNR/SSIM
    clean_frames_dir: Path | None = None  # or pre-extracted clean frames
    clone_text: str | None = None  # target text to synthesize → tts-clone CER (intelligibility)
    clone_ref_wav: Path | None = None  # target-voice reference → tts-clone SIM (timbre); falls back to media
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript_srt": _opt_str(self.transcript_srt),
            "rttm": _opt_str(self.rttm),
            "clean_stems": {k: str(v) for k, v in self.clean_stems.items()},
            "subtitle_boxes": _opt_str(self.subtitle_boxes),
            "clean_video": _opt_str(self.clean_video),
            "clean_frames_dir": _opt_str(self.clean_frames_dir),
            "clone_text": self.clone_text,
            "clone_ref_wav": _opt_str(self.clone_ref_wav),
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class Sample:
    sample_id: str
    media_path: Path  # what translip consumes (audio or video)
    ground_truth: GroundTruth = field(default_factory=GroundTruth)
    meta: dict[str, Any] = field(default_factory=dict)  # lang, num_speakers, duration_sec, source, license

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "media_path": str(self.media_path),
            "ground_truth": self.ground_truth.to_dict(),
            "meta": dict(self.meta),
        }


@dataclass(slots=True)
class SampleManifest:
    dataset: str
    samples: list[Sample] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:  # convenience for "N samples"
        return len(self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "meta": dict(self.meta),
            "samples": [s.to_dict() for s in self.samples],
        }
