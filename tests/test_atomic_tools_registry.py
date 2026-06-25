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
        "detect-language",
        "transcript-correction",
        "translation",
        "tts",
        "probe",
        "muxing",
        "dub-render",
        "subtitle-detect",
        "subtitle-erase",
        "subtitle-burn",
        "subtitle-embed",
        "video-analyze",
        "m3u8-to-mp4",
        "watermark",
        "video-trim",
        "commentary-script",
        "commentary-render",
    }
    assert {tool.category for tool in tools} == {"audio", "speech", "video"}
    trim = next(tool for tool in tools if tool.tool_id == "video-trim")
    assert trim.category == "video"
    assert trim.icon == "Scissors"
    assert trim.max_file_size_mb == 4096
    assert trim.max_files == 1
    m3u8 = next(tool for tool in tools if tool.tool_id == "m3u8-to-mp4")
    assert m3u8.category == "video"
    assert m3u8.accept_formats == [".m3u8"]
    assert m3u8.icon == "FileDown"
    correction = next(tool for tool in tools if tool.tool_id == "transcript-correction")
    assert correction.name_zh == "台词校正"
    assert correction.category == "speech"
    assert correction.max_files == 2
    assert ".json" in correction.accept_formats
    assert next(tool for tool in tools if tool.tool_id == "probe").max_file_size_mb == 4096
    erase = next(tool for tool in tools if tool.tool_id == "subtitle-erase")
    assert erase.category == "video"
    assert erase.max_files == 2
    assert ".json" in erase.accept_formats
    detect = next(tool for tool in tools if tool.tool_id == "subtitle-detect")
    assert detect.category == "video"
    assert detect.max_file_size_mb == 4096
    commentary = next(tool for tool in tools if tool.tool_id == "commentary-script")
    assert commentary.name_zh == "解说文案"
    assert commentary.category == "speech"
    assert commentary.max_files == 2
    assert commentary.accept_formats == [".json"]
    assert commentary.heavy is False
    render = next(tool for tool in tools if tool.tool_id == "commentary-render")
    assert render.name_zh == "解说渲染"
    assert render.category == "video"
    assert render.max_files == 3
    assert render.heavy is True
    assert render.max_file_size_mb == 4096
