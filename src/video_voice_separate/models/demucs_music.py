from __future__ import annotations

import logging
import platform
import subprocess
import sys
from pathlib import Path

from ..exceptions import BackendUnavailableError
from ..types import MusicSeparationOutput
from .base import MusicSeparator

logger = logging.getLogger(__name__)


def _resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested

    try:
        import torch
    except ImportError:
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"

    return "cpu"


class DemucsMusicSeparator(MusicSeparator):
    def __init__(
        self,
        model: str = "htdemucs_ft",
        device: str = "auto",
        segment: int = 7,
        shifts: int = 1,
    ) -> None:
        self.model = model
        self.device = device
        self.segment = segment
        self.shifts = shifts

    def _run(self, wav_path: Path, output_root: Path, device: str) -> None:
        command = [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            self.model,
            "--two-stems",
            "vocals",
            "--segment",
            str(int(self.segment)),
            "--shifts",
            str(self.shifts),
            "-o",
            str(output_root),
            "-d",
            device,
            str(wav_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise BackendUnavailableError(result.stderr.strip() or "Demucs failed")

    def separate(self, wav_path: Path, work_dir: Path) -> MusicSeparationOutput:
        output_root = work_dir / "demucs"
        output_root.mkdir(parents=True, exist_ok=True)

        device = _resolve_device(self.device)
        try:
            self._run(wav_path, output_root, device)
        except BackendUnavailableError:
            if device == "cpu":
                raise
            logger.warning("Demucs failed on device '%s'; retrying on CPU.", device)
            self._run(wav_path, output_root, "cpu")

        stem_dir = output_root / self.model / wav_path.stem
        voice_path = stem_dir / "vocals.wav"
        background_path = stem_dir / "no_vocals.wav"
        if not voice_path.exists() or not background_path.exists():
            raise BackendUnavailableError(
                f"Demucs finished without expected outputs in {stem_dir}"
            )

        return MusicSeparationOutput(
            voice_path=voice_path,
            background_path=background_path,
            backend_name="demucs",
            intermediate_paths={
                "vocals": voice_path,
                "no_vocals": background_path,
            },
        )
