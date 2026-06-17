import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Download, RotateCw, Square, Trash2 } from 'lucide-react'
import { assistantApi } from '../api/assistant'
import { CallChainDiagram } from '../components/assistant/CallChainDiagram'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { StatusBadge } from '../components/shared/StatusBadge'
import { useI18n } from '../i18n/useI18n'
import { formatBytes } from '../lib/utils'
import type { AssistantPlan, RunState } from '../types/assistant'

function planFromRun(run: RunState): AssistantPlan {
  // Prefer the original plan (full rationale/params); fall back to a chain
  // synthesized from the run's steps so the diagram always renders.
  if (run.plan && run.plan.steps.length > 0) return run.plan
  return {
    summary: run.summary,
    steps: run.steps.map(s => ({
      id: s.id,
      tool_id: s.tool_id,
      title: s.title,
      rationale: '',
      params: {},
      inputs: {},
    })),
    edges: run.steps.slice(1).map((s, i) => ({ source: run.steps[i].id, target: s.id })),
  }
}

export function AssistantRunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const { t } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: run, isLoading, isError } = useQuery({
    queryKey: ['assistant-run-detail', runId],
    queryFn: () => assistantApi.getRun(runId as string),
    enabled: runId != null,
    refetchInterval: query => {
      const status = (query.state.data as RunState | undefined)?.status
      return status === 'running' || status === 'pending' ? 2000 : false
    },
  })

  const rerunMutation = useMutation({
    mutationFn: () => assistantApi.rerunRun(runId as string),
    onSuccess: data => {
      queryClient.invalidateQueries({ queryKey: ['assistant-runs'] })
      navigate(`/assistant/tasks/${data.run_id}`)
    },
  })
  const cancelMutation = useMutation({
    mutationFn: () => assistantApi.cancelRun(runId as string),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistant-run-detail', runId] }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => assistantApi.deleteRun(runId as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assistant-runs'] })
      navigate('/assistant/tasks')
    },
  })

  const artifacts = run?.steps.flatMap(s => s.artifacts) ?? []
  const isRunning = run?.status === 'running' || run?.status === 'pending'

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      <button
        type="button"
        onClick={() => navigate('/assistant/tasks')}
        className="inline-flex items-center gap-1.5 text-sm text-[#6b7280] transition-colors hover:text-[#3b5bdb]"
      >
        <ArrowLeft size={14} /> {t.assistantRuns.backToList}
      </button>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-[#9ca3af]">{t.tasks.loading}</div>
      ) : isError || !run ? (
        <div className="py-16 text-center text-sm text-[#9ca3af]">{t.assistantRuns.notFound}</div>
      ) : (
        <>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-xl font-bold text-[#111827]">{t.assistantRuns.detailTitle}</h1>
              <div className="mt-1 flex items-center gap-2">
                <StatusBadge status={run.status} size="sm" />
                <span className="text-xs text-[#9ca3af]">{run.run_id}</span>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {isRunning ? (
                <button
                  onClick={() => cancelMutation.mutate()}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#e4e9f0] px-3 py-1.5 text-[13px] text-[#6b7280] transition-colors hover:bg-amber-50 hover:text-amber-600"
                >
                  <Square size={13} /> {t.assistantRuns.cancel}
                </button>
              ) : (
                <button
                  onClick={() => rerunMutation.mutate()}
                  disabled={rerunMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[#e4e9f0] px-3 py-1.5 text-[13px] text-[#3b5bdb] transition-colors hover:bg-[#eef2ff] disabled:opacity-50"
                >
                  <RotateCw size={13} /> {t.assistantRuns.rerun}
                </button>
              )}
              <button
                onClick={() => {
                  if (confirm(t.assistantRuns.deleteConfirm)) deleteMutation.mutate()
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#e4e9f0] px-3 py-1.5 text-[13px] text-[#6b7280] transition-colors hover:bg-red-50 hover:text-red-600"
              >
                <Trash2 size={13} /> {t.assistantRuns.delete}
              </button>
            </div>
          </div>

          <section className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
            <div className="text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.assistantRuns.request}</div>
            <p className="mt-1 text-sm text-[#374151]">{run.message || run.summary || run.run_id}</p>
            {run.summary && run.summary !== run.message && (
              <p className="mt-1 text-[13px] text-[#6b7280]">{run.summary}</p>
            )}
          </section>

          <section className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
            <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.assistantRuns.columns.chain}</div>
            <div className="overflow-x-auto">
              <CallChainDiagram plan={planFromRun(run)} runState={run} orientation="horizontal" />
            </div>
          </section>

          {run.status === 'failed' && run.error_message && (
            <section className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide">{t.assistantRuns.errorTitle}</div>
              {run.error_message}
            </section>
          )}

          <section className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.assistantRuns.artifacts}</div>
            {artifacts.length === 0 ? (
              <p className="text-[13px] text-[#9ca3af]">{t.assistantRuns.noArtifacts}</p>
            ) : (
              <div className="flex flex-col gap-1.5">
                {artifacts.map(a => (
                  <a
                    key={a.download_url}
                    href={a.download_url}
                    download
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[#e4e9f0] px-2.5 py-1.5 text-[13px] text-[#3b5bdb] transition-colors hover:bg-[#f0f3ff]"
                  >
                    <Download size={13} />
                    <span className="truncate" title={a.filename}>{a.filename}</span>
                    <span className="ml-auto text-[11px] text-[#9ca3af]">{formatBytes(a.size_bytes)}</span>
                  </a>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </PageContainer>
  )
}
