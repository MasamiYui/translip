# translip-lab — evaluation lab

A **loosely-coupled** harness that tests/optimizes existing `translip` capabilities
against external, ground-truth-annotated datasets and produces **quantitative,
comparable** results (CER / DER / SI-SDR / PSNR-SSIM / detection-F1).

## Loose coupling (the one rule)

`translip_lab` depends on `translip` **one way only** — translip never imports the
lab. The integration surface is the stable translip **CLI/JSON contract** (run via
subprocess, exactly like the orchestrator) plus a couple of pure helper imports
(`translip.transcription.benchmark` for ASR scoring). Delete `src/translip_lab/`
and the single "Testing Lab" link in the frontend sidebar, and the main system is
untouched. The dashboard runs as its **own service on its own port** — the main UI
just links to it.

The whole engine runs on translip's base deps (numpy / scipy / soundfile) + ffmpeg
+ the stdlib; the only addition is Pillow (synthetic-subtitle generator), pinned in
the `lab` extra.

## Install

```bash
uv sync --extra lab            # add to your existing extras, e.g.
uv sync --extra dev --extra lab --extra ocr --extra erase
```

Data + runs live on the external disk by default: `/Volumes/EXT/translip-lab/`
(`datasets/`, `runs/`, `cache/`). Override with `TRANSLIP_LAB_HOME` (or the
per-dir `TRANSLIP_LAB_DATASETS_DIR` / `_RUNS_DIR` / `_CACHE_DIR`).

## Quickstart

```bash
translip-lab datasets                 # what's registered + present
translip-lab scenarios                # capabilities + their metric
translip-lab gen-synthetic --kind both --clips 2   # build synthetic GT

# OCR + subtitle-erase on self-built synthetic GT (needs ocr/erase extras)
translip-lab run --suite ocr-erase-synthetic

# ASR + diarization on a meeting corpus (place data first, see below)
translip-lab run --suite asr-diar-meeting --limit 5

# ad-hoc
translip-lab run --dataset synthetic-mix --scenario separation --dataset-param clips=3

translip-lab list-runs
translip-lab report  --run <run_id>                # md + html
translip-lab compare --baseline <run_a> --candidate <run_b>   # regression check

translip-lab-server                   # dashboard on http://localhost:8799
```

## Optimization & windowing

**Config sweep** — declare `[[arms]]` in a suite to run the same dataset × scenarios
across multiple configs and get a comparison matrix + winner (the optimization loop):

```toml
[[arms]]
label = "tiny"
[arms.scenario_config.asr]
asr_model = "tiny"
[[arms]]
label = "small"
[arms.scenario_config.asr]
asr_model = "small"
```

`translip-lab run --suite asr-sweep-aishell4-clips` → per-arm CER (macro mean +
corpus micro), best arm marked 🏆 in the sweep table.

**Corpus metrics + stats** — aggregates report the standard corpus-level (micro)
CER/DER/F1 (pooled errors ÷ pooled denominator), not just the mean of per-sample
rates, plus std and p90.

**Clip windowing** — the `clip` dataset wraps any base dataset and trims each
sample's media + GT (SRT / RTTM / boxes / clean video / stems) to a window, so long
meetings become fast, representative clips (no hand-trimming):

```toml
dataset = "clip"
[dataset_params]
base = "aishell4"
seconds = 180
max_samples = 3
[dataset_params.base_params]
subset = "test"
```

## Scenarios ↔ datasets ↔ metrics

| scenario | translip entry | metric | data |
| --- | --- | --- | --- |
| `asr` | `transcribe` | CER ↓ (reuses translip's scorer) | reference SRT |
| `diarization` | `transcribe --enable-diarization` | DER ↓ | reference RTTM |
| `separation` | `run` (demucs/cdx23) | SI-SDR ↑ | known clean stems |
| `ocr-detect` | `python -m translip.ocr.extract` | box F1 ↑ | subtitle box GT |
| `subtitle-erase` | `… ocr.extract` → `erase.extract` | PSNR/SSIM ↑ | clean (sub-free) video |
| `e2e-dub` | `run-pipeline` → `benchmark-dub` | honest score ↑ | (intrinsic, no GT) |

## Datasets

- **`folder`** — bring your own: drop media + sidecars under a dir. Per `<stem>`:
  `.srt` (ASR), `.rttm` (diar), `.boxes.json` (OCR), `.clean.mp4` (erase),
  `.voice.wav`+`.background.wav` (separation).
- **`aishell4`** (SLR111) / **`alimeeting`** (SLR119) — Mandarin meetings, ASR+diar
  GT. Place under `<datasets>/aishell4/<subset>/{wav,TextGrid}` and
  `<datasets>/alimeeting/<subset>/{audio_dir,textgrid_dir}`. **Domain caveat:**
  meeting/telephone, the only rigorous open CER/DER GT — not film/TV.
- **`synthetic-subtitle`** / **`synthetic-mix`** — generated GT for OCR/erase and
  separation (no public CN film/TV GT exists for these). Synthetic numbers validate
  plumbing; for real numbers supply real material via `folder`.

## Design

`core/` is the engine: `Sample`/`GroundTruth` (normalized records), `Scenario`
(invoke + score, self-registering), `Runner` (samples × scenarios, cached into a run
dir), `run_store` (aggregate + run-vs-run regression). `datasets/` and `scenarios/`
are registries — add a capability or corpus = add a file. `suites/*.toml` glue a
dataset + scenarios + config + baseline declaratively.
