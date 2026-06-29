"""Assembly core for the commentary-render stage — pure, unit-testable.

Turns a reviewed ``commentary.json`` (OST-interleaved items) + the source video
into a concrete edit plan and the exact ffmpeg argv that realises it. No I/O and
no subprocess here (except :func:`write_concat_list`, a trivial file write) so the
timeline math and command construction are tested directly; the adapter owns TTS
synthesis and shelling out.

Each item becomes one **normalised** clip (uniform W×H / fps / 48 kHz stereo /
yuv420p) so the final assembly is a clean concat stream-copy:

* ``ost=0`` — narration over the *ducked* original audio. The clip's length is the
  narration's measured duration; if the source window is shorter than the
  narration, the last video frame is cloned to fill (``tpad``).
* ``ost=1`` — original-sound passthrough: the source window plays untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Canonical output format every clip is normalised to so concat can stream-copy.
FPS = 30
SAMPLE_RATE = 48_000
CHANNELS = 2
# Shortest clip we will emit — guards against degenerate windows / empty narration.
MIN_CLIP_SEC = 0.5


@dataclass(slots=True)
class ClipSpec:
    """One normalised clip on the recap timeline."""

    index: int
    item_id: int
    ost: int
    src_start: float
    # Seconds of *source* video to take from src_start (≤ av_duration for ost=0
    # when the source window is shorter than the narration).
    take_duration: float
    # Final A/V length of the clip on the recap timeline.
    av_duration: float

    @property
    def pad_duration(self) -> float:
        """Seconds of cloned last frame appended to reach ``av_duration`` (ost=0)."""
        return round(max(0.0, self.av_duration - self.take_duration), 3)


def db_to_linear(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def plan_render(
    items: list[dict],
    *,
    narration_durations: dict[int, float],
    source_duration: float,
    min_clip_sec: float = MIN_CLIP_SEC,
) -> list[ClipSpec]:
    """Resolve each commentary item into a :class:`ClipSpec`.

    ``ost=0`` clip length = its narration duration (from ``narration_durations``,
    keyed by item id); ``ost=1`` clip length = its clamped source window. Items
    whose window starts past the source end, or ``ost=0`` items without a measured
    narration, are dropped. ``index`` is contiguous over the surviving clips.
    """
    specs: list[ClipSpec] = []
    for item in items:
        try:
            item_id = int(item["id"])
            ost = 1 if int(item.get("ost", 0) or 0) == 1 else 0
            src = item["src"]
            src_start = float(src[0])
            src_end = float(src[1])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if src_start >= source_duration:
            continue
        window = min(src_end, source_duration) - src_start
        if window <= 0:
            continue

        if ost == 1:
            take = window
            av = window
        else:
            narration = narration_durations.get(item_id)
            if not narration or narration <= 0:
                continue
            av = max(narration, min_clip_sec)
            # We can only take as much source as exists in the window / file.
            take = min(av, window)

        specs.append(
            ClipSpec(
                index=len(specs),
                item_id=item_id,
                ost=ost,
                src_start=round(src_start, 3),
                take_duration=round(take, 3),
                av_duration=round(av, 3),
            )
        )
    return specs


def _even(value: int) -> int:
    """libx264 + yuv420p require even dimensions."""
    return value - (value % 2)


def build_clip_command(
    *,
    ffmpeg: str,
    spec: ClipSpec,
    source_path: Path,
    narration_path: Path | None,
    output_path: Path,
    width: int,
    height: int,
    crf: int,
    preset: str,
    original_gain_db: float,
    fps: int = FPS,
    sample_rate: int = SAMPLE_RATE,
    bgm_path: Path | None = None,
    bgm_gain_db: float = -15.0,
    bgm_duck_db: float = -9.0,
) -> list[str]:
    """ffmpeg argv producing one normalised clip for ``spec``.

    ``ost=0`` requires ``narration_path`` and mixes it over the original audio
    attenuated by ``original_gain_db`` (ducking); ``ost=1`` ignores it and passes
    the original audio through. Both scale-pad to ``width×height`` (letterbox,
    even dims), force ``fps`` / yuv420p / stereo ``sample_rate`` so all clips share
    one profile and the final concat can ``-c copy``.

    When ``bgm_path`` is supplied and ``spec.ost == 0``, a third input (looped to
    cover the clip duration) is mixed in at ``bgm_gain_db`` and **side-chain
    compressed** by the narration: while the narrator speaks the BGM is pushed
    down by an additional ``|bgm_duck_db|`` dB so the voice always sits on top.
    """
    w, h = _even(width), _even(height)
    scale_pad = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p"
    )

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if spec.src_start > 0:
        cmd += ["-ss", f"{spec.src_start:.3f}"]
    cmd += ["-i", str(source_path)]

    if spec.ost == 0:
        if narration_path is None:
            raise ValueError(f"ost=0 clip {spec.item_id} requires a narration_path")
        cmd += ["-i", str(narration_path)]
        # Loop the BGM with the demuxer-level ``-stream_loop -1`` flag so a short
        # placeholder still covers the full clip. The amix ``duration=longest``
        # below ensures we stop precisely when the longest of source/narration
        # ends (then -t caps the output at av_duration).
        if bgm_path is not None:
            cmd += ["-stream_loop", "-1", "-i", str(bgm_path)]
        gain = db_to_linear(original_gain_db)
        video_chain = (
            f"[0:v]trim=duration={spec.take_duration:.3f},setpts=PTS-STARTPTS,{scale_pad}"
        )
        if spec.pad_duration > 0:
            # Source window is shorter than the narration — clone the last frame to
            # fill the remainder so the clip's video lasts the full narration length.
            video_chain += f",tpad=stop_mode=clone:stop_duration={spec.pad_duration:.3f}"
        video_chain += "[v]"
        if bgm_path is not None:
            bgm_base_lin = db_to_linear(bgm_gain_db)
            # Side-chain compressor ratio chosen so the narration drives an extra
            # ~|bgm_duck_db| dB of attenuation on top of the static bgm_gain_db.
            # threshold=0.05 (~-26 dB) trips on normal speech; release=600 ms
            # gives a natural duck-and-recover envelope (matches the dub-stage
            # ``build_sidechain_preview_mix`` profile).
            duck_ratio = max(2.0, min(20.0, abs(bgm_duck_db) / 1.5))
            audio_chain = (
                f"[0:a]atrim=duration={spec.take_duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={gain:.4f},aresample={sample_rate},apad[src];"
                f"[1:a]asetpts=PTS-STARTPTS,aresample={sample_rate},apad[narr];"
                f"[2:a]volume={bgm_base_lin:.4f},aresample={sample_rate},"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo[bgm_raw];"
                f"[bgm_raw][narr]sidechaincompress="
                f"threshold=0.05:ratio={duck_ratio:.2f}:attack=150:release=600[bgm];"
                f"[src][bgm][narr]amix=inputs=3:duration=longest:normalize=0,"
                f"alimiter=limit=0.97,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo[a]"
            )
        else:
            audio_chain = (
                f"[0:a]atrim=duration={spec.take_duration:.3f},asetpts=PTS-STARTPTS,"
                f"volume={gain:.4f},aresample={sample_rate},apad[bg];"
                f"[1:a]asetpts=PTS-STARTPTS,aresample={sample_rate},apad[narr];"
                f"[bg][narr]amix=inputs=2:duration=longest:normalize=0,"
                f"aformat=sample_fmts=fltp:channel_layouts=stereo[a]"
            )
        out_duration = spec.av_duration
    else:
        video_chain = (
            f"[0:v]trim=duration={spec.take_duration:.3f},setpts=PTS-STARTPTS,{scale_pad}[v]"
        )
        audio_chain = (
            f"[0:a]atrim=duration={spec.take_duration:.3f},asetpts=PTS-STARTPTS,"
            f"aresample={sample_rate},aformat=sample_fmts=fltp:channel_layouts=stereo,apad[a]"
        )
        out_duration = spec.take_duration

    cmd += [
        "-filter_complex",
        f"{video_chain};{audio_chain}",
        "-map", "[v]",
        "-map", "[a]",
        "-t", f"{out_duration:.3f}",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-ar", str(sample_rate),
        "-ac", str(CHANNELS),
        "-progress", "pipe:1", "-nostats",
        str(output_path),
    ]
    return cmd


def write_concat_list(clip_paths: list[Path], list_path: Path) -> Path:
    """Write the ffmpeg concat-demuxer playlist (one ``file '<abs>'`` per line)."""
    lines = [f"file '{str(path.resolve())}'" for path in clip_paths]
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path


def build_concat_command(
    *,
    ffmpeg: str,
    list_path: Path,
    output_path: Path,
) -> list[str]:
    """ffmpeg argv concatenating normalised clips by stream-copy (no re-encode)."""
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        str(output_path),
    ]
