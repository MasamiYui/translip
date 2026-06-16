"""clip — wrap another dataset and trim each sample's media + GT to a window.

Long meetings (AISHELL-4 is ~39 min each) make ASR/diar runs take hours. ``clip``
windows every base sample to ``seconds`` (from ``offset``), trimming the media and
re-aligning every ground-truth kind (SRT / RTTM / subtitle boxes / clean video /
clean stems) — times are clipped to the window and shifted to start at 0. This
turns "run on a long corpus" into "run on representative clips" with one config,
replacing hand-rolled trimming.

Suite usage:
    dataset = "clip"
    [dataset_params]
    base = "aishell4"
    seconds = 180
    max_samples = 3
    [dataset_params.base_params]
    subset = "test"
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from ..metrics.diarization import parse_rttm
from .base import DatasetAdapter, get_dataset, register_dataset
from .textgrid import _srt_ts

_AUDIO_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg")


def _safe(text: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in text)


def _ff(args: list[str]) -> None:
    proc = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg clip failed: {proc.stderr.decode('utf-8', 'replace')[:300]}")


def _srt_seconds(stamp: str) -> float:
    h, m, rest = stamp.replace(",", ".").strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def _parse_srt(path: str | Path) -> list[tuple[float, float, str]]:
    text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    items: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        a, b = (p.strip() for p in lines[1].split("-->", 1))
        items.append((_srt_seconds(a), _srt_seconds(b), " ".join(lines[2:]).strip()))
    return items


def _write_srt(items: list[tuple[float, float, str]]) -> str:
    return "\n".join(
        f"{i}\n{_srt_ts(st)} --> {_srt_ts(en)}\n{txt}\n" for i, (st, en, txt) in enumerate(items, start=1)
    )


@register_dataset
class ClipDataset(DatasetAdapter):
    name = "clip"

    def __init__(self, config: LabConfig, *, base: str, seconds: float, offset: float = 0.0,
                 base_params: dict[str, Any] | None = None, max_samples: int | None = None,
                 sr: int = 16000, mono: bool = True, **params: Any) -> None:
        super().__init__(config, base=base, seconds=seconds, offset=offset, **params)
        self.base = base
        self.seconds = float(seconds)
        self.offset = float(offset)
        self.base_params = base_params or {}
        self.max_samples = max_samples
        self.sr = sr
        self.mono = mono

    def normalize(self) -> SampleManifest:
        base_ds = get_dataset(self.base, self.config, self.base_params)
        base_manifest = base_ds.normalize()
        src = base_manifest.samples[:self.max_samples] if self.max_samples else base_manifest.samples
        out_root = self.config.cache_dir / "clips" / _safe(self.base)
        samples = [self._clip_sample(s, out_root) for s in src]
        return SampleManifest(
            dataset=f"clip:{self.base}", samples=samples,
            meta={"base": self.base, "seconds": self.seconds, "offset": self.offset},
        )

    def _clip_sample(self, sample: Sample, out_root: Path) -> Sample:
        t0, dur = self.offset, self.seconds
        t1 = t0 + dur
        d = out_root / _safe(sample.sample_id)
        d.mkdir(parents=True, exist_ok=True)

        ext = sample.media_path.suffix.lower()
        if ext in _AUDIO_EXTS:
            media = d / "clip.wav"
            args = ["-ss", f"{t0}", "-t", f"{dur}", "-i", str(sample.media_path)]
            if self.mono:
                args += ["-ac", "1"]
            args += ["-ar", str(self.sr), str(media)]
            _ff(args)
        else:
            media = d / "clip.mp4"
            _ff(["-ss", f"{t0}", "-t", f"{dur}", "-i", str(sample.media_path), "-pix_fmt", "yuv420p", str(media)])

        gt = GroundTruth()
        src_gt = sample.ground_truth

        if src_gt.transcript_srt and Path(src_gt.transcript_srt).is_file():
            items = [
                (max(0.0, st - t0), min(en, t1) - t0, txt)
                for (st, en, txt) in _parse_srt(src_gt.transcript_srt) if en > t0 and st < t1
            ]
            (d / "clip.srt").write_text(_write_srt(items), encoding="utf-8")
            gt.transcript_srt = d / "clip.srt"

        if src_gt.rttm and Path(src_gt.rttm).is_file():
            segs = [
                (max(0.0, st - t0), min(en, t1) - t0, spk)
                for (st, en, spk) in parse_rttm(src_gt.rttm) if en > t0 and st < t1
            ]
            lines = [f"SPEAKER {_safe(sample.sample_id)} 1 {st:.3f} {en - st:.3f} <NA> <NA> {spk} <NA> <NA>"
                     for (st, en, spk) in segs if en > st]
            (d / "clip.rttm").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            gt.rttm = d / "clip.rttm"

        if src_gt.subtitle_boxes and Path(src_gt.subtitle_boxes).is_file():
            data = json.loads(Path(src_gt.subtitle_boxes).read_text(encoding="utf-8"))
            kept = []
            for e in data.get("events", []):
                st = e.get("start", e.get("start_time"))
                en = e.get("end", e.get("end_time"))
                if st is None or en is None or float(en) <= t0 or float(st) >= t1:
                    continue
                ne = dict(e)
                ne["start"] = max(0.0, float(st) - t0)
                ne["end"] = min(float(en), t1) - t0
                kept.append(ne)
            data["events"] = kept
            (d / "clip.boxes.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            gt.subtitle_boxes = d / "clip.boxes.json"

        if src_gt.clean_video and Path(src_gt.clean_video).is_file():
            cv = d / "clip.clean.mp4"
            _ff(["-ss", f"{t0}", "-t", f"{dur}", "-i", str(src_gt.clean_video), "-pix_fmt", "yuv420p", str(cv)])
            gt.clean_video = cv

        if src_gt.clean_stems:
            stems: dict[str, str] = {}
            for key, value in src_gt.clean_stems.items():
                if Path(value).is_file():
                    sp = d / f"clip.{key}.wav"
                    args = ["-ss", f"{t0}", "-t", f"{dur}", "-i", str(value)]
                    if self.mono:
                        args += ["-ac", "1"]
                    args += ["-ar", str(self.sr), str(sp)]
                    _ff(args)
                    stems[key] = str(sp)
            gt.clean_stems = stems

        meta = dict(sample.meta)
        meta.update({"clip_offset": t0, "clip_seconds": dur, "base_sample_id": sample.sample_id})
        return Sample(sample_id=f"{sample.sample_id}@{int(t0)}-{int(t1)}", media_path=media, ground_truth=gt, meta=meta)
