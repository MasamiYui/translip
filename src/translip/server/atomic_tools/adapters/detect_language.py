"""Spoken-language identification (LID) atomic tool.

Answers "what language is being spoken in this video?" without a full
transcription. Wraps faster-whisper's language-detection head (see
``transcription.asr.detect_audio_language``) and returns the top language plus
the ranked candidate list, so a near-tie (e.g. bilingual content) is visible.

This is the *spoken* language only. Subtitle language is a separate question —
burned-in subtitles go through ``subtitle-detect`` (OCR + script heuristic) and
embedded subtitle/audio track language tags through ``probe``.
"""

from __future__ import annotations

from ....transcription.asr import detect_audio_language
from ..registry import ToolSpec, register_tool
from ..schemas import DetectLanguageToolRequest
from . import ToolAdapter

# Whisper exposes ~100 language codes but no display names; curate the ones most
# likely to matter and fall back to the upper-cased ISO code for the long tail.
_LANGUAGE_NAMES_ZH: dict[str, str] = {
    "zh": "中文", "en": "英语", "ja": "日语", "ko": "韩语", "yue": "粤语",
    "fr": "法语", "de": "德语", "es": "西班牙语", "pt": "葡萄牙语", "it": "意大利语",
    "ru": "俄语", "ar": "阿拉伯语", "hi": "印地语", "th": "泰语", "vi": "越南语",
    "id": "印尼语", "ms": "马来语", "tr": "土耳其语", "nl": "荷兰语", "pl": "波兰语",
    "uk": "乌克兰语", "fa": "波斯语", "he": "希伯来语", "sv": "瑞典语",
}

# Below this top-1 probability the guess is shaky (short/noisy/music-heavy or
# genuinely mixed) — surface it so callers don't over-trust a coin-flip.
_CONFIDENCE_THRESHOLD = 0.5


def _language_name(code: str) -> str:
    return _LANGUAGE_NAMES_ZH.get(code, code.upper())


class DetectLanguageAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return DetectLanguageToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        output_dir.mkdir(parents=True, exist_ok=True)

        on_progress(20.0, "detecting")
        language, probability, candidates, metadata = detect_audio_language(
            input_file,
            model_name=params.get("model", "medium"),
            requested_device="auto",
            windows=int(params.get("windows", 3)),
        )
        on_progress(90.0, "finalizing")

        payload = {
            "language": language,
            "language_name": _language_name(language),
            "confidence": round(probability, 4),
            "is_confident": probability >= _CONFIDENCE_THRESHOLD,
            "candidates": [
                {"language": code, "language_name": _language_name(code), "confidence": round(prob, 4)}
                for code, prob in candidates[:5]
            ],
            "windows_analyzed": metadata["windows_analyzed"],
            "backend": metadata["asr_backend"],
            "model": metadata["asr_model"],
        }
        self.write_json(output_dir / "language.json", payload)
        return payload


register_tool(
    ToolSpec(
        tool_id="detect-language",
        name_zh="语种识别",
        name_en="Language Detection",
        description_zh="识别音/视频中所说语言（不转写），返回语种及置信度与候选列表",
        description_en="Identify the spoken language of audio/video (no transcription) with confidence and ranked candidates",
        category="speech",
        icon="Globe",
        accept_formats=[".mp4", ".mkv", ".mov", ".avi", ".wav", ".mp3", ".flac", ".m4a", ".ogg", ".webm", ".ts"],
        max_file_size_mb=4096,
        max_files=1,
    ),
    DetectLanguageAdapter,
)
