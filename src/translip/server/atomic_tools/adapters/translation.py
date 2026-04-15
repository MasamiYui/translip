from __future__ import annotations

import json
import re
from pathlib import Path

from ....translation.backend import output_tag_for_language
from ....translation.runner import translate_script
from ....types import TranslationRequest
from ..registry import ToolSpec, register_tool
from ..schemas import TranslationToolRequest
from . import ToolAdapter


class TranslationAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return TranslationToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        on_progress(5.0, "preparing")
        text = (params.get("text") or "").strip()
        input_file = self.first_input(input_dir, "file") if params.get("file_id") else None
        glossary_path = self.first_input(input_dir, "glossary_file") if params.get("glossary_file_id") else None

        segments_payload = _segments_payload_from_input(text=text, input_file=input_file, source_lang=params.get("source_lang", "zh"))
        profiles_payload = _profiles_payload_for_segments(segments_payload["segments"])
        prep_dir = output_dir / "_translation_inputs"
        prep_dir.mkdir(parents=True, exist_ok=True)
        segments_path = prep_dir / "segments.json"
        profiles_path = prep_dir / "profiles.json"
        segments_path.write_text(json.dumps(segments_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        profiles_path.write_text(json.dumps(profiles_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        request = TranslationRequest(
            segments_path=segments_path,
            profiles_path=profiles_path,
            output_dir=output_dir,
            source_lang=params.get("source_lang", "zh"),
            target_lang=params.get("target_lang", "en"),
            backend=params.get("backend", "local-m2m100"),
            glossary_path=glossary_path,
        ).normalized()
        on_progress(15.0, "translating")
        result = translate_script(request)
        translation_json_path = self.copy_output(Path(result.artifacts.translation_json_path), output_dir)
        editable_json_path = self.copy_output(Path(result.artifacts.editable_json_path), output_dir)
        srt_path = self.copy_output(Path(result.artifacts.srt_path), output_dir)

        payload = json.loads(Path(result.artifacts.translation_json_path).read_text(encoding="utf-8"))
        translated_text = "\n".join(
            str(segment.get("target_text", "")).strip()
            for segment in payload.get("segments", [])
            if str(segment.get("target_text", "")).strip()
        )
        output_tag = output_tag_for_language(params.get("target_lang", "en"))
        text_output = output_dir / f"translation.{output_tag}.txt"
        text_output.write_text(translated_text, encoding="utf-8")
        on_progress(95.0, "finalizing")
        return {
            "translated_text": translated_text,
            "segments_count": len(payload.get("segments", [])),
            "translation_json_file": translation_json_path.name,
            "editable_file": editable_json_path.name,
            "srt_file": srt_path.name,
            "translation_file": text_output.name,
        }


def _segments_payload_from_input(*, text: str, input_file: Path | None, source_lang: str) -> dict[str, object]:
    if input_file is not None:
        raw_text = input_file.read_text(encoding="utf-8")
        if input_file.suffix.lower() == ".srt":
            segments = _parse_srt(raw_text, source_lang)
        else:
            segments = _segments_from_plain_text(raw_text, source_lang)
    else:
        segments = _segments_from_plain_text(text, source_lang)
    return {
        "input": {"path": str(input_file) if input_file is not None else "<inline-text>"},
        "segments": segments,
    }


def _segments_from_plain_text(text: str, source_lang: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines and text.strip():
        lines = [text.strip()]
    return [
        {
            "id": f"seg-{index:04d}",
            "start": float(index - 1),
            "end": float(index),
            "duration": 1.0,
            "speaker_label": "SPEAKER_00",
            "text": line,
            "language": source_lang,
        }
        for index, line in enumerate(lines, start=1)
    ]


def _parse_srt(raw_text: str, source_lang: str) -> list[dict[str, object]]:
    blocks = re.split(r"\n\s*\n", raw_text.strip(), flags=re.MULTILINE)
    segments: list[dict[str, object]] = []
    for index, block in enumerate(blocks, start=1):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_text, end_text = [part.strip() for part in lines[1].split("-->", 1)]
        start_sec = _parse_srt_timestamp(start_text)
        end_sec = _parse_srt_timestamp(end_text)
        text = " ".join(lines[2:]).strip()
        speaker_label = "SPEAKER_00"
        speaker_match = re.match(r"^\[(?P<label>[^\]]+)\]\s*(?P<text>.*)$", text)
        if speaker_match:
            speaker_label = speaker_match.group("label")
            text = speaker_match.group("text").strip()
        segments.append(
            {
                "id": f"seg-{index:04d}",
                "start": start_sec,
                "end": end_sec,
                "duration": max(0.1, end_sec - start_sec),
                "speaker_label": speaker_label,
                "text": text,
                "language": source_lang,
            }
        )
    return segments


def _parse_srt_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (int(hours) * 3600) + (int(minutes) * 60) + int(seconds) + (int(millis) / 1000.0)


def _profiles_payload_for_segments(segments: list[dict[str, object]]) -> dict[str, object]:
    labels = []
    for segment in segments:
        label = str(segment.get("speaker_label") or "SPEAKER_00")
        if label not in labels:
            labels.append(label)
    return {
        "profiles": [
            {
                "source_label": label,
                "speaker_id": f"spk_{index:04d}",
            }
            for index, label in enumerate(labels)
        ]
    }


register_tool(
    ToolSpec(
        tool_id="translation",
        name_zh="文本翻译",
        name_en="Text Translation",
        description_zh="翻译文本或字幕文件",
        description_en="Translate plain text or subtitle files",
        category="speech",
        icon="Languages",
        accept_formats=[".txt", ".srt", ".json"],
        max_file_size_mb=20,
        max_files=2,
    ),
    TranslationAdapter,
)
