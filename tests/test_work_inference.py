from __future__ import annotations

import pytest

from translip.speaker_review.work_inference import infer_work_from_task


def _w(wid: str, title: str, aliases: list[str] | None = None) -> dict:
    return {"id": wid, "title": title, "aliases": aliases or []}


def test_no_works_returns_empty() -> None:
    out = infer_work_from_task(task_name="Some Task", input_path=None, works=[])
    assert out == []


def test_substring_match_by_alias_high_score() -> None:
    works = [_w("work_friends", "老友记", ["Friends", "六人行"])]
    out = infer_work_from_task(
        task_name="dub-en-zh", input_path="/x/Friends.S01E01.mkv", works=works
    )
    assert len(out) >= 1
    top = out[0]
    assert top["work_id"] == "work_friends"
    assert top["score"] >= 0.9
    assert top["episode_label"] == "S01E01"


def test_chinese_title_substring_match() -> None:
    works = [_w("work_lyj", "老友记", ["Friends"])]
    out = infer_work_from_task(
        task_name="老友记 第一集", input_path=None, works=works
    )
    assert any(c["work_id"] == "work_lyj" and c["score"] >= 0.9 for c in out)


def test_fuzzy_match_when_typo() -> None:
    works = [_w("work_friends", "Friends", [])]
    out = infer_work_from_task(
        task_name="Frienss-S02E03-final", input_path=None, works=works
    )
    found = next((c for c in out if c["work_id"] == "work_friends"), None)
    assert found is not None
    assert 0.55 <= found["score"] < 0.9


def test_pattern_extracts_title_for_create_when_no_match() -> None:
    out = infer_work_from_task(
        task_name="dub-job",
        input_path="/storage/Westworld.S01E02.mp4",
        works=[],
    )
    assert any(
        c.get("work_id") is None
        and c.get("suggest_create", {}).get("title", "").lower().startswith("westworld")
        for c in out
    )


def test_year_pattern_extracts_year() -> None:
    out = infer_work_from_task(
        task_name="",
        input_path="/x/Inception.2010.1080p.mkv",
        works=[],
    )
    create = next((c for c in out if c.get("suggest_create")), None)
    assert create is not None
    assert create["suggest_create"]["year"] == 2010


def test_top_3_limit_and_sort() -> None:
    works = [
        _w(f"w{i}", f"Title{i}", []) for i in range(10)
    ]
    out = infer_work_from_task(task_name="title3 title5 title7", input_path=None, works=works)
    assert len(out) <= 3
    scores = [c["score"] for c in out]
    assert scores == sorted(scores, reverse=True)


def test_episode_label_chinese_pattern() -> None:
    works = [_w("w", "三体", [])]
    out = infer_work_from_task(task_name="三体 第3集", input_path=None, works=works)
    top = out[0]
    assert top["work_id"] == "w"
    assert top["episode_label"] == "E03"
