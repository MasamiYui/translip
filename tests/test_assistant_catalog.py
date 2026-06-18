from __future__ import annotations

from translip.server.assistant.catalog import (
    build_tool_catalog,
    is_file_param,
    model_field_names,
)
from translip.server.atomic_tools.registry import TOOL_REGISTRY


def test_catalog_covers_every_registered_tool() -> None:
    catalog = build_tool_catalog()
    ids = {entry["tool_id"] for entry in catalog}
    assert ids == set(TOOL_REGISTRY)
    assert len(catalog) == 15


def test_catalog_separates_file_inputs_and_params_with_defaults() -> None:
    catalog = {entry["tool_id"]: entry for entry in build_tool_catalog()}
    sep = catalog["separation"]
    assert [f["name"] for f in sep["file_inputs"]] == ["file_id"]
    params = {p["name"]: p for p in sep["params"]}
    assert params["mode"]["default"] == "auto"
    assert params["output_format"]["default"] == "wav"
    # file params never leak into plain params
    assert all(not is_file_param(p["name"]) for p in sep["params"])
    # chainable outputs are advertised
    assert "voice_file" in sep["outputs"]
    assert "background_file" in sep["outputs"]


def test_catalog_exposes_enum_choices() -> None:
    catalog = {entry["tool_id"]: entry for entry in build_tool_catalog()}
    transcription = catalog["transcription"]
    asr_backend = next(p for p in transcription["params"] if p["name"] == "asr_backend")
    assert asr_backend["type"] == "enum"
    assert set(asr_backend["choices"]) == {"faster-whisper", "funasr"}


def test_model_field_names_matches_request_model() -> None:
    fields = model_field_names("translation")
    assert {"text", "file_id", "source_lang", "target_lang", "backend"} <= fields
    assert model_field_names("does-not-exist") == set()
