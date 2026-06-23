"""Cache keys for scenario results — SHA256 over (scenario, version, sample, config, inputs).

Mirrors the orchestrator's idea: a result is reusable only if the scenario, its
scorer ``version``, the sample, the scenario config, and the input file
fingerprints are all unchanged. ``version`` closes a footgun — changing a
scenario's invoke/score logic (or a metric it uses) *without* touching config or
inputs would otherwise serve stale cached scores; bumping ``Scenario.version``
invalidates them. File fingerprints use size+mtime (cheap; media can be multi-GB)
rather than content hashing.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def fingerprint_path(path: str | Path) -> str:
    p = Path(path)
    try:
        st = p.stat()
        return f"{p}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return f"{p}:MISSING"


def scenario_cache_key(*, scenario: str, sample_id: str, config: dict, input_paths: list[str | Path],
                       code_version: int = 1) -> str:
    payload = json.dumps(
        {
            "scenario": scenario,
            "version": code_version,
            "sample": sample_id,
            "config": config,
            "inputs": sorted(fingerprint_path(p) for p in input_paths),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
