from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
from shutil import copy2
from typing import Any, Callable


ProgressCallback = Callable[[float, str | None], None]


class ToolAdapter(ABC):
    @abstractmethod
    def validate_params(self, params: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def run(
        self,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        on_progress: ProgressCallback,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def first_input(input_dir: Path, stem: str | None = None) -> Path:
        base_dir = input_dir / stem if stem else input_dir
        return next(path for path in base_dir.rglob("*") if path.is_file())

    @staticmethod
    def copy_output(src: Path, output_dir: Path, filename: str | None = None) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / (filename or src.name)
        copy2(src, target)
        return target

    @staticmethod
    def write_json(output_path: Path, payload: dict[str, Any]) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output_path


from .separation import SeparationAdapter  # noqa: E402,F401
from .mixing import MixingAdapter  # noqa: E402,F401
from .transcription import TranscriptionAdapter  # noqa: E402,F401
from .transcript_correction import TranscriptCorrectionAdapter  # noqa: E402,F401
from .translation import TranslationAdapter  # noqa: E402,F401
from .tts import TtsAdapter  # noqa: E402,F401
from .probe import ProbeAdapter  # noqa: E402,F401
from .muxing import MuxingAdapter  # noqa: E402,F401
from .subtitle_detect import SubtitleDetectAdapter  # noqa: E402,F401
from .subtitle_erase import SubtitleEraseAdapter  # noqa: E402,F401
