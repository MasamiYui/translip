"""Registry of speaker-diarization backends.

Adding a diarization strategy is a single registration here: provide a factory
that lazily imports and returns the ``assign_speaker_labels`` callable for that
strategy. Lazy imports keep heavy diarization runtimes (speechbrain / pyannote)
off the import path until the backend is actually used, so the transcription
runner can dispatch through this registry instead of an ``if/elif`` chain.

Each factory returns a callable with the signature
``(audio_path, segments, *, requested_device) -> (labels, metadata)`` so the
runner can invoke the resolved backend uniformly.
"""

from __future__ import annotations

from ..registry import BackendRegistry

DIARIZER_BACKENDS: BackendRegistry = BackendRegistry("diarizer")


@DIARIZER_BACKENDS.register(
    "ecapa",
    summary="ECAPA-TDNN embedding + clustering diarization (default).",
)
def _build_ecapa(**_):
    from .speaker import assign_speaker_labels

    return assign_speaker_labels


@DIARIZER_BACKENDS.register(
    "pyannote",
    summary="pyannote.audio speaker diarization pipeline.",
    requires_network=True,
)
def _build_pyannote(**_):
    from .pyannote_diarizer import assign_speaker_labels

    return assign_speaker_labels


__all__ = ["DIARIZER_BACKENDS"]


# --- ASR backends (function-style) -------------------------------------------
DEFAULT_ASR_BACKEND = "faster-whisper"

ASR_BACKENDS: BackendRegistry = BackendRegistry("asr")


@ASR_BACKENDS.register("faster-whisper", summary="faster-whisper (CTranslate2 Whisper).", aliases=("",))
def _transcribe_faster_whisper(*, audio_path, model_name, language, requested_device, options):
    from .asr import transcribe_audio

    return transcribe_audio(audio_path, model_name=model_name, language=language, requested_device=requested_device, options=options)


@ASR_BACKENDS.register("funasr", summary="FunASR / SenseVoice (Paraformer family).")
def _transcribe_funasr(*, audio_path, model_name, language, requested_device, options):
    from .funasr_backend import transcribe_audio

    return transcribe_audio(audio_path, model_name=model_name, language=language, requested_device=requested_device, options=options)
