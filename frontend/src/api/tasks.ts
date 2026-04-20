import api from './client'
import type { CreateTaskRequest, Task, TaskListResponse, WorkflowGraph } from '../types'

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

  createSubtitlePreview: (id: string, payload: SubtitlePreviewPayload) =>
    api.post(`/api/tasks/${id}/subtitle-preview`, payload).then(r => r.data),

  composeDelivery: (id: string, payload: DeliveryComposePayload) =>
    api.post(`/api/tasks/${id}/delivery-compose`, payload).then(r => r.data),
}
