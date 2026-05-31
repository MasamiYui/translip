"""Focused tests for the consolidated JSON/timestamp I/O helpers."""
from __future__ import annotations

import datetime as _dt
import json

import pytest

from translip.utils.io import append_jsonl, now_iso, read_json, write_json


def test_write_then_read_round_trip(tmp_path):
    payload = {"a": 1, "nested": {"b": [1, 2, 3]}, "unicode": "中文"}
    target = tmp_path / "data.json"
    write_json(payload, target)
    assert read_json(target) == payload


def test_write_default_does_not_ascii_escape(tmp_path):
    target = tmp_path / "u.json"
    write_json({"k": "中文"}, target)
    text = target.read_text(encoding="utf-8")
    assert "中文" in text  # ensure_ascii=False by default


def test_atomic_write_leaves_no_temp_file_and_overwrites(tmp_path):
    target = tmp_path / "data.json"
    write_json({"v": 1}, target, atomic=True)
    write_json({"v": 2}, target, atomic=True)
    assert read_json(target) == {"v": 2}
    # no leftover temp artifacts beside the target
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "data.json"]
    assert leftovers == []


def test_write_creates_missing_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "dir" / "data.json"
    assert not target.parent.exists()
    write_json({"ok": True}, target)
    assert target.exists()
    assert read_json(target) == {"ok": True}


def test_trailing_newline_option(tmp_path):
    target = tmp_path / "nl.json"
    write_json({"x": 1}, target, trailing_newline=True)
    assert target.read_text(encoding="utf-8").endswith("}\n")
    plain = tmp_path / "plain.json"
    write_json({"x": 1}, plain)
    assert not plain.read_text(encoding="utf-8").endswith("\n")


def test_non_atomic_write(tmp_path):
    target = tmp_path / "data.json"
    write_json({"v": "x"}, target, atomic=False)
    assert read_json(target) == {"v": "x"}


def test_now_iso_returns_parseable_iso_timestamp():
    value = now_iso()
    assert isinstance(value, str)
    parsed = _dt.datetime.fromisoformat(value)
    # has timezone info and second-level precision (no fractional seconds)
    assert parsed.tzinfo is not None
    assert parsed.microsecond == 0


def test_now_iso_format_matches_pipeline_manifest():
    from translip.pipeline.manifest import now_iso as manifest_now_iso

    a = now_iso()
    b = manifest_now_iso()
    # same structural shape (length + timezone suffix), ignoring the instant
    assert len(a) == len(b)
    assert a[-6:] == b[-6:]


def test_append_jsonl_appends_lines(tmp_path):
    target = tmp_path / "log.jsonl"
    append_jsonl({"i": 1}, target)
    append_jsonl({"i": 2}, target)
    lines = target.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"i": 1}, {"i": 2}]
