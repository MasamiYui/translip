from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from imageio_ffmpeg import get_ffmpeg_exe

from ..exceptions import DependencyError, FFmpegError
from ..types import MediaInfo, StreamInfo


def _resolve_binary(name: str) -> str:
    env_name = name.upper() + "_BINARY"
    env_value = os.environ.get(env_name)
    if env_value:
        return env_value

    found = shutil.which(name)
    if found:
        return found

    if name == "ffmpeg":
        return get_ffmpeg_exe()

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path and name != "ffmpeg":
        try:
            ffmpeg_path = get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None
    if ffmpeg_path:
        sibling = str(Path(ffmpeg_path).with_name(name))
        if Path(sibling).exists():
            return sibling

    raise DependencyError(
        f"Required binary '{name}' not found. Install ffmpeg or set {env_name}."
    )


def ffmpeg_binary() -> str:
    return _resolve_binary("ffmpeg")


def ffmpeg_binary_with_libass() -> str:
    env = os.environ.get("FFMPEG_BINARY")
    if env:
        return env
    try:
        imageio_path = get_ffmpeg_exe()
        result = subprocess.run(
            [imageio_path, "-filters"],
            capture_output=True, text=True,
        )
        if "ass" in result.stdout:
            return imageio_path
    except Exception:
        pass
    return _resolve_binary("ffmpeg")


def ffprobe_binary() -> str:
    return _resolve_binary("ffprobe")


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [ffmpeg_binary(), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffmpeg failed")
    return result


def _run_ffmpeg_with_libass(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [ffmpeg_binary_with_libass(), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffmpeg failed")
    return result


def run_ffprobe_json(path: Path) -> dict[str, Any]:
    command = [
        ffprobe_binary(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffprobe failed")
    return json.loads(result.stdout)


def probe_media(path: Path) -> MediaInfo:
    payload = run_ffprobe_json(path)
    streams = payload.get("streams", [])
    format_info = payload.get("format", {})
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    selected_audio = audio_streams[0] if audio_streams else None
    duration = 0.0
    duration_text = format_info.get("duration") or (
        selected_audio and selected_audio.get("duration")
    )
    if duration_text:
        duration = float(duration_text)

    stream_infos = []
    for stream in streams:
        tags = stream.get("tags") or {}
        language = tags.get("language") or tags.get("LANGUAGE")
        stream_infos.append(
            StreamInfo(
                index=int(stream.get("index", len(stream_infos))),
                codec_type=str(stream.get("codec_type") or "unknown"),
                codec_name=stream.get("codec_name"),
                # ffprobe writes "und" for an unset tag — normalize to None so
                # callers can tell "undefined" apart from a real code.
                language=(language if language and language != "und" else None),
                title=tags.get("title") or tags.get("TITLE"),
            )
        )

    return MediaInfo(
        path=path,
        media_type="video" if video_streams else "audio",
        format_name=format_info.get("format_name"),
        duration_sec=duration,
        audio_stream_index=(selected_audio or {}).get("index"),
        audio_stream_count=len(audio_streams),
        sample_rate=int(selected_audio["sample_rate"]) if selected_audio else None,
        channels=int(selected_audio["channels"]) if selected_audio else None,
        streams=stream_infos,
    )


def extract_audio(
    input_path: Path,
    output_path: Path,
    audio_stream_index: int = 0,
    sample_rate: int = 44_100,
    channels: int = 2,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(input_path),
            "-map",
            f"0:a:{audio_stream_index}",
            "-vn",
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def render_wav(input_path: Path, output_path: Path, sample_rate: int | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y", "-i", str(input_path)]
    if sample_rate:
        args.extend(["-ar", str(sample_rate)])
    args.extend(["-c:a", "pcm_s16le", str(output_path)])
    run_ffmpeg(args)
    return output_path


def mix_audio(inputs: list[Path], output_path: Path) -> Path:
    if not inputs:
        raise FFmpegError("mix_audio requires at least one input stem")

    if len(inputs) == 1:
        return render_wav(inputs[0], output_path)

    args: list[str] = ["-y"]
    for stem in inputs:
        args.extend(["-i", str(stem)])
    args.extend(
        [
            "-filter_complex",
            f"amix=inputs={len(inputs)}:normalize=0,alimiter=limit=0.95",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )
    run_ffmpeg(args)
    return output_path


def export_audio(
    input_path: Path,
    output_path: Path,
    fmt: str,
    sample_rate: int | None = None,
    bitrate: str | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["-y", "-i", str(input_path)]
    if sample_rate:
        args.extend(["-ar", str(sample_rate)])

    if fmt == "wav":
        args.extend(["-c:a", "pcm_s16le"])
    elif fmt == "mp3":
        args.extend(["-c:a", "libmp3lame", "-b:a", bitrate or "320k"])
    elif fmt == "flac":
        args.extend(["-c:a", "flac"])
    elif fmt == "aac":
        args.extend(["-c:a", "aac", "-b:a", bitrate or "256k"])
    elif fmt == "opus":
        args.extend(["-c:a", "libopus", "-b:a", bitrate or "192k"])
    else:
        raise FFmpegError(f"Unsupported output format: {fmt}")

    args.append(str(output_path))
    run_ffmpeg(args)
    return output_path


# EBU R128 integrated-loudness target + true-peak limiter for delivered audio.
# Applied at mux time so every exported variant lands at a consistent loudness
# regardless of mix_profile (mix_profile controls processing quality, not whether
# loudness normalization happens).
_DELIVERY_LOUDNORM_FILTER = "loudnorm=I=-16:LRA=11:TP=-1.5,alimiter=limit=0.97"

# BCP-47 / 2-letter -> ISO 639-2/B for container language tags (mov_text, mkv).
_LANG_ISO639_2 = {
    "en": "eng",
    "zh": "zho",
    "ja": "jpn",
    "ko": "kor",
    "es": "spa",
    "fr": "fra",
    "de": "deu",
    "ru": "rus",
    "pt": "por",
    "it": "ita",
    "ar": "ara",
    "hi": "hin",
}


def iso639_2(language: str | None) -> str:
    """Map a language code to an ISO 639-2/B tag ffmpeg accepts (``und`` if unknown)."""
    if not language:
        return "und"
    base = str(language).strip().lower().replace("_", "-").split("-")[0]
    return _LANG_ISO639_2.get(base, base if len(base) == 3 else "und")


def _soft_subtitle_codec(container: str) -> str:
    return "srt" if container == "mkv" else "mov_text"


def build_soft_subtitle_mux_args(
    *,
    input_video_path: Path,
    dub_audio_path: Path,
    subtitle_path: Path | None,
    output_path: Path,
    container: str = "mp4",
    video_codec: str = "copy",
    audio_codec: str = "aac",
    audio_bitrate: str | None = None,
    audio_language: str | None = None,
    subtitle_language: str | None = None,
    embed_original_audio: bool = False,
    original_audio_language: str | None = None,
    end_policy: str = "trim_audio_to_video",
    loudnorm: bool = False,
) -> list[str]:
    """Build ffmpeg argv to mux a dub track (+ optional original audio + soft
    subtitle stream) without burning subtitles into the video (DEL-1).

    Input order: 0=source video (carries original audio), 1=dub audio,
    2=subtitle file (when present). The dub is the default audio track.
    """
    args: list[str] = ["-y", "-i", str(input_video_path), "-i", str(dub_audio_path)]
    if subtitle_path is not None:
        args.extend(["-i", str(subtitle_path)])

    args.extend(["-map", "0:v:0", "-map", "1:a:0"])
    if embed_original_audio:
        # '?' makes the original audio optional so videos without an audio track
        # still export cleanly.
        args.extend(["-map", "0:a:0?"])
    if subtitle_path is not None:
        args.extend(["-map", f"{2}:s:0"])

    args.extend(["-c:v", video_codec, "-c:a", audio_codec])
    if audio_bitrate:
        args.extend(["-b:a", audio_bitrate])
    if subtitle_path is not None:
        args.extend(["-c:s", _soft_subtitle_codec(container)])

    # loudnorm only the dub track (a:0); the original track is passed through.
    if loudnorm:
        args.extend(["-filter:a:0", _DELIVERY_LOUDNORM_FILTER])

    # Per-stream language tags + dispositions so players label the tracks.
    args.extend(["-metadata:s:a:0", f"language={iso639_2(audio_language)}", "-disposition:a:0", "default"])
    if embed_original_audio:
        args.extend([
            "-metadata:s:a:1",
            f"language={iso639_2(original_audio_language)}",
            "-disposition:a:1",
            "0",
        ])
    if subtitle_path is not None:
        args.extend(["-metadata:s:s:0", f"language={iso639_2(subtitle_language)}"])

    if end_policy == "trim_audio_to_video":
        args.append("-shortest")
    elif end_policy != "keep_longest":
        raise FFmpegError(f"Unsupported end policy: {end_policy}")

    args.extend(["-movflags", "+faststart", str(output_path)])
    return args


def mux_with_soft_subtitle(**kwargs: Any) -> Path:
    output_path = Path(kwargs["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(build_soft_subtitle_mux_args(**kwargs))
    return output_path


def mux_video_with_audio(
    *,
    input_video_path: Path,
    input_audio_path: Path,
    output_path: Path,
    video_codec: str = "copy",
    audio_codec: str = "aac",
    audio_bitrate: str | None = None,
    audio_language: str | None = None,
    end_policy: str = "trim_audio_to_video",
    loudnorm: bool = False,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-i",
        str(input_audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        video_codec,
        "-c:a",
        audio_codec,
    ]
    if audio_bitrate:
        args.extend(["-b:a", audio_bitrate])
    if audio_language:
        args.extend(["-metadata:s:a:0", f"language={iso639_2(audio_language)}"])
    audio_filters: list[str] = []
    if loudnorm:
        audio_filters.append(_DELIVERY_LOUDNORM_FILTER)
    if end_policy == "trim_audio_to_video":
        audio_filters.append("apad")
        trailing = ["-shortest"]
    elif end_policy == "keep_longest":
        audio_filters.append("apad")
        trailing = []
    else:
        raise FFmpegError(f"Unsupported end policy: {end_policy}")
    if audio_filters:
        args.extend(["-af", ",".join(audio_filters)])
    args.extend(trailing)
    args.extend(["-movflags", "+faststart", str(output_path)])
    run_ffmpeg(args)
    return output_path


def probe_video_resolution(path: Path) -> tuple[int, int]:
    payload = run_ffprobe_json(path)
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            if width > 0 and height > 0:
                return width, height
    raise FFmpegError(f"No video stream found in {path}")


def burn_subtitle_and_mux(
    *,
    input_video_path: Path,
    input_audio_path: Path,
    subtitle_path: Path,
    output_path: Path,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: str | None = None,
    audio_language: str | None = None,
    end_policy: str = "trim_audio_to_video",
    crf: int = 18,
    preset: str = "medium",
    loudnorm: bool = False,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"ass={subtitle_path}"
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-i",
        str(input_audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        vf,
        "-c:v",
        video_codec,
    ]
    if video_codec == "libx264":
        args.extend(["-crf", str(crf), "-preset", preset])
    args.extend(["-c:a", audio_codec])
    if audio_bitrate:
        args.extend(["-b:a", audio_bitrate])
    if audio_language:
        args.extend(["-metadata:s:a:0", f"language={iso639_2(audio_language)}"])
    if loudnorm:
        args.extend(["-af", _DELIVERY_LOUDNORM_FILTER])
    if end_policy == "trim_audio_to_video":
        args.extend(["-shortest"])
    args.extend(["-movflags", "+faststart", str(output_path)])
    _run_ffmpeg_with_libass(args)
    return output_path


def burn_subtitle_preview(
    *,
    input_video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    start_sec: float,
    duration_sec: float = 10.0,
    video_codec: str = "libx264",
    crf: int = 20,
    preset: str = "fast",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"ass={subtitle_path}"
    args = [
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(input_video_path),
        "-t",
        str(duration_sec),
        "-vf",
        vf,
        "-c:v",
        video_codec,
        "-crf",
        str(crf),
        "-preset",
        preset,
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run_ffmpeg_with_libass(args)
    return output_path


def burn_subtitle(
    *,
    input_video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    video_codec: str = "libx264",
    audio_codec: str = "copy",
    crf: int = 18,
    preset: str = "medium",
) -> Path:
    """Burn an ASS/SRT subtitle into the video while keeping the source's own
    audio (re-encodes video; audio defaults to stream-copy). Unlike
    ``burn_subtitle_and_mux`` this does not replace the audio with a dub track —
    it is the standalone "hardsub this video" path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"ass={subtitle_path}"
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",  # '?' keeps videos without an audio track exporting cleanly
        "-vf",
        vf,
        "-c:v",
        video_codec,
    ]
    if video_codec == "libx264":
        args.extend(["-crf", str(crf), "-preset", preset])
    args.extend(["-c:a", audio_codec, "-movflags", "+faststart", str(output_path)])
    _run_ffmpeg_with_libass(args)
    return output_path


_WATERMARK_POSITION_EXPR: dict[str, tuple[str, str]] = {
    "top-left": ("{m}", "{m}"),
    "top-right": ("W-w-{m}", "{m}"),
    "bottom-left": ("{m}", "H-h-{m}"),
    "bottom-right": ("W-w-{m}", "H-h-{m}"),
    "center": ("(W-w)/2", "(H-h)/2"),
}


def _watermark_xy(position: str, margin: int) -> tuple[str, str]:
    expr = _WATERMARK_POSITION_EXPR.get(position) or _WATERMARK_POSITION_EXPR["bottom-right"]
    return expr[0].format(m=margin), expr[1].format(m=margin)


def _build_image_watermark_filter(
    *, x_expr: str, y_expr: str, opacity: float, scale: float
) -> str:
    """Construct the image-overlay ``filter_complex`` string (pure; no I/O)."""
    safe_opacity = max(0.0, min(1.0, float(opacity)))
    safe_scale = max(0.01, float(scale))
    return (
        f"[1:v]format=rgba,colorchannelmixer=aa={safe_opacity:.4f},"
        f"scale=iw*{safe_scale:.4f}:-1[wm];"
        f"[0:v][wm]overlay={x_expr}:{y_expr}:format=auto[outv]"
    )


def build_image_watermark_args(
    *,
    input_video_path: Path,
    watermark_image_path: Path,
    output_path: Path,
    position: str = "bottom-right",
    margin: int = 24,
    opacity: float = 0.8,
    scale: float = 0.15,
    video_codec: str = "libx264",
    audio_codec: str = "copy",
    crf: int = 18,
    preset: str = "medium",
    progress: bool = False,
) -> list[str]:
    """ffmpeg argv (sans binary) overlaying an image watermark onto the video.

    The watermark is scaled to ``scale * video_width`` (preserving aspect ratio
    via ``-1`` height), its alpha multiplied by ``opacity`` (so semi-transparent
    PNGs stay semi-transparent), and placed at ``position`` with ``margin`` pixels
    from the chosen edge(s). Audio is stream-copied by default. ``progress=True``
    appends ``-progress pipe:1`` so a caller can stream encode progress.
    """
    x_expr, y_expr = _watermark_xy(position, margin)
    filter_complex = _build_image_watermark_filter(
        x_expr=x_expr, y_expr=y_expr, opacity=opacity, scale=scale
    )
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-i",
        str(watermark_image_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[outv]",
        "-map",
        "0:a:0?",
        "-c:v",
        video_codec,
    ]
    if video_codec == "libx264":
        args.extend(["-crf", str(crf), "-preset", preset])
    args.extend(["-c:a", audio_codec, "-movflags", "+faststart"])
    if progress:
        args.extend(["-progress", "pipe:1", "-nostats"])
    args.append(str(output_path))
    return args


def overlay_image_watermark(**kwargs: Any) -> Path:
    """Overlay a PNG/JPG watermark onto the video and re-encode it (blocking)."""
    output_path: Path = kwargs["output_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(build_image_watermark_args(**kwargs))
    return output_path


def _escape_drawtext(text: str) -> str:
    """Escape characters that have special meaning inside a drawtext value.

    ffmpeg's drawtext treats ``\\``, ``:``, ``'`` and ``%`` specially; we backslash
    each so user-supplied text renders literally without breaking the filter.
    """
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


# Concrete font *files* (not fontconfig family names) for the drawtext filter.
# Unlike libass — which resolves family names like "Noto Sans CJK SC" via
# fontconfig — drawtext needs an actual file path unless ffmpeg was built with
# fontconfig AND a matching font is installed. We resolve a real file so text
# watermarks work on stock builds, and so CJK text doesn't render as tofu when
# the fontconfig default is a Latin-only face. CJK faces also cover ASCII, so
# they double as a Latin fallback.
_CJK_FONT_CANDIDATES: tuple[str, ...] = (
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux (Noto CJK across common distro layouts)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
)
_LATIN_FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def _contains_cjk(text: str) -> bool:
    """True if ``text`` has any CJK/Kana/Hangul/fullwidth character."""
    for ch in text:
        o = ord(ch)
        if (
            0x3040 <= o <= 0x30FF  # Hiragana + Katakana
            or 0x3400 <= o <= 0x9FFF  # CJK Ext-A + Unified Ideographs
            or 0xAC00 <= o <= 0xD7A3  # Hangul syllables
            or 0xF900 <= o <= 0xFAFF  # CJK Compatibility Ideographs
            or 0xFF00 <= o <= 0xFFEF  # Halfwidth/Fullwidth forms
        ):
            return True
    return False


def _resolve_watermark_fontfile(text: str) -> str | None:
    """Pick a concrete font file for drawtext, CJK-aware.

    ``WATERMARK_FONT_FILE`` overrides everything when it points at a real file.
    Otherwise we probe the platform candidate lists (CJK first when the text
    needs it), falling back to any available CJK face since those cover ASCII
    too. Returns ``None`` only when nothing is found, leaving ffmpeg to its
    fontconfig default.
    """
    override = os.environ.get("WATERMARK_FONT_FILE")
    if override and Path(override).exists():
        return override
    candidates = _CJK_FONT_CANDIDATES if _contains_cjk(text) else _LATIN_FONT_CANDIDATES
    for path in candidates:
        if Path(path).exists():
            return path
    # Latin text but no Latin face found: a CJK face still renders ASCII.
    for path in _CJK_FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


def _build_drawtext_filter(
    *,
    text: str,
    x_expr: str,
    y_expr: str,
    font_size: int,
    font_color: str,
    stroke_color: str,
    stroke_width: int,
    opacity: float,
    font_file: str | None,
) -> str:
    """Construct the ``drawtext=...`` filter string (pure; no I/O)."""
    safe_opacity = max(0.0, min(1.0, float(opacity)))
    escaped = _escape_drawtext(text)
    parts = [
        f"text='{escaped}'",
        f"fontsize={int(font_size)}",
        f"fontcolor={font_color}@{safe_opacity:.4f}",
        f"bordercolor={stroke_color}",
        f"borderw={int(max(0, stroke_width))}",
        f"x={x_expr}",
        f"y={y_expr}",
    ]
    if font_file:
        parts.insert(1, f"fontfile='{font_file}'")
    return "drawtext=" + ":".join(parts)


def build_text_watermark_args(
    *,
    input_video_path: Path,
    output_path: Path,
    text: str,
    position: str = "bottom-right",
    margin: int = 24,
    font_size: int = 36,
    font_color: str = "white",
    stroke_color: str = "black@0.6",
    stroke_width: int = 2,
    opacity: float = 1.0,
    font_file: str | None = None,
    video_codec: str = "libx264",
    audio_codec: str = "copy",
    crf: int = 18,
    preset: str = "medium",
    progress: bool = False,
) -> list[str]:
    """ffmpeg argv (sans binary) drawing a text watermark via the drawtext filter.

    When ``font_file`` is not given, a concrete font file is auto-resolved
    (CJK-aware) so Chinese/Japanese/Korean text renders correctly instead of as
    tofu boxes on builds whose fontconfig default is a Latin-only face.
    ``progress=True`` appends ``-progress pipe:1`` for streaming progress.
    """
    x_expr, y_expr = _watermark_xy(position, margin)
    drawtext = _build_drawtext_filter(
        text=text,
        x_expr=x_expr,
        y_expr=y_expr,
        font_size=font_size,
        font_color=font_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        opacity=opacity,
        font_file=font_file or _resolve_watermark_fontfile(text),
    )
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        drawtext,
        "-c:v",
        video_codec,
    ]
    if video_codec == "libx264":
        args.extend(["-crf", str(crf), "-preset", preset])
    args.extend(["-c:a", audio_codec, "-movflags", "+faststart"])
    if progress:
        args.extend(["-progress", "pipe:1", "-nostats"])
    args.append(str(output_path))
    return args


def draw_text_watermark(**kwargs: Any) -> Path:
    """Draw a text watermark onto the video via drawtext and re-encode (blocking)."""
    output_path: Path = kwargs["output_path"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(build_text_watermark_args(**kwargs))
    return output_path


def embed_soft_subtitle(
    *,
    input_video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    container: str = "mp4",
    subtitle_language: str | None = None,
) -> Path:
    """Embed a subtitle as a selectable soft track without re-encoding video or
    audio. Copies every existing source stream (``-map 0``) and adds the new
    subtitle (``mov_text`` for mp4, ``srt`` for mkv)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-y",
        "-i",
        str(input_video_path),
        "-i",
        str(subtitle_path),
        "-map",
        "0",
        "-map",
        "1:s:0",
        "-c",
        "copy",
        "-c:s",
        _soft_subtitle_codec(container),
    ]
    if subtitle_language:
        args.extend(["-metadata:s:s:0", f"language={iso639_2(subtitle_language)}"])
    args.extend(["-movflags", "+faststart", str(output_path)])
    run_ffmpeg(args)
    return output_path
