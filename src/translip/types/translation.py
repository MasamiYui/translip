from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .common import CondenseMode, Device, TranslationBackendName


@dataclass(slots=True)
class TranslationRequest:
    segments_path: Path | str
    profiles_path: Path | str
    output_dir: Path | str = Path("output")
    source_lang: str = "zh"
    target_lang: str = "en"
    backend: TranslationBackendName = "local-m2m100"
    device: Device = "auto"
    glossary_path: Path | str | None = None
    batch_size: int = 4
    local_model: str = "facebook/m2m100_418M"
    api_model: str | None = None
    api_base_url: str | None = None
    condense_mode: CondenseMode = "smart"
    # Optional visual_context.json from the visual-context node; matched to
    # translation units by time overlap and injected as prompt context.
    visual_context_path: Path | str | None = None

    def normalized(self) -> "TranslationRequest":
        # Only paths are transformed; replace() carries every other field (ARCH-14).
        return replace(
            self,
            segments_path=Path(self.segments_path).expanduser().resolve(),
            profiles_path=Path(self.profiles_path).expanduser().resolve(),
            output_dir=Path(self.output_dir).expanduser().resolve(),
            glossary_path=(
                Path(self.glossary_path).expanduser().resolve()
                if self.glossary_path is not None
                else None
            ),
            visual_context_path=(
                Path(self.visual_context_path).expanduser().resolve()
                if self.visual_context_path is not None
                else None
            ),
        )


@dataclass(slots=True)
class TranslationArtifacts:
    bundle_dir: Path
    translation_json_path: Path
    editable_json_path: Path
    srt_path: Path
    manifest_path: Path


@dataclass(slots=True)
class TranslationResult:
    request: TranslationRequest
    artifacts: TranslationArtifacts
    manifest: dict[str, Any]


__all__ = [
    "TranslationRequest",
    "TranslationArtifacts",
    "TranslationResult",
]
