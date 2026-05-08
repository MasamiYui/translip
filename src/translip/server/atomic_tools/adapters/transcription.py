from __future__ import annotations

import re
from pathlib import Path

from ....transcription.runner import transcribe_file
from ....types import TranscriptionRequest
from ..registry import ToolSpec, register_tool
from ..schemas import TranscriptionToolRequest
from . import ToolAdapter


def _artifact_language_tag(language: object) -> str:
    raw = str(language or "zh").strip().lower()
    sanitized = re.sub(r"[^a-z0-9.-]+", "-", raw).strip("-")
    return sanitized or "zh"


class TranscriptionAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return TranscriptionToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        on_progress(5.0, "loading_model")
        request = TranscriptionRequest(
            input_path=input_file,
            output_dir=output_dir,
            language=params.get("language", "zh"),
            asr_model=params.get("asr_model", "small"),
            write_srt=params.get("generate_srt", True),
        ).normalized()
        on_progress(10.0, "transcribing")
        result = transcribe_file(request)
        language_tag = _artifact_language_tag(params.get("language", "zh"))
        segments_path = self.copy_output(
            Path(result.artifacts.segments_json_path),
            output_dir,
            f"segments.{language_tag}.json",
        )
        srt_path = (
            self.copy_output(Path(result.artifacts.srt_path), output_dir, f"segments.{language_tag}.srt")
            if result.artifacts.srt_path is not None
            else None
        )
        unique_speakers = sorted({segment.speaker_label for segment in result.segments})
        on_progress(90.0, "finalizing")
        return {
            "total_segments": len(result.segments),
            "total_duration_sec": result.media_info.duration_sec,
            "language": params.get("language", "zh"),
            "speaker_count": len(unique_speakers),
            "speakers": unique_speakers,
            "segments": [
                {
                    "id": segment.segment_id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "speaker": segment.speaker_label,
                }
                for segment in result.segments
            ],
            "has_srt": srt_path is not None,
            "srt_file": srt_path.name if srt_path is not None else None,
            "segments_file": segments_path.name,
        }


register_tool(
    ToolSpec(
        tool_id="transcription",
        name_zh="语音转文字",
        name_en="Speech to Text",
        description_zh="语音识别并生成带时间戳的文字与字幕",
        description_en="Transcribe audio/video into timestamped text and subtitles",
        category="speech",
        icon="MessageSquareText",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".m4a", ".ogg"],
        max_file_size_mb=500,
        max_files=1,
    ),
    TranscriptionAdapter,
)
