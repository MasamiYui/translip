from __future__ import annotations

from pathlib import Path
import shutil

from ....pipeline.runner import separate_file
from ....types import SeparationRequest
from ..registry import ToolSpec, register_tool
from ..schemas import SeparationToolRequest
from . import ToolAdapter


class SeparationAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        return SeparationToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        input_file = self.first_input(input_dir, "file")
        on_progress(5.0, "preparing")
        request = SeparationRequest(
            input_path=input_file,
            output_dir=output_dir,
            mode=params.get("mode", "auto"),
            quality=params.get("quality", "balanced"),
            output_format=params.get("output_format", "wav"),
        ).normalized()
        on_progress(10.0, "separating")
        result = separate_file(request)
        voice_path = self.copy_output(Path(result.artifacts.voice_path), output_dir)
        background_path = self.copy_output(Path(result.artifacts.background_path), output_dir)
        manifest_path = self.copy_output(Path(result.artifacts.manifest_path), output_dir, "manifest.json")
        bundle_dir = Path(result.artifacts.bundle_dir)
        if bundle_dir.exists() and bundle_dir != output_dir:
            try:
                bundle_dir.relative_to(output_dir)
            except ValueError:
                pass
            else:
                shutil.rmtree(bundle_dir, ignore_errors=True)
        on_progress(95.0, "collecting_artifacts")
        manifest = getattr(result, "manifest", {}) or {}
        resolved = manifest.get("resolved", {}) if isinstance(manifest, dict) else {}
        return {
            "route": result.route.route,
            "route_reason": result.route.reason,
            "backend": resolved.get("dialogue_backend") or resolved.get("music_backend"),
            "voice_file": voice_path.name,
            "background_file": background_path.name,
            "manifest_file": manifest_path.name,
        }


register_tool(
    ToolSpec(
        tool_id="separation",
        name_zh="人声/背景分离",
        name_en="Audio Separation",
        description_zh="从音视频中分离人声轨与背景轨",
        description_en="Separate vocal and background tracks from audio/video",
        category="audio",
        icon="AudioLines",
        accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".m4a", ".ogg"],
        max_file_size_mb=500,
        max_files=1,
    ),
    SeparationAdapter,
)
