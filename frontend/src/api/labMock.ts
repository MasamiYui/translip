import type {
  LabCompareResult,
  LabDataset,
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

export const MOCK_RUN_DETAILS: Record<string, LabRunDetail> = Object.fromEntries(
  MOCK_RUNS.map(r => [
    r.run_id,
    {
      ...r,
      manifest: {
        dataset: r.dataset,
        subset: 'mini',
        license: 'WeNet Open Source — research only',
        source: 'https://wenet.org.cn/WenetSpeech/',
        drama_only: r.suite === 'asr-drama-wenetspeech',
      },
      results: Array.from({ length: Math.min(r.num_samples ?? 0, 5) }).map((_, i) => ({
        sample_id: `Y0000000000_drama_${String(i + 1).padStart(4, '0')}`,
        duration_sec: 4 + Math.random() * 6,
        scenario_metrics: r.aggregates,
      })),
    },
  ]),
)

const _runById = new Map(MOCK_RUNS.map(r => [r.run_id, r]))

function pickPrimary(run: LabRunSummary | undefined, scenario = 'asr'): number | null {
  if (!run) return null
  const m = run.aggregates?.[scenario] ?? {}
  const v = m.cer_micro ?? m.cer ?? m.der ?? m.si_sdr ?? m.f1 ?? m.psnr ?? m.mcd
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

export function buildMockTriggerResponse(payload: LabTriggerRunPayload): LabTriggerRunResponse {
  const cmd = ['translip-lab', 'run']
  if (payload.suite) cmd.push('--suite', payload.suite)
  if (payload.dataset) cmd.push('--dataset', payload.dataset)
  if (payload.limit) cmd.push('--limit', String(payload.limit))
  if (payload.no_cache) cmd.push('--no-cache')
  return { status: 'started', cmd }
}
