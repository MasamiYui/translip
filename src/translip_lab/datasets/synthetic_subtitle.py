"""Synthetic hard-subtitle generator — the only path to OCR/erase quantitative GT.

The research found no public Chinese film/TV dataset with subtitle text/box GT, so
we *make* perfect GT. Frames are composed in numpy (a smooth gradient background)
with subtitles rendered by Pillow; the exact glyph box comes from PIL ``textbbox``
(stroke included). Frames are piped as rawvideo to ffmpeg + libx264 — this avoids
the ``drawtext`` filter, which is missing from many ffmpeg builds. Outputs:
  - ``burned.mp4``  → input fed to OCR/erase
  - ``boxes.json``  → text + box GT for OCR detection F1
  - ``clean.mp4``   → subtitle-free reference for erase PSNR/SSIM

Pillow + a CJK fontfile are required (``TRANSLIP_LAB_FONT`` overrides; macOS
PingFang / Hiragino / Linux Noto auto-detected). ``find_font`` returns None when
neither is available so callers/tests can skip cleanly.
"""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np

from ..config import LabConfig
from ..core.sample import GroundTruth, Sample, SampleManifest
from .base import DatasetAdapter, register_dataset

_FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)

_DEFAULT_TEXTS = ("你好世界", "这是一段测试字幕", "字幕擦除评测")
_STROKE = 2


def find_font(override: str | None = None) -> str | None:
    """Return a fontfile Pillow can load, or None if Pillow/font unavailable."""
    try:
        from PIL import ImageFont
    except Exception:  # noqa: BLE001 — Pillow absent → caller skips
        return None
    for candidate in (override, os.environ.get("TRANSLIP_LAB_FONT")):
        if candidate and Path(candidate).is_file():
            try:
                ImageFont.truetype(candidate, 24)
                return candidate
            except Exception:  # noqa: BLE001
                pass
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                ImageFont.truetype(candidate, 24)
                return candidate
            except Exception:  # noqa: BLE001
                continue
    return None


def _gradient_frame(width: int, height: int, phase: float) -> np.ndarray:
    xx = np.linspace(0, 255, width, dtype=np.float64)[None, :]
    yy = np.linspace(0, 255, height, dtype=np.float64)[:, None]
    r = np.broadcast_to(xx, (height, width))
    g = np.broadcast_to(yy, (height, width))
    b = np.broadcast_to(((xx + yy) / 2 + phase * 255) % 256, (height, width))
    return np.stack([r, g, b], axis=-1).astype(np.uint8)


def _encode(frames: Iterable[np.ndarray], path: Path, width: int, height: int, fps: int) -> None:
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for frame in frames:
            proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
    finally:
        proc.stdin.close()
    err = proc.stderr.read() if proc.stderr else b""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg encode failed: {err.decode('utf-8', 'replace')[:400]}")


class SyntheticSubtitleGenerator:
    def __init__(self, config: LabConfig, *, width: int = 640, height: int = 360,
                 fps: int = 5, font: str | None = None) -> None:
        self.config = config
        self.width = width - (width % 2)  # libx264 needs even dimensions
        self.height = height - (height % 2)
        self.fps = fps
        self.font = find_font(font)

    def generate(self, events: list[dict[str, Any]], *, out_dir: Path, duration: float) -> dict[str, Any]:
        if not self.font:
            raise RuntimeError("no usable font / Pillow; set TRANSLIP_LAB_FONT to a .ttf/.ttc path")
        from PIL import Image, ImageDraw, ImageFont

        out_dir.mkdir(parents=True, exist_ok=True)
        w, h, fps = self.width, self.height, self.fps
        nframes = max(1, int(round(duration * fps)))
        font_cache: dict[int, Any] = {}

        def font_for(size: int):
            if size not in font_cache:
                font_cache[size] = ImageFont.truetype(self.font, size)
            return font_cache[size]

        # exact GT boxes via textbbox (stroke included)
        gt_events: list[dict[str, Any]] = []
        probe = ImageDraw.Draw(Image.new("RGB", (w, h)))
        norm_events = []
        for i, ev in enumerate(events):
            text = str(ev["text"])
            x = int(ev.get("x", 40))
            y = int(ev.get("y", h - 70))
            size = int(ev.get("fontsize", 30))
            start = float(ev["start"])
            end = float(ev["end"])
            norm_events.append({"text": text, "x": x, "y": y, "size": size, "start": start, "end": end})
            left, top, right, bottom = probe.textbbox((x, y), text, font=font_for(size), stroke_width=_STROKE)
            box = [max(0, int(left)), max(0, int(top)), min(w, int(right)), min(h, int(bottom))]
            if box[2] > box[0] and box[3] > box[1]:
                gt_events.append({"event_id": f"evt-{i:04d}", "text": text,
                                  "start": start, "end": end, "box": box})

        clean = out_dir / "clean.mp4"
        _encode((_gradient_frame(w, h, f / nframes) for f in range(nframes)), clean, w, h, fps)

        def burned_frames() -> Iterator[np.ndarray]:
            for f in range(nframes):
                t_sec = f / fps
                img = Image.fromarray(_gradient_frame(w, h, f / nframes))
                draw = ImageDraw.Draw(img)
                for ev in norm_events:
                    if ev["start"] <= t_sec < ev["end"]:
                        draw.text((ev["x"], ev["y"]), ev["text"], font=font_for(ev["size"]),
                                  fill=(255, 255, 255), stroke_width=_STROKE, stroke_fill=(0, 0, 0))
                yield np.asarray(img, dtype=np.uint8)

        burned = out_dir / "burned.mp4"
        _encode(burned_frames(), burned, w, h, fps)

        boxes = out_dir / "boxes.json"
        boxes.write_text(
            json.dumps({"video": {"width": w, "height": h, "fps": fps}, "events": gt_events},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"clean": clean, "burned": burned, "boxes": boxes, "events": gt_events}


@register_dataset
class SyntheticSubtitleDataset(DatasetAdapter):
    name = "synthetic-subtitle"

    def __init__(self, config: LabConfig, *, clips: int = 1, width: int = 640, height: int = 360,
                 fps: int = 5, duration: float = 4.0, texts: list[str] | None = None,
                 font: str | None = None, **params: Any) -> None:
        super().__init__(config, clips=clips, duration=duration, **params)
        self.clips = clips
        self.width = width
        self.height = height
        self.fps = fps
        self.duration = duration
        self.texts = list(texts) if texts else list(_DEFAULT_TEXTS)
        self.font = font

    def _events_for_clip(self, clip_index: int) -> list[dict[str, Any]]:
        events = []
        n = 3
        slot = self.duration / n
        for k in range(n):
            text = self.texts[(clip_index + k) % len(self.texts)]
            events.append({
                "text": text,
                "start": round(k * slot + 0.2, 2),
                "end": round((k + 1) * slot - 0.2, 2),
                "x": 40, "y": self.height - 70, "fontsize": 30,
            })
        return events

    def normalize(self) -> SampleManifest:
        gen = SyntheticSubtitleGenerator(self.config, width=self.width, height=self.height,
                                         fps=self.fps, font=self.font)
        out_root = self.config.cache_dir / "synthetic-subtitle"
        samples: list[Sample] = []
        for i in range(self.clips):
            res = gen.generate(self._events_for_clip(i), out_dir=out_root / f"clip_{i:03d}", duration=self.duration)
            gt = GroundTruth(subtitle_boxes=res["boxes"], clean_video=res["clean"])
            samples.append(Sample(
                sample_id=f"synth_sub_{i:03d}", media_path=res["burned"], ground_truth=gt,
                meta={"lang": "zh", "source": "synthetic", "duration_sec": self.duration},
            ))
        return SampleManifest(dataset=self.name, samples=samples, meta={"generated": True})
