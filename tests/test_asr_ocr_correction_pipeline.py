"""Pipeline wiring for the asr-ocr-correct node's LLM arbitration knob.

The deterministic OCR-guided correction engine is shared by the atomic tool,
the CLI subcommand, and the pipeline node. Only the atomic tool / CLI used to
expose ``llm_arbitration``; these tests pin the pipeline node passing it through
to the ``correct-asr-with-ocr`` CLI and the cache key reacting to it.
"""

from __future__ import annotations

from pathlib import Path

from translip.orchestration.cache import compute_cache_key
from translip.orchestration.commands import build_asr_ocr_correction_command
from translip.orchestration.runner import _stage_cache_payload
from translip.types import PipelineRequest


def _value_after(command: list[str], flag: str) -> str:
    assert flag in command, f"{flag} missing from command: {command}"
    return command[command.index(flag) + 1]


def test_asr_ocr_correction_command_defaults_to_off(tmp_path: Path) -> None:
    request = PipelineRequest(input_path=tmp_path / "sample.mp4", output_root=tmp_path / "out")

    command = build_asr_ocr_correction_command(request)

    # Default request keeps the pipeline local-first/offline.
    assert _value_after(command, "--llm-arbitration") == "off"


def test_asr_ocr_correction_command_passes_llm_arbitration(tmp_path: Path) -> None:
    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        transcription_correction={
            "enabled": True,
            "preset": "aggressive",
            "ocr_only_policy": "report_only",
            "llm_arbitration": "deepseek",
        },
    )

    command = build_asr_ocr_correction_command(request)

    assert _value_after(command, "--preset") == "aggressive"
    assert _value_after(command, "--llm-arbitration") == "deepseek"
    # Arbitration is orthogonal to the disable switch.
    assert "--disabled" not in command


def test_asr_ocr_correction_command_arbitration_with_disabled(tmp_path: Path) -> None:
    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        transcription_correction={
            "enabled": False,
            "preset": "standard",
            "llm_arbitration": "deepseek",
        },
    )

    command = build_asr_ocr_correction_command(request)

    assert _value_after(command, "--llm-arbitration") == "deepseek"
    assert "--disabled" in command


def test_asr_ocr_correction_cache_payload_includes_llm_arbitration(tmp_path: Path) -> None:
    request = PipelineRequest(
        input_path=tmp_path / "sample.mp4",
        output_root=tmp_path / "out",
        transcription_correction={
            "enabled": True,
            "preset": "standard",
            "ocr_only_policy": "report_only",
            "llm_arbitration": "deepseek",
        },
    )

    payload = _stage_cache_payload(request, "asr-ocr-correct")

    assert payload["transcription_correction"]["llm_arbitration"] == "deepseek"


def test_asr_ocr_correction_cache_key_changes_with_llm_arbitration(tmp_path: Path) -> None:
    def _request(mode: str) -> PipelineRequest:
        return PipelineRequest(
            input_path=tmp_path / "sample.mp4",
            output_root=tmp_path / "out",
            transcription_correction={
                "enabled": True,
                "preset": "standard",
                "ocr_only_policy": "report_only",
                "llm_arbitration": mode,
            },
        )

    key_off = compute_cache_key(_stage_cache_payload(_request("off"), "asr-ocr-correct"))
    key_deepseek = compute_cache_key(_stage_cache_payload(_request("deepseek"), "asr-ocr-correct"))

    # Toggling arbitration must force a selective recompute of this stage.
    assert key_off != key_deepseek
