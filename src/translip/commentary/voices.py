"""Built-in narrator voice library for video commentary.

Commentary narration must NOT borrow a character's voice from the source video.
This module provides a small set of built-in narrator timbres backed by the
qwen3tts ``Qwen3-TTS-12Hz-0.6B-CustomVoice`` model, which ships 9 named premium
speakers with natural-language style control. Each built-in voice maps to a named
CustomVoice speaker (plus an optional commentary-style instruction); it is rendered
once into a cached reference clip and then reused via voice cloning for cross-line
consistency. Callers may instead pass a user-supplied reference path, or the
literal ``"source"`` to opt back into borrowing from the source video.

Kept free of the server stack so the CLI / pipeline / atomic-tool paths can all
import it. Only :func:`translip.dubbing.qwen_tts_backend._load_qwen_model` is
reused (it carries the local-first HF loading fix); the rest is self-contained.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import CACHE_ROOT

# 0.6B CustomVoice checkpoint: named speakers + natural-language style control.
_CUSTOM_VOICE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"

# Explicit opt-in selector that reverts to borrowing the narrator timbre from the
# source video (the old default — now never implicit).
SOURCE_VOICE_ID = "source"

# ~10s of neutral commentary prose, read once per voice to bake the timbre into a
# reference clip (then cloned for every narration line).
_READING_TEXT = {
    "zh": (
        "在这部影片里，命运的齿轮悄然转动。一个看似平常的选择，"
        "却把所有人推向了无法回头的境地。接下来发生的一切，超出了所有人的预料。"
    ),
    "en": (
        "In this film, the wheels of fate begin to turn. A seemingly ordinary "
        "choice pushes everyone toward a point of no return, and what happens "
        "next is beyond anyone's expectations."
    ),
    "ja": (
        "この映画では、運命の歯車が静かに回り始める。"
        "何気ない選択が、すべての登場人物を引き返せない場所へと押し進めていく。"
        "この先に待っているのは、誰もが予想しなかった展開だ。"
    ),
    "ko": (
        "이 영화에서, 운명의 톱니바퀴가 조용히 돌아가기 시작한다. "
        "사소해 보였던 선택 하나가 모두를 돌이킬 수 없는 길로 이끌고, "
        "이어지는 이야기는 누구도 예상하지 못한 방향으로 흘러간다."
    ),
}


@dataclass(frozen=True, slots=True)
class NarratorVoice:
    id: str
    name_zh: str
    name_en: str
    gender: str  # "male" | "female"
    speaker: str  # CustomVoice named speaker (validated case-insensitively)
    instruct: str  # optional natural-language commentary-style instruction
    native_language: str  # ISO-639-1 hint for the speaker's native language (zh/en/ja/ko)
    description_zh: str = ""
    description_en: str = ""


BUILTIN_NARRATOR_VOICES: tuple[NarratorVoice, ...] = (
    NarratorVoice(
        id="narrator-male-calm",
        name_zh="沉稳男声",
        name_en="Calm Male",
        gender="male",
        speaker="Uncle_Fu",  # seasoned male voice, mellow timbre
        instruct="语气沉稳、有磁性，娓娓道来、略带悬念的影视解说口吻。",
        native_language="zh",
        description_zh="醇厚成熟的男声，适合悬疑、剧情、纪录片解说。",
        description_en="Mellow, seasoned male voice — fits drama, mystery and documentary.",
    ),
    NarratorVoice(
        id="narrator-female-bright",
        name_zh="知性女声",
        name_en="Bright Female",
        gender="female",
        speaker="Vivian",  # bright young female voice
        instruct="语气清亮、知性，节奏自然、富有代入感的影视解说口吻。",
        native_language="zh",
        description_zh="明亮通透的年轻女声，知性而有代入感。",
        description_en="Bright, articulate young female voice with strong narrative presence.",
    ),
    NarratorVoice(
        id="narrator-female-warm",
        name_zh="温柔女声",
        name_en="Warm Female",
        gender="female",
        speaker="Serena",  # warm, gentle young female voice
        instruct="语气温柔治愈、娓娓道来，节奏舒缓而带有情感色彩的影视解说口吻。",
        native_language="zh",
        description_zh="温柔治愈的年轻女声，适合情感、爱情、治愈系内容。",
        description_en="Warm, gentle young female voice — great for romance and feel-good stories.",
    ),
    NarratorVoice(
        id="narrator-male-beijing",
        name_zh="京片儿少年",
        name_en="Beijing Youth",
        gender="male",
        speaker="Dylan",  # youthful Beijing male voice
        instruct="带北京口音的年轻男声，语气活泼、随性，像老炮儿一样讲故事的影视解说口吻。",
        native_language="zh",
        description_zh="带京味儿的年轻男声，幽默接地气，适合喜剧、市井题材。",
        description_en="Youthful Beijing male voice — lively and casual, great for comedy.",
    ),
    NarratorVoice(
        id="narrator-male-sichuan",
        name_zh="川味儿大哥",
        name_en="Sichuan Bro",
        gender="male",
        speaker="Eric",  # lively Chengdu male voice
        instruct="带成都口音的男声，语气活泼幽默、富有生活气息的影视解说口吻。",
        native_language="zh",
        description_zh="带四川口音的活泼男声，自带烟火气，适合搞笑、地方风味内容。",
        description_en="Lively Chengdu male voice — playful flair, perfect for comedic recaps.",
    ),
    NarratorVoice(
        id="narrator-en-male-dynamic",
        name_zh="英文磁性男声",
        name_en="Dynamic English Male",
        gender="male",
        speaker="Ryan",  # dynamic male with rhythm
        instruct="A dynamic, well-paced English male voice, like a film recap narrator — rhythmic and engaging.",
        native_language="en",
        description_zh="富有节奏感的英文男声，适合英文解说、影评、纪录片。",
        description_en="Dynamic English male voice with strong rhythm — ideal for recaps and docs.",
    ),
    NarratorVoice(
        id="narrator-en-male-sunny",
        name_zh="英文阳光男声",
        name_en="Sunny American Male",
        gender="male",
        speaker="Aiden",  # sunny American male voice
        instruct="A sunny, friendly American male voice with a warm narrative tone for film commentary.",
        native_language="en",
        description_zh="阳光友好的美式男声，亲和力强，适合英文 vlog、轻松题材。",
        description_en="Sunny, friendly American male voice — approachable and warm.",
    ),
    NarratorVoice(
        id="narrator-ja-female",
        name_zh="日语少女音",
        name_en="Japanese Female",
        gender="female",
        speaker="Ono_Anna",  # playful japanese female voice
        instruct="明るく親しみやすい日本語女性ナレーション。映画やアニメの解説に合う、自然なテンポで語る口調。",
        native_language="ja",
        description_zh="活泼亲切的日语女声，适合日漫、日剧解说。",
        description_en="Playful Japanese female voice — perfect for anime and J-drama recaps.",
    ),
    NarratorVoice(
        id="narrator-ko-female",
        name_zh="韩语温柔女声",
        name_en="Korean Female",
        gender="female",
        speaker="Sohee",  # warm korean female voice
        instruct="따뜻하고 부드러운 한국어 여성 내레이션. 영화 해설에 어울리는 자연스러운 톤.",
        native_language="ko",
        description_zh="温暖柔和的韩语女声，适合韩剧、爱情题材解说。",
        description_en="Warm, gentle Korean female voice — fits K-drama and romance.",
    ),
)

DEFAULT_NARRATOR_VOICE = "narrator-male-calm"

_VOICES_BY_ID = {voice.id: voice for voice in BUILTIN_NARRATOR_VOICES}


def list_narrator_voices() -> list[NarratorVoice]:
    return list(BUILTIN_NARRATOR_VOICES)


def get_narrator_voice(voice_id: str) -> NarratorVoice | None:
    return _VOICES_BY_ID.get(voice_id)


def narrator_voices_cache_dir() -> Path:
    return CACHE_ROOT / "narrator_voices"


def _lang_key(language: str) -> str:
    key = (language or "zh").lower()
    if key.startswith("ja"):
        return "ja"
    if key.startswith("ko"):
        return "ko"
    if key.startswith("en"):
        return "en"
    return "zh"


def _reading_text(language: str) -> str:
    return _READING_TEXT[_lang_key(language)]


def _language_name(language: str) -> str:
    key = (language or "zh").lower()
    if key.startswith("zh"):
        return "Chinese"
    if key.startswith("ja"):
        return "Japanese"
    if key.startswith("ko"):
        return "Korean"
    if key.startswith("en"):
        return "English"
    return "Auto"


def _reference_path(voice_id: str, language: str) -> Path:
    return narrator_voices_cache_dir() / f"{voice_id}.{_lang_key(language)}.wav"


def _normalize_waveform(waveform):
    import numpy as np

    array = np.asarray(waveform, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=0 if array.shape[0] <= array.shape[1] else 1)
    return np.squeeze(array).astype(np.float32)


def _generate_voice_reference(voice: NarratorVoice, language: str, out_path: Path) -> Path:
    """Render the named CustomVoice speaker into a reference WAV (cloned later)."""
    import soundfile as sf

    from ..dubbing.qwen_tts_backend import _load_qwen_model

    # CustomVoice generation can emit NaN sampling probabilities on MPS/float16
    # (same failure mode the xvec clone path guards against), so render this
    # one-time, cached reference on CPU for numerical stability.
    device = "cpu"
    try:
        model = _load_qwen_model(_CUSTOM_VOICE_MODEL, device)
    except Exception as exc:  # model missing / download blocked / load failure
        raise RuntimeError(
            f"Could not load the CustomVoice model '{_CUSTOM_VOICE_MODEL}' needed to build "
            f"built-in narrator voice '{voice.id}': {exc}. Set HF_ENDPOINT=https://hf-mirror.com "
            f"to download it, or pass a narrator reference audio, or use voice 'source'."
        ) from exc
    wavs, sample_rate = model.generate_custom_voice(
        text=_reading_text(language),
        speaker=voice.speaker,
        language=_language_name(language),
        instruct=voice.instruct or None,
        non_streaming_mode=True,
        max_new_tokens=512,
    )
    if not wavs:
        raise RuntimeError(f"CustomVoice returned no audio for narrator voice '{voice.id}'.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, _normalize_waveform(wavs[0]), int(sample_rate))
    return out_path


def borrow_from_source(*, source_path: Path, work_dir: Path, source_duration: float) -> Path:
    """Borrow a ~8s clean speech slice from the source as the narrator timbre.

    Legacy fallback, now only reached via the explicit ``"source"`` selector.
    """
    from ..utils.ffmpeg import ffmpeg_binary

    work_dir.mkdir(parents=True, exist_ok=True)
    reference = work_dir / "narrator_ref.wav"
    start = max(0.0, min(source_duration * 0.25, max(0.0, source_duration - 8.0)))
    result = subprocess.run(
        [
            ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-ss", f"{start:.3f}", "-i", str(source_path), "-t", "8",
            "-vn", "-ac", "1", "-ar", "24000", str(reference),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed borrowing narrator reference (exit {result.returncode}): "
            f"{(result.stderr or '').strip()[-400:]}"
        )
    return reference


def resolve_narrator_reference(
    voice: str | None,
    *,
    language: str,
    work_dir: Path,
    source_path: Path,
    source_duration: float,
) -> Path:
    """Resolve a narrator-voice selector to a reference WAV used for cloning.

    Selector semantics:
      - ``None`` / empty   -> :data:`DEFAULT_NARRATOR_VOICE`
      - built-in voice id  -> cached CustomVoice reference (rendered once, reused)
      - ``"source"``       -> borrow from the source video (explicit opt-in)
      - an existing path   -> used as-is (user-supplied narrator reference)
    """
    selector = (voice or "").strip() or DEFAULT_NARRATOR_VOICE

    if selector == SOURCE_VOICE_ID:
        return borrow_from_source(
            source_path=source_path, work_dir=work_dir, source_duration=source_duration
        )

    builtin = get_narrator_voice(selector)
    if builtin is not None:
        cache_path = _reference_path(builtin.id, language)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path
        return _generate_voice_reference(builtin, language, cache_path)

    candidate = Path(selector).expanduser()
    if candidate.exists():
        return candidate

    raise ValueError(
        f"Unknown narrator voice {selector!r}. Use a built-in id "
        f"({', '.join(v.id for v in BUILTIN_NARRATOR_VOICES)}), {SOURCE_VOICE_ID!r}, "
        f"or a path to a reference audio file."
    )


__all__ = [
    "BUILTIN_NARRATOR_VOICES",
    "DEFAULT_NARRATOR_VOICE",
    "SOURCE_VOICE_ID",
    "NarratorVoice",
    "borrow_from_source",
    "get_narrator_voice",
    "list_narrator_voices",
    "narrator_voices_cache_dir",
    "resolve_narrator_reference",
]
