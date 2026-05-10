import api from './client'
import type {
  GlobalPersona,
  Work,
  WorkInferCandidate,
  WorkType,
  WorksListResponse,
} from '../types'

export interface CreateWorkPayload {
  title: string
  type: string
  year?: number | null
  aliases?: string[]
  cover_emoji?: string | null
  color?: string | null
  note?: string | null
  tags?: string[]
}

export type PatchWorkPayload = Partial<CreateWorkPayload>

export interface BindTaskWorkPayload {
  work_id: string | null
  episode_label?: string | null
}

export interface InferWorkResponse {
  ok: boolean
  task_id: string
  candidates: WorkInferCandidate[]
}

export interface AutoBindWorkResponse {
  ok: boolean
  bound: boolean
  work_id?: string | null
  episode_label?: string | null
  candidates: WorkInferCandidate[]
}

export const worksApi = {
  list: (q?: string) =>
    api
      .get<WorksListResponse>(`/api/works`, { params: q ? { q } : undefined })
      .then(r => r.data),

  create: (payload: CreateWorkPayload) =>
    api.post<{ ok: boolean; work: Work }>(`/api/works`, payload).then(r => r.data),

  update: (workId: string, patch: PatchWorkPayload) =>
    api.patch<{ ok: boolean; work: Work }>(`/api/works/${workId}`, patch).then(r => r.data),

  remove: (
    workId: string,
    options: { reassignTo?: string | null; cascade?: boolean } = {},
  ) => {
    const params: Record<string, string> = {}
    if (options.reassignTo) params.reassign_to = options.reassignTo
    if (options.cascade) params.cascade = 'true'
    return api
      .delete<{ ok: boolean; reassigned: number; deleted_personas: number }>(
        `/api/works/${workId}`,
        { params },
      )
      .then(r => r.data)
  },

  listPersonas: (workId: string) =>
    api
      .get<{ ok: boolean; personas: GlobalPersona[] }>(`/api/works/${workId}/personas`)
      .then(r => r.data),

  movePersonas: (workId: string, personaIds: string[]) =>
    api
      .post<{ ok: boolean; moved: string[] }>(
        `/api/works/${workId}/personas/move`,
        { persona_ids: personaIds },
      )
      .then(r => r.data),

  bindTask: (taskId: string, payload: BindTaskWorkPayload) =>
    api
      .post<{ ok: boolean; task: { id: string; work_id: string | null; episode_label: string | null } }>(
        `/api/works/bind-task/${taskId}`,
        payload,
      )
      .then(r => r.data),

  inferFromTask: (taskId: string) =>
    api.post<InferWorkResponse>(`/api/works/infer-from-task/${taskId}`).then(r => r.data),

  autoBindTask: (taskId: string) =>
    api.post<AutoBindWorkResponse>(`/api/works/auto-bind-task/${taskId}`).then(r => r.data),

  listTypes: () =>
    api.get<{ ok: boolean; types: WorkType[] }>(`/api/work-types`).then(r => r.data),

  addCustomType: (payload: { key: string; label_zh: string; label_en: string }) =>
    api.post<{ ok: boolean; types: WorkType[] }>(`/api/work-types`, payload).then(r => r.data),

  removeCustomType: (key: string) =>
    api.delete<{ ok: boolean; types: WorkType[] }>(`/api/work-types/${key}`).then(r => r.data),
}
