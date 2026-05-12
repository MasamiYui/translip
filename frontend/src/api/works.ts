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

// TMDb Types
export interface TMDbSearchResult {
  id: string
  tmdb_id: number
  type: string
  title: string
  original_title: string
  year: string | null
  poster_path: string | null
  backdrop_path: string | null
  overview: string
  popularity: number
  vote_average: number
  media_type: 'movie' | 'tv'
  number_of_seasons?: number
}

export interface TMDbCastMember {
  id: number
  actor_name: string
  character_name: string
  profile_path: string | null
  order: number
}

export interface TMDbDetails extends TMDbSearchResult {
  release_date?: string
  first_air_date?: string
  runtime?: number
  genres: string[]
  origin_country: string[]
  cast: TMDbCastMember[]
}

export interface TMDbConfigResponse {
  ok: boolean
  api_key_v3_set: boolean
  api_key_v4_set: boolean
  default_language: string
}

export interface TMDbSearchResponse {
  ok: boolean
  results: TMDbSearchResult[]
  error?: string
}

export interface TMDbDetailsResponse {
  ok: boolean
  details?: TMDbDetails
  error?: string
}

export interface TMDbImportResponse {
  ok: boolean
  work?: Work
  imported_cast?: { persona_id: string; name: string; actor_name?: string; avatar_url?: string | null }[]
  skipped_cast?: { tmdb_id: number | string | null; reason: string }[]
  error?: string
}

// Cast Import Types
export interface CastPreviewMember {
  tmdb_id: number
  actor_name: string
  character_name: string
  profile_path: string | null
  profile_url: string
  order: number
}

export interface CastPreviewResponse {
  ok: boolean
  cast: CastPreviewMember[]
  error?: string
}

export interface CastImportResponse {
  ok: boolean
  imported: { persona_id: string; name: string; actor_name?: string; avatar_url?: string | null }[]
  skipped: { tmdb_id: number; reason: string }[]
  work_id: string
  error?: string
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

  // TMDb Integration
  tmdbSearch: (query: string, mediaType?: 'movie' | 'tv') =>
    api
      .get<TMDbSearchResponse>('/api/works/tmdb/search', {
        params: { q: query, media_type: mediaType },
      })
      .then(r => r.data),

  tmdbDetails: (tmdbId: number, mediaType: 'movie' | 'tv') =>
    api
      .get<TMDbDetailsResponse>(`/api/works/tmdb/${tmdbId}`, { params: { media_type: mediaType } })
      .then(r => r.data),

  tmdbImport: (tmdbId: number, mediaType: 'movie' | 'tv') =>
    api
      .post<TMDbImportResponse>('/api/works/from-tmdb', { tmdb_id: tmdbId, media_type: mediaType })
      .then(r => r.data),

  tmdbGetConfig: () => api.get<TMDbConfigResponse>('/api/config/tmdb').then(r => r.data),

  tmdbSaveConfig: (payload: { api_key_v3?: string; api_key_v4?: string; default_language?: string }) =>
    api.post<{ ok: boolean; message: string }>('/api/config/tmdb', payload).then(r => r.data),

  // Cast Import
  getCastPreview: (workId: string, tmdbId: number, mediaType: 'movie' | 'tv') =>
    api
      .get<CastPreviewResponse>(`/api/works/${workId}/cast-preview`, {
        params: { tmdb_id: tmdbId, media_type: mediaType },
      })
      .then(r => r.data),

  importCast: (workId: string, tmdbIds: number[]) =>
    api
      .post<CastImportResponse>(`/api/works/${workId}/import-cast`, { tmdb_ids: tmdbIds })
      .then(r => r.data),
}
