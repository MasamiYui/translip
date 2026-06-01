import api from './client'
import type {
  CacheBreakdown,
  CacheCleanupResult,
  CacheMigrateTask,
  ConfigPreset,
  FsBrowseResponse,
  MissingModelsResponse,
  ModelDownloadJob,
  SystemInfo,
  TaskConfig,
} from '../types'

export type GlobalConfigUpdate = {
  [K in keyof TaskConfig]?: TaskConfig[K] | null
}

export const configApi = {
  getDefaults: () => api.get('/api/config/defaults').then(r => r.data),
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
  browse: (path?: string, showHidden = false) =>
    api
      .get<FsBrowseResponse>('/api/system/browse', {
        params: { path: path || undefined, show_hidden: showHidden },
      })
      .then(r => r.data),
  getHfToken: () =>
    api.get<{ ok: boolean; hf_token_set: boolean }>('/api/system/hf-token').then(r => r.data),
  saveHfToken: (hf_token: string) =>
    api
      .post<{ ok: boolean; hf_token_set: boolean }>('/api/system/hf-token', { hf_token })
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
