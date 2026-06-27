import api from './client'
import type {
  CacheBreakdown,
  CacheCleanupResult,
  CacheMigrateTask,
  ConfigPreset,
  MissingModelsResponse,
  ModelDownloadJob,
  PickFileResult,
  SystemInfo,
  TaskConfig,
} from '../types'

export type GlobalConfigUpdate = {
  [K in keyof TaskConfig]?: TaskConfig[K] | null
}

export interface NarratorVoiceInfo {
  id: string
  name_zh: string
  name_en: string
  gender: string
}

export const configApi = {
  getDefaults: () => api.get('/api/config/defaults').then(r => r.data),
  narratorVoices: () =>
    api.get<NarratorVoiceInfo[]>('/api/config/narrator-voices').then(r => r.data),
  getGlobal: () => api.get<Partial<TaskConfig>>('/api/config/global').then(r => r.data),
  updateGlobal: (config: GlobalConfigUpdate) =>
    api.put<{ ok: boolean; config: Partial<TaskConfig> }>('/api/config/global', config).then(r => r.data),
  getPresets: () => api.get<ConfigPreset[]>('/api/config/presets').then(r => r.data),
  createPreset: (preset: Omit<ConfigPreset, 'id' | 'created_at' | 'updated_at'>) =>
    api.post<ConfigPreset>('/api/config/presets', preset).then(r => r.data),
  deletePreset: (id: number) =>
    api.delete(`/api/config/presets/${id}`).then(r => r.data),
}

export const systemApi = {
  getInfo: () => api.get<SystemInfo>('/api/system/info').then(r => r.data),
  probe: (path: string) =>
    api.get('/api/system/probe', { params: { path } }).then(r => r.data),
  pickFile: (initialPath?: string, prompt?: string) =>
    api
      .post<PickFileResult>('/api/system/pick-file', {
        initial_path: initialPath || undefined,
        prompt,
      })
      .then(r => r.data),
  getHfToken: () =>
    api.get<{ ok: boolean; hf_token_set: boolean }>('/api/system/hf-token').then(r => r.data),
  saveHfToken: (hf_token: string) =>
    api
      .post<{ ok: boolean; hf_token_set: boolean }>('/api/system/hf-token', { hf_token })
      .then(r => r.data),
  testHfToken: (hf_token?: string) =>
    api
      .post<{ ok: boolean; message: string }>('/api/system/hf-token/test', { hf_token })
      .then(r => r.data),
  getLlmKeys: () =>
    api
      .get<{
        ok: boolean
        providers: Record<string, boolean>
        base_urls: Record<string, string | null>
      }>('/api/system/llm-keys')
      .then(r => r.data),
  // Only submitted fields take effect (empty string clears); omit to keep as-is.
  saveLlmKey: (provider: string, update: { api_key?: string; base_url?: string }) =>
    api
      .post<{ ok: boolean; provider: string; set: boolean; base_url: string | null }>(
        '/api/system/llm-keys',
        { provider, ...update },
      )
      .then(r => r.data),
  testLlmKey: (provider: string, api_key?: string, base_url?: string) =>
    api
      .post<{ ok: boolean; provider: string; model: string; message: string }>(
        '/api/system/llm-keys/test',
        { provider, api_key, base_url },
      )
      .then(r => r.data),
}

export const modelsApi = {
  listMissing: () =>
    api.get<MissingModelsResponse>('/api/system/models/missing').then(r => r.data),
  downloadMissing: (keys?: string[]) =>
    api
      .post<ModelDownloadJob>('/api/system/models/download-missing', keys ? { keys } : {})
      .then(r => r.data),
  getJob: (jobId: string) =>
    api.get<ModelDownloadJob>(`/api/system/models/download/${jobId}`).then(r => r.data),
  cancelJob: (jobId: string) =>
    api
      .post<{ ok: boolean }>(`/api/system/models/download/${jobId}/cancel`)
      .then(r => r.data),
}

export const cacheApi = {
  getBreakdown: () =>
    api.get<CacheBreakdown>('/api/system/cache/breakdown').then(r => r.data),
  setDir: (target: string, createIfMissing = true) =>
    api
      .post<{ ok: boolean; cache_dir: string }>('/api/system/cache/set-dir', {
        target,
        create_if_missing: createIfMissing,
      })
      .then(r => r.data),
  resetDefault: () =>
    api.post<{ ok: boolean; cache_dir: string }>('/api/system/cache/reset-default').then(r => r.data),
  removeItem: (key: string) =>
    api
      .delete<{ ok: boolean; key: string; freed_bytes: number }>(
        `/api/system/cache/item`,
        { params: { key } },
      )
      .then(r => r.data),
  cleanup: (keys: string[]) =>
    api.post<CacheCleanupResult>('/api/system/cache/cleanup', { keys }).then(r => r.data),
  startMigrate: (target: string, mode: 'move' | 'copy' = 'move', switchAfter = true) =>
    api
      .post<CacheMigrateTask>('/api/system/cache/migrate', {
        target,
        mode,
        switch_after: switchAfter,
      })
      .then(r => r.data),
  pollMigrate: (taskId: string) =>
    api.get<CacheMigrateTask>(`/api/system/cache/migrate/${taskId}`).then(r => r.data),
  cancelMigrate: (taskId: string) =>
    api
      .post<{ ok: boolean }>(`/api/system/cache/migrate/${taskId}/cancel`)
      .then(r => r.data),
}
