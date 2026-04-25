from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

DEFAULT_SAMPLE_RATE = 44_100
TRANSCRIPTION_SAMPLE_RATE = 16_000
DEFAULT_OUTPUT_FORMAT = "wav"
DEFAULT_MODE = "auto"
DEFAULT_DEVICE = "auto"
DEFAULT_TRANSCRIPTION_LANGUAGE = "zh"
DEFAULT_TRANSCRIPTION_ASR_MODEL = "small"
DEFAULT_MUSIC_BACKEND = "demucs"
DEFAULT_DIALOGUE_BACKEND = "cdx23"
DEFAULT_TRANSLATION_BACKEND = "local-m2m100"
DEFAULT_TRANSLATION_SOURCE_LANG = "zh"
DEFAULT_TRANSLATION_TARGET_LANG = "en"
DEFAULT_TRANSLATION_LOCAL_MODEL = "facebook/m2m100_418M"
DEFAULT_TRANSLATION_BATCH_SIZE = 4
DEFAULT_CONDENSE_MODE = "off"
DEFAULT_DUBBING_BACKEND = "moss-tts-nano-onnx"
SUPPORTED_DUBBING_BACKENDS = ("moss-tts-nano-onnx", "qwen3tts")
DEFAULT_DUBBING_BACKREAD_MODEL = "tiny"
DEFAULT_PIPELINE_RUN_FROM_STAGE = "stage1"
DEFAULT_PIPELINE_RUN_TO_STAGE = "task-e"
DEFAULT_PIPELINE_OUTPUT_ROOT = "output-pipeline"
DEFAULT_PIPELINE_WRITE_STATUS = True
DEFAULT_PIPELINE_STATUS_UPDATE_INTERVAL_SEC = 2.0
DEFAULT_RENDER_FIT_POLICY = "conservative"
DEFAULT_RENDER_FIT_BACKEND = "atempo"
# Upper bound for atempo compression when fitting TTS audio into the source window.
# Raised from 1.45 to 1.6 (Sprint 1) to recover ~60% of previously "overflow_unfitted"
# segments without perceptible speed-up artefacts.
DEFAULT_RENDER_MAX_COMPRESS_RATIO = 1.6
# Hard upper bound for TTS-generated duration relative to the source window.
# Used by dubbing runner to trigger a retry/regeneration when a synthesis result is
# pathologically long (e.g. "mom mom mom mom..." repetition from weak MT/TTS).
DEFAULT_TTS_GENERATED_DURATION_HARD_RATIO = 1.5
# Symmetric lower bound: if the generated audio is shorter than this fraction
# of the source window we treat it as pathological (TTS truncation / silence)
# and trigger the same retry logic.
DEFAULT_TTS_GENERATED_DURATION_LOWER_RATIO = 0.5
# Minimum reference clip count per speaker to be considered self-cloneable.
# Speakers below this bar will be flagged and may fall back to cross-speaker clones.
DEFAULT_VOICE_BANK_MIN_REFERENCE_CLIPS = 3
# Minimum reference clip duration (seconds) to be counted towards the above minimum.
DEFAULT_VOICE_BANK_MIN_REFERENCE_DURATION_SEC = 1.2
# Duration bounds (in seconds) used by is_usable_task_d_segment to decide whether a
# translation segment can be used as a reference for speaker-specific TTS cloning.
# Segments outside these bounds will be offered for *resegmentation* first before
# being rejected (Sprint 2 fix for silent drops, e.g. spk_0002 in task 20260425-023015).
DEFAULT_TASK_D_USABLE_MIN_DURATION_SEC = 1.0
DEFAULT_TASK_D_USABLE_MAX_DURATION_SEC = 6.0
# Preferred (tighter) bounds for "ideal" reference segments.
DEFAULT_TASK_D_PREFERRED_MIN_DURATION_SEC = 1.5
DEFAULT_TASK_D_PREFERRED_MAX_DURATION_SEC = 4.5
DEFAULT_RENDER_MIX_PROFILE = "preview"
DEFAULT_RENDER_DUCKING_MODE = "static"
DEFAULT_RENDER_OUTPUT_SAMPLE_RATE = 24_000
DEFAULT_RENDER_BACKGROUND_GAIN_DB = -8.0
DEFAULT_RENDER_WINDOW_DUCKING_DB = -3.0
DEFAULT_RENDER_PREVIEW_FORMAT = "wav"
# --- Rendering quality gate thresholds (Sprint 2) ---------------------------
# Central source of truth for the content_quality block reported by
# rendering/export.py. Keep these in lock-step with the golden metrics documented
# in docs/superpowers/reports/2026-04-25-dubbing-pipeline-optimization-plan.zh-CN.md.
#
# * coverage_ratio = placed_count / total_count  -> minimum for "deliverable".
# * failed_ratio / speaker_failed_ratio / intelligibility_failed_ratio are the
#   historical upper-bounds (reason = review_required above these).
# * speaker_similarity_lowband_ratio is the new Sprint-2 metric: percentage of
#   placed items with speaker_similarity < similarity_review_floor.
DEFAULT_QUALITY_GATE_COVERAGE_MIN = 0.98
DEFAULT_QUALITY_GATE_FAILED_MAX = 0.05
DEFAULT_QUALITY_GATE_SPEAKER_FAILED_MAX = 0.10
DEFAULT_QUALITY_GATE_INTELLIGIBILITY_FAILED_MAX = 0.10
# Sprint 2 new thresholds (matching the golden metrics in the plan doc):
DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_REVIEW_FLOOR = 0.5
DEFAULT_QUALITY_GATE_SPEAKER_SIMILARITY_LOWBAND_MAX = 0.30
DEFAULT_QUALITY_GATE_AVG_SPEAKER_SIMILARITY_MIN = 0.45
DEFAULT_QUALITY_GATE_SKIPPED_RATIO_BLOCK = 0.20
DEFAULT_DELIVERY_CONTAINER = "mp4"
DEFAULT_DELIVERY_VIDEO_CODEC = "copy"
DEFAULT_DELIVERY_AUDIO_CODEC = "aac"
DEFAULT_DELIVERY_AUDIO_BITRATE = "192k"
DEFAULT_DELIVERY_END_POLICY = "trim_audio_to_video"
DEFAULT_SILICONFLOW_BASE_URL = os.environ.get("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
DEFAULT_SILICONFLOW_MODEL = os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
DEFAULT_SUBTITLE_MODE = "none"
DEFAULT_SUBTITLE_SOURCE = "ocr"
DEFAULT_SUBTITLE_FONT_CJK = "Noto Sans CJK SC"
DEFAULT_SUBTITLE_FONT_LATIN = "Noto Sans"
DEFAULT_SUBTITLE_PRIMARY_COLOR = "#FFFFFF"
DEFAULT_SUBTITLE_OUTLINE_COLOR = "#000000"
DEFAULT_SUBTITLE_OUTLINE_WIDTH = 2.0
DEFAULT_SUBTITLE_SHADOW_DEPTH = 1.0
DEFAULT_SUBTITLE_PREVIEW_DURATION_SEC = 10
SUPPORTED_OUTPUT_FORMATS = {"wav", "mp3", "flac", "aac", "opus"}
OUTPUT_ROOT = Path("output")
CACHE_ROOT = Path(
    os.environ.get(
        "TRANSLIP_CACHE_DIR",
        Path.home() / ".cache" / "translip",
    )
)
