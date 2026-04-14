from __future__ import annotations

import logging
import time
from pathlib import Path

from ..config import OUTPUT_ROOT, SUPPORTED_OUTPUT_FORMATS
from ..exceptions import TranslipError
from ..models.cdx23_dialogue import Cdx23DialogueSeparator
from ..models.clearervoice import NoOpVoiceEnhancer
from ..models.demucs_music import DemucsMusicSeparator
from ..pipeline.export import export_pair
from ..pipeline.ingest import prepare_working_audio
from ..pipeline.manifest import build_manifest, now_iso, write_manifest
from ..pipeline.route import resolve_route
from ..types import MediaInfo, RouteDecision, SeparationArtifacts, SeparationRequest, SeparationResult
from ..utils.files import bundle_directory, copy_if_exists, remove_tree, work_directory
from ..utils.ffmpeg import render_wav

logger = logging.getLogger(__name__)


def _resolve_music_model(request: SeparationRequest) -> str:
    if request.music_model:
        return request.music_model
    return "htdemucs_ft" if request.quality == "high" else "htdemucs"


def _validate_request(request: SeparationRequest) -> SeparationRequest:
    normalized = request.normalized()
    if normalized.output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise TranslipError(
            f"Unsupported output format: {normalized.output_format}. "
            f"Expected one of: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    return normalized


def separate_file(request: SeparationRequest | str, **kwargs) -> SeparationResult:
    if isinstance(request, str):
        request = SeparationRequest(input_path=request, **kwargs)
    else:
        request = request

    normalized_request = _validate_request(request)
    output_root = normalized_request.output_dir or OUTPUT_ROOT
    bundle_dir = bundle_directory(Path(output_root), Path(normalized_request.input_path))
    work_dir = work_directory(Path(output_root))

    started_at = now_iso()
    started_monotonic = time.monotonic()
    media_info: MediaInfo | None = None
    route: RouteDecision | None = None

    try:
        media_info, working_audio = prepare_working_audio(normalized_request, work_dir)
        route = resolve_route(normalized_request, working_audio)

        music_model = _resolve_music_model(normalized_request)
        demucs_separator = DemucsMusicSeparator(
            model=music_model,
            device=normalized_request.device,
        )
        dialogue_separator = Cdx23DialogueSeparator(
            quality=normalized_request.quality,
            device=normalized_request.device,
        )

        if route.route == "music":
            logger.info("Running music separation backend.")
            music_result = demucs_separator.separate(working_audio, work_dir)
            final_voice_wav = work_dir / "final" / "voice.wav"
            final_background_wav = work_dir / "final" / "background.wav"
            render_wav(music_result.voice_path, final_voice_wav)
            render_wav(music_result.background_path, final_background_wav)
            backend_names = {
                "music_backend": music_result.backend_name,
                "music_model": music_model,
                "dialogue_backend": normalized_request.backend_dialogue,
            }
            intermediate_paths = music_result.intermediate_paths
        else:
            logger.info("Running dialogue separation backend.")
            dialogue_result = dialogue_separator.separate(working_audio, work_dir)
            final_voice_wav = work_dir / "final" / "voice.wav"
            final_background_wav = work_dir / "final" / "background.wav"
            render_wav(dialogue_result.dialog_path, final_voice_wav)
            render_wav(dialogue_result.background_path, final_background_wav)
            backend_names = {
                "music_backend": None,
                "music_model": None,
                "dialogue_backend": dialogue_result.backend_name,
            }
            intermediate_paths = dialogue_result.intermediate_paths

        if normalized_request.enhance_voice:
            logger.info("Enhancing voice track.")
            enhancer = NoOpVoiceEnhancer()
            enhanced_voice = work_dir / "final" / "voice_enhanced.wav"
            final_voice_wav = enhancer.enhance(final_voice_wav, enhanced_voice)

        output_dir = bundle_dir
        voice_out, background_out = export_pair(
            final_voice_wav,
            final_background_wav,
            output_dir,
            fmt=normalized_request.output_format,
            sample_rate=normalized_request.sample_rate,
            bitrate=normalized_request.bitrate,
        )

        copied_intermediates: dict[str, Path] = {}
        if normalized_request.keep_intermediate:
            stem_dir = output_dir / "stems"
            for name, src in intermediate_paths.items():
                if src.exists():
                    copied_intermediates[name] = copy_if_exists(
                        src,
                        stem_dir / src.name,
                    )

        finished_at = now_iso()
        manifest_path = output_dir / "manifest.json"
        manifest = build_manifest(
            request=normalized_request,
            media_info=media_info,
            route=route,
            voice_path=voice_out,
            background_path=background_out,
            started_at=started_at,
            finished_at=finished_at,
            elapsed_sec=time.monotonic() - started_monotonic,
            backends=backend_names,
        )
        write_manifest(manifest, manifest_path)

        if not normalized_request.keep_intermediate:
            remove_tree(work_dir)

        return SeparationResult(
            request=normalized_request,
            media_info=media_info,
            route=route,
            artifacts=SeparationArtifacts(
                bundle_dir=output_dir,
                voice_path=voice_out,
                background_path=background_out,
                manifest_path=manifest_path,
                intermediate_paths=copied_intermediates,
            ),
            manifest=manifest,
            work_dir=work_dir,
        )
    except Exception as exc:
        logger.exception("Separation failed.")
        manifest_path = bundle_dir / "manifest.json"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        finished_at = now_iso()
        route = route or RouteDecision(
            route="dialogue"
            if normalized_request.mode == "auto"
            else normalized_request.mode,
            reason="failed-before-route",
            metrics={},
        )
        manifest = build_manifest(
            request=normalized_request,
            media_info=media_info,
            route=route,
            voice_path=bundle_dir / f"voice.{normalized_request.output_format}",
            background_path=bundle_dir / f"background.{normalized_request.output_format}",
            started_at=started_at,
            finished_at=finished_at,
            elapsed_sec=time.monotonic() - started_monotonic,
            backends={
                "music_backend": normalized_request.backend_music,
                "music_model": _resolve_music_model(normalized_request),
                "dialogue_backend": normalized_request.backend_dialogue,
            },
            error=str(exc),
        )
        write_manifest(manifest, manifest_path)
        raise
