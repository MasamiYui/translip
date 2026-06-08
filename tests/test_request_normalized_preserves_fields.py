from __future__ import annotations

import pytest

from translip.types import (
    DubbingRequest,
    ExportVideoRequest,
    RenderDubRequest,
    SeparationRequest,
    SpeakerRegistryRequest,
    TranscriptionRequest,
    TranslationRequest,
)

# ARCH-14b: every Request.normalized() now uses dataclasses.replace, so a
# non-default value on a pass-through field must survive normalize() (the
# previous hand-listed reconstructions could silently drop a forgotten field).
CASES = [
    (lambda: SeparationRequest(input_path="a.mp4", backend_music="custom-music"), "backend_music", "custom-music"),
    (lambda: TranscriptionRequest(input_path="a.mp4", asr_model="large-v3"), "asr_model", "large-v3"),
    (lambda: TranscriptionRequest(input_path="a.mp4", hotwords=("Ne Zha",)), "hotwords", ("Ne Zha",)),
    (
        lambda: TranslationRequest(segments_path="s.json", profiles_path="p.json", local_model="custom/model"),
        "local_model",
        "custom/model",
    ),
    (
        lambda: DubbingRequest(translation_path="t.json", profiles_path="p.json", backread_model="big"),
        "backread_model",
        "big",
    ),
    (
        lambda: RenderDubRequest(
            background_path="b.wav",
            segments_path="s.json",
            translation_path="t.json",
            task_d_report_paths=[],
            mix_profile="podcast",
        ),
        "mix_profile",
        "podcast",
    ),
    (
        lambda: SpeakerRegistryRequest(segments_path="s.json", audio_path="a.wav", top_k=7),
        "top_k",
        7,
    ),
    (
        lambda: ExportVideoRequest(input_video_path="v.mp4", subtitle_delivery="soft", preset="slow"),
        "subtitle_delivery",
        "soft",
    ),
    (
        lambda: ExportVideoRequest(input_video_path="v.mp4", preset="slow"),
        "preset",
        "slow",
    ),
]


@pytest.mark.parametrize("factory,field_name,expected", CASES)
def test_normalized_preserves_passthrough_field(factory, field_name, expected) -> None:
    normalized = factory().normalized()
    assert getattr(normalized, field_name) == expected


def test_normalized_resolves_paths() -> None:
    sep = SeparationRequest(input_path="a.mp4").normalized()
    assert sep.input_path.is_absolute()
    sep_out = sep.output_dir
    assert sep_out.is_absolute()
