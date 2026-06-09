import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, RotateCw, Search, Square, Trash2, X } from 'lucide-react'
import { atomicToolsApi } from '../api/atomic-tools'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { Pagination } from '../components/shared/Pagination'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { useI18n } from '../i18n/useI18n'
import type { AtomicJobRead } from '../types/atomic-tools'

const DEFAULT_PAGE_SIZE = 20

type BulkBanner =
  | { tone: 'success'; message: string }
  | { tone: 'warning'; message: string }
  | { tone: 'error'; message: string }

export function AtomicJobListPage() {
  const { t, formatDuration, formatRelativeTime } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('all')
  const [toolFilter, setToolFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkBanner, setBulkBanner] = useState<BulkBanner | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const { data: tools = [] } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })
  const { data, isLoading } = useQuery({
    queryKey: ['atomic-tool-jobs', statusFilter, toolFilter, search, page, pageSize],
    queryFn: () =>
      atomicToolsApi.listJobs({
        status: statusFilter === 'all' ? undefined : statusFilter,
        tool_id: toolFilter === 'all' ? undefined : toolFilter,
        search: search.trim() || undefined,
        page,
        size: pageSize,
      }),
    refetchInterval: 3000,
  })

  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => atomicToolsApi.deleteJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] }),
  })

  const rerunMutation = useMutation({
    mutationFn: (jobId: string) => atomicToolsApi.rerunJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] }),
  })

  const stopMutation = useMutation({
    mutationFn: (jobId: string) => atomicToolsApi.stopJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] }),
  })

  const toolLabels = useMemo(() => {
    return new Map(tools.map(tool => [tool.tool_id, tool.name_zh]))
  }, [tools])

  const jobs = data?.items ?? []
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
    { value: 'interrupted', label: t.status.interrupted },
  ]

  function toggleSelect(id: string) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleBulkDelete() {
    if (bulkDeleting) return
    if (!confirm(t.atomicJobs.deleteConfirmMany(selected.size))) return
    const ids = Array.from(selected)
    setBulkDeleting(true)
    setBulkBanner(null)
    const results = await Promise.allSettled(ids.map(id => atomicToolsApi.deleteJob(id)))
    const okCount = results.filter(r => r.status === 'fulfilled').length
    const failCount = results.length - okCount
    if (failCount === 0) {
      setBulkBanner({ tone: 'success', message: t.atomicJobs.bulkDeleteSuccess(okCount) })
    } else if (okCount === 0) {
      setBulkBanner({ tone: 'error', message: t.atomicJobs.bulkDeleteAllFailed(failCount) })
    } else {
      setBulkBanner({ tone: 'warning', message: t.atomicJobs.bulkDeletePartial(okCount, failCount) })
    }
    setSelected(new Set())
    setBulkDeleting(false)
    queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] })
  }

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-[#111827]">{t.atomicJobs.title}</h1>
        <Link
          to="/tools"
          className="flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
        >
          {t.atomicJobs.library}
          <ArrowRight size={13} />
        </Link>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="relative min-w-[200px] max-w-xs flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" size={13} />
          <input
            value={search}
            onChange={event => { setSearch(event.target.value); setPage(1) }}
            placeholder={t.atomicJobs.filters.searchPlaceholder}
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
        <select
          aria-label={t.atomicJobs.columns.tool}
          value={toolFilter}
          onChange={event => { setToolFilter(event.target.value); setPage(1) }}
          className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs font-semibold text-[#6b7280] outline-none transition-all hover:bg-[#f9fafb] hover:text-[#374151] focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
        >
          <option value="all">{t.atomicJobs.filters.allTools}</option>
          {tools.map(tool => (
            <option key={tool.tool_id} value={tool.tool_id}>
              {tool.name_zh}
            </option>
          ))}
        </select>
        {selected.size > 0 && (
          <button
            onClick={handleBulkDelete}
            disabled={bulkDeleting}
            aria-busy={bulkDeleting}
            className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-600 transition-colors hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 size={12} />
            {t.atomicJobs.deleteSelected(selected.size)}
          </button>
        )}
      </div>

      {bulkBanner && (
        <div
          role="status"
          aria-live="polite"
          className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-2.5 text-sm ${
            bulkBanner.tone === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
              : bulkBanner.tone === 'warning'
                ? 'border-amber-200 bg-amber-50 text-amber-700'
                : 'border-red-200 bg-red-50 text-red-600'
          }`}
        >
          <span>{bulkBanner.message}</span>
          <button
            type="button"
            onClick={() => setBulkBanner(null)}
            aria-label={t.atomicJobs.bulkDismissBanner}
            className="inline-flex h-6 w-6 items-center justify-center rounded hover:bg-black/5"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        {isLoading ? (
          <div className="py-16 text-center text-sm text-[#9ca3af]">{t.tasks.loading}</div>
        ) : jobs.length === 0 ? (
          <div className="py-16 text-center text-sm text-[#9ca3af]">{t.atomicJobs.empty}</div>
        ) : (
          <table className="w-full min-w-[520px] md:min-w-[700px] lg:min-w-[960px] text-sm">
            <thead>
              <tr className="border-b border-[#f3f4f6] text-left">
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={selected.size === jobs.length && jobs.length > 0}
                    onChange={e => setSelected(e.target.checked ? new Set(jobs.map(j => j.job_id)) : new Set())}
                    className="rounded accent-[#3b5bdb]"
                  />
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.atomicJobs.columns.tool}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.atomicJobs.columns.status}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden lg:table-cell">{t.atomicJobs.columns.input}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] w-32 whitespace-nowrap">{t.atomicJobs.columns.progress}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden lg:table-cell">{t.atomicJobs.columns.duration}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden md:table-cell">{t.atomicJobs.columns.createdAt}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] w-32 whitespace-nowrap">{t.atomicJobs.columns.actions}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <AtomicJobRow
                  key={job.job_id}
                  job={job}
                  toolName={toolLabels.get(job.tool_id) ?? job.tool_name}
                  selected={selected.has(job.job_id)}
                  onSelect={() => toggleSelect(job.job_id)}
                  onDelete={() => {
                    if (confirm(t.atomicJobs.deleteConfirm)) deleteMutation.mutate(job.job_id)
                  }}
                  onRerun={() => rerunMutation.mutate(job.job_id)}
                  onStop={() => stopMutation.mutate(job.job_id)}
                  onClick={() => navigate(`/tools/jobs/${job.job_id}`)}
                  formatDuration={formatDuration}
                  formatRelativeTime={formatRelativeTime}
                  rerunLabel={t.atomicJobs.rerun}
                  stopLabel={t.atomicJobs.stop}
                  deleteLabel={t.atomicJobs.deleteAction}
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
        onPageSizeChange={(size) => {
          setPageSize(size)
          setPage(1)
        }}
      />
    </PageContainer>
  )
}

function AtomicJobRow({
  job,
  toolName,
  selected,
  onSelect,
  onDelete,
  onRerun,
  onStop,
  onClick,
  formatDuration,
  formatRelativeTime,
  rerunLabel,
  stopLabel,
  deleteLabel,
}: {
  job: AtomicJobRead
  toolName: string
  selected: boolean
  onSelect: () => void
  onDelete: () => void
  onRerun: () => void
  onStop: () => void
  onClick: () => void
  formatDuration: (seconds: number | undefined) => string
  formatRelativeTime: (date: string) => string
  rerunLabel: string
  stopLabel: string
  deleteLabel: string
}) {
  const inputName = job.input_files[0]?.filename ?? job.job_id
  const isRunning = job.status === 'running' || job.status === 'pending'
  const canRerun = !isRunning

  return (
    <tr
      className={`cursor-pointer border-b border-[#f9fafb] transition-colors last:border-0 hover:bg-[#fafafa] ${
        job.status === 'running' ? 'border-l-2 border-l-[#3b5bdb]' : ''
      }`}
    >
      <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onSelect}
          className="rounded accent-[#3b5bdb]"
        />
      </td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <Link
          to={`/tools/jobs/${job.job_id}`}
          className="font-medium text-[#111827] hover:text-[#3b5bdb]"
          onClick={e => e.stopPropagation()}
        >
          {toolName}
        </Link>
        <div className="mt-0.5 max-w-[200px] truncate text-[11px] font-normal text-[#9ca3af]">{job.job_id}</div>
      </td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <StatusBadge status={job.status} size="sm" />
      </td>
      <td className="max-w-[220px] truncate px-4 py-3.5 text-[#6b7280] hidden lg:table-cell" onClick={onClick}>{inputName}</td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <div className="flex items-center gap-2">
          <ProgressBar value={job.progress_percent} size="sm" className="flex-1" />
          <span className="w-8 text-right text-xs tabular-nums text-[#6b7280]">{job.progress_percent.toFixed(0)}%</span>
        </div>
      </td>
      <td className="px-4 py-3.5 tabular-nums text-[#6b7280] whitespace-nowrap hidden lg:table-cell" onClick={onClick}>{formatDuration(job.elapsed_sec ?? undefined)}</td>
      <td className="px-4 py-3.5 text-[#9ca3af] whitespace-nowrap hidden md:table-cell" onClick={onClick}>{formatRelativeTime(job.created_at)}</td>
      <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-0.5">
          {isRunning ? (
            <button
              onClick={onStop}
              className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-amber-50 hover:text-amber-600"
              title={stopLabel}
              aria-label={stopLabel}
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              onClick={onRerun}
              disabled={!canRerun}
              className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-[#eef2ff] hover:text-[#3b5bdb] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-[#9ca3af]"
              title={rerunLabel}
              aria-label={rerunLabel}
            >
              <RotateCw size={14} />
            </button>
          )}
          <button
            onClick={onDelete}
            className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-red-50 hover:text-red-600"
            title={deleteLabel}
            aria-label={deleteLabel}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
}
