"""Built-in background-music (BGM) library for video commentary.

Short-video recap channels almost always lay a "mood" music bed under the
narration. This module mirrors the design of :mod:`translip.commentary.voices`
but for music beds:

* a small, opinionated set of mood presets (suspense / hype / warm / ...);
* every preset resolves to a *committable* placeholder WAV bundled inside the
  repository at ``assets/bgm/<preset_id>.wav`` — these are synthesised with
  ffmpeg's ``sine`` / ``afade`` generators so they have **no third-party
  copyright**. They are intentionally simple; users who want production-grade
  beds should drop replacement WAVs at the same path (see ``assets/bgm/LICENSE.md``);
* renderer-side mixing parameters (target gain dB, sidechain ducking depth)
  travel with the preset so the renderer can build a sane filtergraph with
  no extra configuration from the caller.

Kept free of the FastAPI / server stack so the CLI / pipeline / atomic-tool
paths can all import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Repository-relative location of the bundled BGM placeholders. Computed once
# at import time so callers don't have to thread paths around.
_BGM_ASSETS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "assets" / "bgm"
)


@dataclass(frozen=True, slots=True)
class BgmPreset:
    """One mood preset for the commentary BGM picker.

    ``asset_filename`` resolves under :func:`bgm_assets_dir`; ``gain_db`` is the
    suggested BGM bus level (negative dB) and ``duck_db`` is the suggested
    *additional* compression applied while the narration is speaking (handled
    via ``sidechaincompress`` in the renderer).
    """

    id: str
    name_zh: str
    name_en: str
    mood: str  # one of: suspense / hype / warm / documentary / comedy / action
    asset_filename: str
    gain_db: float = -15.0
    duck_db: float = -9.0
    description_zh: str = ""
    description_en: str = ""
    license: str = "CC0"  # placeholder is algorithmically synthesised → public-domain
    license_note: str = (
        "Algorithmically synthesised placeholder (sine + envelope). Replace "
        "the WAV at the same path with a licensed track for production use."
    )


BUILTIN_BGM_PRESETS: tuple[BgmPreset, ...] = (
    BgmPreset(
        id="bgm-suspense-dark",
        name_zh="悬疑暗流",
        name_en="Suspense Dark",
        mood="suspense",
        asset_filename="bgm-suspense-dark.wav",
        gain_db=-17.0,
        duck_db=-10.0,
        description_zh="低频持续音 + 缓慢心跳脉冲，适合悬疑、犯罪、未解之谜解说底床。",
        description_en="Low drone + slow heartbeat pulse — fits mystery / true-crime recap beds.",
    ),
    BgmPreset(
        id="bgm-epic-hype",
        name_zh="史诗燃向",
        name_en="Epic Hype",
        mood="hype",
        asset_filename="bgm-epic-hype.wav",
        gain_db=-14.0,
        duck_db=-9.0,
        description_zh="昂扬上行的合成铺底，适合预告片式燃向混剪与高能解说。",
        description_en="Rising synth bed for trailer-style hype reels and high-energy recaps.",
    ),
    BgmPreset(
        id="bgm-emotional-warm",
        name_zh="温情治愈",
        name_en="Emotional Warm",
        mood="warm",
        asset_filename="bgm-emotional-warm.wav",
        gain_db=-16.0,
        duck_db=-8.0,
        description_zh="温柔大调和声铺底，适合情感、爱情、治愈题材的解说背景。",
        description_en="Warm major-key pad — great for romantic, feel-good, slice-of-life recaps.",
    ),
    BgmPreset(
        id="bgm-documentary-neutral",
        name_zh="纪录片中立",
        name_en="Documentary Neutral",
        mood="documentary",
        asset_filename="bgm-documentary-neutral.wav",
        gain_db=-18.0,
        duck_db=-7.0,
        description_zh="克制的中性铺底，存在感弱、不抢解说，适合纪录片 / 知识科普解说。",
        description_en="Restrained neutral bed — quiet, never competing with the voice, fits documentary.",
    ),
    BgmPreset(
        id="bgm-comedy-quirky",
        name_zh="搞笑灵动",
        name_en="Comedy Quirky",
        mood="comedy",
        asset_filename="bgm-comedy-quirky.wav",
        gain_db=-15.0,
        duck_db=-9.0,
        description_zh="跳跃的弹拨节奏，适合喜剧 / 综艺 / 吐槽类解说。",
        description_en="Bouncy plucked rhythm — fits comedy, variety, and roast-style recaps.",
    ),
    BgmPreset(
        id="bgm-action-chase",
        name_zh="动作追逐",
        name_en="Action Chase",
        mood="action",
        asset_filename="bgm-action-chase.wav",
        gain_db=-14.0,
        duck_db=-10.0,
        description_zh="紧张推进的节奏脉冲，适合动作、追车、犯罪题材解说。",
        description_en="Driving pulse rhythm — fits action, chase, and crime-thriller recaps.",
    ),
)

DEFAULT_BGM_PRESET = ""  # empty = no BGM (opt-in)
NO_BGM_SELECTOR = ""

_PRESETS_BY_ID = {preset.id: preset for preset in BUILTIN_BGM_PRESETS}


def list_bgm_presets() -> list[BgmPreset]:
    return list(BUILTIN_BGM_PRESETS)


def get_bgm_preset(preset_id: str) -> BgmPreset | None:
    return _PRESETS_BY_ID.get(preset_id)


def bgm_assets_dir() -> Path:
    return _BGM_ASSETS_DIR


def bgm_asset_path(preset: BgmPreset) -> Path:
    """Absolute path to the bundled placeholder WAV for ``preset``.

    The file may or may not exist on disk — callers should check before use
    (the placeholders are generated by ``scripts/build_bgm_placeholders.py`` /
    pytest fixtures and committed under ``assets/bgm/``).
    """
    return bgm_assets_dir() / preset.asset_filename


def resolve_bgm_path(selector: str | None) -> Path | None:
    """Resolve a BGM selector to a concrete WAV path.

    Selector semantics:
      - ``None`` / empty   -> no BGM (returns ``None``)
      - built-in preset id -> bundled placeholder WAV under ``assets/bgm/``
      - an existing path   -> used as-is (user-supplied music bed)

    Returning ``None`` is the explicit "no BGM" signal so the renderer can skip
    the sidechain branch entirely.
    """
    raw = (selector or "").strip()
    if not raw:
        return None

    preset = get_bgm_preset(raw)
    if preset is not None:
        path = bgm_asset_path(preset)
        if not path.exists() or path.stat().st_size == 0:
            raise FileNotFoundError(
                f"BGM placeholder asset missing for preset {preset.id!r}: {path}. "
                f"Run scripts/build_bgm_placeholders.py to (re)generate the bundled WAVs."
            )
        return path

    candidate = Path(raw).expanduser()
    if candidate.exists():
        return candidate

    raise ValueError(
        f"Unknown BGM selector {selector!r}. Use a built-in preset id "
        f"({', '.join(p.id for p in BUILTIN_BGM_PRESETS)}) or a path to a music file."
    )


__all__ = [
    "BUILTIN_BGM_PRESETS",
    "DEFAULT_BGM_PRESET",
    "NO_BGM_SELECTOR",
    "BgmPreset",
    "bgm_asset_path",
    "bgm_assets_dir",
    "get_bgm_preset",
    "list_bgm_presets",
    "resolve_bgm_path",
]
