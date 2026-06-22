"""WenetSpeech-Drama adapter — Mandarin film/TV ASR (the "D" subset of WenetSpeech).

WenetSpeech (Wenet Open Source Mandarin Corpus, 10000h+) is the only large open
Mandarin ASR corpus that exposes a film/TV ("drama") subset with reliable
transcripts (≈4338h labelled). Its license requires registration with the WeNet
team (research-only, EULA-gated), so this adapter does NOT auto-download — the
user places a pre-segmented subset under ``<datasets>/wenetspeech-drama/<subset>/``
and the adapter only validates layout + produces a ``SampleManifest``.

Expected layout (per subset, e.g. ``mini`` / ``dev`` / ``test``):

    <datasets>/wenetspeech-drama/<subset>/
        manifest.json            # required, see schema below
        audio/<segment_id>.wav   # 16kHz mono, segment-level (already trimmed)
        srt/<segment_id>.srt     # single-cue SRT carrying the reference text

``manifest.json`` is a thin wrapper over the segment metadata exported from the
official ``WenetSpeech.json`` (filtered by ``"D" in segment.subsets``); we keep
only the fields the lab needs and let users regenerate the subset offline. The
expected schema is::

    {
      "dataset": "wenetspeech-drama",
      "subset": "mini",
      "license": "WeNet Open Source — research only, registration required",
      "source": "https://wenet.org.cn/WenetSpeech/",
      "segments": [
        {
          "segment_id": "Y0000000000_drama_0001",
          "audio": "audio/Y0000000000_drama_0001.wav",
          "srt": "srt/Y0000000000_drama_0001.srt",
          "duration_sec": 6.42,
          "show_id": "Y0000000000",      # optional (WenetSpeech "aid")
          "subsets": ["D"],
          "confidence": 1.0               # optional, from WenetSpeech
        }
      ]
    }

Sidecar SRT is preferred so the ASR scenario (``required_gt = transcript_srt``)
works without any further conversion. If a segment ships plain text instead,
set ``"text": "..."`` on the segment and the adapter will materialise a single-
cue SRT (0 → ``duration_sec``) under the lab cache dir.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset

_DRAMA_TAG = "D"


def _format_srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_single_cue_srt(path: Path, text: str, duration_sec: float) -> None:
    cue_end = max(0.1, float(duration_sec) if duration_sec else 0.1)
    body = (
        "1\n"
        f"{_format_srt_timestamp(0.0)} --> {_format_srt_timestamp(cue_end)}\n"
        f"{text.strip()}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@register_dataset
class WenetSpeechDramaDataset(DatasetAdapter):
    """Adapter for the WenetSpeech drama ("D") subset, segment-level."""

    name = "wenetspeech-drama"

    def __init__(self, config: LabConfig, *, subset: str = "mini",
                 manifest_filename: str = "manifest.json",
                 require_drama_tag: bool = True,
                 max_samples: int | None = None, **params: Any) -> None:
        super().__init__(config, subset=subset, manifest_filename=manifest_filename,
                         require_drama_tag=require_drama_tag, max_samples=max_samples,
                         **params)
        self.subset = subset
        self.manifest_filename = manifest_filename
        self.require_drama_tag = bool(require_drama_tag)
        self.max_samples = max_samples
        self._declared_root = config.datasets_dir / self.name

    @property
    def root(self) -> Path:
        return self._declared_root

    @property
    def subset_root(self) -> Path:
        return self._declared_root / self.subset

    def _cache_dir(self) -> Path:
        d = self.config.cache_dir / "datasets" / self.name / self.subset
        d.mkdir(parents=True, exist_ok=True)
        return d

    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d.update({
            "subset": self.subset,
            "subset_root": str(self.subset_root),
            "subset_exists": self.subset_root.exists(),
            "license": "WeNet Open Source — research only, registration required "
                       "at https://wenet.org.cn/WenetSpeech/",
            "provides": ["asr (CER)"],
            "expected_layout": (
                f"{self.subset_root}/manifest.json + audio/<sid>.wav "
                "(+ srt/<sid>.srt or per-segment 'text')"
            ),
        })
        return d

    def normalize(self) -> SampleManifest:
        subset_root = self.subset_root
        if not subset_root.is_dir():
            raise FileNotFoundError(
                f"wenetspeech-drama subset not found: {subset_root}. "
                "Register at https://wenet.org.cn/WenetSpeech/, export the 'D' "
                "(drama) subset to that path with manifest.json + audio/*.wav."
            )
        manifest_path = subset_root / self.manifest_filename
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"missing manifest: {manifest_path}. See translip_lab/datasets/"
                "wenetspeech_drama.py for the expected schema."
            )
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {manifest_path}: {exc}") from exc
        segments = payload.get("segments")
        if not isinstance(segments, list):
            raise ValueError(f"{manifest_path}: 'segments' must be a list")

        cache = self._cache_dir()
        samples: list[Sample] = []
        for entry in segments:
            if not isinstance(entry, dict):
                continue
            sid = entry.get("segment_id")
            audio_rel = entry.get("audio")
            if not sid or not audio_rel:
                continue
            if self.require_drama_tag:
                subsets = entry.get("subsets") or []
                if _DRAMA_TAG not in subsets:
                    continue
            audio_path = (subset_root / audio_rel).resolve()
            if not audio_path.is_file():
                continue

            srt_path: Path | None = None
            srt_rel = entry.get("srt")
            if srt_rel:
                candidate = (subset_root / srt_rel).resolve()
                if candidate.is_file():
                    srt_path = candidate
            if srt_path is None and entry.get("text"):
                derived = cache / f"{sid}.srt"
                _write_single_cue_srt(derived, str(entry["text"]),
                                       float(entry.get("duration_sec") or 0.0))
                srt_path = derived
            if srt_path is None:
                continue  # no reference → cannot score ASR

            gt = GroundTruth(transcript_srt=srt_path)
            meta: dict[str, Any] = {
                "lang": "zh",
                "source": self.name,
                "subset": self.subset,
                "license": "wenetspeech-research",
            }
            for k in ("duration_sec", "show_id", "confidence", "subsets"):
                if k in entry:
                    meta[k] = entry[k]
            samples.append(Sample(sample_id=str(sid), media_path=audio_path,
                                   ground_truth=gt, meta=meta))
            if self.max_samples is not None and len(samples) >= self.max_samples:
                break

        return SampleManifest(
            dataset=self.name,
            samples=samples,
            meta={
                "subset": self.subset,
                "subset_root": str(subset_root),
                "license": payload.get("license", "wenetspeech-research"),
                "source": payload.get("source", "https://wenet.org.cn/WenetSpeech/"),
                "drama_only": self.require_drama_tag,
            },
        )
