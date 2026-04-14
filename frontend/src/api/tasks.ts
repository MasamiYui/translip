import api from './client'
import type { CreateTaskRequest, Task, TaskListResponse } from '../types'

export const tasksApi = {
  list: (params?: {
    status?: string
    target_lang?: string
    search?: string
    page?: number
    size?: number
  }) => api.get<TaskListResponse>('/api/tasks', { params }).then(r => r.data),

  get: (id: string) => api.get<Task>(`/api/tasks/${id}`).then(r => r.data),

  create: (req: CreateTaskRequest) =>
    api.post<Task>('/api/tasks', req).then(r => r.data),

  delete: (id: string, deleteArtifacts = false) =>
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
}
