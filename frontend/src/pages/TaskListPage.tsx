import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { PlusCircle, Search, Trash2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { Pagination } from '../components/shared/Pagination'
import type { Task } from '../types'
import { useI18n } from '../i18n/useI18n'

const DEFAULT_PAGE_SIZE = 20

export function TaskListPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['tasks', statusFilter, search, page, pageSize],
    queryFn: () =>
      tasksApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search || undefined,
        page,
        size: pageSize,
      }),
    refetchInterval: 5000,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => tasksApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, pageCount)
  const statusOptions = [
    { value: 'all', label: t.tasks.filters.all },
    { value: 'running', label: t.tasks.filters.running },
    { value: 'pending', label: t.tasks.filters.pending },
    { value: 'succeeded', label: t.tasks.filters.succeeded },
    { value: 'failed', label: t.tasks.filters.failed },
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
    if (!confirm(t.tasks.deleteConfirmMany(selected.size))) return
    for (const id of selected) {
      await deleteMutation.mutateAsync(id)
    }
    setSelected(new Set())
  }

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-[#111827]">{t.tasks.title}</h1>
        <Link
          to="/tasks/new"
          className="flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
        >
          <PlusCircle size={14} />
          {t.common.createTask}
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder={t.tasks.searchPlaceholder}
            className="w-full pl-9 pr-3 py-2 text-sm border border-[#e5e7eb] rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
          />
        </div>
        <div className="flex gap-1.5">
          {statusOptions.map(opt => (
            <button
              key={opt.value}
              onClick={() => { setStatusFilter(opt.value); setPage(1) }}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                statusFilter === opt.value
                  ? 'bg-[#3b5bdb] text-white shadow-sm'
                  : 'bg-white border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f9fafb] hover:text-[#374151]'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {selected.size > 0 && (
          <button
            onClick={handleBulkDelete}
            className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-600 transition-colors hover:bg-red-100"
          >
            <Trash2 size={12} />
            {t.tasks.deleteSelected(selected.size)}
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        {isLoading ? (
          <div className="py-16 text-center text-[#9ca3af] text-sm">{t.tasks.loading}</div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center text-[#9ca3af] text-sm">{t.tasks.noMatches}</div>
        ) : (
          <table className="w-full min-w-[520px] md:min-w-[680px] lg:min-w-[920px] text-sm">
            <thead>
              <tr className="border-b border-[#f3f4f6] text-left">
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={selected.size === items.length && items.length > 0}
                    onChange={e => setSelected(e.target.checked ? new Set(items.map(t => t.id)) : new Set())}
                    className="rounded"
                  />
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.tasks.columns.name}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.tasks.columns.status}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] w-32 whitespace-nowrap">{t.tasks.columns.progress}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden lg:table-cell">{t.tasks.columns.language}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden lg:table-cell">{t.tasks.columns.duration}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap hidden md:table-cell">{t.tasks.columns.createdAt}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] w-20 whitespace-nowrap">{t.tasks.columns.actions}</th>
              </tr>
            </thead>
            <tbody>
              {items.map(task => (
                <TaskRow
                  key={task.id}
                  task={task}
                  selected={selected.has(task.id)}
                  onSelect={() => toggleSelect(task.id)}
                  onDelete={() => {
                    if (confirm(t.tasks.deleteConfirmOne)) deleteMutation.mutate(task.id)
                  }}
                  onClick={() => navigate(`/tasks/${task.id}`)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
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

function TaskRow({ task, selected, onSelect, onDelete, onClick }: {
  task: Task
  selected: boolean
  onSelect: () => void
  onDelete: () => void
  onClick: () => void
}) {
  const { formatDuration, formatRelativeTime, getLanguageLabel, t } = useI18n()

  const elapsedSec = computeElapsedSec(task)

  return (
    <tr
      className={`border-b border-[#f9fafb] last:border-0 hover:bg-[#fafafa] cursor-pointer transition-colors ${
        task.status === 'running' ? 'border-l-2 border-l-[#3b5bdb]' : ''
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
        <div className="font-medium text-[#111827]">{task.name}</div>
        <div className="text-[11px] text-[#9ca3af] font-normal mt-0.5 truncate max-w-[200px]">
          {task.id}
        </div>
      </td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <StatusBadge status={task.status} size="sm" />
      </td>
      <td className="px-4 py-3.5" onClick={onClick}>
        <div className="flex items-center gap-2">
          <ProgressBar value={task.overall_progress} size="sm" className="flex-1" />
          <span className="text-xs text-[#6b7280] w-8 text-right tabular-nums">{task.overall_progress.toFixed(0)}%</span>
        </div>
      </td>
      <td className="px-4 py-3.5 text-[#6b7280] whitespace-nowrap hidden lg:table-cell" onClick={onClick}>
        {getLanguageLabel(task.source_lang)} → {getLanguageLabel(task.target_lang)}
      </td>
      <td className="px-4 py-3.5 text-[#6b7280] tabular-nums whitespace-nowrap hidden lg:table-cell" onClick={onClick}>
        {formatDuration(elapsedSec)}
      </td>
      <td className="px-4 py-3.5 text-[#9ca3af] whitespace-nowrap hidden md:table-cell" onClick={onClick}>
        {formatRelativeTime(task.created_at)}
      </td>
      <td className="px-4 py-3.5 text-right" onClick={e => e.stopPropagation()}>
        <button
          onClick={onDelete}
          className="inline-flex items-center justify-center rounded-lg p-1.5 text-[#9ca3af] transition-colors hover:bg-red-50 hover:text-red-600"
          title={t.tasks.deleteAction}
          aria-label={t.tasks.deleteAction}
        >
          <Trash2 size={14} />
        </button>
      </td>
    </tr>
  )
}

function computeElapsedSec(task: Task): number | undefined {
  if (typeof task.elapsed_sec === 'number') return task.elapsed_sec
  if (!task.started_at) return undefined
  const startMs = new Date(task.started_at).getTime()
  if (Number.isNaN(startMs)) return undefined
  const endMs = task.finished_at
    ? new Date(task.finished_at).getTime()
    : task.status === 'running'
      ? Date.now()
      : NaN
  if (Number.isNaN(endMs)) return undefined
  const diff = (endMs - startMs) / 1000
  return diff >= 0 ? diff : undefined
}
