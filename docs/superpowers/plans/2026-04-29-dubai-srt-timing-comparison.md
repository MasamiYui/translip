# Dubai SRT Timing Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare the existing dubbing pipeline against an SRT-guided timing experiment on `test_video/我在迪拜等你.mp4`, then write a conclusion report with metrics and artifact paths.

**Architecture:** Reuse the existing complete Qwen3TTS baseline in `tmp/dubai-rerun-v3`, convert `test_video/我的迪拜等你.srt` into OCR-style events, run the existing ASR/OCR correction module against baseline Task A, then rerun Task B/C/D/E/G in a new experiment directory. Compare baseline and experiment with the same metrics script.

**Tech Stack:** Existing `translip` CLI, existing `ocr_correction` module, local `uv run python`, `ffmpeg`/audio artifacts already used by the project.

---

### Task 1: Prepare Experiment Inputs

**Files:**
- Read: `tmp/dubai-rerun-v3/task-a/voice/segments.zh.json`
- Read: `tmp/dubai-rerun-v3/stage1/我在迪拜等你/voice.mp3`
- Read: `tmp/dubai-rerun-v3/stage1/我在迪拜等你/background.mp3`
- Read: `test_video/我的迪拜等你.srt`
- Create: `tmp/dubai-srt-v2/ocr-detect/ocr_events.json`
- Create: `tmp/dubai-srt-v2/ocr-detect/ocr_subtitles.source.srt`

- [ ] **Step 1: Verify baseline artifacts exist**

```bash
test -s tmp/dubai-rerun-v3/task-a/voice/segments.zh.json
test -s tmp/dubai-rerun-v3/stage1/我在迪拜等你/voice.mp3
test -s tmp/dubai-rerun-v3/stage1/我在迪拜等你/background.mp3
test -s test_video/我的迪拜等你.srt
```

- [ ] **Step 2: Convert SRT to OCR-style events**

```bash
uv run python - <<'PY'
import json, re
from pathlib import Path

src = Path("test_video/我的迪拜等你.srt")
out_dir = Path("tmp/dubai-srt-v2/ocr-detect")
out_dir.mkdir(parents=True, exist_ok=True)

def ts(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000

blocks = re.split(r"\n\s*\n", src.read_text(encoding="utf-8").strip())
events = []
for index, block in enumerate(blocks, start=1):
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if len(lines) < 3 or "-->" not in lines[1]:
        continue
    start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
    text = "".join(lines[2:]).strip()
    if not text:
        continue
    events.append({
        "event_id": f"srt-{index:04d}",
        "start": round(ts(start_raw), 3),
        "end": round(ts(end_raw), 3),
        "text": text,
        "confidence": 1.0,
        "source": "provided_srt"
    })

payload = {
    "source": "provided_srt",
    "input_srt": str(src.resolve()),
    "events": events,
    "summary": {"event_count": len(events)}
}
Path(out_dir / "ocr_events.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
Path(out_dir / "ocr_subtitles.source.srt").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
PY
```

- [ ] **Step 3: Verify converted events**

```bash
uv run python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path("tmp/dubai-srt-v2/ocr-detect/ocr_events.json").read_text(encoding="utf-8"))
assert payload["summary"]["event_count"] > 0
print(payload["summary"])
PY
```

### Task 2: Run SRT-Guided Correction

**Files:**
- Read: `tmp/dubai-rerun-v3/task-a/voice/segments.zh.json`
- Read: `tmp/dubai-srt-v2/ocr-detect/ocr_events.json`
- Create: `tmp/dubai-srt-v2/asr-ocr-correct/voice/segments.zh.corrected.json`
- Create: `tmp/dubai-srt-v2/asr-ocr-correct/voice/correction-report.json`

- [ ] **Step 1: Run correction**

```bash
uv run translip correct-asr-with-ocr \
  --segments tmp/dubai-rerun-v3/task-a/voice/segments.zh.json \
  --ocr-events tmp/dubai-srt-v2/ocr-detect/ocr_events.json \
  --output-dir tmp/dubai-srt-v2/asr-ocr-correct \
  --preset standard
```

- [ ] **Step 2: Verify correction artifacts**

```bash
test -s tmp/dubai-srt-v2/asr-ocr-correct/voice/segments.zh.corrected.json
test -s tmp/dubai-srt-v2/asr-ocr-correct/voice/correction-report.json
```

### Task 3: Rerun Downstream Pipeline Manually

**Files:**
- Read: `tmp/dubai-srt-v2/asr-ocr-correct/voice/segments.zh.corrected.json`
- Read: `tmp/dubai-rerun-v3/stage1/我在迪拜等你/voice.mp3`
- Read: `tmp/dubai-rerun-v3/stage1/我在迪拜等你/background.mp3`
- Create: `tmp/dubai-srt-v2/task-b/voice/speaker_profiles.json`
- Create: `tmp/dubai-srt-v2/task-c/voice/translation.en.json`
- Create: `tmp/dubai-srt-v2/task-d/task-d-stage-manifest.json`
- Create: `tmp/dubai-srt-v2/task-e/voice/mix_report.en.json`
- Create: `tmp/dubai-srt-v2/task-g/final-preview/final_preview.en.mp4`

- [ ] **Step 1: Build speaker profiles**

```bash
uv run translip build-speaker-registry \
  --segments tmp/dubai-srt-v2/asr-ocr-correct/voice/segments.zh.corrected.json \
  --audio tmp/dubai-rerun-v3/stage1/我在迪拜等你/voice.mp3 \
  --output-dir tmp/dubai-srt-v2/task-b \
  --device auto \
  --top-k 3
```

- [ ] **Step 2: Translate corrected script**

```bash
uv run translip translate-script \
  --segments tmp/dubai-srt-v2/asr-ocr-correct/voice/segments.zh.corrected.json \
  --profiles tmp/dubai-srt-v2/task-b/voice/speaker_profiles.json \
  --output-dir tmp/dubai-srt-v2/task-c \
  --target-lang en \
  --backend local-m2m100 \
  --device auto \
  --glossary config/glossary.travel.json \
  --condense-mode smart
```

- [ ] **Step 3: Synthesize all renderable speakers with Qwen3TTS**

```bash
uv run python - <<'PY'
import json, subprocess
from pathlib import Path
from translip.dubbing.planning import pick_task_d_speaker_ids, pick_segment_ids_for_speaker

root = Path("tmp/dubai-srt-v2")
profiles = json.loads((root / "task-b/voice/speaker_profiles.json").read_text(encoding="utf-8"))
translation = json.loads((root / "task-c/voice/translation.en.json").read_text(encoding="utf-8"))
speaker_ids = pick_task_d_speaker_ids(profiles_payload=profiles, translation_payload=translation, limit=len(profiles.get("profiles", [])))
reports = []
selected = {}
for speaker_id in speaker_ids:
    segment_ids = pick_segment_ids_for_speaker(translation_payload=translation, speaker_id=speaker_id, limit=None)
    selected[speaker_id] = segment_ids
    cmd = [
        "uv", "run", "translip", "synthesize-speaker",
        "--translation", str(root / "task-c/voice/translation.en.json"),
        "--profiles", str(root / "task-b/voice/speaker_profiles.json"),
        "--speaker-id", speaker_id,
        "--output-dir", str(root / "task-d"),
        "--backend", "qwen3tts",
        "--device", "auto",
        "--backread-model", "tiny",
    ]
    for segment_id in segment_ids or []:
        cmd.extend(["--segment-id", segment_id])
    subprocess.run(cmd, check=True)
    report = root / "task-d" / "voice" / speaker_id / "speaker_segments.en.json"
    if report.exists():
        payload = json.loads(report.read_text(encoding="utf-8"))
        if payload.get("segments"):
            reports.append(str(report.resolve()))
(root / "task-d").mkdir(parents=True, exist_ok=True)
(root / "task-d/task-d-stage-manifest.json").write_text(json.dumps({
    "status": "succeeded",
    "target_lang": "en",
    "reports": reports,
    "selected_segment_map": selected,
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print({"speakers": speaker_ids, "reports": len(reports)})
PY
```

- [ ] **Step 4: Render dub**

```bash
uv run python - <<'PY'
import json, subprocess
from pathlib import Path
root = Path("tmp/dubai-srt-v2")
manifest = json.loads((root / "task-d/task-d-stage-manifest.json").read_text(encoding="utf-8"))
cmd = [
    "uv", "run", "translip", "render-dub",
    "--background", "tmp/dubai-rerun-v3/stage1/我在迪拜等你/background.mp3",
    "--segments", str(root / "asr-ocr-correct/voice/segments.zh.corrected.json"),
    "--translation", str(root / "task-c/voice/translation.en.json"),
    "--output-dir", str(root / "task-e"),
    "--target-lang", "en",
    "--fit-policy", "conservative",
    "--fit-backend", "atempo",
    "--mix-profile", "preview",
    "--preview-format", "mp3",
    "--max-compress-ratio", "1.6",
]
for report in manifest["reports"]:
    cmd.extend(["--task-d-report", report])
subprocess.run(cmd, check=True)
PY
```

- [ ] **Step 5: Export preview/dub videos**

```bash
uv run translip export-video \
  --input-video test_video/我在迪拜等你.mp4 \
  --task-e-dir tmp/dubai-srt-v2/task-e/voice \
  --output-dir tmp/dubai-srt-v2/task-g \
  --target-lang en \
  --export-preview \
  --export-dub \
  --subtitle-mode none
```

### Task 4: Compare Metrics and Write Report

**Files:**
- Read: `tmp/dubai-rerun-v3/**`
- Read: `tmp/dubai-srt-v2/**`
- Create: `docs/superpowers/reports/2026-04-29-dubai-srt-timing-comparison.zh-CN.md`

- [ ] **Step 1: Generate metrics JSON**

```bash
uv run python .tmp/compare_dubai_runs.py
```

- [ ] **Step 2: Write final Markdown report**

```bash
test -s docs/superpowers/reports/2026-04-29-dubai-srt-timing-comparison.zh-CN.md
```
