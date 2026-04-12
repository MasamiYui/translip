from __future__ import annotations

import os
import zlib
from functools import lru_cache
from pathlib import Path

import soundfile as sf

from ..config import CACHE_ROOT
from .assets import ensure_f5tts_assets
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput, resolve_tts_device


def _silent_show_info(*_args, **_kwargs) -> None:
    return None


@lru_cache(maxsize=4)
def _load_client(
    model_name: str,
    device: str,
    cache_dir: str,
    checkpoint_path: str,
    vocoder_dir: str,
):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from f5_tts.api import F5TTS

    return F5TTS(
        model=model_name,
        ckpt_file=checkpoint_path,
        vocoder_local_path=vocoder_dir,
        device=device,
        hf_cache_dir=cache_dir,
    )


class F5TTSBackend:
    backend_name = "f5tts"

    def __init__(
        self,
        *,
        requested_device: str,
        model_name: str = "F5TTS_v1_Base",
    ) -> None:
        self.requested_device = requested_device
        self.resolved_device = resolve_tts_device(requested_device)
        self.resolved_model = model_name
        self.cache_dir = str(CACHE_ROOT / "f5-tts")
        self._assets = None

    @property
    def client(self):
        assets = self._ensure_assets()
        return _load_client(
            self.resolved_model,
            self.resolved_device,
            self.cache_dir,
            str(assets.checkpoint_path),
            str(assets.vocoder_dir),
        )

    def _ensure_assets(self):
        if self._assets is None:
            self._assets = ensure_f5tts_assets(Path(self.cache_dir), self.resolved_model)
        return self._assets

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
        assets = self._ensure_assets()
        client = _load_client(
            self.resolved_model,
            device,
            self.cache_dir,
            str(assets.checkpoint_path),
            str(assets.vocoder_dir),
        )
        target_duration_sec = max(
            float(segment.duration_budget_sec or segment.source_duration_sec or 0.0),
            0.8,
        )
        client.infer(
            ref_file=str(reference.prepared_audio_path),
            ref_text=reference.text,
            gen_text=segment.target_text,
            show_info=_silent_show_info,
            progress=None,
            fix_duration=round(reference.duration_sec + target_duration_sec, 3),
            remove_silence=False,
            file_wave=str(output_path),
            seed=zlib.crc32(segment.segment_id.encode("utf-8")),
        )
        info = sf.info(output_path)
        return SynthSegmentOutput(
            segment_id=segment.segment_id,
            audio_path=output_path,
            sample_rate=info.samplerate,
            generated_duration_sec=round(info.duration, 3),
            backend_metadata={"reference_score": reference.score},
        )
