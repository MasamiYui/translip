from __future__ import annotations

import pytest

pytest.importorskip("cv2")  # ocr extra (geometry uses cv2); skip cleanly without it (e.g. CI base)
pytest.importorskip("pydantic_settings")

from translip.ocr.core import subtitle_merger
from translip.ocr.core.subtitle_merger import SubtitleMerger, to_simplified


def test_to_simplified_uses_opencc_when_available() -> None:
    # opencc (optional ocr extra) gives full Traditional->Simplified coverage.
    pytest.importorskip("opencc")
    assert to_simplified("亂世佳人與東風") == "乱世佳人与东风"


def test_to_simplified_falls_back_to_table_without_opencc(monkeypatch) -> None:
    # Force the fallback path; '東' is present in the hand-written variant table,
    # so the base install (no opencc) still normalizes common variants.
    monkeypatch.setattr(subtitle_merger, "_opencc_converter", None)
    assert subtitle_merger.to_simplified("東") == "东"


def test_to_simplified_handles_empty() -> None:
    assert to_simplified("") == ""


def test_normalize_text_dedups_traditional_and_simplified() -> None:
    merger = SubtitleMerger()
    # Traditional and simplified of the same character normalize to the same key,
    # so OCR cues that differ only by variant dedup/merge correctly.
    assert merger._normalize_text("東") == merger._normalize_text("东")
