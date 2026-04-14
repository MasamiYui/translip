from __future__ import annotations

import inspect
import logging
import warnings
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.states import set_state

from ..config import CACHE_ROOT
from ..exceptions import BackendUnavailableError
from ..types import DialogueSeparationOutput
from .base import DialogueSeparator

logger = logging.getLogger(__name__)

CDX23_RELEASE_BASE = (
    "https://github.com/ZFTurbo/MVSEP-CDX23-Cinematic-Sound-Demixing/"
    "releases/download/v.1.0.0"
)
CDX23_BALANCED_WEIGHTS = ("97d170e1-dbb4db15.th",)
CDX23_HIGH_QUALITY_WEIGHTS = (
    "97d170e1-a778de4a.th",
    "97d170e1-dbb4db15.th",
    "97d170e1-e41a5468.th",
)


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class Cdx23DialogueSeparator(DialogueSeparator):
    def __init__(
        self,
        *,
        quality: str = "balanced",
        device: str = "auto",
        cache_dir: Path | None = None,
    ) -> None:
        self.quality = quality
        self.device = _resolve_device(device)
        self.cache_dir = (cache_dir or CACHE_ROOT / "models" / "cdx23").expanduser().resolve()
        self._models = None

    @property
    def weight_names(self) -> tuple[str, ...]:
        if self.quality == "high":
            return CDX23_HIGH_QUALITY_WEIGHTS
        return CDX23_BALANCED_WEIGHTS

    def ensure_weights(self, force: bool = False) -> list[Path]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []
        for weight_name in self.weight_names:
            destination = self.cache_dir / weight_name
            if force and destination.exists():
                destination.unlink()
            if not destination.exists():
                url = f"{CDX23_RELEASE_BASE}/{weight_name}"
                logger.info("Downloading CDX23 checkpoint %s", weight_name)
                torch.hub.download_url_to_file(url, str(destination))
            downloaded.append(destination)
        return downloaded

    def _load_models(self) -> list[torch.nn.Module]:
        if self._models is not None:
            return self._models

        model_paths = self.ensure_weights()
        models: list[torch.nn.Module] = []
        try:
            for model_path in model_paths:
                model = self._load_model_compat(model_path)
                model.to(self.device)
                model.eval()
                models.append(model)
        except Exception as exc:
            raise BackendUnavailableError(f"Failed to load CDX23 checkpoints: {exc}") from exc
        self._models = models
        return models

    def _load_model_compat(self, model_path: Path) -> torch.nn.Module:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                package = torch.load(str(model_path), map_location="cpu", weights_only=False)
            except TypeError:
                package = torch.load(str(model_path), map_location="cpu")

        klass = package["klass"]
        args = package["args"]
        kwargs = dict(package["kwargs"])

        sig = inspect.signature(klass)
        for key in list(kwargs):
            if key not in sig.parameters:
                del kwargs[key]
        model = klass(*args, **kwargs)
        set_state(model, package["state"])
        return model

    def _load_audio(self, wav_path: Path) -> tuple[np.ndarray, int]:
        audio, sample_rate = librosa.load(wav_path, sr=44_100, mono=False)
        if audio.ndim == 1:
            audio = np.stack([audio, audio], axis=0)
        return audio, sample_rate

    def separate(self, wav_path: Path, work_dir: Path) -> DialogueSeparationOutput:
        models = self._load_models()
        audio, sample_rate = self._load_audio(wav_path)
        audio_tensor = torch.from_numpy(np.expand_dims(audio, axis=0)).float().to(self.device)

        outputs = []
        try:
            with torch.no_grad():
                for model in models:
                    prediction = apply_model(model, audio_tensor, shifts=1, overlap=0.8)[0]
                    outputs.append(prediction.cpu().numpy())
        except Exception as exc:
            raise BackendUnavailableError(f"CDX23 inference failed: {exc}") from exc

        averaged = np.mean(np.stack(outputs, axis=0), axis=0)
        music = averaged[0].T
        effect = averaged[1].T
        dialog = averaged[2].T
        background = music + effect

        output_dir = work_dir / "cdx23"
        output_dir.mkdir(parents=True, exist_ok=True)
        dialog_path = output_dir / "dialog.wav"
        music_path = output_dir / "music.wav"
        effect_path = output_dir / "effect.wav"
        background_path = output_dir / "background.wav"

        for path, stem in (
            (dialog_path, dialog),
            (music_path, music),
            (effect_path, effect),
            (background_path, background),
        ):
            sf.write(path, stem, sample_rate, subtype="FLOAT")

        return DialogueSeparationOutput(
            dialog_path=dialog_path,
            background_path=background_path,
            backend_name="cdx23",
            intermediate_paths={
                "dialog": dialog_path,
                "music": music_path,
                "effect": effect_path,
                "background": background_path,
            },
        )
