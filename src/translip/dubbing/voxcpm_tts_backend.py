from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ..exceptions import DependencyError
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput, resolve_tts_device

_DEFAULT_MODEL_NAME = "openbmb/VoxCPM2"
_DEFAULT_CFG_VALUE = 2.0
_DEFAULT_INFERENCE_TIMESTEPS = 10
_DEFAULT_RETRY_BADCASE_MAX_TIMES = 3

logger = logging.getLogger(__name__)


def _load_voxcpm_package():
    try:
        from voxcpm import VoxCPM
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised in integration
        raise DependencyError(
            "voxcpm is required for the voxcpm2 backend. Install project dependencies again to enable VoxCPM2."
        ) from exc
    return VoxCPM


@lru_cache(maxsize=2)
def _load_voxcpm_model(model_name: str, device: str, optimize: bool, load_denoiser: bool):
    model_cls = _load_voxcpm_package()
    kwargs = {
        "device": device,
        "optimize": optimize,
        "load_denoiser": load_denoiser,
    }
    prefer_local = _env_bool("VOXCPM_PREFER_LOCAL_FILES", True)
    allow_download = _env_bool("VOXCPM_ALLOW_DOWNLOAD", True)
    if prefer_local:
        try:
            return _from_pretrained(
                model_cls,
                model_name,
                kwargs=kwargs,
                local_files_only=True,
            )
        except Exception as exc:
            if not allow_download:
                raise
            logger.warning("Failed to load VoxCPM2 from local cache, retrying with download enabled: %s", exc)
    return _from_pretrained(
        model_cls,
        model_name,
        kwargs=kwargs,
        local_files_only=False,
    )


def _from_pretrained(
    model_cls,
    model_name: str,
    *,
    kwargs: dict[str, object],
    local_files_only: bool,
):
    call_kwargs = {
        **kwargs,
        "local_files_only": local_files_only,
    }
    try:
        return model_cls.from_pretrained(model_name, **call_kwargs)
    except TypeError:
        # Older package builds used enable_denoiser in the constructor path.
        compat_kwargs = dict(call_kwargs)
        compat_kwargs["enable_denoiser"] = compat_kwargs.pop("load_denoiser")
        return model_cls.from_pretrained(model_name, **compat_kwargs)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _normalize_waveform(waveform) -> np.ndarray:
    array = np.asarray(waveform, dtype=np.float32)
    if array.ndim == 2:
        array = array.mean(axis=0 if array.shape[0] <= array.shape[1] else 1)
    return np.squeeze(array).astype(np.float32)


def _model_sample_rate(model) -> int:
    tts_model = getattr(model, "tts_model", None)
    return int(getattr(tts_model, "sample_rate", 48_000))


class VoxCPMTTSBackend:
    backend_name = "voxcpm2"

    def __init__(
        self,
        *,
        requested_device: str,
        model_name: str | None = None,
        optimize: bool | None = None,
        load_denoiser: bool | None = None,
    ) -> None:
        self.requested_device = requested_device
        self.resolved_device = resolve_tts_device(requested_device)
        self.backend_metadata_device_reason: str | None = None
        if self.resolved_device == "mps" and not _env_bool("VOXCPM_ALLOW_MPS", False):
            self.resolved_device = "cpu"
            self.backend_metadata_device_reason = "mps_disabled_for_voxcpm2"
        self.resolved_model = model_name or os.environ.get("VOXCPM_MODEL") or _DEFAULT_MODEL_NAME
        default_optimize = self.resolved_device == "cuda"
        self.optimize = _env_bool("VOXCPM_OPTIMIZE", default_optimize) if optimize is None else optimize
        self.load_denoiser = (
            _env_bool("VOXCPM_LOAD_DENOISER", False) if load_denoiser is None else load_denoiser
        )
        self.cfg_value = _env_float("VOXCPM_CFG_VALUE", _DEFAULT_CFG_VALUE)
        self.inference_timesteps = _env_int("VOXCPM_INFERENCE_TIMESTEPS", _DEFAULT_INFERENCE_TIMESTEPS)
        self.retry_badcase = _env_bool("VOXCPM_RETRY_BADCASE", True)
        self.retry_badcase_max_times = _env_int(
            "VOXCPM_RETRY_BADCASE_MAX_TIMES",
            _DEFAULT_RETRY_BADCASE_MAX_TIMES,
        )

    @property
    def model(self):
        return _load_voxcpm_model(
            self.resolved_model,
            self.resolved_device,
            self.optimize,
            self.load_denoiser,
        )

    def synthesize(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model = self.model
        generate_kwargs, clone_mode = self._generate_kwargs(reference=reference, segment=segment)
        generated = model.generate(**generate_kwargs)
        sample_rate = _model_sample_rate(model)
        if isinstance(generated, tuple) and len(generated) == 2:
            generated, sample_rate = generated
            sample_rate = int(sample_rate)
        waveform = _normalize_waveform(generated)
        sf.write(output_path, waveform, sample_rate, format="WAV")
        return SynthSegmentOutput(
            segment_id=segment.segment_id,
            audio_path=output_path,
            sample_rate=sample_rate,
            generated_duration_sec=round(float(len(waveform) / sample_rate), 3),
            backend_metadata={
                "reference_score": reference.score,
                "clone_mode": clone_mode,
                "cfg_value": self.cfg_value,
                "inference_timesteps": self.inference_timesteps,
                "device_reason": self.backend_metadata_device_reason,
            },
        )

    def _generate_kwargs(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
    ) -> tuple[dict[str, object], str]:
        reference_path = str(reference.prepared_audio_path)
        prompt_text = reference.text.strip()
        kwargs: dict[str, object] = {
            "text": segment.target_text,
            "reference_wav_path": reference_path,
            "cfg_value": self.cfg_value,
            "inference_timesteps": self.inference_timesteps,
            "normalize": True,
            "denoise": self.load_denoiser,
            "retry_badcase": self.retry_badcase,
            "retry_badcase_max_times": self.retry_badcase_max_times,
        }
        if prompt_text:
            kwargs["prompt_wav_path"] = reference_path
            kwargs["prompt_text"] = prompt_text
            return kwargs, "ultimate"
        return kwargs, "reference"
