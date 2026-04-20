from __future__ import annotations

from ....transcription.ocr_correction import (
    CorrectionConfig,
    correct_asr_segments_with_ocr,
    load_json_payload,
    write_correction_artifacts,
)
from ..registry import ToolSpec, register_tool
from ..schemas import TranscriptCorrectionToolRequest
from . import ToolAdapter


def _config_from_params(params: dict) -> CorrectionConfig:
    preset = params.get("preset", "standard")
    factories = {
        "conservative": CorrectionConfig.conservative,
        "standard": CorrectionConfig.standard,
        "aggressive": CorrectionConfig.aggressive,
    }
    config = factories[preset]()
    if params.get("enabled", True) is False:
        return CorrectionConfig(enabled=False, preset=preset)
    return config


class TranscriptCorrectionAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return TranscriptCorrectionToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        segments_file = self.first_input(input_dir, "segments_file")
        ocr_events_file = self.first_input(input_dir, "ocr_events_file")
        on_progress(5.0, "loading_inputs")
        segments_payload = load_json_payload(segments_file)
        ocr_payload = load_json_payload(ocr_events_file)
        config = _config_from_params(params)

        on_progress(35.0, "correcting_transcript")
        result = correct_asr_segments_with_ocr(
            segments_payload=segments_payload,
            ocr_payload=ocr_payload,
            config=config,
        )

        on_progress(80.0, "writing_artifacts")
        artifacts = write_correction_artifacts(result, output_dir=output_dir)
        summary = dict(result.report.get("summary") or {})

        on_progress(95.0, "finalizing")
        return {
            "status": "succeeded",
            "segment_count": summary.get("segment_count", 0),
            "corrected_count": summary.get("corrected_count", 0),
            "kept_asr_count": summary.get("kept_asr_count", 0),
            "review_count": summary.get("review_count", 0),
            "ocr_only_count": summary.get("ocr_only_count", 0),
            "algorithm_version": summary.get("algorithm_version", config.algorithm_version),
            "corrected_segments_file": artifacts.corrected_segments_path.name,
            "corrected_srt_file": artifacts.corrected_srt_path.name,
            "report_file": artifacts.report_path.name,
            "manifest_file": artifacts.manifest_path.name,
        }


register_tool(
    ToolSpec(
        tool_id="transcript-correction",
        name_zh="台词校正",
        name_en="Transcript Correction",
        description_zh="使用 OCR 字幕校正 ASR 文稿，保留 ASR 时间轴和说话人",
        description_en="Correct ASR transcript text with OCR subtitle events while preserving ASR timing and speakers",
        category="speech",
        icon="ScanText",
        accept_formats=[".json"],
        max_file_size_mb=500,
        max_files=2,
    ),
    TranscriptCorrectionAdapter,
)
