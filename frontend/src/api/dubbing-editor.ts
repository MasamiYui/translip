import api from './client'

const apiClient = api

export interface DubbingEditorIssue {
  issue_id: string
  type: string
  severity: 'P0' | 'P1' | 'P2'
  unit_id: string
  character_id: string
  title: string
  description: string
  status: 'open' | 'resolved' | 'ignored'
  time_sec: number
}

export interface DubbingEditorClip {
  clip_id: string
  audio_path: string | null
  audio_artifact_path: string | null
  duration: number | null
  backend: string
  mix_status: string
  fit_strategy: string
}

export interface DubbingEditorUnit {
  unit_id: string
  source_segment_ids: string[]
  speaker_id: string
  character_id: string
  start: number
  end: number
  duration: number
  source_text: string
  target_text: string
  status: 'unreviewed' | 'needs_review' | 'approved' | 'locked' | 'ignored'
  issue_ids: string[]
  current_clip: DubbingEditorClip
  candidates: DubbingEditorCandidate[]
}

export interface DubbingEditorCandidate {
  candidate_id: string
  backend: string
  reference_path: string | null
  score: number | null
  duration: number | null
  audio_path: string | null
}

export interface DubbingEditorCharacter {
  character_id: string
  display_name: string
  speaker_ids: string[]
  review_status: 'passed' | 'needs_review' | 'blocked'
  risk_flags: string[]
  pitch_class: string
  pitch_hz: number | null
  stats: {
    segment_count: number
    speaker_failed_count: number
    overall_failed_count: number
    voice_mismatch_count: number
    speaker_failed_ratio: number
  }
  voice_lock: boolean
  default_voice: {
    backend: string
    reference_path: string | null
  }
}

export interface DubbingEditorSummary {
  unit_count: number
  character_count: number
  issue_count: number
  p0_count: number
  candidate_count: number
  approved_count: number
  char_review_count: number
  quality_status: string
  quality_score: number
}

export interface DubbingEditorProject {
  version: string
  created_at: string
  task_id: string
  target_lang: string
  status: string
  source_video_path: string
  artifact_paths: Record<string, string>
  quality_benchmark: {
    version: string
    status: string
    score: number
    reasons: string[]
    metrics: Record<string, number>
    gates: Array<{ id: string; label: string; status: string; value: unknown; threshold: string }>
  }
  characters: DubbingEditorCharacter[]
  units: DubbingEditorUnit[]
  issues: DubbingEditorIssue[]
  operations: Array<{
    op_id: string
    type: string
    target_id: string
    payload: Record<string, unknown>
    author: string
    created_at: string
  }>
  summary: DubbingEditorSummary
}

export interface WaveformData {
  track: string
  peaks: number[]
  duration_sec: number
  available: boolean
  pending?: boolean
}

export interface RenderRangeResult {
  ok: boolean
  artifact_path: string
  start_sec: number
  end_sec: number
  duration_sec: number
  url: string
}

export interface ClipPreviewResult {
  url: string
  start_sec: number
  end_sec: number
  duration_sec: number
}

export interface SynthesizeUnitResult {
  status: string
  unit_id: string
  message: string
}

export interface OperationResult {
  ok: boolean
  applied: number
  summary: DubbingEditorSummary
}

export const dubbingEditorApi = {
  getProject: (taskId: string): Promise<DubbingEditorProject> =>
    apiClient.get(`/api/tasks/${taskId}/dubbing-editor`).then(r => r.data),

  importProject: (taskId: string): Promise<DubbingEditorProject> =>
    apiClient.post(`/api/tasks/${taskId}/dubbing-editor/import`).then(r => r.data),

  saveOperations: (
    taskId: string,
    operations: Array<{ type: string; target_id: string; payload: Record<string, unknown> }>,
  ): Promise<OperationResult> =>
    apiClient.post(`/api/tasks/${taskId}/dubbing-editor/operations`, { operations }).then(r => r.data),

  renderRange: (taskId: string, startSec: number, endSec: number): Promise<RenderRangeResult> =>
    apiClient
      .post(`/api/tasks/${taskId}/dubbing-editor/render-range`, { start_sec: startSec, end_sec: endSec })
      .then(r => r.data),

  getWaveform: (taskId: string, track: string): Promise<WaveformData> =>
    apiClient.get(`/api/tasks/${taskId}/dubbing-editor/waveforms/${track}`).then(r => r.data),

  getClipPreview: (
    taskId: string,
    startSec: number,
    endSec: number,
    track: string = 'original',
  ): Promise<ClipPreviewResult> =>
    apiClient
      .get(`/api/tasks/${taskId}/dubbing-editor/clip-preview`, {
        params: { start_sec: startSec, end_sec: endSec, track },
      })
      .then(r => r.data),

  synthesizeUnit: (taskId: string, unitId: string): Promise<SynthesizeUnitResult> =>
    apiClient
      .post(`/api/tasks/${taskId}/dubbing-editor/synthesize-unit`, { unit_id: unitId })
      .then(r => r.data),
}
