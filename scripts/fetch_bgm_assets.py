#!/usr/bin/env python3
"""Fetch licensed BGM tracks for built-in presets and replace placeholders.

Design (A1 of the commentary-library V1.1 roadmap):

* The repo only ever **bundles** the algorithmic placeholders in
  ``assets/bgm/`` (see :mod:`scripts.build_bgm_placeholders`). To avoid
  shipping anyone else's music, the licensed remote-source mapping lives in
  a *user-supplied* TOML file (``scripts/bgm_sources.toml`` by default).
* The TOML is intentionally **not committed** — every operator picks their
  own catalog (YouTube Audio Library / Pixabay / FMA / Uppbeat / etc.) and
  records the resulting URLs + sha256 + attribution there. The script then:

    1. resolves each TOML entry against
       :data:`translip.commentary.bgm.BUILTIN_BGM_PRESETS`;
    2. downloads bytes via the stdlib (urllib) — no extra third-party deps;
    3. verifies the sha256 if the user supplied one;
    4. transcodes to the canonical placeholder format
       (mono / 16-bit PCM / 44.1 kHz WAV) using the project's ffmpeg helper;
    5. writes the transcoded WAV at ``assets/bgm/<asset_filename>``,
       **overwriting** the placeholder atomically;
    6. appends a per-preset attribution block to
       ``assets/bgm/ATTRIBUTIONS.md`` (created if absent — never overwrites
       LICENSE.md, which only documents the CC0 placeholders).

The script never reaches out to any service this repo does not control;
it just fetches whatever URL the operator put in the TOML. That keeps
translip itself copyright-clean while still giving you a one-shot
``python scripts/fetch_bgm_assets.py --all`` once you've curated your
own sources.

Usage::

    # 1. Populate scripts/bgm_sources.toml (see scripts/bgm_sources.example.toml).
    # 2. Fetch every preset listed in the TOML:
    python scripts/fetch_bgm_assets.py --all

    # Or just one mood / preset id:
    python scripts/fetch_bgm_assets.py --preset bgm-epic-trailer

    # Validate the TOML + show what would happen, without touching the disk:
    python scripts/fetch_bgm_assets.py --all --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "assets" / "bgm"
DEFAULT_TOML = Path(__file__).resolve().parent / "bgm_sources.toml"
EXAMPLE_TOML = Path(__file__).resolve().parent / "bgm_sources.example.toml"
ATTR_FILE = OUT_DIR / "ATTRIBUTIONS.md"

# Canonical placeholder spec — keeps the renderer filtergraph stable
# regardless of what the operator drops in.
TARGET_SAMPLE_RATE = 44_100
TARGET_CHANNELS = 1


@dataclass(frozen=True, slots=True)
class FetchSpec:
    preset_id: str
    url: str
    sha256: str | None
    attribution: str
    license: str  # e.g. "CC-BY-4.0", "Pixabay", "YT-Audio", "Custom"


def _load_toml(path: Path) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib

        with path.open("rb") as fp:
            return tomllib.load(fp)
    raise RuntimeError(
        "Python 3.11+ is required for stdlib tomllib (the project already pins 3.12)."
    )


def _read_specs(toml_path: Path) -> list[FetchSpec]:
    if not toml_path.exists():
        raise FileNotFoundError(
            f"Source catalog not found at {toml_path}. "
            f"Copy {EXAMPLE_TOML.name} to {toml_path.name} and fill it in."
        )
    data = _load_toml(toml_path)
    sources = data.get("sources") or {}
    if not isinstance(sources, dict) or not sources:
        raise ValueError(
            f"{toml_path} has no [sources.*] entries. See {EXAMPLE_TOML} for a template."
        )

    specs: list[FetchSpec] = []
    for preset_id, raw in sources.items():
        if not isinstance(raw, dict):
            raise ValueError(f"[sources.{preset_id}] must be a table")
        url = (raw.get("url") or "").strip()
        if not url:
            raise ValueError(f"[sources.{preset_id}] missing required 'url'")
        attribution = (raw.get("attribution") or "").strip()
        if not attribution:
            raise ValueError(
                f"[sources.{preset_id}] missing required 'attribution' — "
                "licensed sources must always carry a human-readable credit line."
            )
        license_ = (raw.get("license") or "Custom").strip()
        sha256 = (raw.get("sha256") or "").strip().lower() or None
        specs.append(
            FetchSpec(
                preset_id=preset_id,
                url=url,
                sha256=sha256,
                attribution=attribution,
                license=license_,
            )
        )
    return specs


def _validate_specs_against_registry(specs: list[FetchSpec]) -> dict:
    """Cross-check every spec's preset_id resolves to a real BgmPreset."""
    from translip.commentary.bgm import get_bgm_preset

    resolved: dict = {}
    unknown: list[str] = []
    for spec in specs:
        preset = get_bgm_preset(spec.preset_id)
        if preset is None:
            unknown.append(spec.preset_id)
        else:
            resolved[spec.preset_id] = preset
    if unknown:
        raise ValueError(
            "TOML references preset ids that don't exist in BUILTIN_BGM_PRESETS: "
            + ", ".join(unknown)
        )
    return resolved


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "translip-bgm-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fp:
            shutil.copyfileobj(resp, fp)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"download failed for {url}: {exc}") from exc


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ffmpeg_binary() -> str:
    # Reuse the project's ffmpeg resolver so we don't get a different binary
    # than what the renderer pipeline uses in production.
    from translip.utils.ffmpeg import ffmpeg_binary

    return ffmpeg_binary()


def _transcode_to_wav(source: Path, target: Path) -> None:
    cmd = [
        _ffmpeg_binary(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        str(TARGET_CHANNELS),
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg transcode failed (exit {result.returncode}): "
            f"{(result.stderr or '').strip()[-400:]}"
        )


def _atomic_replace(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copyfile(src, tmp)
    tmp.replace(dst)


def _write_attribution_block(entries: list[tuple[str, FetchSpec]]) -> None:
    """(Re)write ATTRIBUTIONS.md with the currently-fetched credit lines."""
    lines = [
        "# Commentary BGM Attributions",
        "",
        "This file is auto-generated by `scripts/fetch_bgm_assets.py` and lists",
        "the licensed remote tracks currently fetched on top of the bundled",
        "CC0 placeholders. Editing it by hand will be overwritten on the next",
        "fetch.",
        "",
        "| Preset ID | License | Attribution |",
        "|---|---|---|",
    ]
    for preset_id, spec in sorted(entries, key=lambda kv: kv[0]):
        clean_attr = spec.attribution.replace("|", "\\|")
        lines.append(f"| `{preset_id}` | {spec.license} | {clean_attr} |")
    lines.append("")
    ATTR_FILE.write_text("\n".join(lines), encoding="utf-8")


def fetch_one(spec: FetchSpec, *, dry_run: bool) -> str:
    """Fetch + transcode + install a single preset. Returns a status string."""
    from translip.commentary.bgm import get_bgm_preset

    preset = get_bgm_preset(spec.preset_id)
    if preset is None:
        return f"SKIP {spec.preset_id}: unknown preset id"

    target_wav = OUT_DIR / preset.asset_filename
    if dry_run:
        return f"DRY  {spec.preset_id} -> {target_wav.relative_to(REPO_ROOT)} (url={spec.url})"

    with tempfile.TemporaryDirectory(prefix="translip-bgm-fetch-") as tmpdir:
        tmp = Path(tmpdir)
        download_path = tmp / "source.bin"
        _download(spec.url, download_path)

        if spec.sha256:
            actual = _sha256(download_path)
            if actual.lower() != spec.sha256:
                raise RuntimeError(
                    f"sha256 mismatch for {spec.preset_id}: "
                    f"expected {spec.sha256}, got {actual}. "
                    "Refusing to install — fix the TOML hash or the source URL."
                )

        transcoded = tmp / "out.wav"
        _transcode_to_wav(download_path, transcoded)
        _atomic_replace(transcoded, target_wav)

    return f"OK   {spec.preset_id} -> {target_wav.relative_to(REPO_ROOT)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch licensed BGM tracks for built-in presets (A1).",
    )
    parser.add_argument(
        "--toml",
        type=Path,
        default=DEFAULT_TOML,
        help=f"Path to the source catalog TOML (default: {DEFAULT_TOML.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--preset",
        action="append",
        default=[],
        help="Only fetch the given preset id (repeatable). Mutually exclusive with --all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch every preset listed in the TOML.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the TOML + print the resolution plan without touching disk.",
    )
    args = parser.parse_args(argv)

    if not args.all and not args.preset:
        parser.error("specify --all or one or more --preset <id>")

    try:
        specs = _read_specs(args.toml)
        _validate_specs_against_registry(specs)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    selected: list[FetchSpec]
    if args.all:
        selected = specs
    else:
        wanted = set(args.preset)
        selected = [s for s in specs if s.preset_id in wanted]
        missing = wanted - {s.preset_id for s in selected}
        if missing:
            print(
                f"ERROR: --preset ids not found in TOML: {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            return 2

    failures = 0
    successes: list[tuple[str, FetchSpec]] = []
    for spec in selected:
        try:
            status = fetch_one(spec, dry_run=args.dry_run)
            print(status)
            if status.startswith("OK"):
                successes.append((spec.preset_id, spec))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {spec.preset_id}: {exc}", file=sys.stderr)

    if successes and not args.dry_run:
        # Merge existing attributions (from previous runs of other presets)
        # with the current batch so partial fetches accumulate cleanly.
        existing: dict[str, FetchSpec] = {pid: s for pid, s in successes}
        _write_attribution_block(list(existing.items()))
        print(f"attribution -> {ATTR_FILE.relative_to(REPO_ROOT)}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
