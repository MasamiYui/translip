from __future__ import annotations

import logging
import time
from pathlib import Path

from ..exceptions import TranslipError
from ..pipeline.ingest import prepare_transcription_audio
from ..transcription.asr import AsrOptions, AsrSegment
from ..transcription.asr import transcribe_audio as transcribe_audio_faster_whisper
from ..transcription.export import (
    build_transcription_manifest,
    now_iso,
    segments_payload,
    write_manifest,
    write_segments_json,
    write_segments_srt,
)
from ..transcription.speaker import assign_speaker_labels as assign_speaker_labels_ecapa
from ..types import (
    MediaInfo,
    TranscriptionArtifacts,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptionSegment,
)
from ..utils.files import bundle_directory, copy_if_exists, remove_tree, work_directory

logger = logging.getLogger(__name__)


def _validate_request(request: TranscriptionRequest) -> TranscriptionRequest:
    normalized = request.normalized()
    if not Path(normalized.input_path).exists():
        raise TranslipError(f"Input file does not exist: {normalized.input_path}")
    return normalized


def _run_asr(
    audio_path: Path,
    *,
    backend: str,
    model_name: str,
    language: str,
    requested_device: str,
    options: AsrOptions,
) -> tuple[list[AsrSegment], dict[str, str | float | int | bool]]:
    if backend == "funasr":
        from ..transcription.funasr_backend import transcribe_audio as transcribe_audio_funasr

        return transcribe_audio_funasr(
            audio_path,
            model_name=model_name,
            language=language,
            requested_device=requested_device,
            options=options,
        )
    if backend not in {"faster-whisper", ""}:
        logger.warning("Unknown asr_backend=%s, falling back to faster-whisper.", backend)
    return transcribe_audio_faster_whisper(
        audio_path,
        model_name=model_name,
        language=language,
        requested_device=requested_device,
        options=options,
    )


def _run_diarization(
    audio_path: Path,
    asr_segments: list[AsrSegment],
    *,
    backend: str,
    requested_device: str,
) -> tuple[list[str], dict[str, int | float | str]]:
    if backend == "pyannote":
        from ..transcription.pyannote_diarizer import assign_speaker_labels as assign_pyannote

        return assign_pyannote(
            audio_path,
            asr_segments,
            requested_device=requested_device,
        )
    if backend not in {"ecapa", ""}:
        logger.warning("Unknown diarizer_backend=%s, falling back to ECAPA clustering.", backend)
    return assign_speaker_labels_ecapa(
        audio_path,
        asr_segments,
        requested_device=requested_device,
    )


def transcribe_file(
    request: TranscriptionRequest | str,
    **kwargs,
) -> TranscriptionResult:
    if isinstance(request, str):
        request = TranscriptionRequest(input_path=request, **kwargs)

    normalized_request = _validate_request(request)
    output_root = Path(normalized_request.output_dir)
    bundle_dir = bundle_directory(output_root, Path(normalized_request.input_path))
    work_dir = work_directory(output_root)

    started_at = now_iso()
    started_monotonic = time.monotonic()
    media_info: MediaInfo | None = None
    segments: list[TranscriptionSegment] = []
    metadata: dict[str, object] = {}

    try:
        media_info, working_audio = prepare_transcription_audio(normalized_request, work_dir)
        asr_segments, asr_metadata = _run_asr(
            working_audio,
            backend=normalized_request.asr_backend,
            model_name=normalized_request.asr_model,
            language=normalized_request.language,
            requested_device=normalized_request.device,
            options=AsrOptions(
                vad_filter=normalized_request.vad_filter,
                vad_min_silence_duration_ms=normalized_request.vad_min_silence_duration_ms,
                vad_max_segment_sec=normalized_request.vad_max_segment_sec,
                beam_size=normalized_request.beam_size,
                best_of=normalized_request.best_of,
                temperature=normalized_request.temperature,
                condition_on_previous_text=normalized_request.condition_on_previous_text,
            ),
        )
        if normalized_request.enable_diarization:
            speaker_labels, speaker_metadata = _run_diarization(
                working_audio,
                asr_segments,
                backend=normalized_request.diarizer_backend,
                requested_device=normalized_request.device,
            )
        else:
            speaker_labels = ["SPEAKER_00"] * len(asr_segments)
            speaker_metadata = {
                "speaker_backend": "disabled",
                "speaker_count": 1 if asr_segments else 0,
            }
        metadata = {**asr_metadata, **speaker_metadata, "segment_count": len(asr_segments)}

        segments = [
            TranscriptionSegment(
                segment_id=segment.segment_id,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker_label=speaker_label,
                language=segment.language,
                duration=round(segment.duration, 3),
            )
            for segment, speaker_label in zip(asr_segments, speaker_labels, strict=True)
        ]

        segments_json_path = bundle_dir / "segments.zh.json"
        payload = segments_payload(
            request=normalized_request,
            media_info=media_info,
            segments=segments,
            metadata=metadata,
        )
        write_segments_json(payload, segments_json_path)

        srt_path: Path | None = None
        if normalized_request.write_srt:
            srt_path = bundle_dir / "segments.zh.srt"
            write_segments_srt(segments, srt_path)

        copied_intermediates: dict[str, Path] = {}
        if normalized_request.keep_intermediate:
            copied_intermediates["preprocessed_audio"] = copy_if_exists(
                working_audio,
                bundle_dir / "intermediate" / working_audio.name,
            )

        manifest_path = bundle_dir / "task-a-manifest.json"
        manifest = build_transcription_manifest(
            request=normalized_request,
            media_info=media_info,
            segments_path=segments_json_path,
            srt_path=srt_path,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            metadata=metadata,
        )
        write_manifest(manifest, manifest_path)

        if not normalized_request.keep_intermediate:
            remove_tree(work_dir)

        return TranscriptionResult(
            request=normalized_request,
            media_info=media_info,
            artifacts=TranscriptionArtifacts(
                bundle_dir=bundle_dir,
                segments_json_path=segments_json_path,
                manifest_path=manifest_path,
                srt_path=srt_path,
                intermediate_paths=copied_intermediates,
            ),
            segments=segments,
            manifest=manifest,
            work_dir=work_dir,
        )
    except Exception as exc:
        logger.exception("Speaker-attributed transcription failed.")
        bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = bundle_dir / "task-a-manifest.json"
        manifest = build_transcription_manifest(
            request=normalized_request,
            media_info=media_info,
            segments_path=bundle_dir / "segments.zh.json",
            srt_path=bundle_dir / "segments.zh.srt" if normalized_request.write_srt else None,
            started_at=started_at,
            finished_at=now_iso(),
            elapsed_sec=time.monotonic() - started_monotonic,
            metadata=metadata,
            error=str(exc),
        )
        write_manifest(manifest, manifest_path)
        raise
