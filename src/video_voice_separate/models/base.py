from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..types import DialogueSeparationOutput, MusicSeparationOutput


class MusicSeparator(ABC):
    @abstractmethod
    def separate(self, wav_path: Path, work_dir: Path) -> MusicSeparationOutput:
        raise NotImplementedError


class DialogueSeparator(ABC):
    @abstractmethod
    def separate(self, wav_path: Path, work_dir: Path) -> DialogueSeparationOutput:
        raise NotImplementedError


class VoiceEnhancer(ABC):
    @abstractmethod
    def enhance(self, voice_path: Path, output_path: Path) -> Path:
        raise NotImplementedError

