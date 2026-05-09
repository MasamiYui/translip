import api from './client'
import type {
  CreateTaskRequest,
  GlobalExportFromTaskResponse,
  GlobalPersona,
  GlobalPersonaImportResponse,
  GlobalPersonasListResponse,
  ImportFromGlobalResponse,
  PersonaApplyPreviewResponse,
  PersonaHistoryStatus,
  PersonaSuggestCandidate,
  SpeakerPersona,
  SpeakerPersonasBundle,
  SpeakerReferenceClip,
  SpeakerReviewApplyResponse,
  SpeakerReviewDecisionPayload,
  SpeakerReviewResponse,
  SpeakerSimilarityMatrix,
  SuggestFromGlobalResponse,
  Task,
  TaskListResponse,
  WorkflowGraph,
} from '../types'

export type PersonaBulkTemplate = 'role_abc' | 'protagonist' | 'by_index'

export type PersonaCreatePayload = {
  name: string
  bindings?: string[]
  color?: string | null
  avatar_emoji?: string | null
  note?: string | null
  role?: string | null
  gender?: string | null
  age_hint?: string | null
  pinned?: boolean
  is_target?: boolean
  confidence?: number | null
  tts_voice_id?: string | null
  tts_skip?: boolean
  force?: boolean
}

export type PersonaUpdatePayload = Partial<{
  name: string
  color: string | null
  avatar_emoji: string | null
  note: string | null
  aliases: string[]
  role: string | null
  gender: string | null
  age_hint: string | null
  pinned: boolean
  is_target: boolean
  confidence: number | null
  tts_voice_id: string | null
  tts_skip: boolean
  force: boolean
}>

export type SubtitlePreviewPayload = {
  input_video_path: string
  subtitle_path: string
  output_path?: string
  font_family: string
  font_size: number
  primary_color: string
  outline_color: string
  outline_width: number
  position: 'top' | 'bottom'
  margin_v: number
  bold: boolean
  start_sec?: number
  duration_sec: number
}

export type DeliveryComposePayload = {
  subtitle_mode: 'none' | 'chinese_only' | 'english_only' | 'bilingual'
  subtitle_source: 'ocr' | 'asr'
  bilingual_export_strategy: 'auto_standard_bilingual' | 'preserve_hard_subtitles_add_english' | 'clean_video_rebuild_bilingual'
  font_family: string
  font_size: number
  primary_color: string
  outline_color: string
  outline_width: number
  position: 'top' | 'bottom'
  margin_v: number
  bold: boolean
  bilingual_chinese_position: 'top' | 'bottom'
  bilingual_english_position: 'top' | 'bottom'
  export_preview: boolean
  export_dub: boolean
}

const DELIVERY_COMPOSE_TIMEOUT_MS = 10 * 60 * 1000

export const tasksApi = {
  list: (params?: {
    status?: string
    target_lang?: string
    search?: string
    page?: number
    size?: number
  }) => api.get<TaskListResponse>('/api/tasks', { params }).then(r => r.data),

  get: (id: string) => api.get<Task>(`/api/tasks/${id}`).then(r => r.data),

  getGraph: (id: string) =>
    api.get<WorkflowGraph>(`/api/tasks/${id}/graph`).then(r => r.data),

  create: (req: CreateTaskRequest) =>
    api.post<Task>('/api/tasks', req).then(r => r.data),

  delete: (id: string, deleteArtifacts = true) =>
    api.delete(`/api/tasks/${id}`, { params: { delete_artifacts: deleteArtifacts } }).then(r => r.data),

  rerun: (id: string, fromStage: string) =>
    api.post<Task>(`/api/tasks/${id}/rerun`, { from_stage: fromStage }).then(r => r.data),

  stop: (id: string) =>
    api.post(`/api/tasks/${id}/stop`).then(r => r.data),

  getStatus: (id: string) =>
    api.get(`/api/tasks/${id}/status`).then(r => r.data),

  getManifest: (id: string) =>
    api.get(`/api/tasks/${id}/manifest`).then(r => r.data),

  getStageManifest: (id: string, stage: string) =>
    api.get(`/api/tasks/${id}/stages/${stage}/manifest`).then(r => r.data),

  listArtifacts: (id: string) =>
    api.get(`/api/tasks/${id}/artifacts`).then(r => r.data),

  getDelivery: (id: string) =>
    api.get(`/api/tasks/${id}/delivery`).then(r => r.data),

  getSpeakerReview: (id: string) =>
    api.get<SpeakerReviewResponse>(`/api/tasks/${id}/speaker-review`).then(r => r.data),

  saveSpeakerReviewDecision: (id: string, payload: SpeakerReviewDecisionPayload) =>
    api.post(`/api/tasks/${id}/speaker-review/decisions`, payload).then(r => r.data),

  deleteSpeakerReviewDecision: (id: string, itemId: string) =>
    api
      .delete(`/api/tasks/${id}/speaker-review/decisions/${encodeURIComponent(itemId)}`)
      .then(r => r.data),

  applySpeakerReviewDecisions: (id: string) =>
    api.post<SpeakerReviewApplyResponse>(`/api/tasks/${id}/speaker-review/apply`).then(r => r.data),

  getSpeakerSimilarity: (id: string) =>
    api.get<SpeakerSimilarityMatrix>(`/api/tasks/${id}/speaker-review/similarity`).then(r => r.data),

  getSpeakerReferenceClips: (id: string, label: string) =>
    api
      .get<{ speaker_label: string; best_clip_id: string | null; clips: SpeakerReferenceClip[] }>(
        `/api/tasks/${id}/speaker-review/speakers/${encodeURIComponent(label)}/reference-clips`,
      )
      .then(r => r.data),

  listSpeakerPersonas: (id: string) =>
    api.get<SpeakerPersonasBundle>(`/api/tasks/${id}/speaker-review/personas`).then(r => r.data),

  createSpeakerPersona: (id: string, payload: PersonaCreatePayload) =>
    api
      .post<{ ok: boolean; persona: SpeakerPersona; personas: SpeakerPersonasBundle }>(
        `/api/tasks/${id}/speaker-review/personas`,
        payload,
      )
      .then(r => r.data),

  updateSpeakerPersona: (id: string, personaId: string, payload: PersonaUpdatePayload) =>
    api
      .patch<{ ok: boolean; persona: SpeakerPersona; personas: SpeakerPersonasBundle }>(
        `/api/tasks/${id}/speaker-review/personas/${encodeURIComponent(personaId)}`,
        payload,
      )
      .then(r => r.data),

  deleteSpeakerPersona: (id: string, personaId: string) =>
    api
      .delete<{ ok: boolean; personas: SpeakerPersonasBundle }>(
        `/api/tasks/${id}/speaker-review/personas/${encodeURIComponent(personaId)}`,
      )
      .then(r => r.data),

  bindSpeakerPersona: (id: string, personaId: string, speaker: string) =>
    api
      .post<{ ok: boolean; persona: SpeakerPersona; personas: SpeakerPersonasBundle }>(
        `/api/tasks/${id}/speaker-review/personas/${encodeURIComponent(personaId)}/bind`,
        { speaker },
      )
      .then(r => r.data),

  unbindSpeakerPersona: (id: string, personaId: string, speaker: string) =>
    api
      .post<{ ok: boolean; persona: SpeakerPersona; personas: SpeakerPersonasBundle }>(
        `/api/tasks/${id}/speaker-review/personas/${encodeURIComponent(personaId)}/unbind`,
        { speaker },
      )
      .then(r => r.data),

  bulkCreateSpeakerPersonas: (id: string, template: PersonaBulkTemplate) =>
    api
      .post<{ ok: boolean; created: SpeakerPersona[]; personas: SpeakerPersonasBundle }>(
        `/api/tasks/${id}/speaker-review/personas/bulk`,
        { template },
      )
      .then(r => r.data),

  suggestSpeakerPersonas: (id: string, speakers?: string[]) =>
    api
      .post<{ ok: boolean; suggestions: Record<string, PersonaSuggestCandidate[]> }>(
        `/api/tasks/${id}/speaker-review/personas/suggest`,
        { speakers: speakers ?? null },
      )
      .then(r => r.data),

  undoSpeakerPersonas: (id: string) =>
    api
      .post<{
        ok: boolean
        reverted: Record<string, unknown> | null
        personas: SpeakerPersonasBundle
        history?: PersonaHistoryStatus
      }>(`/api/tasks/${id}/speaker-review/personas/undo`)
      .then(r => r.data),

  redoSpeakerPersonas: (id: string) =>
    api
      .post<{
        ok: boolean
        replayed: Record<string, unknown> | null
        personas: SpeakerPersonasBundle
        history?: PersonaHistoryStatus
      }>(`/api/tasks/${id}/speaker-review/personas/redo`)
      .then(r => r.data),

  getSpeakerPersonasHistory: (id: string) =>
    api
      .get<{ ok: boolean; history: PersonaHistoryStatus }>(
        `/api/tasks/${id}/speaker-review/personas/history`,
      )
      .then(r => r.data),

  previewSpeakerReviewApply: (id: string) =>
    api
      .post<PersonaApplyPreviewResponse>(`/api/tasks/${id}/speaker-review/apply-preview`)
      .then(r => r.data),

  listGlobalPersonas: () =>
    api.get<GlobalPersonasListResponse>(`/api/global-personas`).then(r => r.data),

  importGlobalPersonas: (payload: { personas: GlobalPersona[]; mode?: 'merge' | 'replace' }) =>
    api
      .post<GlobalPersonaImportResponse>(`/api/global-personas/import`, payload)
      .then(r => r.data),

  deleteGlobalPersona: (personaId: string) =>
    api
      .delete<{ ok: boolean; personas: GlobalPersona[] }>(
        `/api/global-personas/${personaId}`,
      )
      .then(r => r.data),

  exportTaskPersonasToGlobal: (id: string, payload: { overwrite?: boolean } = {}) =>
    api
      .post<GlobalExportFromTaskResponse>(
        `/api/tasks/${id}/speaker-review/global-personas/export-from-task`,
        { overwrite: payload.overwrite ?? true },
      )
      .then(r => r.data),

  importPersonasFromGlobal: (
    id: string,
    payload: { persona_ids: string[]; bindings_by_id?: Record<string, string[]> },
  ) =>
    api
      .post<ImportFromGlobalResponse>(
        `/api/tasks/${id}/speaker-review/personas/import-from-global`,
        payload,
      )
      .then(r => r.data),

  suggestPersonasFromGlobal: (
    id: string,
    payload: { speakers?: Array<{ speaker_label: string; gender?: string | null; role?: string | null }> } = {},
  ) =>
    api
      .post<SuggestFromGlobalResponse>(
        `/api/tasks/${id}/speaker-review/personas/suggest-from-global`,
        payload,
      )
      .then(r => r.data),

  createSubtitlePreview: (id: string, payload: SubtitlePreviewPayload) =>
    api.post(`/api/tasks/${id}/subtitle-preview`, payload).then(r => r.data),

  composeDelivery: (id: string, payload: DeliveryComposePayload) =>
    api.post(`/api/tasks/${id}/delivery-compose`, payload, { timeout: DELIVERY_COMPOSE_TIMEOUT_MS }).then(r => r.data),
}
