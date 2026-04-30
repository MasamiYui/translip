from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from ..config import DEFAULT_SUBTITLE_FONT_CJK, DEFAULT_SUBTITLE_FONT_LATIN
from ..types import SubtitleStyle
from ..utils.ffmpeg import burn_subtitle_and_mux, burn_subtitle_preview

_SPEAKER_LABEL_RE = re.compile(
    r"(?im)^\s*(?:\[(?:speaker|spk)[_-][\w-]+\]|(?:speaker|spk)[_-][\w-]+:)\s*"
)


def recommend_style(
    video_width: int,
    video_height: int,
    lang: str = "en",
    position: str = "bottom",
) -> SubtitleStyle:
    height = max(video_height, 1)
    if height <= 720:
        font_size, margin_v, outline = 20, 20, 1.5
    elif height <= 1080:
        font_size, margin_v, outline = 28, 30, 2.0
    elif height <= 2160:
        font_size, margin_v, outline = 36, 40, 2.5
    else:
        font_size, margin_v, outline = 42, 50, 3.0

    is_cjk = lang.lower() in {"zh", "zh-cn", "zh-hans", "zh-tw", "ja", "ko"}
    font_family = DEFAULT_SUBTITLE_FONT_CJK if is_cjk else DEFAULT_SUBTITLE_FONT_LATIN
    alignment = 8 if position == "top" else 2

    return SubtitleStyle(
        font_family=font_family,
        font_size=font_size,
        primary_color="#FFFFFF",
        outline_color="#000000",
        outline_width=outline,
        shadow_depth=1.0,
        bold=False,
        position=position,
        margin_v=margin_v,
        margin_h=20,
        alignment=alignment,
    )


def _hex_to_ass_color(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"&H00{b:02X}{g:02X}{r:02X}"
    return "&H00FFFFFF"


def _build_ass_style(name: str, style: SubtitleStyle) -> str:
    primary = _hex_to_ass_color(style.primary_color)
    outline = _hex_to_ass_color(style.outline_color)
    bold_flag = -1 if style.bold else 0
    return (
        f"Style: {name},"
        f"{style.font_family},"
        f"{style.font_size},"
        f"{primary},&H000000FF,{outline},&H80000000,"
        f"{bold_flag},0,0,0,"
        f"100,100,0,0,"
        f"1,{style.outline_width:.1f},{style.shadow_depth:.1f},"
        f"{style.alignment},"
        f"{style.margin_h},{style.margin_h},{style.margin_v},1"
    )


def _parse_srt_time(time_str: str) -> float:
    time_str = time_str.strip().replace(",", ".")
    match = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", time_str)
    if not match:
        return 0.0
    h, m, s, ms = match.groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def _format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _parse_srt_blocks(srt_path: Path) -> list[dict]:
    text = srt_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*\n", text)
    events = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_match = re.match(
            r"(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)", lines[1]
        )
        if not time_match:
            continue
        start = _parse_srt_time(time_match.group(1))
        end = _parse_srt_time(time_match.group(2))
        content = "\n".join(lines[2:]).strip()
        events.append({"start": start, "end": end, "text": content})
    return events


def _display_subtitle_text(text: str) -> str:
    cleaned = _SPEAKER_LABEL_RE.sub("", text)
    return "\n".join(line.strip() for line in cleaned.splitlines()).strip()


def srt_to_ass(
    srt_path: Path,
    style: SubtitleStyle,
    output_path: Path,
    style_name: str = "Default",
    play_res: tuple[int, int] | None = None,
) -> Path:
    events = _parse_srt_blocks(srt_path)
    header = _build_ass_header([(style_name, style)], play_res=play_res)
    dialogue_lines = []
    for event in events:
        start = _format_ass_time(event["start"])
        end = _format_ass_time(event["end"])
        text = _display_subtitle_text(event["text"]).replace("\n", "\\N")
        if not text:
            continue
        dialogue_lines.append(f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{text}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = header + "\n".join(dialogue_lines) + "\n"
    output_path.write_text(content, encoding="utf-8-sig")
    return output_path


def merge_bilingual_ass(
    chinese_srt: Path,
    english_srt: Path,
    chinese_style: SubtitleStyle,
    english_style: SubtitleStyle,
    output_path: Path,
    play_res: tuple[int, int] | None = None,
) -> Path:
    cn_events = _parse_srt_blocks(chinese_srt)
    en_events = _parse_srt_blocks(english_srt)
    header = _build_ass_header([("Chinese", chinese_style), ("English", english_style)], play_res=play_res)
    dialogue_lines = []
    for event in cn_events:
        start = _format_ass_time(event["start"])
        end = _format_ass_time(event["end"])
        text = _display_subtitle_text(event["text"]).replace("\n", "\\N")
        if not text:
            continue
        dialogue_lines.append(f"Dialogue: 0,{start},{end},Chinese,,0,0,0,,{text}")
    for event in en_events:
        start = _format_ass_time(event["start"])
        end = _format_ass_time(event["end"])
        text = _display_subtitle_text(event["text"]).replace("\n", "\\N")
        if not text:
            continue
        dialogue_lines.append(f"Dialogue: 0,{start},{end},English,,0,0,0,,{text}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = header + "\n".join(dialogue_lines) + "\n"
    output_path.write_text(content, encoding="utf-8-sig")
    return output_path


def _build_ass_header(
    styles: list[tuple[str, SubtitleStyle]],
    *,
    play_res: tuple[int, int] | None = None,
) -> str:
    play_res_x, play_res_y = play_res or (1920, 1080)
    play_res_x = max(1, int(play_res_x))
    play_res_y = max(1, int(play_res_y))
    style_lines = "\n".join(_build_ass_style(name, s) for name, s in styles)
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style_lines}\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def first_subtitle_time(srt_path: Path) -> float:
    events = _parse_srt_blocks(srt_path)
    if not events:
        return 0.0
    return max(0.0, events[0]["start"] - 1.0)


__all__ = [
    "first_subtitle_time",
    "merge_bilingual_ass",
    "recommend_style",
    "srt_to_ass",
]
