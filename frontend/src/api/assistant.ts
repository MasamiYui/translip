import api from './client'
import type { AssistantPlan, RunState } from '../types/assistant'

export const assistantApi = {
  plan: (message: string, fileIds: string[], filenames: string[]) =>
    api
      .post<AssistantPlan>('/api/assistant/plan', {
        message,
        file_ids: fileIds,
        filenames,
      })
      .then(r => r.data),

  execute: (plan: AssistantPlan, fileIds: string[], conversationId?: string) =>
    api
      .post<{ run_id: string }>('/api/assistant/execute', {
        plan,
        file_ids: fileIds,
        conversation_id: conversationId ?? null,
      })
      .then(r => r.data),

  getRun: (runId: string) =>
    api.get<RunState>(`/api/assistant/runs/${runId}`).then(r => r.data),

  cancelRun: (runId: string) =>
    api.post<{ ok: boolean }>(`/api/assistant/runs/${runId}/cancel`).then(r => r.data),
}
