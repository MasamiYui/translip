import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { PlusCircle, Search, Trash2, RotateCcw } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { formatDuration, formatRelativeTime, LANG_LABELS } from '../lib/utils'
import type { Task } from '../types'

const STATUS_OPTIONS = [
  { value: 'all', label: '全部' },
  { value: 'running', label: '运行中' },
  { value: 'pending', label: '等待中' },
  { value: 'succeeded', label: '已完成' },
  { value: 'failed', label: '失败' },
]

export function TaskListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const { data, isLoading } = useQuery({
    queryKey: ['tasks', statusFilter, search, page],
    queryFn: () =>
      tasksApi.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search || undefined,
        page,
        size: 20,
      }),
    refetchInterval: 5000,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => tasksApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pageCount = Math.ceil(total / 20)

  function toggleSelect(id: string) {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleBulkDelete() {
    if (!confirm(`确定删除 ${selected.size} 个任务？`)) return
    for (const id of selected) {
      await deleteMutation.mutateAsync(id)
    }
    setSelected(new Set())
  }

  return (
    <div className="max-w-5xl space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">任务列表</h1>
        <Link
          to="/tasks/new"
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <PlusCircle size={15} />
          新建任务
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="搜索任务名称..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
          />
        </div>
        <div className="flex gap-2">
          {STATUS_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => { setStatusFilter(opt.value); setPage(1) }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                statusFilter === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {selected.size > 0 && (
          <button
            onClick={handleBulkDelete}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 transition-colors"
          >
            <Trash2 size={13} />
            删除 {selected.size} 项
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        {isLoading ? (
          <div className="py-16 text-center text-slate-400 text-sm">加载中...</div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm">没有找到匹配的任务</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left">
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={selected.size === items.length && items.length > 0}
                    onChange={e => setSelected(e.target.checked ? new Set(items.map(t => t.id)) : new Set())}
                    className="rounded"
                  />
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">名称</th>
                <th className="px-4 py-3 font-medium text-slate-500">状态</th>
                <th className="px-4 py-3 font-medium text-slate-500 w-32">进度</th>
                <th className="px-4 py-3 font-medium text-slate-500">语言</th>
                <th className="px-4 py-3 font-medium text-slate-500">耗时</th>
                <th className="px-4 py-3 font-medium text-slate-500">创建时间</th>
                <th className="px-4 py-3 font-medium text-slate-500 w-20">操作</th>
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
                    if (confirm('确定删除此任务？')) deleteMutation.mutate(task.id)
                  }}
                  onClick={() => navigate(`/tasks/${task.id}`)}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {pageCount > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>共 {total} 条</span>
          <div className="flex gap-1">
            {Array.from({ length: pageCount }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={`w-8 h-8 rounded-lg font-medium ${
                  p === page ? 'bg-blue-600 text-white' : 'hover:bg-slate-100 text-slate-600'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TaskRow({ task, selected, onSelect, onDelete, onClick }: {
  task: Task
  selected: boolean
  onSelect: () => void
  onDelete: () => void
  onClick: () => void
}) {
  return (
    <tr
      className={`border-b border-slate-50 hover:bg-slate-50 cursor-pointer group ${
        task.status === 'running' ? 'border-l-2 border-l-blue-500' : ''
      }`}
    >
      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onSelect}
          className="rounded"
        />
      </td>
      <td className="px-4 py-3 font-medium text-slate-900" onClick={onClick}>
        {task.name}
        <div className="text-xs text-slate-400 font-normal mt-0.5 truncate max-w-[200px]">
          {task.id}
        </div>
      </td>
      <td className="px-4 py-3" onClick={onClick}>
        <StatusBadge status={task.status} size="sm" />
      </td>
      <td className="px-4 py-3" onClick={onClick}>
        <div className="flex items-center gap-2">
          <ProgressBar value={task.overall_progress} size="sm" className="flex-1" />
          <span className="text-xs text-slate-500 w-8 text-right">{task.overall_progress.toFixed(0)}%</span>
        </div>
      </td>
      <td className="px-4 py-3 text-slate-600" onClick={onClick}>
        {task.source_lang} → {task.target_lang}
      </td>
      <td className="px-4 py-3 text-slate-600" onClick={onClick}>
        {formatDuration(task.elapsed_sec)}
      </td>
      <td className="px-4 py-3 text-slate-400" onClick={onClick}>
        {formatRelativeTime(task.created_at)}
      </td>
      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
        <button
          onClick={onDelete}
          className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-50 text-red-400 hover:text-red-600 transition-all"
          title="删除"
        >
          <Trash2 size={14} />
        </button>
      </td>
    </tr>
  )
}
