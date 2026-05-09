import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, Search } from 'lucide-react'
import { atomicToolsApi } from '../api/atomic-tools'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { useI18n } from '../i18n/useI18n'
import type { AtomicJobRead } from '../types/atomic-tools'

export function AtomicJobListPage() {
  const { t, formatDuration, formatRelativeTime } = useI18n()
  const [statusFilter, setStatusFilter] = useState('all')
  const [toolFilter, setToolFilter] = useState('all')
  const [search, setSearch] = useState('')

  const { data: tools = [] } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })
  const { data } = useQuery({
    queryKey: ['atomic-tool-jobs', statusFilter, toolFilter, search],
    queryFn: () =>
      atomicToolsApi.listJobs({
        status: statusFilter === 'all' ? undefined : statusFilter,
        tool_id: toolFilter === 'all' ? undefined : toolFilter,
        search: search.trim() || undefined,
        size: 50,
      }),
    refetchInterval: 3000,
  })

  const toolLabels = useMemo(() => {
    return new Map(tools.map(tool => [tool.tool_id, tool.name_zh]))
  }, [tools])

  const jobs = data?.items ?? []
  const statusOptions = [
    { value: 'all', label: t.tasks.filters.all },
    { value: 'running', label: t.status.running },
    { value: 'pending', label: t.status.pending },
    { value: 'completed', label: t.status.completed },
    { value: 'failed', label: t.status.failed },
    { value: 'cancelled', label: t.status.cancelled },
    { value: 'interrupted', label: t.status.interrupted },
  ]

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
            onChange={event => setSearch(event.target.value)}
            placeholder={t.atomicJobs.filters.searchPlaceholder}
            className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
          />
        </label>
        <div className="flex flex-wrap gap-1.5">
          {statusOptions.map(option => (
            <button
              key={option.value}
              type="button"
              onClick={() => setStatusFilter(option.value)}
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
          onChange={event => setToolFilter(event.target.value)}
          className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs font-semibold text-[#6b7280] outline-none transition-all hover:bg-[#f9fafb] hover:text-[#374151] focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
        >
          <option value="all">{t.atomicJobs.filters.allTools}</option>
          {tools.map(tool => (
            <option key={tool.tool_id} value={tool.tool_id}>
              {tool.name_zh}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
        {jobs.length === 0 ? (
          <div className="py-16 text-center text-sm text-[#9ca3af]">{t.atomicJobs.empty}</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#f3f4f6] text-left">
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.tool}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.status}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.input}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.progress}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.artifacts}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.duration}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.createdAt}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <AtomicJobRow
                  key={job.job_id}
                  job={job}
                  toolName={toolLabels.get(job.tool_id) ?? job.tool_name}
                  formatDuration={formatDuration}
                  formatRelativeTime={formatRelativeTime}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="text-xs font-semibold text-[#9ca3af]">{t.atomicJobs.totalCount(data?.total ?? 0)}</div>
    </PageContainer>
  )
}

function AtomicJobRow({
  job,
  toolName,
  formatDuration,
  formatRelativeTime,
}: {
  job: AtomicJobRead
  toolName: string
  formatDuration: (seconds: number | undefined) => string
  formatRelativeTime: (date: string) => string
}) {
  const inputName = job.input_files[0]?.filename ?? job.job_id

  return (
    <tr className="border-b border-[#f9fafb] transition-colors last:border-0 hover:bg-[#fafafa]">
      <td className="px-4 py-3.5">
        <Link to={`/tools/jobs/${job.job_id}`} className="font-semibold text-[#111827] hover:text-[#3b5bdb]">
          {toolName}
        </Link>
        <div className="mt-0.5 text-[11px] text-[#9ca3af]">{job.job_id}</div>
      </td>
      <td className="px-4 py-3.5">
        <StatusBadge status={job.status} size="sm" />
      </td>
      <td className="max-w-[220px] truncate px-4 py-3.5 text-[#6b7280]">{inputName}</td>
      <td className="px-4 py-3.5">
        <div className="flex min-w-28 items-center gap-2">
          <ProgressBar value={job.progress_percent} size="sm" className="flex-1" />
          <span className="w-8 text-right text-xs tabular-nums text-[#6b7280]">{job.progress_percent.toFixed(0)}%</span>
        </div>
      </td>
      <td className="px-4 py-3.5 tabular-nums text-[#6b7280]">{job.artifact_count}</td>
      <td className="px-4 py-3.5 text-[#6b7280]">{formatDuration(job.elapsed_sec ?? undefined)}</td>
      <td className="px-4 py-3.5 text-[#9ca3af]">{formatRelativeTime(job.created_at)}</td>
    </tr>
  )
}
