import type {
  LabCompareResult,
  LabDataset,
  LabJob,
  LabRunDetail,
  LabRunSummary,
  LabScenario,
  LabTriggerRunPayload,
  LabTriggerRunResponse,
} from './lab'

export const MOCK_SCENARIOS: LabScenario[] = [
  { name: 'asr', primary_metric: 'cer_micro', higher_is_better: false, required_gt: ['transcript_srt'] },
  { name: 'diarization', primary_metric: 'der', higher_is_better: false, required_gt: ['diarization_rttm'] },
  { name: 'subtitle_erase', primary_metric: 'psnr', higher_is_better: true, required_gt: ['clean_video'] },
  { name: 'ocr_detect', primary_metric: 'f1', higher_is_better: true, required_gt: ['ocr_boxes'] },
  { name: 'separation', primary_metric: 'si_sdr', higher_is_better: true, required_gt: ['stem_audio'] },
  { name: 'e2e_dub', primary_metric: 'mcd', higher_is_better: false, required_gt: ['reference_dub'] },
  { name: 'tts-clone', primary_metric: 'sim', higher_is_better: true, required_gt: ['clone_text'] },
]

export const MOCK_SUITES: string[] = [
  'asr-drama-wenetspeech',
  'asr-sweep-paraformer',
  'asr-diar-aishell4-clips',
  'asr-diar-alimeeting',
  'separation-synthetic-mix',
  'subtitle-erase-synthetic',
  'ocr-detect-synthetic',
  'e2e-dub-folder',
  'tts-clone-synthetic',
  'asr-diar-ramc',
]

export const MOCK_DATASETS: LabDataset[] = [
  {
    name: 'wenetspeech-drama',
    license: 'WeNet Open Source — research only, registration required',
    provides: ['asr (CER)'],
    subset: 'mini',
    subset_root: '/Users/lab/datasets/wenetspeech-drama/mini',
    subset_exists: true,
    expected_layout: 'wenetspeech-drama/mini/{manifest.json, audio/, srt/}',
    samples: 48,
    total_duration_min: 5.6,
  },
  {
    name: 'aishell4',
    license: 'CC BY-NC-ND 4.0 (SLR111)',
    provides: ['asr (CER)', 'diarization (DER)'],
    subset: 'test',
    subset_root: '/Users/lab/datasets/aishell4/test',
    subset_exists: true,
    expected_layout: 'aishell4/<subset>/{wav, TextGrid}',
    samples: 120,
    total_duration_min: 240,
  },
  {
    name: 'alimeeting',
    license: 'Apache-2.0 (SLR119)',
    provides: ['asr (CER)', 'diarization (DER)'],
    subset: 'eval',
    subset_root: '/Users/lab/datasets/alimeeting/eval',
    subset_exists: true,
    expected_layout: 'alimeeting/<subset>/{audio_dir, textgrid_dir}',
    samples: 50,
    total_duration_min: 180,
  },
  {
    name: 'magicdata-ramc',
    license: 'CC BY-NC-ND 4.0 (SLR123)',
    provides: ['asr (CER)', 'diarization (DER)'],
    subset: 'test',
    subset_root: '/Users/lab/datasets/magicdata-ramc/test',
    subset_exists: false,
    expected_layout: 'magicdata-ramc/<subset>/**/*.wav + <stem>.txt',
    samples: 43,
    total_duration_min: 1238,
  },
  {
    name: 'synthetic-subtitle',
    license: 'CC0',
    provides: ['ocr_detect (F1)', 'subtitle_erase (PSNR)'],
    subset: 'mini',
    subset_root: '/Users/lab/cache/synthetic-subtitle/mini',
    subset_exists: true,
    expected_layout: 'auto-generated at runtime',
    samples: 32,
    total_duration_min: 1.2,
  },
  {
    name: 'synthetic-mix',
    license: 'CC0',
    provides: ['separation (SI-SDR)'],
    subset: 'mini',
    subset_root: '/Users/lab/cache/synthetic-mix/mini',
    subset_exists: true,
    expected_layout: 'auto-generated at runtime',
    samples: 24,
    total_duration_min: 0.8,
  },
  {
    name: 'synthetic-clone',
    license: 'CC0',
    provides: ['tts-clone (SIM)'],
    subset: 'mini',
    subset_root: '/Users/lab/cache/synthetic-clone/mini',
    subset_exists: true,
    expected_layout: 'auto-generated at runtime',
    samples: 2,
    total_duration_min: 0.13,
  },
  {
    name: 'folder',
    license: 'user-provided',
    provides: ['asr (CER)', 'e2e_dub (MCD)'],
    subset: 'default',
    subset_root: '/Users/lab/datasets/folder/default',
    subset_exists: false,
    expected_layout: 'folder/<name>/{media, transcripts, references}',
    samples: 0,
    total_duration_min: 0,
  },
]

export const MOCK_RUNS: LabRunSummary[] = [
  {
    run_id: '20260621-1842-asr-drama-paraformer',
    suite: 'asr-drama-wenetspeech',
    dataset: 'wenetspeech-drama',
    scenarios: ['asr'],
    status: 'finished',
    created_at: '2026-06-21 18:42:11',
    duration_sec: 326,
    num_samples: 48,
    aggregates: {
      asr: { cer_micro: 0.0871, cer_macro: 0.0934, rtf: 0.18, samples: 48 },
    },
    arm_label: 'paraformer-zh',
    notes: 'baseline · paraformer-zh',
  },
  {
    run_id: '20260621-1855-asr-drama-whisper-small',
    suite: 'asr-drama-wenetspeech',
    dataset: 'wenetspeech-drama',
    scenarios: ['asr'],
    status: 'finished',
    created_at: '2026-06-21 18:55:03',
    duration_sec: 612,
    num_samples: 48,
    aggregates: {
      asr: { cer_micro: 0.1184, cer_macro: 0.1247, rtf: 0.41, samples: 48 },
    },
    arm_label: 'whisper-small',
  },
  {
    run_id: '20260621-1922-asr-drama-whisper-medium',
    suite: 'asr-drama-wenetspeech',
    dataset: 'wenetspeech-drama',
    scenarios: ['asr'],
    status: 'finished',
    created_at: '2026-06-21 19:22:48',
    duration_sec: 1284,
    num_samples: 48,
    aggregates: {
      asr: { cer_micro: 0.0962, cer_macro: 0.1015, rtf: 0.92, samples: 48 },
    },
    arm_label: 'whisper-medium',
  },
  {
    run_id: '20260620-1410-asr-aishell4-paraformer',
    suite: 'asr-diar-aishell4-clips',
    dataset: 'aishell4',
    scenarios: ['asr', 'diarization'],
    status: 'finished',
    created_at: '2026-06-20 14:10:02',
    duration_sec: 4180,
    num_samples: 120,
    aggregates: {
      asr: { cer_micro: 0.1521, cer_macro: 0.1604, rtf: 0.22 },
      diarization: { der: 0.0876, jer: 0.1142 },
    },
    arm_label: 'paraformer-zh + pyannote-3.1',
  },
  {
    run_id: '20260619-2003-separation-synth',
    suite: 'separation-synthetic-mix',
    dataset: 'synthetic-mix',
    scenarios: ['separation'],
    status: 'finished',
    created_at: '2026-06-19 20:03:55',
    duration_sec: 78,
    num_samples: 24,
    aggregates: {
      separation: { si_sdr: 12.41, sdr: 11.88, samples: 24 },
    },
    arm_label: 'mdx-net',
  },
  {
    run_id: '20260623-1012-tts-clone-synthetic',
    suite: 'tts-clone-synthetic',
    dataset: 'synthetic-clone',
    scenarios: ['tts-clone'],
    status: 'finished',
    created_at: '2026-06-23 10:12:30',
    duration_sec: 96,
    num_samples: 2,
    aggregates: {
      'tts-clone': { sim: 0.812, cer_micro: 0.104, samples: 2 },
    },
    arm_label: 'qwen3tts',
    notes: 'voice-clone SIM + intelligibility',
  },
  {
    run_id: '20260623-0930-asr-diar-ramc',
    suite: 'asr-diar-ramc',
    dataset: 'magicdata-ramc',
    scenarios: ['asr', 'diarization'],
    status: 'finished',
    created_at: '2026-06-23 09:30:14',
    duration_sec: 540,
    num_samples: 5,
    aggregates: {
      asr: { cer_micro: 0.191, rtf: 0.21 },
      diarization: { der: 0.0796, jer: 0.102 },
    },
    arm_label: 'paraformer-zh + ecapa',
  },
  {
    run_id: '20260622-0805-asr-drama-paraformer-rerun',
    suite: 'asr-drama-wenetspeech',
    dataset: 'wenetspeech-drama',
    scenarios: ['asr'],
    status: 'running',
    created_at: '2026-06-22 08:05:00',
    duration_sec: 184,
    num_samples: 48,
    aggregates: {},
    arm_label: 'paraformer-zh (nightly)',
    progress: 0.42,
  },
  {
    run_id: '20260618-2350-ocr-detect-synth',
    suite: 'ocr-detect-synthetic',
    dataset: 'synthetic-subtitle',
    scenarios: ['ocr_detect'],
    status: 'failed',
    created_at: '2026-06-18 23:50:17',
    duration_sec: 12,
    num_samples: 0,
    aggregates: {},
    arm_label: 'paddleocr-v4',
    error: 'GPU OOM at sample 3/32',
  },
]

function mockResults(r: LabRunSummary): Array<Record<string, unknown>> {
  const scenarios = r.scenarios?.length ? r.scenarios : ['asr']
  const n = Math.max(3, Math.min(r.num_samples ?? 3, 4))
  const arm = String((r as Record<string, unknown>).arm_label ?? 'default')
  const rows: Array<Record<string, unknown>> = []
  for (let i = 0; i < n; i++) {
    const scenario = scenarios[i % scenarios.length]
    const agg = r.aggregates?.[scenario] ?? {}
    const raw = agg.sim ?? agg.cer_micro ?? agg.der ?? agg.si_sdr ?? agg.cer
    const base = typeof raw === 'number' ? raw : undefined
    const failed = r.status === 'failed' && i === 0 // demo a traceable failure
    rows.push({
      sample_id: `${r.dataset ?? 'sample'}_${String(i + 1).padStart(4, '0')}`,
      scenario,
      arm,
      status: failed ? 'failed' : 'succeeded',
      primary_metric: failed || base === undefined ? null : Number((base * (0.92 + 0.04 * i)).toFixed(4)),
      duration_sec: 4 + i * 3,
      cached: i === n - 1,
      ...(failed ? { error: r.error ?? 'stage exit 1: RuntimeError: GPU OOM\n  at sample 3/32' } : {}),
    })
  }
  return rows
}

// Promote the leaderboard's flat {metric: value} aggregates into the full run-store
// aggregate shape (primary_metric / mean / scored…) the detail page (and live API) use.
function mockAggregates(r: LabRunSummary): Record<string, Record<string, unknown>> {
  const arm = String((r as Record<string, unknown>).arm_label ?? 'default')
  const out: Record<string, Record<string, unknown>> = {}
  for (const [scenario, metrics] of Object.entries(r.aggregates ?? {})) {
    const def = MOCK_SCENARIOS.find(s => s.name === scenario)
    const primary = def?.primary_metric ?? Object.keys(metrics)[0] ?? 'metric'
    const mean = metrics[primary]
    out[scenario] = {
      scenario,
      arm,
      primary_metric: primary,
      higher_is_better: def?.higher_is_better ?? false,
      mean: typeof mean === 'number' ? mean : null,
      std: 0,
      scored: r.num_samples ?? 0,
      failed: r.status === 'failed' ? 1 : 0,
      skipped: 0,
    }
  }
  return out
}

export const MOCK_RUN_DETAILS: Record<string, LabRunDetail> = Object.fromEntries(
  MOCK_RUNS.map(r => [
    r.run_id,
    {
      ...r,
      aggregates: mockAggregates(r) as unknown as Record<string, Record<string, number | string>>,
      sample_count: r.num_samples,
      started_at: r.created_at,
      elapsed_sec: r.duration_sec,
      results: mockResults(r),
    },
  ]),
)

const _runById = new Map(MOCK_RUNS.map(r => [r.run_id, r]))

function pickPrimary(run: LabRunSummary | undefined, scenario = 'asr'): number | null {
  if (!run) return null
  const m = run.aggregates?.[scenario] ?? {}
  const v = m.sim ?? m.cer_micro ?? m.cer ?? m.der ?? m.si_sdr ?? m.f1 ?? m.psnr ?? m.mcd
  return typeof v === 'number' ? v : null
}

export function buildMockCompare(baseline: string, candidate: string): LabCompareResult {
  const a = _runById.get(baseline)
  const b = _runById.get(candidate)
  const scenario = a?.scenarios?.[0] ?? 'asr'
  const aV = pickPrimary(a, scenario) ?? 0
  const bV = pickPrimary(b, scenario) ?? 0
  const lower = ['cer_micro', 'cer', 'der', 'mcd'].includes(
    MOCK_SCENARIOS.find(s => s.name === scenario)?.primary_metric ?? 'cer_micro',
  )
  const winner = aV === bV ? null : lower ? (aV < bV ? baseline : candidate) : aV > bV ? baseline : candidate
  return {
    baseline,
    candidate,
    per_scenario: {
      [scenario]: {
        baseline_value: aV,
        candidate_value: bV,
        delta: Number((bV - aV).toFixed(4)),
        relative_delta_pct: Number((((bV - aV) / Math.max(Math.abs(aV), 1e-6)) * 100).toFixed(2)),
        primary_metric: MOCK_SCENARIOS.find(s => s.name === scenario)?.primary_metric ?? 'cer_micro',
        higher_is_better: !lower,
      },
    },
    winner,
    delta: { [scenario]: Number((bV - aV).toFixed(4)) },
  }
}

const _mockJobStart = new Map<string, number>()

export function buildMockTriggerResponse(payload: LabTriggerRunPayload): LabTriggerRunResponse {
  const label = payload.suite ?? payload.dataset ?? 'run'
  const jobId = `mock-${label}-${Date.now()}`
  const cmd = ['translip-lab', 'run', '--run-id', jobId]
  if (payload.suite) cmd.push('--suite', payload.suite)
  if (payload.dataset) cmd.push('--dataset', payload.dataset)
  if (payload.limit) cmd.push('--limit', String(payload.limit))
  if (payload.no_cache) cmd.push('--no-cache')
  _mockJobStart.set(jobId, Date.now())
  return { status: 'queued', cmd, job_id: jobId, run_id: jobId }
}

// A tiny client-side state machine so the offline demo shows queued → running →
// succeeded without a backend (the real flow polls GET /api/lab/jobs/{id}).
export function buildMockJob(jobId: string): LabJob {
  if (!_mockJobStart.has(jobId)) _mockJobStart.set(jobId, Date.now())
  const t0 = _mockJobStart.get(jobId) ?? Date.now()
  const elapsed = Date.now() - t0
  const status = elapsed < 1600 ? 'running' : 'succeeded'
  const suite = jobId.replace(/^mock-/, '').replace(/-\d+$/, '')
  const matchRun = MOCK_RUNS.find(r => r.suite === suite)
  return {
    job_id: jobId,
    status,
    suite,
    run_id: status === 'succeeded' ? (matchRun?.run_id ?? jobId) : null,
    created_at: new Date(t0).toISOString(),
    started_at: new Date(t0).toISOString(),
    finished_at: status === 'succeeded' ? new Date().toISOString() : null,
    log_tail:
      status === 'succeeded'
        ? '$ translip-lab run …\n[3/3] sample · scenario → succeeded\n\nreport: …/report.html\n'
        : '$ translip-lab run …\n[1/3] sample · scenario → running…\n',
  }
}

export const MOCK_JOBS: LabJob[] = [
  {
    job_id: 'mock-tts-clone-synthetic-001',
    status: 'running',
    suite: 'tts-clone-synthetic',
    run_id: null,
    created_at: '2026-06-23 10:12:00',
  },
  {
    job_id: 'mock-asr-drama-wenetspeech-002',
    status: 'succeeded',
    suite: 'asr-drama-wenetspeech',
    run_id: '20260621-1842-asr-drama-paraformer',
    created_at: '2026-06-23 09:00:00',
    finished_at: '2026-06-23 09:05:26',
  },
]

export function buildMockReport(runId: string): string {
  const r = MOCK_RUN_DETAILS[runId] ?? MOCK_RUNS.find(x => x.run_id === runId)
  if (!r) return `# Lab run \`${runId}\`\n\n(not found — demo data)\n`
  const lines = [
    `# Lab run \`${runId}\``,
    '',
    `- suite: \`${r.suite ?? '—'}\``,
    `- dataset: \`${r.dataset ?? '—'}\``,
    `- samples: ${(r as Record<string, unknown>).sample_count ?? r.num_samples ?? '—'}`,
    '',
    '## Aggregates',
    '',
    '| scenario | metric | mean |',
    '|---|---|---|',
  ]
  for (const [name, agg] of Object.entries(r.aggregates ?? {})) {
    const a = agg as Record<string, number | string>
    const metric = ['cer_micro', 'sim', 'der', 'si_sdr', 'cer', 'psnr', 'f1'].find(k => k in a) ?? '—'
    lines.push(`| ${name} | ${metric} | ${String(a[metric] ?? '—')} |`)
  }
  lines.push('', '_(demo data — generated client-side)_', '')
  return lines.join('\n')
}
