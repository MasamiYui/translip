import api from './client'

export type AnalysisStatus = 'pending' | 'running' | 'succeeded' | 'failed'

export interface AnalysisSummary {
  score?: number | null
  status?: string | null
  problem_segment_count?: number
  issue_counts?: Record<string, number>
  judge_status?: string
}

export interface Analysis {
  id: string
  task_id: string
  analysis_type: string
  status: AnalysisStatus
  target_lang: string
  source_lang: string
  params: { run_translation_judge?: boolean }
  result?: AnalysisSummary | null
  report_path?: string | null
  error_message?: string | null
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  elapsed_sec?: number | null
}

export interface DubQaGate {
  id: string
  label: string
  status: string
  value: unknown
  threshold: string
}

export interface DubQaScorecard {
  version: string
  status: string
  score: number
  reasons: string[]
  metrics: Record<string, unknown>
  gates: DubQaGate[]
}

export type IssueTag =
  | 'undubbed'
  | 'timbre_mismatch'
  | 'dropout'
  | 'pacing'
  | 'low_intelligibility'
  | 'inaudible'
  | 'bad_translation'

export type SegmentSeverity = 'P0' | 'P1' | 'P2' | 'ok'

export interface DubQaSegment {
  segment_id: string
  speaker_id?: string | null
  start?: number | null
  end?: number | null
  duration?: number | null
  source_text: string
  target_text: string
  backread_text: string
  dub_audio_path?: string | null
  placed: boolean
  mix_status?: string | null
  fit_strategy?: string | null
  overall_status?: string | null
  speaker_status?: string | null
  intelligibility_status?: string | null
  duration_status?: string | null
  speaker_similarity?: number | null
  text_similarity?: number | null
  duration_ratio?: number | null
  // Timeline-fit detail (original window vs the dub's actual placed footprint).
  source_duration_sec?: number | null
  generated_duration_sec?: number | null
  fitted_duration_sec?: number | null
  placement_start?: number | null
  placement_end?: number | null
  subtitle_coverage_ratio?: number | null
  qa_flags: string[]
  dropout_token_count: number
  dropout_total_tokens: number
  dropout_ratio: number
  judge_score?: number | null
  judge_adequacy?: number | null
  judge_fluency?: number | null
  judge_reason?: string | null
  issue_tags: IssueTag[]
  severity: SegmentSeverity
}

export interface DubQaSummary {
  segment_count: number
  problem_segment_count: number
  issue_counts: Record<IssueTag, number>
  severity_counts: Record<string, number>
  skip_reason_counts: Record<string, number>
  coverage: {
    translated_count: number
    dubbed_count: number
    undubbed_count: number
    coverage_ratio: number | null
  }
  dropout: { affected_count: number; average_ratio: number | null }
  translation_judge?: {
    status: string
    scored_count: number
    failed_count: number
    average_score: number | null
    min_score: number | null
  } | null
  judge_status: string
}

export type RemediationAction =
  | 'rewrite_translation'
  | 'resynthesize'
  | 'switch_voice'
  | 'switch_tts_backend'
  | 'refit_timeline'
  | 'retranslate'
  | 'fill_undubbed'
  | 'manual_review'

export type RemediationExecutor = 'repair' | 'editor' | 'render' | 'rerun' | 'manual'

export interface RemediationEvidence {
  duration_ratio?: number | null
  fit_strategy?: string | null
  speaker_similarity?: number | null
  text_similarity?: number | null
  dropout_ratio?: number | null
  subtitle_coverage_ratio?: number | null
  judge_score?: number | null
}

export interface RemediationKnob {
  stage: string
  params: Record<string, string>
}

export interface SegmentDirective {
  segment_id: string
  start?: number | null
  speaker_id?: string | null
  severity: SegmentSeverity
  defects: IssueTag[]
  primary_action: RemediationAction
  executor: RemediationExecutor
  repair_action?: string | null
  auto_fixable: boolean
  gain: number
  knob?: RemediationKnob | null
  evidence: RemediationEvidence
}

export interface RemediationActionGroup {
  action: RemediationAction
  executor: RemediationExecutor
  repair_action?: string | null
  auto_fixable: boolean
  knob?: RemediationKnob | null
  segment_ids: string[]
  count: number
  total_gain: number
}

export interface DeliveryBlocker {
  gate: string
  status: string
  segment_ids: string[]
  count: number
}

export interface RemediationPlan {
  version: string
  summary: {
    problem_count: number
    auto_fixable_count: number
    manual_count: number
    recoverable_gain: number
    total_gain: number
  }
  actions: RemediationActionGroup[]
  next_best_actions: Array<{
    action: RemediationAction
    executor: RemediationExecutor
    count: number
    total_gain: number
    auto_fixable: boolean
  }>
  delivery_blockers: DeliveryBlocker[]
  repair_directive?: {
    segment_ids: string[]
    tts_backends: string[]
    include_risk: boolean
    attempts_per_item: number
  } | null
  segment_directives: Record<string, SegmentDirective>
}

export interface DubQaReport {
  version: string
  created_at: string
  target_lang: string
  source_lang: string
  scorecard: DubQaScorecard
  qa_summary: DubQaSummary
  segments: DubQaSegment[]
  remediation?: RemediationPlan | null
  input: Record<string, string | null>
}

export const ISSUE_TAGS: IssueTag[] = [
  'undubbed',
  'timbre_mismatch',
  'dropout',
  'pacing',
  'low_intelligibility',
  'inaudible',
  'bad_translation',
]

/** Build the artifact download/stream URL for a path relative to the task output root. */
export function taskArtifactUrl(taskId: string, relPath: string): string {
  const encoded = relPath
    .split('/')
    .map(encodeURIComponent)
    .join('/')
  return `/api/tasks/${encodeURIComponent(taskId)}/artifacts/${encoded}?preview=true`
}

export function taskInputFileUrl(taskId: string): string {
  return `/api/tasks/${encodeURIComponent(taskId)}/input-file`
}

export interface AutoFixResult {
  before_score?: number | null
  after_score?: number | null
  before_problem_count?: number | null
  after_problem_count?: number | null
  repaired_count?: number
  requested_count?: number
  tts_backends?: string[]
  device?: string
  rolled_back?: boolean
  new_analysis_id?: string | null
}

export interface AutoFixJob extends Omit<Analysis, 'result'> {
  result?: AutoFixResult | null
}

export const evaluationApi = {
  list: (taskId: string) =>
    api.get<Analysis[]>(`/api/tasks/${taskId}/analyses`).then(r => r.data),

  autoFix: (taskId: string, body: { segment_ids?: string[]; tts_backends?: string[] }) =>
    api.post<AutoFixJob>(`/api/tasks/${taskId}/auto-fix`, body).then(r => r.data),

  getAutoFix: (taskId: string, jobId: string) =>
    api.get<AutoFixJob>(`/api/tasks/${taskId}/auto-fix/${jobId}`).then(r => r.data),

  get: (taskId: string, analysisId: string) =>
    api.get<Analysis>(`/api/tasks/${taskId}/analyses/${analysisId}`).then(r => r.data),

  create: (taskId: string, body: { run_translation_judge: boolean }) =>
    api.post<Analysis>(`/api/tasks/${taskId}/analyses/dub-qa`, body).then(r => r.data),

  getReport: (taskId: string, analysisId: string) =>
    api.get<DubQaReport>(`/api/tasks/${taskId}/analyses/${analysisId}/report`).then(r => r.data),

  remove: (taskId: string, analysisId: string) =>
    api.delete(`/api/tasks/${taskId}/analyses/${analysisId}`).then(r => r.data),
}
