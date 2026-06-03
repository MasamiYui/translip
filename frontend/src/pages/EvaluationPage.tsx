import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Gauge, ChevronRight, Search } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { evaluationApi, type Analysis } from '../api/evaluation'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { StatusBadge } from '../components/shared/StatusBadge'
import { Pagination } from '../components/shared/Pagination'
import { useI18n } from '../i18n/useI18n'
import type { Task } from '../types'

const DEFAULT_PAGE_SIZE = 20

export function EvaluationPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

  const { data, isLoading } = useQuery({
    queryKey: ['evaluation-tasks', statusFilter, search, page, pageSize],
    queryFn: () =>
      tasksApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search || undefined,
        page,
        size: pageSize,
      }),
  })

  const items: Task[] = data?.items ?? []
  const total = data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, pageCount)

  const statusOptions = [
    { value: 'all', label: t.evaluation.filters.all },
    { value: 'succeeded', label: t.evaluation.filters.succeeded },
    { value: 'partial_success', label: t.evaluation.filters.partial_success },
    { value: 'failed', label: t.evaluation.filters.failed },
  ]

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5 px-6 py-6`}>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#3b5bdb]/10 text-[#3b5bdb]">
          <Gauge size={20} />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-[#111827]">{t.evaluation.title}</h1>
          <p className="text-sm text-[#6b7280]">{t.evaluation.subtitle}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[200px] max-w-xs flex-1">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" />
          <input
            value={search}
            onChange={e => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder={t.evaluation.searchPlaceholder}
            className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
            aria-label={t.evaluation.searchPlaceholder}
          />
        </div>
        <div className="flex gap-1.5">
          {statusOptions.map(opt => (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                setStatusFilter(opt.value)
                setPage(1)
              }}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                statusFilter === opt.value
                  ? 'bg-[#3b5bdb] text-white shadow-sm'
                  : 'border border-[#e5e7eb] bg-white text-[#6b7280] hover:bg-[#f9fafb] hover:text-[#374151]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
        {isLoading ? (
          <div className="p-8 text-center text-sm text-[#9ca3af]">{t.evaluation.loadingReport}</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-sm text-[#9ca3af]">
            {search || statusFilter !== 'all' ? t.evaluation.noMatches : t.evaluation.noTasks}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#f3f4f6] bg-[#f9fafb] text-left">
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">
                  {t.evaluation.pickTask}
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">
                  {t.evaluation.status}
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">
                  {t.evaluation.score}
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">
                  {t.evaluation.createdAt}
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map(task => (
                <EvaluationRow key={task.id} task={task} onClick={() => navigate(`/evaluation/${task.id}`)} />
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
        onPageSizeChange={size => {
          setPageSize(size)
          setPage(1)
        }}
      />
    </PageContainer>
  )
}

function EvaluationRow({ task, onClick }: { task: Task; onClick: () => void }) {
  const { formatRelativeTime } = useI18n()

  return (
    <tr
      onClick={onClick}
      className="cursor-pointer border-b border-[#f9fafb] transition-colors last:border-0 hover:bg-[#fafafa]"
    >
      <td className="px-4 py-3.5">
        <div className="font-medium text-[#111827]">{task.name}</div>
        <div className="text-xs text-[#9ca3af]">
          {task.source_lang} → {task.target_lang} · {task.id}
        </div>
      </td>
      <td className="px-4 py-3.5">
        <StatusBadge status={task.status} size="sm" />
      </td>
      <td className="px-4 py-3.5">
        <SummaryBadge task={task} />
      </td>
      <td
        className="px-4 py-3.5 text-xs text-[#6b7280]"
        title={new Date(task.created_at).toLocaleString()}
      >
        {formatRelativeTime(task.created_at)}
      </td>
      <td className="px-4 py-3.5 text-right text-[#cbd5e1]">
        <ChevronRight size={16} className="inline" />
      </td>
    </tr>
  )
}

const SUMMARY_ELIGIBLE_STATUSES = new Set(['succeeded', 'partial_success', 'completed'])

function SummaryBadge({ task }: { task: Task }) {
  const { t } = useI18n()
  const enabled = SUMMARY_ELIGIBLE_STATUSES.has(task.status)

  const { data, isLoading } = useQuery({
    queryKey: ['evaluation-summary', task.id],
    queryFn: () => evaluationApi.list(task.id),
    enabled,
    staleTime: 60 * 1000,
  })

  if (!enabled) {
    return <span className="text-xs text-[#cbd5e1]">—</span>
  }
  if (isLoading) {
    return <span className="text-xs text-[#9ca3af]">{t.evaluation.summary.loading}</span>
  }

  const latest = pickLatestSucceeded(data ?? [])
  if (!latest || !latest.result) {
    return <span className="text-xs text-[#9ca3af]">{t.evaluation.summary.noReport}</span>
  }

  const score = typeof latest.result.score === 'number' ? Math.round(latest.result.score) : null
  const problemCount = latest.result.problem_segment_count ?? 0
  const scoreColor =
    score === null
      ? 'bg-[#f3f4f6] text-[#6b7280]'
      : score >= 85
        ? 'bg-[#ecfdf5] text-[#047857]'
        : score >= 70
          ? 'bg-[#fffbeb] text-[#b45309]'
          : 'bg-[#fef2f2] text-[#b91c1c]'
  const problemColor =
    problemCount === 0
      ? 'bg-[#ecfdf5] text-[#047857]'
      : problemCount < 5
        ? 'bg-[#fffbeb] text-[#b45309]'
        : 'bg-[#fef2f2] text-[#b91c1c]'

  return (
    <div className="flex items-center gap-1.5">
      {score !== null ? (
        <span
          className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums ${scoreColor}`}
          title={t.evaluation.summary.score}
        >
          {score}
        </span>
      ) : null}
      <span
        className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${problemColor}`}
      >
        {problemCount === 0 ? t.evaluation.summary.noProblems : t.evaluation.summary.problems(problemCount)}
      </span>
    </div>
  )
}

function pickLatestSucceeded(analyses: Analysis[]): Analysis | undefined {
  const succeeded = analyses.filter(a => a.status === 'succeeded' && a.result)
  if (succeeded.length === 0) return undefined
  return succeeded.reduce((acc, cur) => {
    const accTime = new Date(acc.finished_at ?? acc.updated_at ?? acc.created_at).getTime()
    const curTime = new Date(cur.finished_at ?? cur.updated_at ?? cur.created_at).getTime()
    return curTime > accTime ? cur : acc
  })
}
