from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from importlib import util as importlib_util
from pathlib import Path

from ..asr import AsrSegment
from .base import DiarizationBackend, DiarizationResult, DiarizedTurn

logger = logging.getLogger(__name__)

MODELSCOPE_PIPELINE_ID = "iic/speech_campplus_speaker-diarization_common"
_TARGET_SAMPLE_RATE = 16000


def _has_module(name: str) -> bool:
    try:
        return importlib_util.find_spec(name) is not None
    except ValueError:  # pragma: no cover - defensive; malformed spec names
        return False


class ThreeDSpeakerBackend(DiarizationBackend):
    """3D-Speaker / CAM++ based diarization via modelscope.

    Preferred backend on Chinese content (see research report).  If the
    modelscope/funasr stack is not installed or the pipeline fails to load,
    :meth:`is_available` returns ``False`` so the factory can fall back to
    the legacy backend without breaking the pipeline.
    """

    name = "threed_speaker"

    def __init__(self, *, pipeline_id: str = MODELSCOPE_PIPELINE_ID) -> None:
        self.pipeline_id = pipeline_id
        self._pipeline = None
        self._last_error: str | None = None

    def is_available(self) -> bool:
        if self._pipeline is not None:
            return True
        if not _has_module("modelscope"):
            self._last_error = "modelscope is not installed"
            return False
        try:
            # Import lazily to avoid heavy dependencies at import time.
            from modelscope.pipelines import pipeline as ms_pipeline  # type: ignore

            self._pipeline = ms_pipeline(
                task="speaker-diarization",
                model=self.pipeline_id,
            )
            return True
        except Exception as exc:  # pragma: no cover - environment dependent
            self._last_error = f"failed to load modelscope pipeline: {exc}"
            logger.warning(
                "ThreeDSpeakerBackend unavailable (pipeline_id=%s): %s",
                self.pipeline_id,
                exc,
            )
            self._pipeline = None
            return False

    def diarize(
        self,
        audio_path: Path,
        *,
        segments: list[AsrSegment],
        requested_device: str,
    ) -> DiarizationResult:
        if not self.is_available() or self._pipeline is None:
            raise RuntimeError(
                "ThreeDSpeakerBackend is not available: "
                f"{self._last_error or 'unknown reason'}"
            )

        # Newer torchaudio releases removed ``sox_effects`` which the
        # modelscope CAM++ pipeline relies on for resampling.  We prepare a
        # 16 kHz mono WAV via ffmpeg and feed that to the pipeline instead.
        audio_input = _ensure_mono_16k_wav(audio_path)
        try:
            result = self._pipeline(str(audio_input))
        finally:
            if audio_input != audio_path and audio_input.exists():
                audio_input.unlink(missing_ok=True)

        raw_segments = _extract_segments(result)
        turns = [
            DiarizedTurn(
                start=float(start),
                end=float(end),
                speaker_id=int(speaker_id),
            )
            for start, end, speaker_id in raw_segments
            if float(end) > float(start)
        ]
        turns.sort(key=lambda turn: turn.start)
        return DiarizationResult(
            turns=turns,
            backend=self.name,
            metadata={
                "speaker_backend": "3d-speaker-campplus",
                "pipeline_id": self.pipeline_id,
                "speaker_count": len({turn.speaker_id for turn in turns}),
                "turn_count": len(turns),
            },
        )


def _ensure_mono_16k_wav(audio_path: Path) -> Path:
    """Return a path to a 16 kHz mono WAV copy of ``audio_path``.

    The CAM++ pipeline shipped by modelscope expects a torchaudio backend with
    ``sox_effects`` to resample arbitrary inputs.  Recent torchaudio releases
    removed that module, so we fall back to invoking ``ffmpeg`` out-of-process
    and returning a temporary WAV that the pipeline can consume directly.
    """

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        # Best effort: return the original file and hope the pipeline can
        # handle it.  The caller will surface any downstream error.
        return audio_path

    tmp = Path(tempfile.mkstemp(prefix="translip-campplus-", suffix=".wav")[1])
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        str(_TARGET_SAMPLE_RATE),
        "-sample_fmt",
        "s16",
        str(tmp),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
        tmp.unlink(missing_ok=True)
        logger.warning(
            "ffmpeg resample failed for CAM++ input %s: %s",
            audio_path,
            exc.stderr.decode("utf-8", errors="ignore")[:400],
        )
        return audio_path
    return tmp


def _extract_segments(raw: object) -> list[tuple[float, float, int]]:
    """Normalize a modelscope pipeline result into ``(start, end, speaker)``.

    ModelScope's diarization pipelines historically emit one of two shapes:

    * ``{"text": [[start, end, spk_id], ...]}``
    * ``{"segments": [{"start": ..., "end": ..., "speaker": ...}, ...]}``

    Unknown shapes fall back to an empty list so the caller can surface a
    clear error via the metadata.
    """

    if isinstance(raw, dict):
        if isinstance(raw.get("text"), list):
            return _normalize_triples(raw["text"])
        if isinstance(raw.get("segments"), list):
            return _normalize_dict_segments(raw["segments"])
    if isinstance(raw, list):
        return _normalize_triples(raw)
    return []


def _normalize_triples(items: list) -> list[tuple[float, float, int]]:
    out: list[tuple[float, float, int]] = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        try:
            start = float(item[0])
            end = float(item[1])
            speaker = _coerce_speaker(item[2])
        except (TypeError, ValueError):
            continue
        out.append((start, end, speaker))
    return out


def _normalize_dict_segments(items: list) -> list[tuple[float, float, int]]:
    out: list[tuple[float, float, int]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start", item.get("begin", 0.0)))
            end = float(item.get("end", 0.0))
            speaker = _coerce_speaker(item.get("speaker", item.get("spk", 0)))
        except (TypeError, ValueError):
            continue
        out.append((start, end, speaker))
    return out


def _coerce_speaker(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else 0
    # Support numpy scalar types (``np.int64`` etc.) and other objects that
    # expose an ``__int__`` method without inheriting from ``int``.
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0
