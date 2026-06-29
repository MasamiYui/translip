"""Tests for the built-in commentary BGM registry & resolver."""
from __future__ import annotations

from pathlib import Path

import pytest

from translip.commentary.bgm import (
    BUILTIN_BGM_PRESETS,
    BgmPreset,
    bgm_asset_path,
    bgm_assets_dir,
    get_bgm_preset,
    list_bgm_presets,
    resolve_bgm_path,
)


# --- registry shape ----------------------------------------------------------

def test_six_built_in_moods_registered() -> None:
    presets = list_bgm_presets()
    assert len(presets) == 6
    moods = {p.mood for p in presets}
    assert moods == {"suspense", "hype", "warm", "documentary", "comedy", "action"}


def test_every_preset_has_unique_id_and_filename() -> None:
    ids = [p.id for p in BUILTIN_BGM_PRESETS]
    assert len(set(ids)) == len(ids), "duplicate preset id"
    filenames = [p.asset_filename for p in BUILTIN_BGM_PRESETS]
    assert len(set(filenames)) == len(filenames), "duplicate asset filename"


def test_preset_metadata_is_well_formed() -> None:
    for p in BUILTIN_BGM_PRESETS:
        assert p.id.startswith("bgm-")
        assert p.asset_filename.endswith(".wav")
        # Gain levels are negative dB; duck depth is also negative (further attenuation).
        assert p.gain_db < 0
        assert p.duck_db < 0
        # Bilingual labels are present.
        assert p.name_zh and p.name_en
        assert p.license  # CC0 by default


def test_get_preset_returns_dataclass_or_none() -> None:
    preset = get_bgm_preset("bgm-suspense-dark")
    assert isinstance(preset, BgmPreset)
    assert preset.mood == "suspense"
    assert get_bgm_preset("bogus") is None


# --- asset path resolution ---------------------------------------------------

def test_asset_path_lives_under_repo_assets_bgm() -> None:
    preset = BUILTIN_BGM_PRESETS[0]
    path = bgm_asset_path(preset)
    assert path.parent == bgm_assets_dir()
    assert path.name == preset.asset_filename
    # Path resolution should be absolute (not relative to CWD).
    assert path.is_absolute()


def test_bundled_placeholder_wavs_exist() -> None:
    # Sanity-check that scripts/build_bgm_placeholders.py has been run and the
    # WAVs are committed; otherwise the API will 500 in production.
    for preset in BUILTIN_BGM_PRESETS:
        path = bgm_asset_path(preset)
        assert path.exists(), f"missing placeholder {path}"
        assert path.stat().st_size > 1024, f"placeholder {path} suspiciously small"


# --- resolve_bgm_path --------------------------------------------------------

def test_resolve_empty_means_no_bgm() -> None:
    assert resolve_bgm_path(None) is None
    assert resolve_bgm_path("") is None
    assert resolve_bgm_path("   ") is None


def test_resolve_built_in_preset_returns_bundled_wav() -> None:
    path = resolve_bgm_path("bgm-suspense-dark")
    assert path is not None
    assert path.exists()
    assert path.name == "bgm-suspense-dark.wav"


def test_resolve_existing_file_path_passes_through(tmp_path: Path) -> None:
    custom = tmp_path / "my-track.wav"
    custom.write_bytes(b"\0\0")
    assert resolve_bgm_path(str(custom)) == custom


def test_resolve_unknown_selector_raises() -> None:
    with pytest.raises(ValueError, match="Unknown BGM selector"):
        resolve_bgm_path("bgm-does-not-exist")


def test_resolve_missing_built_in_asset_raises(monkeypatch, tmp_path: Path) -> None:
    # Point the assets dir at an empty location to simulate a fresh clone where
    # ``scripts/build_bgm_placeholders.py`` has not been run yet.
    monkeypatch.setattr("translip.commentary.bgm._BGM_ASSETS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="placeholder asset missing"):
        resolve_bgm_path("bgm-suspense-dark")
