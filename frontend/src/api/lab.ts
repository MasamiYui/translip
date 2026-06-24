import axios, { type AxiosError } from 'axios'
import {
  MOCK_DATASETS,
  MOCK_JOBS,
  MOCK_RUNS,
  MOCK_RUN_DETAILS,
  MOCK_SCENARIOS,
  MOCK_SUITES,
  buildMockCompare,
  buildMockJob,
  buildMockReport,
  buildMockTriggerResponse,
} from './labMock'

const DEFAULT_LAB_URL = 'http://localhost:8799'

type ViteEnv = Record<string, string | undefined>

function viteEnv(): ViteEnv {
  return (import.meta as { env?: ViteEnv }).env ?? {}
}

export function getLabBaseUrl(): string {
  return viteEnv().VITE_LAB_URL || DEFAULT_LAB_URL
}

export function isMockForced(): boolean {
  const flag = viteEnv().VITE_LAB_USE_MOCK
  return flag === '1' || flag === 'true'
}

export type LabSource = 'live' | 'mock'

let runtimeSource: LabSource = isMockForced() ? 'mock' : 'live'
const listeners = new Set<(source: LabSource) => void>()

export function getLabSource(): LabSource {
  return runtimeSource
}

export function subscribeLabSource(fn: (source: LabSource) => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

function setSource(next: LabSource) {
  if (runtimeSource === next) return
  runtimeSource = next
  listeners.forEach(fn => fn(next))
}

const labClient = axios.create({
  baseURL: getLabBaseUrl(),
  timeout: 6000,
  headers: { 'Content-Type': 'application/json' },
})

async function callOrFallback<T>(live: () => Promise<T>, mock: () => T): Promise<T> {
  if (isMockForced()) {
    setSource('mock')
    return Promise.resolve(mock())
  }
  try {
    const data = await live()
    setSource('live')
    return data
  } catch (error) {
    const axErr = error as AxiosError
    const isNetwork =
      axErr.code === 'ERR_NETWORK' ||
      axErr.code === 'ECONNABORTED' ||
      axErr.message?.includes('Network Error') ||
      !axErr.response
    if (isNetwork) {
      setSource('mock')
      return mock()
    }
    throw error
  }
}

export interface LabScenario {
  name: string
  primary_metric: string
  higher_is_better: boolean
  required_gt: string[]
}

export interface LabDataset {
  name: string
  root?: string
  exists?: boolean
  params?: Record<string, unknown>
  license?: string
  provides?: string[]
  expected_layout?: string
  subset?: string
  subset_root?: string
  subset_exists?: boolean
  error?: string
  [key: string]: unknown
}

export interface LabRunSummary {
  run_id: string
  suite?: string | null
  dataset?: string | null
  scenarios?: string[]
  status?: string
  created_at?: string | number
  duration_sec?: number
  num_samples?: number
  aggregates?: Record<string, Record<string, number | string>>
  [key: string]: unknown
}

export interface LabRunDetail extends LabRunSummary {
  results?: Array<Record<string, unknown>>
  arms?: Array<Record<string, unknown>>
  manifest?: Record<string, unknown>
}

export interface LabCompareResult {
  baseline: string
  candidate: string
  per_scenario?: Record<string, Record<string, number | string | boolean>>
  winner?: string | null
  delta?: Record<string, number>
  [key: string]: unknown
}

export interface LabTriggerRunPayload {
  suite?: string
  dataset?: string
  scenarios?: string[] | string
  limit?: number
  no_cache?: boolean
}

export interface LabTriggerRunResponse {
  status: string
  cmd: string[]
  job_id?: string
  run_id?: string
}

export interface LabJob {
  job_id: string
  status: string // queued | running | succeeded | failed
  suite?: string | null
  dataset?: string | null
  scenarios?: string[]
  run_id?: string | null
  returncode?: number | null
  created_at?: string
  started_at?: string | null
  finished_at?: string | null
  error?: string | null
  log_tail?: string
}

export const labApi = {
  source: getLabSource,
  subscribeSource: subscribeLabSource,
  scenarios: () =>
    callOrFallback(
      () => labClient.get<LabScenario[]>('/api/lab/scenarios').then(r => r.data),
      () => MOCK_SCENARIOS,
    ),
  suites: () =>
    callOrFallback(
      () => labClient.get<string[]>('/api/lab/suites').then(r => r.data),
      () => MOCK_SUITES,
    ),
  datasets: () =>
    callOrFallback(
      () => labClient.get<LabDataset[]>('/api/lab/datasets').then(r => r.data),
      () => MOCK_DATASETS,
    ),
  runs: () =>
    callOrFallback(
      () => labClient.get<LabRunSummary[]>('/api/lab/runs').then(r => r.data),
      () => MOCK_RUNS,
    ),
  runDetail: (runId: string) =>
    callOrFallback(
      () => labClient.get<LabRunDetail>(`/api/lab/runs/${runId}`).then(r => r.data),
      () => MOCK_RUN_DETAILS[runId] ?? { ...MOCK_RUNS[0], run_id: runId },
    ),
  reportMarkdown: (runId: string) =>
    callOrFallback(
      () => labClient.get(`/api/lab/runs/${runId}/report.md`, { responseType: 'text' }).then(r => String(r.data)),
      () => buildMockReport(runId),
    ),
  compare: (baseline: string, candidate: string) =>
    callOrFallback(
      () =>
        labClient
          .get<LabCompareResult>('/api/lab/compare', { params: { baseline, candidate } })
          .then(r => r.data),
      () => buildMockCompare(baseline, candidate),
    ),
  triggerRun: (payload: LabTriggerRunPayload) =>
    callOrFallback(
      () => labClient.post<LabTriggerRunResponse>('/api/lab/runs', payload).then(r => r.data),
      () => buildMockTriggerResponse(payload),
    ),
  jobs: () =>
    callOrFallback(
      () => labClient.get<LabJob[]>('/api/lab/jobs').then(r => r.data),
      () => MOCK_JOBS,
    ),
  jobDetail: (jobId: string) =>
    callOrFallback(
      () => labClient.get<LabJob>(`/api/lab/jobs/${jobId}`).then(r => r.data),
      () => buildMockJob(jobId),
    ),
}
