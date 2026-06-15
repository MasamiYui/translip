"""key=value stdout parsing (translip's machine-readable stage output)."""
from __future__ import annotations

from translip_lab.core.invoke import parse_kv


def test_parse_kv_extracts_outputs():
    text = "manifest=/a/b.json\nsegments=/a/seg.json\n# comment\nrandom line\nscore=0.5"
    assert parse_kv(text) == {"manifest": "/a/b.json", "segments": "/a/seg.json", "score": "0.5"}


def test_parse_kv_ignores_prose_with_equals():
    text = "note: x = y\nkey=value"
    out = parse_kv(text)
    assert out == {"key": "value"}


def test_parse_kv_empty():
    assert parse_kv("") == {}
