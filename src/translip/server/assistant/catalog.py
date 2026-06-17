"""Machine-readable atomic-tool catalog for the DeepSeek planner.

The planner needs, per tool: its parameters (names / types / defaults / allowed
values), which parameters are *file inputs*, and which *named outputs* it
produces so a later step can bind to them. The atomic-tool ``ToolSpec`` registry
covers names/descriptions but not params or outputs, so we derive params from the
Pydantic request models in ``atomic_tools/schemas.py`` and curate the output
descriptions here (the adapters' return dicts use stable keys like
``voice_file`` / ``segments_file`` — see ``adapters/*.py``).
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from ..atomic_tools.registry import TOOL_REGISTRY, get_tool_spec
from ..atomic_tools.schemas import (
    M3u8ToMp4ToolRequest,
    MixingToolRequest,
    MuxingToolRequest,
    ProbeToolRequest,
    SeparationToolRequest,
    SubtitleDetectToolRequest,
    SubtitleEraseToolRequest,
    TranscriptCorrectionToolRequest,
    TranscriptionToolRequest,
    TranslationToolRequest,
    TtsToolRequest,
    VideoAnalyzeToolRequest,
)


@dataclass(frozen=True)
class ToolCatalogEntry:
    request_model: type[BaseModel]
    # Result-dict keys this tool produces, mapped to a human description of the
    # artifact's role. A later step binds an input to one of these keys.
    outputs: dict[str, str]


# tool_id -> (request model, output roles). Output keys MUST match the adapter
# return dicts in src/translip/server/atomic_tools/adapters/*.py.
TOOL_CATALOG: dict[str, ToolCatalogEntry] = {
    "separation": ToolCatalogEntry(
        SeparationToolRequest,
        {"voice_file": "分离出的人声音轨", "background_file": "分离出的背景/伴奏音轨"},
    ),
    "transcription": ToolCatalogEntry(
        TranscriptionToolRequest,
        {"segments_file": "转写分段 JSON（含时间轴与文本）", "srt_file": "转写字幕 SRT"},
    ),
    "transcript-correction": ToolCatalogEntry(
        TranscriptCorrectionToolRequest,
        {
            "corrected_segments_file": "校正后的分段 JSON",
            "corrected_srt_file": "校正后的字幕 SRT",
            "corrected_clean_srt_file": "去标注的干净 SRT",
        },
    ),
    "translation": ToolCatalogEntry(
        TranslationToolRequest,
        {
            "translation_json_file": "翻译结果 JSON",
            "srt_file": "翻译后的字幕 SRT",
            "translation_file": "翻译纯文本",
        },
    ),
    "tts": ToolCatalogEntry(
        TtsToolRequest,
        {"speech_file": "合成的语音 WAV"},
    ),
    "mixing": ToolCatalogEntry(
        MixingToolRequest,
        {"mixed_file": "混合后的音频"},
    ),
    "muxing": ToolCatalogEntry(
        MuxingToolRequest,
        {"output_file": "合成后的视频 MP4"},
    ),
    "subtitle-detect": ToolCatalogEntry(
        SubtitleDetectToolRequest,
        {
            "ocr_events_file": "OCR 字幕事件 JSON（含时间轴）",
            "detection_file": "OCR 原始检测 JSON（用于字幕擦除）",
        },
    ),
    "subtitle-erase": ToolCatalogEntry(
        SubtitleEraseToolRequest,
        {"erased_file": "擦除字幕后的视频"},
    ),
    "video-analyze": ToolCatalogEntry(
        VideoAnalyzeToolRequest,
        {"result_file": "视频内容分析结果 JSON"},
    ),
    "probe": ToolCatalogEntry(
        ProbeToolRequest,
        {},
    ),
    "m3u8-to-mp4": ToolCatalogEntry(
        M3u8ToMp4ToolRequest,
        {"output_file": "转换得到的 MP4/MKV"},
    ),
}


def is_file_param(name: str) -> bool:
    return name == "file_id" or name.endswith("_file_id") or name.endswith("_file_ids")


def _describe_type(annotation: Any) -> tuple[str, list[Any] | None]:
    """Return (type label, allowed values | None) for a model field annotation."""
    origin = get_origin(annotation)
    # Unwrap Optional[...] / X | None
    if origin is Union or origin is getattr(typing, "UnionType", object()):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _describe_type(args[0])
        labels = [_describe_type(arg)[0] for arg in args]
        return " | ".join(labels), None
    if origin is Literal:
        choices = list(get_args(annotation))
        return "enum", choices
    if annotation in (str, int, float, bool):
        return annotation.__name__, None
    if origin in (list, set, tuple):
        return "list", None
    return getattr(annotation, "__name__", str(annotation)), None


def _params_for(model: type[BaseModel]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a request model into (file_inputs, plain_params) descriptors."""
    file_inputs: list[dict[str, Any]] = []
    plain: list[dict[str, Any]] = []
    for name, field in model.model_fields.items():
        type_label, choices = _describe_type(field.annotation)
        default = field.default
        if default is PydanticUndefined:
            default = None
        descriptor: dict[str, Any] = {
            "name": name,
            "type": type_label,
            "required": field.is_required(),
        }
        if choices is not None:
            descriptor["choices"] = choices
        if not field.is_required():
            descriptor["default"] = default
        if field.description:
            descriptor["description"] = field.description
        if is_file_param(name):
            file_inputs.append(descriptor)
        else:
            plain.append(descriptor)
    return file_inputs, plain


def build_tool_catalog() -> list[dict[str, Any]]:
    """Return the full catalog the planner is given (one entry per registered tool)."""
    catalog: list[dict[str, Any]] = []
    for tool_id in TOOL_REGISTRY:
        spec = get_tool_spec(tool_id)
        entry = TOOL_CATALOG.get(tool_id)
        if entry is None:
            # A tool exists but we have no curated metadata — expose names only so
            # the planner still knows it exists, without inventing params.
            catalog.append(
                {
                    "tool_id": tool_id,
                    "name": spec.name_zh,
                    "description": spec.description_zh,
                    "accept_formats": spec.accept_formats,
                    "file_inputs": [],
                    "params": [],
                    "outputs": {},
                }
            )
            continue
        file_inputs, plain = _params_for(entry.request_model)
        catalog.append(
            {
                "tool_id": tool_id,
                "name": spec.name_zh,
                "description": spec.description_zh,
                "accept_formats": spec.accept_formats,
                "file_inputs": file_inputs,
                "params": plain,
                "outputs": entry.outputs,
            }
        )
    return catalog


def model_field_names(tool_id: str) -> set[str]:
    """Valid parameter names for a tool's request model (for plan validation)."""
    entry = TOOL_CATALOG.get(tool_id)
    if entry is None:
        return set()
    return set(entry.request_model.model_fields)
