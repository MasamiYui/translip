from __future__ import annotations

from translip.subtitles.parse import SubtitleCue, parse_subtitles, parse_timestamp


def test_parse_timestamp_variants() -> None:
    assert parse_timestamp("01:02:03,500") == 3723.5  # SRT comma
    assert parse_timestamp("01:02:03.500") == 3723.5  # VTT dot
    assert parse_timestamp("02:03.250") == 123.25  # omitted hours
    assert parse_timestamp("garbage") == 0.0


def test_parse_srt_basic() -> None:
    srt = "\n".join(
        [
            "1",
            "00:00:00,000 --> 00:00:02,000",
            "第一句",
            "",
            "2",
            "00:00:02,000 --> 00:00:04,000",
            "第二句",
            "",
        ]
    )
    cues = parse_subtitles(srt)
    assert [c.text for c in cues] == ["第一句", "第二句"]
    assert cues[0] == SubtitleCue(index=1, start=0.0, end=2.0, text="第一句", speaker_label=None)
    assert cues[1].start == 2.0 and cues[1].end == 4.0


def test_parse_srt_speaker_prefix_roundtrip() -> None:
    srt = "1\n00:00:00,000 --> 00:00:02,000\n[SPEAKER_01] 你好世界\n"
    cues = parse_subtitles(srt)
    assert cues[0].speaker_label == "SPEAKER_01"
    assert cues[0].text == "你好世界"


def test_parse_vtt_with_header_note_and_cue_settings() -> None:
    vtt = "\n".join(
        [
            "WEBVTT",
            "Kind: captions",
            "",
            "NOTE this block must be ignored",
            "",
            "intro",  # cue identifier line
            "00:00:01.000 --> 00:00:03.000 align:start position:10%",
            "hello there",
            "",
            "00:01.000 --> 00:02.000",  # omitted-hours form
            "<v Roger>second line</v>",
            "",
        ]
    )
    cues = parse_subtitles(vtt)
    assert len(cues) == 2
    assert cues[0].start == 1.0 and cues[0].end == 3.0
    assert cues[0].text == "hello there"
    assert cues[1].start == 1.0 and cues[1].speaker_label == "Roger"
    assert cues[1].text == "second line"


def test_parse_skips_empty_and_malformed_blocks() -> None:
    srt = "1\n00:00:00,000 --> 00:00:01,000\n\n\n2\nnot a timestamp\nbody\n"
    # First block has no body, second block has no '-->' line — both dropped.
    assert parse_subtitles(srt) == []
