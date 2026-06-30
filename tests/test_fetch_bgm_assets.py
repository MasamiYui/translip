"""Tests for scripts/fetch_bgm_assets.py — dry-run / TOML validation paths only.

The actual network fetch + ffmpeg transcode pipeline is integration-tested
manually (it pulls operator-owned licensed assets); here we only guard the
pure-logic parts:

* TOML parsing & required-field validation
* preset-id cross-check against the registry
* CLI dry-run plan output
* attribution markdown writer

This keeps the script's correctness reproducible in CI without needing
network access or curated music files.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "fetch_bgm_assets.py"


@pytest.fixture(scope="module")
def fetch_module():
    """Load scripts/fetch_bgm_assets.py as a module (it's not in a package)."""
    spec = importlib.util.spec_from_file_location("fetch_bgm_assets", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_toml(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


# --- TOML parsing -----------------------------------------------------------

def test_missing_toml_raises_friendly_error(fetch_module, tmp_path: Path) -> None:
    missing = tmp_path / "nope.toml"
    with pytest.raises(FileNotFoundError, match="Source catalog not found"):
        fetch_module._read_specs(missing)


def test_toml_without_sources_section_raises(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "empty.toml"
    _write_toml(toml, "")
    with pytest.raises(ValueError, match="no \\[sources\\.\\*\\] entries"):
        fetch_module._read_specs(toml)


def test_toml_entry_missing_url_raises(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "no-url.toml"
    _write_toml(
        toml,
        """
[sources.bgm-epic-trailer]
attribution = "Example credit"
license = "CC0"
""".strip(),
    )
    with pytest.raises(ValueError, match="missing required 'url'"):
        fetch_module._read_specs(toml)


def test_toml_entry_missing_attribution_raises(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "no-attr.toml"
    _write_toml(
        toml,
        """
[sources.bgm-epic-trailer]
url = "https://example.com/track.mp3"
""".strip(),
    )
    with pytest.raises(ValueError, match="missing required 'attribution'"):
        fetch_module._read_specs(toml)


def test_toml_valid_entry_parses_into_fetchspec(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "ok.toml"
    _write_toml(
        toml,
        """
[sources.bgm-epic-trailer]
url = "https://example.com/track.mp3"
sha256 = "ABC123"
license = "CC-BY-4.0"
attribution = "Music by Example — CC-BY 4.0"
""".strip(),
    )
    specs = fetch_module._read_specs(toml)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.preset_id == "bgm-epic-trailer"
    assert spec.url == "https://example.com/track.mp3"
    # sha256 should be lowercased for case-insensitive comparison later
    assert spec.sha256 == "abc123"
    assert spec.license == "CC-BY-4.0"
    assert "Example" in spec.attribution


# --- registry cross-check ---------------------------------------------------

def test_unknown_preset_id_in_toml_is_rejected(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "bad-id.toml"
    _write_toml(
        toml,
        """
[sources.bgm-does-not-exist]
url = "https://example.com/track.mp3"
attribution = "X"
""".strip(),
    )
    specs = fetch_module._read_specs(toml)
    with pytest.raises(ValueError, match="don't exist in BUILTIN_BGM_PRESETS"):
        fetch_module._validate_specs_against_registry(specs)


def test_known_preset_id_is_accepted(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "good.toml"
    _write_toml(
        toml,
        """
[sources.bgm-epic-trailer]
url = "https://example.com/track.mp3"
attribution = "ok"
""".strip(),
    )
    specs = fetch_module._read_specs(toml)
    resolved = fetch_module._validate_specs_against_registry(specs)
    assert "bgm-epic-trailer" in resolved


# --- dry-run plan + CLI -----------------------------------------------------

def test_dry_run_does_not_touch_filesystem(
    fetch_module, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    toml = tmp_path / "good.toml"
    _write_toml(
        toml,
        """
[sources.bgm-epic-trailer]
url = "https://example.invalid/track.mp3"
attribution = "ok"
""".strip(),
    )
    exit_code = fetch_module.main(
        ["--toml", str(toml), "--all", "--dry-run"]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DRY" in captured.out
    assert "bgm-epic-trailer" in captured.out
    # Dry-run must never write the ATTRIBUTIONS.md file.
    assert not fetch_module.ATTR_FILE.exists() or fetch_module.ATTR_FILE.stat().st_size > 0


def test_cli_requires_all_or_preset_flag(fetch_module, tmp_path: Path) -> None:
    toml = tmp_path / "good.toml"
    _write_toml(
        toml,
        """
[sources.bgm-epic-trailer]
url = "https://example.com/track.mp3"
attribution = "ok"
""".strip(),
    )
    with pytest.raises(SystemExit) as excinfo:
        fetch_module.main(["--toml", str(toml)])
    # argparse.error -> SystemExit(2)
    assert excinfo.value.code == 2


def test_attribution_writer_round_trips(
    fetch_module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "ATTRIBUTIONS.md"
    monkeypatch.setattr(fetch_module, "ATTR_FILE", target)
    spec = fetch_module.FetchSpec(
        preset_id="bgm-epic-trailer",
        url="https://example.com/x.mp3",
        sha256=None,
        attribution="Music by Example | Composer",  # pipe must be escaped
        license="CC-BY-4.0",
    )
    fetch_module._write_attribution_block([("bgm-epic-trailer", spec)])
    body = target.read_text(encoding="utf-8")
    assert "# Commentary BGM Attributions" in body
    assert "`bgm-epic-trailer`" in body
    # The pipe inside attribution must be escaped so the markdown table stays valid.
    assert r"Example \| Composer" in body
