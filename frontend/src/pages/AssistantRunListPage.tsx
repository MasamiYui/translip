import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Bot, RotateCw, Search, Square, Trash2 } from 'lucide-react'
import { assistantApi } from '../api/assistant'
import { FALLBACK_TOOL_ICON, TOOL_META } from '../components/assistant/toolMeta'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { Pagination } from '../components/shared/Pagination'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { useAssistantStore } from '../stores/assistantStore'
import { useI18n } from '../i18n/useI18n'
import type { AssistantRunListResponse, AssistantRunSummary } from '../types/assistant'

const DEFAULT_PAGE_SIZE = 20
const POLL_INTERVAL_MS = 3000
const RUNNING_STATES = new Set<AssistantRunSummary['status']>(['running', 'pending'])

function runListRefetchInterval(query: {
  state: { data?: AssistantRunListResponse }
}): number | false {
  const items = query.state.data?.items ?? []
  return items.some(run => RUNNING_STATES.has(run.status)) ? POLL_INTERVAL_MS : false
}

export function AssistantRunListPage() {
  const { t, formatDuration, formatRelativeTime } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const openAssistant = useAssistantStore(s => s.open)
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

  const { data, isLoading } = useQuery({
    queryKey: ['assistant-runs', statusFilter, search, page, pageSize],
    queryFn: () =>
      assistantApi.listRuns({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search.trim() || undefined,
        page,
        size: pageSize,
      }),
    refetchInterval: runListRefetchInterval,
    refetchIntervalInBackground: false,
  })

  const rerunMutation = useMutation({
    mutationFn: (runId: string) => assistantApi.rerunRun(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistant-runs'] }),
  })
  const cancelMutation = useMutation({
    mutationFn: (runId: string) => assistantApi.cancelRun(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistant-runs'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (runId: string) => assistantApi.deleteRun(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistant-runs'] }),
  })

  const runs = data?.items ?? []
  const total = data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, pageCount)
  const statusOptions = [
    { value: 'all', label: t.tasks.filters.all },
    { value: 'running', label: t.status.running },
    { value: 'pending', label: t.status.pending },
    { value: 'completed', label: t.status.completed },
    { value: 'failed', label: t.status.failed },
    { value: 'cancelled', label: t.status.cancelled },
  ]

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[#111827]">{t.assistantRuns.title}</h1>
          <p className="mt-0.5 text-sm text-[#9ca3af]">{t.assistantRuns.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={openAssistant}
          className="flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
        >
          <Bot size={15} />
          {t.assistantRuns.openAssistant}
          <ArrowRight size={13} />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="relative min-w-[200px] max-w-xs flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" size={13} />
          <input
            value={search}
            onChange={event => { setSearch(event.target.value); setPage(1) }}
            placeholder={t.assistantRuns.searchPlaceholder}
            className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
          />
        </label>
        <div className="flex flex-wrap gap-1.5">
          {statusOptions.map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => { setStatusFilter(option.value); setPage(1) }}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                statusFilter === option.value
                  ? 'bg-[#3b5bdb] text-white shadow-sm'
                  : 'border border-[#e5e7eb] bg-white text-[#6b7280] hover:bg-[#f9fafb] hover:text-[#374151]'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        {isLoading ? (
          <div className="py-16 text-center text-sm text-[#9ca3af]">{t.tasks.loading}</div>
        ) : runs.length === 0 ? (
          <div className="py-16 text-center text-sm text-[#9ca3af]">{t.assistantRuns.empty}</div>
        ) : (
          <table className="w-full min-w-[560px] md:min-w-[720px] lg:min-w-[960px] text-sm">
            <thead>
              <tr className="border-b border-[#f3f4f6] text-left">
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.assistantRuns.columns.request}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.assistantRuns.columns.status}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden lg:table-cell">{t.assistantRuns.columns.chain}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] w-36 whitespace-nowrap">{t.assistantRuns.columns.progress}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden md:table-cell">{t.assistantRuns.columns.createdAt}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] w-28 whitespace-nowrap">{t.assistantRuns.columns.actions}</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => (
                <RunRow
                  key={run.run_id}
                  run={run}
                  onClick={() => navigate(`/assistant/tasks/${run.run_id}`)}
                  onRerun={() => rerunMutation.mutate(run.run_id)}
                  onCancel={() => cancelMutation.mutate(run.run_id)}
                  onDelete={() => {
                    if (confirm(t.assistantRuns.deleteConfirm)) deleteMutation.mutate(run.run_id)
                  }}
                  formatRelativeTime={formatRelativeTime}
                  formatDuration={formatDuration}
                  labels={{
                    view: t.assistantRuns.view,
                    rerun: t.assistantRuns.rerun,
                    cancel: t.assistantRuns.cancel,
                    delete: t.assistantRuns.delete,
                    steps: t.assistantRuns.stepsProgress,
                  }}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Pagination
        page={safePage}
        pageCount={pageCount}
        onChange={setPage}
        total={total}
        pageSize={pageSize}
        onPageSizeChange={size => { setPageSize(size); setPage(1) }}
      />
    </PageContainer>
  )
}

function RunRow({
  run,
  onClick,
  onRerun,
  onCancel,
  onDelete,
  formatRelativeTime,
  formatDuration,
  labels,
}: {
  run: AssistantRunSummary
  onClick: () => void
  onRerun: () => void
  onCancel: () => void
  onDelete: () => void
  formatRelativeTime: (date: string) => string
  formatDuration: (seconds: number | undefined) => string
  labels: {
    view: string
    rerun: string
    cancel: string
    delete: string
    steps: (done: number, total: number) => string
  }
}) {
  const isRunning = run.status === 'running' || run.status === 'pending'
  const percent = run.step_count > 0 ? (run.completed_steps / run.step_count) * 100 : 0

  return (
    <tr
      className={`cursor-pointer border-b border-[#f9fafb] transition-colors last:border-0 hover:bg-[#fafafa] ${
        run.status === 'running' ? 'border-l-2 border-l-[#3b5bdb]' : ''
      }`}
    >
      <td className="px-4 py-3.5" onClick={onClick}>
        <div className="max-w-[280px] truncate font-medium text-[#111827]" title={run.message}>
          {run.message || run.summary || run.run_id}
        </div>
        <div className="mt-0.5 max-w-[280px] truncate text-[11px] text-[#9ca3af]">{run.run_id}</div>
      </td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <StatusBadge status={run.status} size="sm" />
      </td>
      <td className="px-4 py-3.5 hidden lg:table-cell" onClick={onClick}>
        <div className="flex items-center gap-1">
          {run.tools.slice(0, 5).map((id, i) => {
            const Icon = TOOL_META[id]?.icon ?? FALLBACK_TOOL_ICON
            return (
              <span
                key={`${id}-${i}`}
                title={id}
                className="flex h-6 w-6 items-center justify-center rounded-md bg-[#3b5bdb]/10 text-[#3b5bdb]"
              >
                <Icon size={13} />
              </span>
            )
          })}
          {run.tools.length > 5 && (
            <span className="text-[11px] text-[#9ca3af]">+{run.tools.length - 5}</span>
          )}
        </div>
      </td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <div className="flex items-center gap-2">
          <ProgressBar value={percent} size="sm" className="flex-1" />
          <span className="w-12 text-right text-[11px] tabular-nums text-[#6b7280]">
            {labels.steps(run.completed_steps, run.step_count)}
          </span>
        </div>
        {run.elapsed_sec != null && (
          <div className="mt-0.5 text-[10px] tabular-nums text-[#9ca3af]">
            {formatDuration(run.elapsed_sec)}
          </div>
        )}
      </td>
      <td className="px-4 py-3.5 text-[#9ca3af] whitespace-nowrap hidden md:table-cell" onClick={onClick}>
        {formatRelativeTime(run.created_at)}
      </td>
      <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-0.5">
          {isRunning ? (
            <button
              onClick={onCancel}
              className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-amber-50 hover:text-amber-600"
              title={labels.cancel}
              aria-label={labels.cancel}
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              onClick={onRerun}
              className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-[#eef2ff] hover:text-[#3b5bdb]"
              title={labels.rerun}
              aria-label={labels.rerun}
            >
              <RotateCw size={14} />
            </button>
          )}
          <button
            onClick={onDelete}
            className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-red-50 hover:text-red-600"
            title={labels.delete}
            aria-label={labels.delete}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
}
