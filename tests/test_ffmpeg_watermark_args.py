from __future__ import annotations

from translip.utils import ffmpeg


def test_watermark_xy_per_position() -> None:
    assert ffmpeg._watermark_xy("top-left", 24) == ("24", "24")
    assert ffmpeg._watermark_xy("top-right", 24) == ("W-w-24", "24")
    assert ffmpeg._watermark_xy("bottom-left", 24) == ("24", "H-h-24")
    assert ffmpeg._watermark_xy("bottom-right", 30) == ("W-w-30", "H-h-30")
    assert ffmpeg._watermark_xy("center", 24) == ("(W-w)/2", "(H-h)/2")


def test_watermark_xy_unknown_position_falls_back_to_bottom_right() -> None:
    assert ffmpeg._watermark_xy("nonsense", 12) == ("W-w-12", "H-h-12")


def test_escape_drawtext_escapes_special_chars() -> None:
    # Backslash must be escaped first so the others aren't double-escaped.
    assert ffmpeg._escape_drawtext("a\\b") == "a\\\\b"
    assert ffmpeg._escape_drawtext("a:b") == "a\\:b"
    assert ffmpeg._escape_drawtext("it's") == "it\\'s"
    assert ffmpeg._escape_drawtext("100%") == "100\\%"
    assert ffmpeg._escape_drawtext("c:\\x'%") == "c\\:\\\\x\\'\\%"


def test_escape_drawtext_leaves_plain_text_untouched() -> None:
    assert ffmpeg._escape_drawtext("Hello World 你好") == "Hello World 你好"


def test_contains_cjk() -> None:
    assert ffmpeg._contains_cjk("你好")
    assert ffmpeg._contains_cjk("こんにちは")  # Hiragana
    assert ffmpeg._contains_cjk("안녕")  # Hangul
    assert ffmpeg._contains_cjk("ＡＢＣ")  # Fullwidth Latin
    assert ffmpeg._contains_cjk("mix 中文 in")
    assert not ffmpeg._contains_cjk("Hello World")
    assert not ffmpeg._contains_cjk("100% off!")
    assert not ffmpeg._contains_cjk("")


def test_build_image_watermark_filter_clamps_and_formats() -> None:
    f = ffmpeg._build_image_watermark_filter(
        x_expr="W-w-24", y_expr="H-h-24", opacity=0.5, scale=0.2
    )
    assert "colorchannelmixer=aa=0.5000" in f
    assert "scale=iw*0.2000:-1[wm]" in f
    assert "overlay=W-w-24:H-h-24:format=auto[outv]" in f


def test_build_image_watermark_filter_clamps_out_of_range() -> None:
    f = ffmpeg._build_image_watermark_filter(x_expr="0", y_expr="0", opacity=5.0, scale=0.0)
    assert "aa=1.0000" in f  # opacity clamped to 1.0
    assert "scale=iw*0.0100:-1" in f  # scale floored to 0.01


def test_build_drawtext_filter_basic() -> None:
    f = ffmpeg._build_drawtext_filter(
        text="hi",
        x_expr="W-w-24",
        y_expr="H-h-24",
        font_size=36,
        font_color="white",
        stroke_color="black@0.6",
        stroke_width=2,
        opacity=0.9,
        font_file=None,
    )
    assert f.startswith("drawtext=text='hi'")
    assert "fontsize=36" in f
    assert "fontcolor=white@0.9000" in f
    assert "bordercolor=black@0.6" in f
    assert "borderw=2" in f
    assert "x=W-w-24" in f
    assert "y=H-h-24" in f
    assert "fontfile" not in f


def test_build_drawtext_filter_inserts_fontfile_after_text() -> None:
    f = ffmpeg._build_drawtext_filter(
        text="hi",
        x_expr="0",
        y_expr="0",
        font_size=36,
        font_color="white",
        stroke_color="black",
        stroke_width=0,
        opacity=1.0,
        font_file="/fonts/PingFang.ttc",
    )
    assert f == (
        "drawtext=text='hi':fontfile='/fonts/PingFang.ttc':fontsize=36:"
        "fontcolor=white@1.0000:bordercolor=black:borderw=0:x=0:y=0"
    )


def test_build_drawtext_filter_escapes_text_and_clamps_opacity() -> None:
    f = ffmpeg._build_drawtext_filter(
        text="a:b",
        x_expr="0",
        y_expr="0",
        font_size=36,
        font_color="white",
        stroke_color="black",
        stroke_width=-5,
        opacity=2.0,
        font_file=None,
    )
    assert "text='a\\:b'" in f
    assert "fontcolor=white@1.0000" in f
    assert "borderw=0" in f  # negative width floored to 0


def test_resolve_watermark_fontfile_env_override(monkeypatch, tmp_path) -> None:
    font = tmp_path / "my.ttf"
    font.write_bytes(b"font")
    monkeypatch.setenv("WATERMARK_FONT_FILE", str(font))
    assert ffmpeg._resolve_watermark_fontfile("anything") == str(font)


def test_resolve_watermark_fontfile_ignores_missing_override(monkeypatch) -> None:
    monkeypatch.setenv("WATERMARK_FONT_FILE", "/does/not/exist.ttf")
    monkeypatch.setattr(ffmpeg, "_CJK_FONT_CANDIDATES", ())
    monkeypatch.setattr(ffmpeg, "_LATIN_FONT_CANDIDATES", ())
    assert ffmpeg._resolve_watermark_fontfile("hi") is None


def test_resolve_watermark_fontfile_prefers_cjk_for_cjk_text(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WATERMARK_FONT_FILE", raising=False)
    cjk = tmp_path / "cjk.ttc"
    latin = tmp_path / "latin.ttf"
    cjk.write_bytes(b"f")
    latin.write_bytes(b"f")
    monkeypatch.setattr(ffmpeg, "_CJK_FONT_CANDIDATES", (str(cjk),))
    monkeypatch.setattr(ffmpeg, "_LATIN_FONT_CANDIDATES", (str(latin),))
    assert ffmpeg._resolve_watermark_fontfile("你好") == str(cjk)
    assert ffmpeg._resolve_watermark_fontfile("hello") == str(latin)


def test_resolve_watermark_fontfile_latin_falls_back_to_cjk(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WATERMARK_FONT_FILE", raising=False)
    cjk = tmp_path / "cjk.ttc"
    cjk.write_bytes(b"f")
    monkeypatch.setattr(ffmpeg, "_CJK_FONT_CANDIDATES", (str(cjk),))
    monkeypatch.setattr(ffmpeg, "_LATIN_FONT_CANDIDATES", ("/missing/latin.ttf",))
    # No Latin face on disk, but a CJK face covers ASCII.
    assert ffmpeg._resolve_watermark_fontfile("hello") == str(cjk)
