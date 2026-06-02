import api from './client'
import type { OpenApiSpec } from '../types/openapi'

export const apiDocsApi = {
  // Served under /api so the Vite dev proxy forwards it (it only proxies /api),
  // matching production where the backend serves it directly.
  getSpec: () => api.get<OpenApiSpec>('/api/meta/openapi').then(r => r.data),
}
