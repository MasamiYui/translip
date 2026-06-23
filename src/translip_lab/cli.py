"""translip-lab CLI: list/generate datasets, run suites, report, compare.

Examples:
  translip-lab datasets
  translip-lab scenarios
  translip-lab gen-synthetic --kind both --clips 2
  translip-lab run --suite ocr-erase-synthetic
  translip-lab run --dataset alimeeting --scenario asr,diarization --limit 5
  translip-lab report --run <run_id>
  translip-lab compare --baseline <run_a> --candidate <run_b>
"""
from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from typing import Any

from .config import LabConfig, load_config
from .core.invoke import SubprocessInvoker
from .core.run_store import compare_runs, list_runs, load_run
from .core.runner import run_suite
from .core.scenario import SCENARIO_REGISTRY, get_scenario
from .datasets import DATASET_REGISTRY, get_dataset
from .report import compare_to_html, compare_to_markdown, run_to_html, run_to_markdown, sweep_to_markdown
from . import scenarios as _scenarios  # noqa: F401  — import side-effect populates SCENARIO_REGISTRY

_SUITES_DIR = Path(__file__).parent / "suites"


# ---------------------------------------------------------------- helpers
def _coerce(value: str) -> Any:
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def _parse_params(pairs: list[str] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        out[key.strip()] = _coerce(value.strip())
    return out


def _resolve_suite(spec: str) -> dict[str, Any]:
    path = Path(spec)
    if not path.is_file():
        packaged = _SUITES_DIR / f"{spec}.toml"
        if not packaged.is_file():
            raise FileNotFoundError(f"suite not found: {spec} (looked for file and {packaged})")
        path = packaged
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _resolve_run_dir(spec: str, config: LabConfig) -> Path:
    path = Path(spec)
    if (path / "run-manifest.json").is_file():
        return path
    candidate = config.runs_dir / spec
    if (candidate / "run-manifest.json").is_file():
        return candidate
    raise FileNotFoundError(f"run not found: {spec}")


def _evaluate_gates(spec: str, manifest: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check '<aggregate_key>=<threshold>' gates against primary-metric means.

    Pass = mean >= threshold for higher-is-better metrics, mean <= threshold
    otherwise. Keys are aggregate keys (scenario, or scenario@arm for sweeps).
    """
    aggregates = manifest.get("aggregates", {})
    lines: list[str] = []
    all_ok = True
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, _, raw = pair.partition("=")
        key = key.strip()
        try:
            threshold = float(raw)
        except ValueError:
            lines.append(f"  ? {key}: bad threshold {raw!r}")
            all_ok = False
            continue
        agg = aggregates.get(key)
        if not agg or not isinstance(agg.get("mean"), (int, float)):
            lines.append(f"  ? {key}: no scored result")
            all_ok = False
            continue
        mean = agg["mean"]
        higher = agg.get("higher_is_better")
        passed = mean >= threshold if higher else mean <= threshold
        op = ">=" if higher else "<="
        lines.append(f"  {'✓' if passed else '✗'} {key}: {mean:.4g} {op} {threshold} → {'PASS' if passed else 'FAIL'}")
        all_ok = all_ok and passed
    return all_ok, lines


def _print_aggregates(manifest: dict[str, Any]) -> None:
    print(f"\nrun_id: {manifest['run_id']}  ({manifest.get('elapsed_sec')}s)")
    for name, agg in manifest.get("aggregates", {}).items():
        mean = agg.get("mean")
        mean_s = f"{mean:.4g}" if isinstance(mean, (int, float)) else "—"
        print(f"  {name:16s} {agg.get('primary_metric','?'):>10}={mean_s:8} "
              f"scored={agg.get('scored',0)} failed={agg.get('failed',0)} skipped={agg.get('skipped',0)}")


# ---------------------------------------------------------------- commands
def cmd_datasets(args, config: LabConfig) -> int:
    for name in sorted(DATASET_REGISTRY):
        try:
            desc = get_dataset(name, config).describe()
        except Exception as exc:  # noqa: BLE001
            desc = {"error": str(exc)}
        present = desc.get("exists")
        flag = "✓" if present else "·"
        extra = desc.get("provides") or desc.get("license") or ""
        print(f"{flag} {name:20s} {desc.get('root','')}  {extra}")
    return 0


def cmd_scenarios(args, config: LabConfig) -> int:
    for name in sorted(SCENARIO_REGISTRY):
        s = SCENARIO_REGISTRY[name]
        direction = "higher better" if s.higher_is_better else "lower better"
        print(f"{name:16s} primary={s.primary_metric_key:10s} ({direction})  needs_gt={s.required_gt() or '—'}")
    return 0


def cmd_gen_synthetic(args, config: LabConfig) -> int:
    config.ensure_dirs()
    kinds = ["synthetic-subtitle", "synthetic-mix"] if args.kind == "both" else [f"synthetic-{args.kind}"]
    for name in kinds:
        ds = get_dataset(name, config, {"clips": args.clips, "duration": args.duration})
        manifest = ds.normalize()
        print(f"\n{name}: {len(manifest)} sample(s)")
        for s in manifest.samples:
            print(f"  {s.sample_id}: media={s.media_path}")
            for k, v in s.ground_truth.to_dict().items():
                if v:
                    print(f"      gt.{k}={v}")
    return 0


def cmd_run(args, config: LabConfig) -> int:
    config.ensure_dirs()
    scenario_config: dict[str, dict] = {}
    if args.suite:
        suite = _resolve_suite(args.suite)
        suite_name = suite.get("name", args.suite)
        dataset_name = suite["dataset"]
        dataset_params = suite.get("dataset_params", {})
        scenario_names = suite["scenarios"]
        scenario_config = suite.get("scenario_config", {})
        arms = suite.get("arms")
        limit = args.limit if args.limit is not None else suite.get("limit")
        timeout = args.timeout if args.timeout is not None else suite.get("timeout_sec")
    else:
        if not args.dataset or not args.scenario:
            print("error: provide --suite, or both --dataset and --scenario")
            return 2
        suite_name = args.dataset
        dataset_name = args.dataset
        dataset_params = _parse_params(args.dataset_param)
        scenario_names = [s.strip() for s in args.scenario.split(",") if s.strip()]
        arms = None
        limit = args.limit
        timeout = args.timeout

    dataset = get_dataset(dataset_name, config, dataset_params)
    manifest = dataset.normalize()
    scenarios = [get_scenario(n) for n in scenario_names]
    print(f"dataset={dataset_name} samples={len(manifest)} scenarios={[s.name for s in scenarios]} "
          f"limit={limit} cache={not args.no_cache}")

    if args.dry_run:
        n = len(manifest.samples[:limit] if limit else manifest.samples)
        n_arms = len(arms) if arms else 1
        print(f"[dry-run] would run {n * len(scenarios) * n_arms} (sample × scenario × arm) units")
        return 0

    def on_progress(ev: dict) -> None:
        pm = ev.get("primary_metric")
        pm_s = f" ({pm:.4g})" if isinstance(pm, (int, float)) else ""
        cached = " [cached]" if ev.get("cached") else ""
        arm = ev.get("arm", "default")
        arm_s = f"@{arm}" if arm != "default" else ""
        print(f"[{ev['index']}/{ev['total']}] {ev['sample_id']} · {ev['scenario']}{arm_s} → {ev['status']}{pm_s}{cached}")

    manifest_out = run_suite(
        manifest=manifest, scenarios=scenarios, suite=suite_name,
        invoker=SubprocessInvoker(config), lab_config=config,
        scenario_config=scenario_config, arms=arms, limit=limit, timeout_sec=timeout,
        use_cache=not args.no_cache, run_id=args.run_id, on_progress=on_progress,
    )
    run_dir = config.runs_dir / manifest_out["run_id"]
    (run_dir / "report.md").write_text(run_to_markdown(manifest_out), encoding="utf-8")
    (run_dir / "report.html").write_text(run_to_html(manifest_out), encoding="utf-8")
    _print_aggregates(manifest_out)
    if len(manifest_out.get("arms", [])) > 1:
        print("\n" + sweep_to_markdown(manifest_out))
    gate_failed = False
    if args.fail_under:
        ok, lines = _evaluate_gates(args.fail_under, manifest_out)
        print("\nGates:")
        for ln in lines:
            print(ln)
        gate_failed = not ok
    print(f"\nreport: {run_dir / 'report.html'}")
    return 1 if gate_failed else 0


def cmd_doctor(args, config: LabConfig) -> int:
    from .doctor import run_doctor

    icon = {"ok": "✓", "warn": "·", "missing": "✗"}
    checks = run_doctor(config)
    for c in checks:
        print(f"  {icon.get(c['status'], '?')} {c['name']:28s} {c['detail']}")
    missing_critical = [c for c in checks if c["status"] == "missing" and c.get("critical")]
    warnings = [c for c in checks if c["status"] == "warn"]
    print(f"\n{sum(1 for c in checks if c['status'] == 'ok')} ok · {len(warnings)} warn · "
          f"{len(missing_critical)} critical missing")
    return 1 if missing_critical else 0


def cmd_list_runs(args, config: LabConfig) -> int:
    runs = list_runs(config.runs_dir)
    if not runs:
        print(f"(no runs under {config.runs_dir})")
        return 0
    for r in runs:
        print(f"{r['run_id']:32s} suite={r.get('suite')} dataset={r.get('dataset')} "
              f"scenarios={','.join(r.get('scenarios', []))}")
    return 0


def cmd_report(args, config: LabConfig) -> int:
    run_dir = _resolve_run_dir(args.run, config)
    manifest = load_run(run_dir)
    md_path = Path(args.md) if args.md else run_dir / "report.md"
    html_path = Path(args.html) if args.html else run_dir / "report.html"
    md_path.write_text(run_to_markdown(manifest), encoding="utf-8")
    html_path.write_text(run_to_html(manifest), encoding="utf-8")
    print(run_to_markdown(manifest))
    print(f"written: {md_path}  {html_path}")
    return 0


def cmd_compare(args, config: LabConfig) -> int:
    baseline = load_run(_resolve_run_dir(args.baseline, config))
    candidate = load_run(_resolve_run_dir(args.candidate, config))
    comparison = compare_runs(baseline, candidate)
    print(compare_to_markdown(comparison))
    if args.html:
        Path(args.html).write_text(compare_to_html(comparison), encoding="utf-8")
        print(f"written: {args.html}")
    return 1 if comparison.get("regressions") else 0


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="translip-lab",
                                     description="Loosely-coupled evaluation lab for the translip pipeline")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("datasets", help="list registered datasets + presence")
    sub.add_parser("scenarios", help="list capability scenarios")

    g = sub.add_parser("gen-synthetic", help="generate synthetic GT datasets into the cache")
    g.add_argument("--kind", choices=["subtitle", "mix", "clone", "both"], default="both")
    g.add_argument("--clips", type=int, default=1)
    g.add_argument("--duration", type=float, default=4.0)

    r = sub.add_parser("run", help="run a suite or an ad-hoc dataset×scenario set")
    r.add_argument("--suite", default=None, help="suite name (packaged) or path to a .toml")
    r.add_argument("--dataset", default=None)
    r.add_argument("--scenario", default=None, help="comma-separated scenario names")
    r.add_argument("--dataset-param", action="append", dest="dataset_param", help="k=v (repeatable)")
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--timeout", type=float, default=None, help="per-stage timeout seconds")
    r.add_argument("--no-cache", action="store_true")
    r.add_argument("--run-id", default=None)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--fail-under", default=None,
                   help="regression gate, e.g. 'asr=0.4,diarization=0.3' (or scenario@arm=thr); "
                        "non-zero exit if a primary-metric mean violates the threshold")

    sub.add_parser("list-runs", help="list previous runs")
    sub.add_parser("doctor", help="check readiness: ffmpeg, extras, models, datasets, disk")

    rep = sub.add_parser("report", help="(re)generate md/html report for a run")
    rep.add_argument("--run", required=True, help="run id or run dir")
    rep.add_argument("--md", default=None)
    rep.add_argument("--html", default=None)

    cmp = sub.add_parser("compare", help="compare two runs (regression check)")
    cmp.add_argument("--baseline", required=True)
    cmp.add_argument("--candidate", required=True)
    cmp.add_argument("--html", default=None)
    return parser


_COMMANDS = {
    "datasets": cmd_datasets,
    "scenarios": cmd_scenarios,
    "gen-synthetic": cmd_gen_synthetic,
    "run": cmd_run,
    "list-runs": cmd_list_runs,
    "doctor": cmd_doctor,
    "report": cmd_report,
    "compare": cmd_compare,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    config = load_config()
    return _COMMANDS[args.command](args, config)
