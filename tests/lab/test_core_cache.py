"""Cache-key stability and sensitivity."""
from __future__ import annotations

from translip_lab.core.cache import scenario_cache_key


def test_key_stable(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"abc")
    k1 = scenario_cache_key(scenario="asr", sample_id="s", config={"a": 1}, input_paths=[f])
    k2 = scenario_cache_key(scenario="asr", sample_id="s", config={"a": 1}, input_paths=[f])
    assert k1 == k2


def test_key_changes_with_config(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"abc")
    k1 = scenario_cache_key(scenario="asr", sample_id="s", config={"a": 1}, input_paths=[f])
    k2 = scenario_cache_key(scenario="asr", sample_id="s", config={"a": 2}, input_paths=[f])
    assert k1 != k2


def test_key_changes_with_input_content(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"abc")
    k1 = scenario_cache_key(scenario="asr", sample_id="s", config={}, input_paths=[f])
    f.write_bytes(b"abcd")  # size change → fingerprint change
    k2 = scenario_cache_key(scenario="asr", sample_id="s", config={}, input_paths=[f])
    assert k1 != k2


def test_key_changes_with_scorer_version(tmp_path):
    # the footgun fix: same config + inputs but a bumped scorer version must not collide
    f = tmp_path / "x.wav"
    f.write_bytes(b"abc")
    k1 = scenario_cache_key(scenario="asr", sample_id="s", config={}, input_paths=[f], code_version=1)
    k2 = scenario_cache_key(scenario="asr", sample_id="s", config={}, input_paths=[f], code_version=2)
    assert k1 != k2


def test_version_defaults_to_one(tmp_path):
    f = tmp_path / "x.wav"
    f.write_bytes(b"abc")
    explicit = scenario_cache_key(scenario="asr", sample_id="s", config={}, input_paths=[f], code_version=1)
    default = scenario_cache_key(scenario="asr", sample_id="s", config={}, input_paths=[f])
    assert explicit == default
