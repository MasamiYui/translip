from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from ..exceptions import DependencyError
from ..translation.backend import canonical_language_code
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput, resolve_tts_device

_LANGUAGE_NAMES = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
}

_DEFAULT_MODEL_NAME = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
_DEFAULT_CLONE_MODE = "icl"
_CLONE_MODES = {"icl", "xvec"}
_QWEN_AUDIO_TOKENS_PER_SEC = 12
_QWEN_TOKEN_HEADROOM_RATIO = 1.25
_QWEN_MIN_NEW_TOKENS = 12
_QWEN_MAX_NEW_TOKENS = 256


def _load_qwen_package():
    try:
        from qwen_tts import Qwen3TTSModel
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in integration
        raise DependencyError(
            "qwen-tts is required for Task D. Install project dependencies again to enable qwen3tts."
        ) from exc
    return Qwen3TTSModel


@lru_cache(maxsize=4)
def _load_qwen_model(model_name: str, device: str):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    model_cls = _load_qwen_package()
    kwargs = {
        "device_map": _device_map_for(device),
        "dtype": _dtype_for(device),
    }
    attn_impl = _attn_implementation_for(device)
    if attn_impl is not None:
        kwargs["attn_implementation"] = attn_impl
    return model_cls.from_pretrained(model_name, **kwargs)


def _device_map_for(device: str) -> str:
    if device == "cuda":
        return "cuda:0"
    if device == "mps":
        return "mps"
    return "cpu"


def _dtype_for(device: str):
    if device == "cuda":
        return torch.bfloat16
    if device == "mps":
        return torch.float16
    return torch.float32


def _attn_implementation_for(device: str) -> str | None:
    if device == "cuda":
        return "flash_attention_2"
    return None


def _language_name(language: str) -> str:
    canonical = canonical_language_code(language)
    return _LANGUAGE_NAMES.get(canonical, "Auto")


def _max_new_tokens_for(segment: SynthSegmentInput) -> int:
    target_sec = max(
        float(segment.duration_budget_sec or 0.0),
        float(segment.source_duration_sec),
        0.8,
    )
    calibrated_budget = target_sec * _QWEN_AUDIO_TOKENS_PER_SEC * _QWEN_TOKEN_HEADROOM_RATIO
    return max(_QWEN_MIN_NEW_TOKENS, min(_QWEN_MAX_NEW_TOKENS, int(round(calibrated_budget))))


def _normalize_waveform(waveform) -> np.ndarray:
    array = np.asarray(waveform, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=0 if array.shape[0] <= array.shape[1] else 1)
    return np.squeeze(array).astype(np.float32)


class QwenTTSBackend:
    backend_name = "qwen3tts"

    def __init__(
        self,
        *,
        requested_device: str,
        model_name: str | None = None,
        clone_mode: str | None = None,
    ) -> None:
        self.requested_device = requested_device
        self.resolved_device = resolve_tts_device(requested_device)
        self.resolved_model = model_name or os.environ.get("QWEN_TTS_MODEL") or _DEFAULT_MODEL_NAME
        self.clone_mode = _normalize_clone_mode(clone_mode or os.environ.get("QWEN_TTS_CLONE_MODE"))
        if self.clone_mode == "xvec" and self.resolved_device == "mps":
            # The x-vector-only path can produce NaN sampling probabilities on MPS/float16.
            self.resolved_device = "cpu"
        self._prompt_cache: dict[tuple[Path, str, str, str], object] = {}

    @property
    def model(self):
        return _load_qwen_model(self.resolved_model, self.resolved_device)

    def synthesize(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return self._infer(reference=reference, segment=segment, output_path=output_path, device=self.resolved_device)
        except RuntimeError:
            if self.resolved_device != "mps":
                raise
            self.resolved_device = "cpu"
            return self._infer(reference=reference, segment=segment, output_path=output_path, device="cpu")

    def _infer(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
        device: str,
    ) -> SynthSegmentOutput:
        if device != self.resolved_device:
            self.resolved_device = device
        model = self.model
        prompt = self._voice_clone_prompt(model, reference)
        wavs, sample_rate = model.generate_voice_clone(
            text=segment.target_text,
            language=_language_name(segment.target_lang),
            voice_clone_prompt=prompt,
            non_streaming_mode=True,
            max_new_tokens=_max_new_tokens_for(segment),
        )
        if not wavs:
            raise RuntimeError(f"Qwen3-TTS returned no waveform for segment {segment.segment_id}")
        waveform = _normalize_waveform(wavs[0])
        sf.write(output_path, waveform, sample_rate)
        return SynthSegmentOutput(
            segment_id=segment.segment_id,
            audio_path=output_path,
            sample_rate=int(sample_rate),
            generated_duration_sec=round(float(len(waveform) / sample_rate), 3),
            backend_metadata={"reference_score": reference.score, "clone_mode": self.clone_mode},
        )

    def _voice_clone_prompt(self, model, reference: ReferencePackage):
        cache_key = (
            reference.prepared_audio_path.resolve(),
            reference.text,
            self.resolved_model,
            self.clone_mode,
        )
        prompt = self._prompt_cache.get(cache_key)
        if prompt is None:
            prompt = model.create_voice_clone_prompt(
                ref_audio=str(reference.prepared_audio_path),
                ref_text=None if self.clone_mode == "xvec" else reference.text,
                x_vector_only_mode=self.clone_mode == "xvec",
            )
            self._prompt_cache[cache_key] = prompt
        return prompt


def _normalize_clone_mode(value: str | None) -> str:
    mode = (value or _DEFAULT_CLONE_MODE).strip().lower()
    if mode in {"x-vector", "x_vector", "x-vector-only", "x_vector_only"}:
        mode = "xvec"
    if mode not in _CLONE_MODES:
        raise ValueError(f"Unsupported Qwen3-TTS clone mode: {value}")
    return mode
