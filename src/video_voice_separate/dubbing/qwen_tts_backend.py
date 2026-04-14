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
    return max(48, min(256, int(round(target_sec * 24 + 24))))


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
        model_name: str = "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    ) -> None:
        self.requested_device = requested_device
        self.resolved_device = resolve_tts_device(requested_device)
        self.resolved_model = model_name
        self._prompt_cache: dict[tuple[Path, str, str], object] = {}

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
            backend_metadata={"reference_score": reference.score},
        )

    def _voice_clone_prompt(self, model, reference: ReferencePackage):
        cache_key = (
            reference.prepared_audio_path.resolve(),
            reference.text,
            self.resolved_model,
        )
        prompt = self._prompt_cache.get(cache_key)
        if prompt is None:
            prompt = model.create_voice_clone_prompt(
                ref_audio=str(reference.prepared_audio_path),
                ref_text=reference.text,
                x_vector_only_mode=False,
            )
            self._prompt_cache[cache_key] = prompt
        return prompt
