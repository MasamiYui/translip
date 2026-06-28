"""Works (TV shows, movies, etc.) management routes.

These endpoints manage `~/.translip/works.json` — a structured registry of works
(作品) used to disambiguate personas across productions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ...config import DEFAULT_RENDER_OUTPUT_SAMPLE_RATE

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_DIR = Path.home() / ".translip"
CONFIG_PATH = CONFIG_DIR / "config.json"

_DEFAULT_CONFIG = {
    "device": "auto",
    "run_from_stage": "separation",
    "run_to_stage": "delivery",
    "use_cache": True,
    "keep_intermediate": False,
    "separation_mode": "dialogue",
    "separation_quality": "balanced",
    "music_backend": "demucs",
    "dialogue_backend": "cdx23",
    "stage1_output_format": "mp3",
    "audio_stream_index": 0,
    "asr_model": "paraformer-zh",
    "asr_backend": "funasr",
    "diarizer_backend": "ecapa",
    "enable_diarization": True,
    "vad_filter": True,
    "vad_min_silence_duration_ms": 400,
    "beam_size": 5,
    "best_of": 5,
    "temperature": 0.0,
    "condition_on_previous_text": False,
    "generate_srt": True,
    "top_k": 3,
    "ocr_sample_interval": 0.25,
    "ocr_position_mode": "auto",
    "ocr_extraction_mode": "conservative",
    "translation_backend": "local-m2m100",
    "translation_batch_size": 4,
    "deepseek_model": None,
    "condense_mode": "smart",
    "transcription_correction": {"enabled": True, "preset": "standard", "ocr_only_policy": "report_only", "llm_arbitration": "off"},
    "tts_backend": "moss-tts-nano-onnx",
    "dubbing_quality_check": "standard",
    "dubbing_workers": None,
    "dub_repair_enabled": False,
    "dub_repair_backend": [],
    "dub_repair_max_items": 12,
    "dub_repair_attempts_per_item": 3,
    "dub_repair_include_risk": False,
    "fit_policy": "conservative",
    "fit_backend": "atempo",
    "mix_profile": "preview",
    "ducking_mode": "static",
    "background_gain_db": -8.0,
    "window_ducking_db": -3.0,
    "max_compress_ratio": 1.45,
    "output_sample_rate": DEFAULT_RENDER_OUTPUT_SAMPLE_RATE,
    "preview_format": "wav",
    "export_preview": True,
    "export_dub": True,
    "delivery_container": "mp4",
    "delivery_video_codec": "copy",
    "delivery_audio_codec": "aac",
    "subtitle_mode": "none",
    "subtitle_render_source": "ocr",
    "subtitle_font": None,
    "subtitle_font_size": 0,
    "subtitle_color": "#FFFFFF",
    "subtitle_outline_color": "#000000",
    "subtitle_outline_width": 2.0,
    "subtitle_position": "bottom",
    "subtitle_margin_v": 0,
    "subtitle_bold": False,
    "bilingual_chinese_position": "bottom",
    "bilingual_english_position": "top",
    "bilingual_export_strategy": "auto_standard_bilingual",
    # Subtitle erase (subtitle-erase node, +erase template only)
    "erase_backend": "sttn",
    "erase_device": "auto",
    "erase_mask_dilate_x": 12,
    "erase_mask_dilate_y": 8,
    "erase_event_lead_frames": 3,
    "erase_event_trail_frames": 8,
    "erase_neighbor_stride": 5,
    "erase_reference_length": 10,
    "erase_max_load": 50,
}


def _load_config() -> dict[str, Any]:
    """Load config from ~/.translip/config.json."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_config(config: dict[str, Any]) -> None:
    """Save config to ~/.translip/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.chmod(CONFIG_PATH, 0o600)


def _load_global_config() -> dict[str, Any]:
    config = _load_config()
    saved_global = config.get("global", {})
    if not isinstance(saved_global, dict):
        saved_global = {}
    merged = {**_DEFAULT_CONFIG, **saved_global}
    # Dropped from task defaults (now an account-level setting next to the API
    # key); tolerate stale saved configs that still carry it.
    merged.pop("deepseek_base_url", None)
    return merged


def migrate_deepseek_base_url_to_user_settings() -> None:
    """One-time migration: move ``global.deepseek_base_url`` to user settings.

    The DeepSeek API base URL used to live in the task-default config; it is now
    an account-level setting stored next to the API key (see
    ``cache_manager.set_llm_base_url``). Runs at server startup; a no-op once the
    old key is gone. An already-saved user-setting value wins over the old one.
    """
    config = _load_config()
    saved_global = config.get("global")
    if not isinstance(saved_global, dict) or "deepseek_base_url" not in saved_global:
        return
    from .. import cache_manager

    old_value = saved_global.pop("deepseek_base_url", None)
    if old_value and not cache_manager.read_llm_base_url("deepseek"):
        cache_manager.set_llm_base_url("deepseek", str(old_value))
    config["global"] = saved_global
    _save_config(config)


@router.get("/narrator-voices", summary="内置解说音色列表")
def list_narrator_voices_endpoint() -> list[dict[str, str]]:
    from translip.commentary.voices import list_narrator_voices

    return [
        {
            "id": v.id,
            "name_zh": v.name_zh,
            "name_en": v.name_en,
            "gender": v.gender,
            "native_language": v.native_language,
            "description_zh": v.description_zh,
            "description_en": v.description_en,
            "preview_url": f"/api/config/narrator-voices/{v.id}/preview",
        }
        for v in list_narrator_voices()
    ]


@router.get(
    "/narrator-voices/{voice_id}/preview",
    summary="试听解说音色",
    responses={
        200: {"content": {"audio/wav": {}}},
        404: {"description": "Voice id not found"},
        500: {"description": "Failed to render preview audio"},
    },
)
def preview_narrator_voice(
    voice_id: Annotated[str, PathParam(description="解说音色 ID")],
    language: Annotated[
        Optional[str],
        Query(description="试听语种（默认按该音色的母语；可显式传入 zh/en/ja/ko）"),
    ] = None,
) -> FileResponse:
    """按需生成并缓存音色试听片段。

    复用 ``translip.commentary.voices`` 中的缓存机制：首轮调用会渲染
    ``Qwen3-TTS-12Hz-0.6B-CustomVoice`` 一次（落盘约 10 秒的中性解说样片），
    之后所有请求都直接复用缓存 WAV，无需再次推理。
    """
    from translip.commentary import voices as narrator_voices

    voice = narrator_voices.get_narrator_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Unknown narrator voice {voice_id!r}")

    lang = language or voice.native_language or "zh"
    cache_path = narrator_voices._reference_path(voice.id, lang)
    if not (cache_path.exists() and cache_path.stat().st_size > 0):
        try:
            narrator_voices._generate_voice_reference(voice, lang, cache_path)
        except Exception as exc:  # pragma: no cover - depends on model download
            message = str(exc).strip() or exc.__class__.__name__
            hint = ""
            low = message.lower()
            if any(
                key in low
                for key in (
                    "connection",
                    "timeout",
                    "resolve",
                    "huggingface.co",
                    "hf-mirror",
                    "proxy",
                )
            ):
                hint = (
                    " 提示：模型下载失败，请设置 HF_ENDPOINT=https://hf-mirror.com "
                    "或检查网络连接后重试。"
                )
            elif "no module" in low or "import" in low:
                hint = " 提示：依赖未安装，请运行 `uv sync` 后重试。"
            raise HTTPException(
                status_code=500,
                detail=f"音色 {voice_id!r} 试听生成失败：{message}.{hint}",
            ) from exc

    return FileResponse(
        path=str(cache_path),
        media_type="audio/wav",
        filename=f"{voice_id}.{narrator_voices._lang_key(lang)}.wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/defaults", summary="默认全局配置")
def get_defaults():
    """获取全局默认配置（内置默认值叠加已保存的全局覆盖项），用于初始化表单。"""
    return _load_global_config()


class GlobalConfigRequest(BaseModel):
    device: Optional[str] = Field(default=None, description="运行设备，如 auto/cpu/cuda/mps")
    use_cache: Optional[bool] = Field(default=None, description="是否复用各阶段的缓存产物")
    keep_intermediate: Optional[bool] = Field(default=None, description="是否保留流水线中间产物")
    separation_mode: Optional[str] = Field(default=None, description="separation 人声/背景分离模式，如 auto")
    separation_quality: Optional[str] = Field(default=None, description="separation 分离质量档位，如 balanced")
    music_backend: Optional[str] = Field(default=None, description="separation 背景音乐分离后端，如 demucs")
    dialogue_backend: Optional[str] = Field(default=None, description="separation 人声/对白分离后端，如 cdx23")
    stage1_output_format: Optional[str] = Field(default=None, description="separation 输出音频格式，如 mp3/wav")
    audio_stream_index: Optional[int] = Field(default=None, description="源视频中要处理的音轨索引，从 0 开始")
    asr_model: Optional[str] = Field(default=None, description="transcription 转写所用 ASR 模型名，如 paraformer-zh")
    asr_backend: Optional[str] = Field(default=None, description="transcription 转写后端，如 funasr/faster-whisper")
    diarizer_backend: Optional[str] = Field(default=None, description="说话人分离(diarization)后端，如 ecapa/pyannote")
    enable_diarization: Optional[bool] = Field(default=None, description="是否启用说话人分离(diarization)")
    generate_srt: Optional[bool] = Field(default=None, description="转写后是否生成 SRT 字幕文件")
    vad_filter: Optional[bool] = Field(default=None, description="转写时是否启用 VAD 语音活动检测过滤")
    vad_min_silence_duration_ms: Optional[int] = Field(default=None, description="VAD 最小静音时长（毫秒），需大于 0")
    beam_size: Optional[int] = Field(default=None, description="ASR 解码 beam search 宽度，需大于 0")
    best_of: Optional[int] = Field(default=None, description="ASR 采样候选数 best_of，需大于 0")
    temperature: Optional[float] = Field(default=None, description="ASR 解码温度，需大于等于 0")
    condition_on_previous_text: Optional[bool] = Field(default=None, description="转写是否以上文文本为条件")
    top_k: Optional[int] = Field(default=None, description="候选保留数 top_k，需大于 0")
    ocr_sample_interval: Optional[float] = Field(default=None, description="字幕识别(OCR)抽帧采样间隔（秒）")
    ocr_position_mode: Optional[str] = Field(default=None, description="OCR 字幕区域定位模式，如 auto")
    ocr_extraction_mode: Optional[str] = Field(default=None, description="OCR 字幕提取模式，如 conservative")
    translation_backend: Optional[str] = Field(default=None, description="translation 翻译后端，如 local-m2m100/deepseek")
    translation_batch_size: Optional[int] = Field(default=None, description="翻译批处理大小，需大于 0")
    deepseek_model: Optional[str] = Field(default=None, description="deepseek 翻译后端使用的模型名")
    condense_mode: Optional[str] = Field(default=None, description="文本精简模式，如 off")
    transcription_correction: Optional[dict] = Field(default=None, description="转写纠错配置（启用开关、预设、OCR 仅报告策略、LLM 仲裁等）")
    tts_backend: Optional[str] = Field(default=None, description="synthesis 语音合成(TTS)后端，如 moss-tts-nano-onnx")
    dubbing_quality_check: Optional[str] = Field(default=None, description="配音(dub)质量检查档位，如 standard")
    dubbing_workers: Optional[int] = Field(default=None, description="配音合成并发 worker 数，需大于 0")
    dub_repair_enabled: Optional[bool] = Field(default=None, description="是否启用配音修复（重合成失败片段）")
    dub_repair_backend: Optional[list[str]] = Field(default=None, description="配音修复使用的 TTS 后端列表")
    dub_repair_max_items: Optional[int] = Field(default=None, description="单次配音修复最多处理的片段数，需大于 0")
    dub_repair_attempts_per_item: Optional[int] = Field(default=None, description="每个片段的配音修复重试次数，需大于 0")
    dub_repair_include_risk: Optional[bool] = Field(default=None, description="配音修复是否纳入风险（疑似异常）片段")
    fit_policy: Optional[str] = Field(default=None, description="render 时间轴重拟合策略，如 conservative")
    fit_backend: Optional[str] = Field(default=None, description="时间轴拟合后端，如 atempo/rubberband")
    mix_profile: Optional[str] = Field(default=None, description="混音档位，如 preview")
    ducking_mode: Optional[str] = Field(default=None, description="背景闪避(ducking)模式，如 static")
    background_gain_db: Optional[float] = Field(default=None, description="背景音增益（分贝）")
    window_ducking_db: Optional[float] = Field(default=None, description="人声窗口内背景闪避量（分贝）")
    max_compress_ratio: Optional[float] = Field(default=None, description="时间轴最大压缩比，需大于 0")
    output_sample_rate: Optional[int] = Field(default=None, description="输出音频采样率（Hz），需大于 0")
    preview_format: Optional[str] = Field(default=None, description="预览音频格式，如 wav")
    export_preview: Optional[bool] = Field(default=None, description="是否导出预览音频")
    export_dub: Optional[bool] = Field(default=None, description="是否导出配音成品")
    delivery_container: Optional[str] = Field(default=None, description="delivery 导出视频封装容器，如 mp4")
    delivery_video_codec: Optional[str] = Field(default=None, description="导出视频编码，如 copy 表示直接复制")
    delivery_audio_codec: Optional[str] = Field(default=None, description="导出音频编码，如 aac")
    subtitle_mode: Optional[str] = Field(default=None, description="导出字幕模式，如 none/不烧录")
    subtitle_render_source: Optional[str] = Field(default=None, description="渲染字幕的来源，如 ocr")
    subtitle_font: Optional[str] = Field(default=None, description="烧录字幕字体名")
    subtitle_font_size: Optional[int] = Field(default=None, description="烧录字幕字号，需大于等于 0")
    subtitle_color: Optional[str] = Field(default=None, description="字幕填充颜色（十六进制）")
    subtitle_outline_color: Optional[str] = Field(default=None, description="字幕描边颜色（十六进制）")
    subtitle_outline_width: Optional[float] = Field(default=None, description="字幕描边宽度，需大于等于 0")
    subtitle_position: Optional[str] = Field(default=None, description="字幕位置，如 bottom/top")
    subtitle_margin_v: Optional[int] = Field(default=None, description="字幕垂直边距，需大于等于 0")
    subtitle_bold: Optional[bool] = Field(default=None, description="字幕是否加粗")
    bilingual_chinese_position: Optional[str] = Field(default=None, description="双语字幕中文行位置，如 bottom")
    bilingual_english_position: Optional[str] = Field(default=None, description="双语字幕英文行位置，如 top")
    bilingual_export_strategy: Optional[str] = Field(default=None, description="双语字幕导出策略，如 auto_standard_bilingual")
    erase_backend: Optional[str] = Field(default=None, description="字幕擦除后端：sttn/lama（仅 +擦除 模板生效）")
    erase_device: Optional[str] = Field(default=None, description="字幕擦除计算设备，如 auto/mps/cuda/cpu")
    erase_mask_dilate_x: Optional[int] = Field(default=None, description="字幕擦除掩码横向膨胀像素，需大于等于 0")
    erase_mask_dilate_y: Optional[int] = Field(default=None, description="字幕擦除掩码纵向膨胀像素，需大于等于 0")
    erase_event_lead_frames: Optional[int] = Field(default=None, description="字幕事件提前擦除帧数，需大于等于 0")
    erase_event_trail_frames: Optional[int] = Field(default=None, description="字幕事件延后擦除帧数，需大于等于 0")
    erase_neighbor_stride: Optional[int] = Field(default=None, description="STTN 时间邻域采样步长，需大于 0")
    erase_reference_length: Optional[int] = Field(default=None, description="STTN 全局参考帧步长，需大于 0")
    erase_max_load: Optional[int] = Field(default=None, description="字幕擦除单批最大加载帧数，需大于 0")


def _validate_global_update(update: dict[str, Any]) -> None:
    for field in (
        "vad_min_silence_duration_ms",
        "beam_size",
        "best_of",
        "top_k",
        "translation_batch_size",
        "dubbing_workers",
        "dub_repair_max_items",
        "dub_repair_attempts_per_item",
        "output_sample_rate",
        "erase_max_load",
        "erase_neighbor_stride",
        "erase_reference_length",
    ):
        if field in update and update[field] is not None and int(update[field]) <= 0:
            raise HTTPException(status_code=400, detail=f"{field} must be greater than 0")
    for field in (
        "audio_stream_index",
        "subtitle_font_size",
        "subtitle_margin_v",
        "erase_mask_dilate_x",
        "erase_mask_dilate_y",
        "erase_event_lead_frames",
        "erase_event_trail_frames",
    ):
        if field in update and update[field] is not None and int(update[field]) < 0:
            raise HTTPException(status_code=400, detail=f"{field} must be greater than or equal to 0")
    if "max_compress_ratio" in update and update["max_compress_ratio"] is not None and float(update["max_compress_ratio"]) <= 0:
        raise HTTPException(status_code=400, detail="max_compress_ratio must be greater than 0")
    for field in ("subtitle_outline_width",):
        if field in update and update[field] is not None and float(update[field]) < 0:
            raise HTTPException(status_code=400, detail=f"{field} must be greater than or equal to 0")
    if "temperature" in update and update["temperature"] is not None and float(update["temperature"]) < 0:
        raise HTTPException(status_code=400, detail="temperature must be greater than or equal to 0")


@router.get("/global", summary="读取全局配置")
def get_global_config() -> dict[str, Any]:
    """获取当前生效的全局配置（内置默认值叠加已保存的全局覆盖项）。"""
    return _load_global_config()


@router.put("/global", summary="更新全局配置")
def update_global_config(req: GlobalConfigRequest) -> dict[str, Any]:
    """更新全局配置：仅提交的字段生效，值为 null 表示清除该项覆盖以回退默认值，写入后返回最新配置。"""
    update = req.model_dump(exclude_unset=True)
    _validate_global_update(update)
    config = _load_config()
    saved_global = config.get("global", {})
    if not isinstance(saved_global, dict):
        saved_global = {}
    for key, value in update.items():
        if value is None:
            saved_global.pop(key, None)
        else:
            saved_global[key] = value
    config["global"] = saved_global
    _save_config(config)
    return {"ok": True, "config": _load_global_config()}


@router.get("/tmdb", summary="读取 TMDb 配置")
def get_tmdb_config() -> dict[str, Any]:
    """获取当前 TMDb API 配置：仅返回 v3/v4 密钥是否已设置及默认语言，不回传密钥明文。"""
    config = _load_config()
    tmdb = config.get("tmdb", {})
    return {
        "ok": True,
        "api_key_v3_set": bool(tmdb.get("api_key_v3")),
        "api_key_v4_set": bool(tmdb.get("api_key_v4")),
        "default_language": tmdb.get("default_language", "zh-CN"),
    }


class TMDbConfigRequest(BaseModel):
    api_key_v3: Optional[str] = Field(default=None, description="TMDb v3 API Key，留空则不更新")
    api_key_v4: Optional[str] = Field(default=None, description="TMDb v4 Bearer Token，留空则不更新")
    default_language: Optional[str] = Field(default=None, description="TMDb 查询默认语言，如 zh-CN")


@router.post("/tmdb", summary="保存 TMDb 配置")
def save_tmdb_config(req: TMDbConfigRequest) -> dict[str, Any]:
    """保存 TMDb API 配置：仅写入非空字段（其余保持原值），凭据明文落盘于本地配置文件。"""
    config = _load_config()
    
    if "tmdb" not in config:
        config["tmdb"] = {}
    
    if req.api_key_v3 is not None:
        config["tmdb"]["api_key_v3"] = req.api_key_v3
    if req.api_key_v4 is not None:
        config["tmdb"]["api_key_v4"] = req.api_key_v4
    if req.default_language is not None:
        config["tmdb"]["default_language"] = req.default_language
    
    _save_config(config)

    return {
        "ok": True,
        "message": "TMDb configuration saved",
    }


class TMDbTestRequest(BaseModel):
    api_key_v3: Optional[str] = Field(default=None, description="待校验的 TMDb v3 API Key，留空则回退已保存或环境变量值")
    api_key_v4: Optional[str] = Field(default=None, description="待校验的 TMDb v4 Bearer Token，留空则回退已保存或环境变量值")


@router.post("/tmdb/test", summary="测试 TMDb 凭据")
def test_tmdb_config(req: TMDbTestRequest) -> dict[str, Any]:
    """校验 TMDb 凭据连通性：优先用请求内提供的密钥，否则回退已保存的配置或环境变量，不落盘。"""
    saved = _load_config().get("tmdb", {})
    v3 = (req.api_key_v3 or "").strip() or saved.get("api_key_v3") or os.environ.get("TMDB_API_KEY", "")
    v4 = (req.api_key_v4 or "").strip() or saved.get("api_key_v4") or os.environ.get("TMDB_BEARER_TOKEN", "")
    from ...speaker_review.works_providers.tmdb import verify_credentials

    result = verify_credentials(api_key_v3=v3, api_key_v4=v4)
    return {"ok": bool(result.get("ok")), "message": result.get("message", "")}


# ---- Presets ----

from datetime import datetime

from fastapi import Depends
from sqlmodel import Session, select

from ..database import get_session
from ..models import ConfigPreset
from ..schemas import ConfigPresetRead, CreatePresetRequest

presets_router = APIRouter(prefix="/api/config/presets", tags=["config-presets"])


@router.get("/presets", response_model=list[ConfigPresetRead], summary="预设列表")
def list_presets(session: Session = Depends(get_session)):
    """列出所有已保存的配置预设(preset)。"""
    return list(session.exec(select(ConfigPreset)).all())


@router.post("/presets", response_model=ConfigPresetRead, summary="创建预设")
def create_preset(req: CreatePresetRequest, session: Session = Depends(get_session)):
    """新建一个配置预设(preset)；预设名称需唯一，重名将返回 400。"""
    existing = session.exec(select(ConfigPreset).where(ConfigPreset.name == req.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Preset with this name already exists")
    preset = ConfigPreset(
        name=req.name,
        description=req.description,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
        config=req.config,
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)
    return preset


@router.delete("/presets/{preset_id}", summary="删除预设")
def delete_preset(preset_id: Annotated[int, PathParam(description="预设 ID")], session: Session = Depends(get_session)):
    """按 ID 删除指定的配置预设(preset)；不存在则返回 404。"""
    preset = session.get(ConfigPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    session.delete(preset)
    session.commit()
    return {"ok": True}
