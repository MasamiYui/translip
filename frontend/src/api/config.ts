import api from './client'
import type { ConfigPreset, SystemInfo } from '../types'

export const configApi = {
  getDefaults: () => api.get('/api/config/defaults').then(r => r.data),
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
}
