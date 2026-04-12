from __future__ import annotations

from pathlib import Path

from ..exceptions import BackendUnavailableError
from .backend import ReferencePackage, SynthSegmentInput, SynthSegmentOutput, resolve_tts_device


class OpenVoiceBackend:
    backend_name = "openvoice"

    def __init__(self, *, requested_device: str) -> None:
        self.resolved_model = "OpenVoice_V2"
        self.resolved_device = resolve_tts_device(requested_device)

    def synthesize(
        self,
        *,
        reference: ReferencePackage,
        segment: SynthSegmentInput,
        output_path: Path,
    ) -> SynthSegmentOutput:
        raise BackendUnavailableError(
            "OpenVoice V2 is not wired into the local runtime yet. Use --backend f5tts for Task D."
        )
