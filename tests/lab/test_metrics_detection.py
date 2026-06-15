"""Box IoU / matching / P-R-F1 unit tests."""
from __future__ import annotations

from translip_lab.metrics.detection import box_iou, match_boxes, prf


def test_iou_identical_and_disjoint():
    assert box_iou([0, 0, 2, 2], [0, 0, 2, 2]) == 1.0
    assert box_iou([0, 0, 1, 1], [5, 5, 6, 6]) == 0.0


def test_iou_partial_known_value():
    # A=[0,0,2,2] (area 4), B=[1,0,3,2] (area 4), inter=2, union=6 → 1/3
    assert abs(box_iou([0, 0, 2, 2], [1, 0, 3, 2]) - (1.0 / 3.0)) < 1e-9


def test_match_perfect():
    gt = [[0, 0, 2, 2], [10, 10, 12, 12]]
    pred = [[0, 0, 2, 2], [10, 10, 12, 12]]
    m = match_boxes(pred, gt)
    assert (m["tp"], m["fp"], m["fn"]) == (2, 0, 0)
    assert prf(m["tp"], m["fp"], m["fn"])["f1"] == 1.0


def test_match_none():
    gt = [[0, 0, 2, 2]]
    pred = [[50, 50, 52, 52]]
    m = match_boxes(pred, gt)
    assert (m["tp"], m["fp"], m["fn"]) == (0, 1, 1)
    assert prf(m["tp"], m["fp"], m["fn"])["f1"] == 0.0


def test_match_partial_with_extra_prediction():
    gt = [[0, 0, 2, 2], [10, 10, 12, 12]]
    pred = [[0, 0, 2, 2], [99, 99, 100, 100]]  # one hit, one false positive
    m = match_boxes(pred, gt)
    assert (m["tp"], m["fp"], m["fn"]) == (1, 1, 1)
    scores = prf(m["tp"], m["fp"], m["fn"])
    assert scores["precision"] == 0.5
    assert scores["recall"] == 0.5
