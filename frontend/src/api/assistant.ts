import api from './client'
import type {
  AssistantPlan,
  AssistantRunListResponse,
  AvailableFileRef,
  ConversationTurn,
  PlanResult,
  RunState,
} from '../types/assistant'

export const assistantApi = {
  plan: (
    message: string,
    fileIds: string[],
    filenames: string[],
    history: ConversationTurn[] = [],
    availableFiles: AvailableFileRef[] = [],
  ) =>
    api
      .post<PlanResult>('/api/assistant/plan', {
        message,
        file_ids: fileIds,
        filenames,
        history,
        available_files: availableFiles,
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

  listRuns: (params?: { status?: string; search?: string; page?: number; size?: number }) =>
    api.get<AssistantRunListResponse>('/api/assistant/runs', { params }).then(r => r.data),

  rerunRun: (runId: string) =>
    api.post<{ run_id: string }>(`/api/assistant/runs/${runId}/rerun`).then(r => r.data),

  deleteRun: (runId: string) =>
    api.delete<{ ok: boolean }>(`/api/assistant/runs/${runId}`).then(r => r.data),
}
