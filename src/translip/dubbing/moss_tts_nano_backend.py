from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import soundfile as sf

from ..config import CACHE_ROOT
from ..exceptions import DependencyError
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput

_DEFAULT_MODEL_NAME = "OpenMOSS-Team/MOSS-TTS-Nano-100M-ONNX"
_DEFAULT_CLI = "moss-tts-nano"
_DEFAULT_CPU_THREADS = 4
_DEFAULT_MAX_NEW_FRAMES = 375
_DEFAULT_VOICE_CLONE_MAX_TEXT_TOKENS = 75
_DEFAULT_SAMPLE_MODE = "fixed"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_cli_path() -> str:
    if cli_path := os.environ.get("MOSS_TTS_NANO_CLI"):
        return cli_path
    if cli_path := shutil.which(_DEFAULT_CLI):
        return cli_path
    local_cli = _repo_root() / ".dev-runtime" / "moss-tts-nano-venv" / "bin" / _DEFAULT_CLI
    if local_cli.exists():
        return str(local_cli)
    return _DEFAULT_CLI


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return int(value)


class MossTtsNanoOnnxBackend:
    backend_name = "moss-tts-nano-onnx"

    def __init__(self, *, requested_device: str) -> None:
        self.requested_device = requested_device
        self.resolved_device = "cpu"
        self.resolved_model = _DEFAULT_MODEL_NAME
        self.cli_path = _resolve_cli_path()
        self.model_dir = os.environ.get("MOSS_TTS_NANO_MODEL_DIR", str(CACHE_ROOT / "models"))
        self.cpu_threads = _env_int("MOSS_TTS_NANO_CPU_THREADS", _DEFAULT_CPU_THREADS)
        self.max_new_frames = _env_int("MOSS_TTS_NANO_MAX_NEW_FRAMES", _DEFAULT_MAX_NEW_FRAMES)
        self.voice_clone_max_text_tokens = _env_int(
            "MOSS_TTS_NANO_VOICE_CLONE_MAX_TEXT_TOKENS",
            _DEFAULT_VOICE_CLONE_MAX_TEXT_TOKENS,
        )
        self.sample_mode = os.environ.get("MOSS_TTS_NANO_SAMPLE_MODE", _DEFAULT_SAMPLE_MODE)

    def synthesize(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        command = self._build_command(
            reference_audio_path=reference.prepared_audio_path,
            text=segment.target_text,
            output_path=output_path,
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise DependencyError(
                "moss-tts-nano is required for the moss-tts-nano-onnx backend. "
                "Install OpenMOSS/MOSS-TTS-Nano and ensure the `moss-tts-nano` CLI is on PATH, "
                "or set MOSS_TTS_NANO_CLI to its executable path."
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise RuntimeError(f"MOSS-TTS-Nano ONNX synthesis failed for {segment.segment_id}: {detail}") from exc

        if not output_path.exists():
            raise RuntimeError(f"MOSS-TTS-Nano ONNX did not create output audio for {segment.segment_id}")

        info = sf.info(output_path)
        return SynthSegmentOutput(
            segment_id=segment.segment_id,
            audio_path=output_path,
            sample_rate=int(info.samplerate),
            generated_duration_sec=round(float(info.duration), 3),
            backend_metadata={
                "reference_score": reference.score,
                "cpu_threads": self.cpu_threads,
                "max_new_frames": self.max_new_frames,
                "sample_mode": self.sample_mode,
            },
        )

    def _build_command(self, *, reference_audio_path: Path, text: str, output_path: Path) -> list[str]:
        command = [
            self.cli_path,
            "generate",
            "--backend",
            "onnx",
            "--output",
            str(output_path),
            "--text",
            text,
            "--prompt-speech",
            str(reference_audio_path),
        ]
        if self.model_dir:
            command.extend(["--onnx-model-dir", self.model_dir])
        command.extend(
            [
                "--cpu-threads",
                str(self.cpu_threads),
                "--max-new-frames",
                str(self.max_new_frames),
                "--voice-clone-max-text-tokens",
                str(self.voice_clone_max_text_tokens),
                "--sample-mode",
                self.sample_mode,
            ]
        )
        return command
