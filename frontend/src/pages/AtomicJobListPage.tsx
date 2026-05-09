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

const STATUS_FILTERS = ['all', 'pending', 'running', 'completed', 'failed', 'cancelled', 'interrupted'] as const

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

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[#111827]">{t.atomicJobs.title}</h1>
          <p className="mt-1 text-sm leading-relaxed text-[#6b7280]">{t.atomicJobs.description}</p>
        </div>
        <Link
          to="/tools"
          className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-xs font-semibold text-[#3b5bdb] transition-all hover:bg-[#f0f3ff]"
        >
          {t.atomicJobs.library}
          <ArrowRight size={13} />
        </Link>
      </div>

      <div className="grid gap-3 rounded-xl border border-[#e5e7eb] bg-white p-4 md:grid-cols-[1fr_180px_180px]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" size={15} />
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder={t.atomicJobs.filters.searchPlaceholder}
            className="h-10 w-full rounded-lg border border-[#e5e7eb] bg-white pl-9 pr-3 text-sm text-[#374151] outline-none transition-colors focus:border-[#3b5bdb]"
          />
        </label>
        <select
          aria-label={t.atomicJobs.columns.status}
          value={statusFilter}
          onChange={event => setStatusFilter(event.target.value)}
          className="h-10 rounded-lg border border-[#e5e7eb] bg-white px-3 text-sm text-[#374151] outline-none focus:border-[#3b5bdb]"
        >
          <option value="all">{t.atomicJobs.filters.allStatuses}</option>
          {STATUS_FILTERS.filter(status => status !== 'all').map(status => (
            <option key={status} value={status}>
              {t.status[status]}
            </option>
          ))}
        </select>
        <select
          aria-label={t.atomicJobs.columns.tool}
          value={toolFilter}
          onChange={event => setToolFilter(event.target.value)}
          className="h-10 rounded-lg border border-[#e5e7eb] bg-white px-3 text-sm text-[#374151] outline-none focus:border-[#3b5bdb]"
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
