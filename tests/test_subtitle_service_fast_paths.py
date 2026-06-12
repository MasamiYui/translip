"""Tests for the OCR fast paths: secondary-pass skip, empty-region skip,
and visual-gap-aware line joining (no invented spaces in CJK lines)."""
from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("cv2", reason="ocr extra not installed")
pytest.importorskip("pydantic_settings", reason="ocr extra not installed")

from translip.ocr.config import settings
from translip.ocr.services.subtitle_service import SubtitleService


@pytest.fixture()
def service() -> SubtitleService:
    return SubtitleService()


def _localized(tight_box, selected, indices=None):
    return {
        "recognition_region": tight_box,
        "selected_detections": selected,
        "debug": {
            "tight_box": list(tight_box),
            "selected_line_indices": indices if indices is not None else [0],
        },
    }


class TestSecondaryRecognitionSkip:
    SEARCH = (100, 300, 900, 420)

    def test_skips_single_confident_interior_line(self, service):
        localized = _localized(
            (300, 340, 700, 380),
            [{"text": "你好世界", "confidence": 0.97, "box": (300, 340, 700, 380)}],
        )
        assert service._should_skip_secondary_recognition(localized, self.SEARCH) is True

    def test_reruns_when_confidence_low(self, service):
        localized = _localized(
            (300, 340, 700, 380),
            [{"text": "你好世界", "confidence": 0.85, "box": (300, 340, 700, 380)}],
        )
        assert service._should_skip_secondary_recognition(localized, self.SEARCH) is False

    def test_reruns_when_box_touches_search_border(self, service):
        # Tight box flush with the left border: glyphs may be clipped.
        localized = _localized(
            (101, 340, 700, 380),
            [{"text": "你好世界", "confidence": 0.97, "box": (101, 340, 700, 380)}],
        )
        assert service._should_skip_secondary_recognition(localized, self.SEARCH) is False

    def test_reruns_for_multi_line_selection(self, service):
        localized = _localized(
            (300, 320, 700, 400),
            [
                {"text": "第一行", "confidence": 0.97, "box": (300, 320, 700, 355)},
                {"text": "第二行", "confidence": 0.97, "box": (300, 365, 700, 400)},
            ],
            indices=[0, 1],
        )
        assert service._should_skip_secondary_recognition(localized, self.SEARCH) is False

    def test_disabled_by_setting(self, service, monkeypatch):
        monkeypatch.setattr(settings, "SUBTITLE_SECONDARY_RECOGNITION_SKIP_ENABLED", False)
        localized = _localized(
            (300, 340, 700, 380),
            [{"text": "你好世界", "confidence": 0.97, "box": (300, 340, 700, 380)}],
        )
        assert service._should_skip_secondary_recognition(localized, self.SEARCH) is False

    def test_disabled_in_variety_recall_mode(self, service):
        service.variety_recall_enabled = True
        localized = _localized(
            (300, 340, 700, 380),
            [{"text": "你好世界", "confidence": 0.97, "box": (300, 340, 700, 380)}],
        )
        assert service._should_skip_secondary_recognition(localized, self.SEARCH) is False


class TestEmptyRegionSkip:
    def test_skips_identical_region_after_confirmed_empty(self, service):
        tracker = service._create_tracker_state()
        signature = np.full((32, 96), 0.5, dtype=np.float32)
        service._arm_empty_region_skip(tracker, signature)

        assert service._maybe_skip_confirmed_empty_region(tracker, signature.copy()) is True
        assert tracker["empty_skip_streak"] == 1

    def test_reverifies_after_max_consecutive(self, service):
        tracker = service._create_tracker_state()
        signature = np.full((32, 96), 0.5, dtype=np.float32)
        service._arm_empty_region_skip(tracker, signature)

        limit = int(settings.SUBTITLE_EMPTY_REGION_SKIP_MAX_CONSECUTIVE)
        for _ in range(limit):
            assert service._maybe_skip_confirmed_empty_region(tracker, signature.copy()) is True
        # Streak exhausted -> must OCR again (and state cleared).
        assert service._maybe_skip_confirmed_empty_region(tracker, signature.copy()) is False
        assert tracker["empty_region_signature"] is None

    def test_changed_region_breaks_the_skip(self, service):
        tracker = service._create_tracker_state()
        signature = np.full((32, 96), 0.5, dtype=np.float32)
        service._arm_empty_region_skip(tracker, signature)

        changed = signature + 0.2  # text faded in
        assert service._maybe_skip_confirmed_empty_region(tracker, changed) is False
        assert tracker["empty_region_signature"] is None

    def test_success_clears_empty_state(self, service):
        tracker = service._create_tracker_state()
        signature = np.full((32, 96), 0.5, dtype=np.float32)
        service._arm_empty_region_skip(tracker, signature)

        service._update_tracker_reuse_candidate(
            tracker,
            {"text": "你好", "confidence": 0.95, "box": (10, 10, 100, 40)},
            signature=signature,
            timestamp=1.0,
        )
        assert tracker["empty_region_signature"] is None
        assert service._maybe_skip_confirmed_empty_region(tracker, signature.copy()) is False

    def test_disabled_by_setting(self, service, monkeypatch):
        monkeypatch.setattr(settings, "SUBTITLE_EMPTY_REGION_SKIP_ENABLED", False)
        tracker = service._create_tracker_state()
        signature = np.full((32, 96), 0.5, dtype=np.float32)
        service._arm_empty_region_skip(tracker, signature)
        assert tracker["empty_region_signature"] is None


class TestJoinLineTexts:
    def _det(self, text, box):
        return {"text": text, "confidence": 0.9, "box": box}

    def test_fragmented_cjk_concatenates_without_space(self, service):
        # Detector split a continuous phrase into two boxes 4px apart.
        line = [
            self._det("哈利法塔是不是", (100, 300, 380, 340)),
            self._det("那个电影", (384, 300, 540, 340)),
        ]
        assert service._join_line_texts(line) == "哈利法塔是不是那个电影"

    def test_visual_gap_keeps_space(self, service):
        # Real on-screen gap (a full glyph width) marks an intentional pause.
        line = [
            self._det("乐乐", (100, 300, 180, 340)),
            self._det("你在哪呢", (240, 300, 400, 340)),
        ]
        assert service._join_line_texts(line) == "乐乐 你在哪呢"

    def test_latin_words_always_get_space(self, service):
        line = [
            self._det("excuse", (100, 300, 220, 330)),
            self._det("me", (224, 300, 270, 330)),
        ]
        assert service._join_line_texts(line) == "excuse me"

    def test_sorts_by_x_position(self, service):
        line = [
            self._det("世界", (300, 300, 380, 340)),
            self._det("你好", (100, 300, 180, 340)),
        ]
        assert service._join_line_texts(line) == "你好 世界"

    def test_empty_pieces_are_dropped(self, service):
        line = [
            self._det("  ", (100, 300, 120, 340)),
            self._det("你好", (130, 300, 210, 340)),
        ]
        assert service._join_line_texts(line) == "你好"
