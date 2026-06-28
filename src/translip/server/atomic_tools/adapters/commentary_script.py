from __future__ import annotations

from typing import Any

from ....commentary.chain import generate_commentary_script
from ....commentary.inputs import build_story_document, load_segments, load_visual_units
from ....commentary.types import CommentaryOptions
from ..registry import ToolSpec, register_tool
from ..schemas import CommentaryScriptToolRequest
from . import ToolAdapter


class CommentaryScriptAdapter(ToolAdapter):
    """Step 1 of the commentary pipeline: transcript (+ optional scene analysis) →
    reviewable ``commentary.json`` (OST-interleaved narration script).

    Thin wrapper over :func:`translip.commentary.generate_commentary_script`; the
    heavy lifting (3-stage LLM chain) lives in ``translip.commentary``.
    """

    def validate_params(self, params: dict) -> dict:
        return CommentaryScriptToolRequest(**params).model_dump()

    def run(self, params, input_dir, output_dir, on_progress):
        on_progress(3.0, "loading_inputs")
        segments_file = self.first_input(input_dir, "segments_file")
        segments = load_segments(segments_file)
        if not segments:
            raise RuntimeError(
                "转写 segments JSON 为空或缺少 segments 字段，无法生成解说文案。"
            )

        visual_units: list[dict[str, Any]] = []
        if params.get("visual_context_file_id"):
            visual_file = self.first_input(input_dir, "visual_context_file")
            visual_units = load_visual_units(visual_file)

        story = build_story_document(segments, visual_units)
        options = CommentaryOptions(
            style=params.get("commentary_style", "plot_recap"),
            genre=params.get("drama_genre", "剧情"),
            language=params.get("narration_language", "zh"),
            original_sound_ratio=int(params.get("original_sound_ratio", 20)),
            model=params.get("model"),
            tone_preset=params.get("tone_preset", "objective"),
            pacing_preset=params.get("pacing_preset", "balanced"),
            perspective=params.get("perspective", "third_person"),
            audience=params.get("audience", "generic"),
            style_intensity=float(params.get("style_intensity", 0.6)),
        )

        # Raises BackendUnavailableError (clear message) when DEEPSEEK_API_KEY is unset.
        script = generate_commentary_script(story=story, options=options, on_progress=on_progress)

        output_dir.mkdir(parents=True, exist_ok=True)
        payload = script.to_payload(
            source={
                "segment_count": story.segment_count,
                "visual_unit_count": story.visual_unit_count,
                "duration_sec": story.duration_sec,
                "truncated": story.truncated,
            }
        )
        commentary_path = self.write_json(output_dir / "commentary.json", payload)

        on_progress(96.0, "finalizing")
        return {
            "status": "succeeded",
            "commentary_file": commentary_path.name,
            "item_count": len(script.items),
            "ost0_count": script.ost0_count,
            "ost1_count": script.ost1_count,
            "realized_ost1_ratio": script.realized_ost1_ratio(),
            "commentary_style": script.style,
            "narration_language": script.language,
            "tone_preset": script.tone_preset,
            "pacing_preset": script.pacing_preset,
            "perspective": script.perspective,
            "audience": script.audience,
            "style_intensity": script.style_intensity,
            "model": script.model,
            "source_truncated": story.truncated,
        }


register_tool(
    ToolSpec(
        tool_id="commentary-script",
        name_zh="解说文案",
        name_en="Commentary Script",
        description_zh="由转写台词（可选叠加画面分析）生成影视解说文案脚本：理解剧情→规划片段→撰写解说，输出可人工审阅的 commentary.json（解说/原声交错）",
        description_en="Generate a movie-recap narration script from a transcript (+ optional scene analysis): understand → plan clips → write commentary, emitting a reviewable OST-interleaved commentary.json",
        category="speech",
        icon="ScrollText",
        accept_formats=[".json"],
        max_file_size_mb=500,
        max_files=2,
    ),
    CommentaryScriptAdapter,
)
