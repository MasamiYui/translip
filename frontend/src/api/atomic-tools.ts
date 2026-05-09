import api from './client'
import type {
  ArtifactInfo,
  AtomicJob,
  AtomicJobDetail,
  AtomicJobListResponse,
  AtomicJobRead,
  FileUploadResponse,
  ToolInfo,
} from '../types/atomic-tools'

export const atomicToolsApi = {
  listTools: () => api.get<ToolInfo[]>('/api/atomic-tools/tools').then(r => r.data),

  listJobs: (params?: {
    status?: string
    tool_id?: string
    search?: string
    page?: number
    size?: number
  }) => api.get<AtomicJobListResponse>('/api/atomic-tools/jobs', { params }).then(r => r.data),

  listRecentJobs: (limit = 5) =>
    api.get<AtomicJobRead[]>('/api/atomic-tools/jobs/recent', { params: { limit } }).then(r => r.data),

  getJobDetail: (jobId: string) =>
    api.get<AtomicJobDetail>(`/api/atomic-tools/jobs/${jobId}`).then(r => r.data),

  deleteJob: (jobId: string, deleteArtifacts = true) =>
    api
      .delete(`/api/atomic-tools/jobs/${jobId}`, { params: { delete_artifacts: deleteArtifacts } })
      .then(r => r.data),

  rerunJob: (jobId: string) =>
    api.post<AtomicJob>(`/api/atomic-tools/jobs/${jobId}/rerun`).then(r => r.data),

  upload: (file: File, onProgress?: (percent: number) => void) => {
    const formData = new FormData()
    formData.append('file', file)
    return api
      .post<FileUploadResponse>('/api/atomic-tools/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: event => {
          if (onProgress && event.total) {
            onProgress((event.loaded / event.total) * 100)
          }
        },
      })
      .then(r => r.data)
  },

  run: (toolId: string, params: Record<string, unknown>) =>
    api.post<AtomicJob>(`/api/atomic-tools/${toolId}/run`, params).then(r => r.data),

  getJob: (toolId: string, jobId: string) =>
    api.get<AtomicJob>(`/api/atomic-tools/${toolId}/jobs/${jobId}`).then(r => r.data),

  listArtifacts: (toolId: string, jobId: string) =>
    api.get<ArtifactInfo[]>(`/api/atomic-tools/${toolId}/jobs/${jobId}/artifacts`).then(r => r.data),

  getArtifactUrl: (toolId: string, jobId: string, filename: string) =>
    `/api/atomic-tools/${toolId}/jobs/${jobId}/artifacts/${encodeURIComponent(filename)}`,
}
