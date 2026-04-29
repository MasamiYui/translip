from __future__ import annotations

import logging
import os
from typing import Any

from .base import DiarizationBackend
from .legacy_ecapa import LegacyEcapaBackend
from .threed_speaker import ThreeDSpeakerBackend

logger = logging.getLogger(__name__)

_BACKEND_ENV_VAR = "TRANSLIP_DIARIZATION_BACKEND"
_DEFAULT_BACKEND = "auto"

_BACKEND_ALIASES = {
    "legacy": "legacy_ecapa",
    "legacy_ecapa": "legacy_ecapa",
    "ecapa": "legacy_ecapa",
    "3dspeaker": "threed_speaker",
    "threed_speaker": "threed_speaker",
    "3d_speaker": "threed_speaker",
    "3d-speaker": "threed_speaker",
    "campplus": "threed_speaker",
    "cam_plus": "threed_speaker",
    "auto": "auto",
}


def available_backends() -> list[str]:
    return ["auto", "legacy_ecapa", "threed_speaker"]


def resolve_backend_name(name: str | None) -> str:
    if name is None:
        name = os.environ.get(_BACKEND_ENV_VAR, _DEFAULT_BACKEND)
    key = (name or _DEFAULT_BACKEND).strip().lower()
    return _BACKEND_ALIASES.get(key, _DEFAULT_BACKEND)


def create_backend(
    name: str | None = None,
    *,
    config: dict[str, Any] | None = None,
) -> DiarizationBackend:
    """Instantiate a diarization backend, honouring ``auto`` fallback rules.

    ``auto`` tries ``ThreeDSpeakerBackend`` first and transparently falls
    back to ``LegacyEcapaBackend`` when the heavy modelscope dependencies
    are missing.  Explicit selections surface a clear warning when the
    chosen backend is unavailable but still return the legacy backend so
    downstream stages can always complete.
    """

    resolved = resolve_backend_name(name)
    config = config or {}

    if resolved == "legacy_ecapa":
        return LegacyEcapaBackend()

    if resolved == "threed_speaker":
        backend = ThreeDSpeakerBackend(
            pipeline_id=config.get(
                "pipeline_id",
                "iic/speech_campplus_speaker-diarization_common",
            ),
        )
        if backend.is_available():
            return backend
        logger.warning(
            "Requested diarization backend 'threed_speaker' is unavailable; "
            "falling back to 'legacy_ecapa'."
        )
        return LegacyEcapaBackend()

    # auto
    candidate = ThreeDSpeakerBackend(
        pipeline_id=config.get(
            "pipeline_id",
            "iic/speech_campplus_speaker-diarization_common",
        ),
    )
    if candidate.is_available():
        return candidate
    logger.info("ThreeDSpeakerBackend not available; using LegacyEcapaBackend.")
    return LegacyEcapaBackend()
