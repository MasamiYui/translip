#!/usr/bin/env python3
"""Pre-bake reference clips for every built-in narrator voice (A2).

The runtime path :func:`translip.commentary.voices.resolve_narrator_reference`
lazily renders a CustomVoice reference clip the first time each voice is
played. That's correct on cold start but can take 20-40 seconds per voice on
first use, which makes the [/commentary-library] try-listen UX feel sluggish.

This script eagerly walks every entry in
:data:`translip.commentary.voices.BUILTIN_NARRATOR_VOICES` and renders the
reference clip into the same cache the runtime reads from
(:func:`translip.commentary.voices.narrator_voices_cache_dir`). Once the
cache is populated, the preview endpoint hits the cache and returns in
~200ms.

Defaults:
    * For each voice, we bake exactly one language: its ``native_language``
      (zh / en / ja / ko). That's what the preview endpoint requests when no
      explicit ``?language=`` is provided.
    * Pass ``--language LANG`` to bake an additional language across every
      voice (e.g. ``--language en`` to also pre-render English clips for the
      Chinese narrators — useful for bilingual demos).
    * ``--force`` re-renders even when the cache file already exists.
    * ``--voice ID`` (repeatable) restricts to a subset.

Usage::

    python scripts/prebake_narrator_voices.py            # bake all 17 in native lang
    python scripts/prebake_narrator_voices.py --voice narrator-recap-jianghu --voice narrator-recap-dongbei-roast
    python scripts/prebake_narrator_voices.py --language en --force
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _bake_one(voice, language: str, *, force: bool) -> str:
    from translip.commentary import voices as narrator_voices

    cache_path = narrator_voices._reference_path(voice.id, language)
    if cache_path.exists() and cache_path.stat().st_size > 0 and not force:
        return f"SKIP {voice.id:<36} [{language}] (cached, {cache_path.stat().st_size} bytes)"

    started = time.monotonic()
    try:
        narrator_voices._generate_voice_reference(voice, language, cache_path)
    except Exception as exc:  # noqa: BLE001
        return f"FAIL {voice.id:<36} [{language}] : {exc}"
    elapsed = time.monotonic() - started
    size = cache_path.stat().st_size
    return f"OK   {voice.id:<36} [{language}] ({size} bytes, {elapsed:.1f}s)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-bake reference clips for built-in narrator voices (A2).",
    )
    parser.add_argument(
        "--voice",
        action="append",
        default=[],
        help="Voice id to bake (repeatable). Defaults to every voice in the registry.",
    )
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        help=(
            "Additional language to bake across every voice "
            "(repeatable, ISO-639-1 like 'zh' 'en' 'ja' 'ko'). "
            "The voice's native_language is always included."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-render even when a cached reference already exists.",
    )
    args = parser.parse_args(argv)

    from translip.commentary import voices as narrator_voices

    all_voices = list(narrator_voices.BUILTIN_NARRATOR_VOICES)
    if args.voice:
        wanted = set(args.voice)
        selected = [v for v in all_voices if v.id in wanted]
        missing = wanted - {v.id for v in selected}
        if missing:
            print(
                f"ERROR: unknown voice id(s): {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            return 2
    else:
        selected = all_voices

    extra_langs = [lang.lower() for lang in args.language]

    plan: list[tuple] = []
    for voice in selected:
        langs = {voice.native_language or "zh"}
        for lang in extra_langs:
            langs.add(lang)
        for lang in sorted(langs):
            plan.append((voice, lang))

    cache_dir = narrator_voices.narrator_voices_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"cache dir: {cache_dir}")
    print(f"baking {len(plan)} (voice, language) combos ({len(selected)} voices)\n")

    failures = 0
    for voice, lang in plan:
        line = _bake_one(voice, lang, force=args.force)
        print(line)
        if line.startswith("FAIL"):
            failures += 1

    print(f"\ndone — failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
