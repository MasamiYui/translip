from __future__ import annotations


def test_atomic_tools_registry_exposes_all_tools() -> None:
    import translip.server.atomic_tools as atomic_tools  # noqa: F401
    from translip.server.atomic_tools.registry import get_all_tools

    tools = get_all_tools()

    # Auto-discovered (pkgutil) so order is not meaningful — assert the full set.
    assert {tool.tool_id for tool in tools} == {
        "separation",
        "mixing",
        "transcription",
        "transcript-correction",
        "translation",
        "tts",
        "probe",
        "muxing",
        "subtitle-detect",
        "subtitle-erase",
        "video-analyze",
        "m3u8-to-mp4",
    }
    assert {tool.category for tool in tools} == {"audio", "speech", "video"}
    m3u8 = next(tool for tool in tools if tool.tool_id == "m3u8-to-mp4")
    assert m3u8.category == "video"
    assert m3u8.accept_formats == [".m3u8"]
    assert m3u8.icon == "FileDown"
    correction = next(tool for tool in tools if tool.tool_id == "transcript-correction")
    assert correction.name_zh == "台词校正"
    assert correction.category == "speech"
    assert correction.max_files == 2
    assert ".json" in correction.accept_formats
    assert next(tool for tool in tools if tool.tool_id == "probe").max_file_size_mb == 2000
    erase = next(tool for tool in tools if tool.tool_id == "subtitle-erase")
    assert erase.category == "video"
    assert erase.max_files == 2
    assert ".json" in erase.accept_formats
    detect = next(tool for tool in tools if tool.tool_id == "subtitle-detect")
    assert detect.category == "video"
    assert detect.max_file_size_mb == 2048
