from __future__ import annotations

import logging
import time
from pathlib import Path

from ..exceptions import TranslipError
from ..pipeline.ingest import prepare_transcription_audio
from ..transcription.asr import AsrOptions, transcribe_audio
from ..transcription.export import (
    build_transcription_manifest,
    now_iso,
    segments_payload,
    write_manifest,
    write_segments_json,
    write_segments_srt,
)
from ..transcription.speaker import assign_speaker_labels
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
        asr_segments, asr_metadata = transcribe_audio(
            working_audio,
            model_name=normalized_request.asr_model,
            language=normalized_request.language,
            requested_device=normalized_request.device,
            options=AsrOptions(
                vad_filter=normalized_request.vad_filter,
                vad_min_silence_duration_ms=normalized_request.vad_min_silence_duration_ms,
                beam_size=normalized_request.beam_size,
                best_of=normalized_request.best_of,
                temperature=normalized_request.temperature,
                condition_on_previous_text=normalized_request.condition_on_previous_text,
            ),
        )
        speaker_labels, speaker_metadata = assign_speaker_labels(
            working_audio,
            asr_segments,
            requested_device=normalized_request.device,
        )
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
