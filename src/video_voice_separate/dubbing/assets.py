from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..exceptions import BackendUnavailableError, DependencyError

F5_TTS_CHECKPOINT_URL = (
    "https://huggingface.co/SWivid/F5-TTS/resolve/main/"
    "F5TTS_v1_Base/model_1250000.safetensors"
)
VOCOS_CONFIG_URL = "https://huggingface.co/charactr/vocos-mel-24khz/resolve/main/config.yaml"
VOCOS_WEIGHTS_URL = "https://huggingface.co/charactr/vocos-mel-24khz/resolve/main/pytorch_model.bin"


@dataclass(frozen=True, slots=True)
class F5TTSAssets:
    checkpoint_path: Path
    vocoder_dir: Path


def ensure_f5tts_assets(cache_root: Path, model_name: str) -> F5TTSAssets:
    if model_name != "F5TTS_v1_Base":
        raise BackendUnavailableError(f"Unsupported F5 model preset: {model_name}")

    checkpoint_path = cache_root / "assets" / model_name / "model_1250000.safetensors"
    vocoder_dir = cache_root / "assets" / "vocos-mel-24khz"

    _download_with_curl(F5_TTS_CHECKPOINT_URL, checkpoint_path)
    _download_with_curl(VOCOS_CONFIG_URL, vocoder_dir / "config.yaml")
    _download_with_curl(VOCOS_WEIGHTS_URL, vocoder_dir / "pytorch_model.bin")

    return F5TTSAssets(
        checkpoint_path=checkpoint_path,
        vocoder_dir=vocoder_dir,
    )


def _download_with_curl(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return

    curl_path = shutil.which("curl")
    if curl_path is None:
        raise DependencyError("curl is required to download F5-TTS model assets")

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_suffix(destination.suffix + ".part")
    command = [
        curl_path,
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "5",
        "--retry-delay",
        "2",
        "--retry-all-errors",
        "--continue-at",
        "-",
        "--output",
        str(partial_path),
        url,
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - network/runtime dependent
        stderr = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise BackendUnavailableError(f"Failed to download model asset {destination.name}: {stderr}") from exc

    if not partial_path.exists() or partial_path.stat().st_size <= 0:
        raise BackendUnavailableError(f"Downloaded asset is empty: {destination.name}")

    partial_path.replace(destination)
