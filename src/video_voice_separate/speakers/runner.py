from __future__ import annotations

import logging
import time
from pathlib import Path

from ..exceptions import VideoVoiceSeparateError
from ..pipeline.ingest import prepare_analysis_audio
from ..speaker_embedding import read_audio_mono
from ..speakers.embedding import enrich_reference_embeddings
from ..speakers.export import build_speaker_manifest, now_iso, write_json
from ..speakers.profile import build_profiles_payload
from ..speakers.reference import build_profile_drafts, export_reference_clips, load_segments_payload
from ..speakers.registry import apply_registry_updates, load_registry, match_profiles, write_registry
from ..types import (
    MediaInfo,
    SpeakerRegistryArtifacts,
    SpeakerRegistryRequest,
    SpeakerRegistryResult,
    TranscriptionRequest,
)
from ..utils.files import bundle_directory, copy_if_exists, remove_tree, work_directory

logger = logging.getLogger(__name__)


def _validate_request(request: SpeakerRegistryRequest) -> SpeakerRegistryRequest:
    normalized = request.normalized()
    if not Path(normalized.audio_path).exists():
        raise VideoVoiceSeparateError(f"Audio file does not exist: {normalized.audio_path}")
    if not Path(normalized.segments_path).exists():
        raise VideoVoiceSeparateError(f"Segments file does not exist: {normalized.segments_path}")
    return normalized


def build_speaker_registry(
    request: SpeakerRegistryRequest | str,
    **kwargs,
) -> SpeakerRegistryResult:
    if isinstance(request, str):
        raise VideoVoiceSeparateError("Task B requires explicit segments and audio paths")

    normalized_request = _validate_request(request)
    output_root = Path(normalized_request.output_dir)
    bundle_dir = bundle_directory(output_root, Path(normalized_request.audio_path))
    work_dir = work_directory(output_root)

    started_at = now_iso()
    started_monotonic = time.monotonic()
    media_info: MediaInfo | None = None
    stats: dict[str, object] = {}

    try:
        payload, segments = load_segments_payload(Path(normalized_request.segments_path))
        transcription_request = TranscriptionRequest(
            input_path=normalized_request.audio_path,
            device=normalized_request.device,
        )
        media_info, working_audio = prepare_analysis_audio(
            input_path=Path(transcription_request.input_path).expanduser().resolve(),
            audio_stream_index=0,
            work_dir=work_dir,
        )
        waveform, sample_rate = read_audio_mono(working_audio)

        drafts = build_profile_drafts(segments, waveform=waveform, sample_rate=sample_rate)
        reference_dir = bundle_dir / "reference_clips"
        export_reference_clips(drafts, waveform=waveform, sample_rate=sample_rate, output_dir=reference_dir)
        backend = enrich_reference_embeddings(
            drafts,
            waveform=waveform,
            sample_rate=sample_rate,
            requested_device=normalized_request.device,
        )
        profiles_payload = build_profiles_payload(drafts, backend=backend)

        registry = load_registry(
            Path(normalized_request.registry_path) if normalized_request.registry_path else None,
            backend_name=str(backend["speaker_backend"]),
            embedding_dim=int(backend["embedding_dim"] or 0),
        )
        matches_payload = match_profiles(
            profiles_payload,
            registry,
            top_k=normalized_request.top_k,
        )

        registry_root = (
            Path(normalized_request.registry_path).parent
            if normalized_request.registry_path is not None
            else None
        )
        profiles_payload, registry = apply_registry_updates(
            profiles_payload,
            matches_payload,
            registry,
            registry_root=registry_root,
            update_registry=normalized_request.update_registry,
        )

        profiles_path = write_json(profiles_payload, bundle_dir / "speaker_profiles.json")
        matches_path = write_json(matches_payload, bundle_dir / "speaker_matches.json")
        registry_snapshot_path = write_json(registry, bundle_dir / "speaker_registry.json")
        if normalized_request.update_registry and normalized_request.registry_path is not None:
            write_registry(registry, Path(normalized_request.registry_path))

        copied_intermediates: dict[str, Path] = {}
        if normalized_request.keep_intermediate:
            copied_intermediates["analysis_audio"] = copy_if_exists(
                working_audio,
                bundle_dir / "intermediate" / working_audio.name,
            )

        decision_counts: dict[str, int] = {}
        for match in matches_payload.get("matches", []):
            decision = match["decision"]
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
        stats = {
            "speaker_backend": backend["speaker_backend"],
            "speaker_device": backend["speaker_device"],
            "embedding_dim": backend["embedding_dim"],
            "profile_count": len(profiles_payload.get("profiles", [])),
            "registry_speaker_count": len(registry.get("speakers", [])),
            "match_decisions": decision_counts,
        }
        manifest_path = write_json(
            build_speaker_manifest(
                request=normalized_request,
                media_info=media_info,
                profiles_path=profiles_path,
                matches_path=matches_path,
                registry_snapshot_path=registry_snapshot_path,
                started_at=started_at,
                finished_at=now_iso(),
                elapsed_sec=time.monotonic() - started_monotonic,
                stats=stats,
            ),
            bundle_dir / "task-b-manifest.json",
        )

        if not normalized_request.keep_intermediate:
            remove_tree(work_dir)

        return SpeakerRegistryResult(
            request=normalized_request,
            media_info=media_info,
            artifacts=SpeakerRegistryArtifacts(
                bundle_dir=bundle_dir,
                profiles_path=profiles_path,
                matches_path=matches_path,
                registry_snapshot_path=registry_snapshot_path,
                manifest_path=manifest_path,
                intermediate_paths=copied_intermediates,
            ),
            manifest=jsonable_manifest(manifest_path),
            work_dir=work_dir,
        )
    except Exception as exc:
        logger.exception("Task B speaker registry build failed.")
        bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = write_json(
            build_speaker_manifest(
                request=normalized_request,
                media_info=media_info,
                profiles_path=bundle_dir / "speaker_profiles.json",
                matches_path=bundle_dir / "speaker_matches.json",
                registry_snapshot_path=bundle_dir / "speaker_registry.json",
                started_at=started_at,
                finished_at=now_iso(),
                elapsed_sec=time.monotonic() - started_monotonic,
                stats=stats,
                error=str(exc),
            ),
            bundle_dir / "task-b-manifest.json",
        )
        raise


def jsonable_manifest(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
