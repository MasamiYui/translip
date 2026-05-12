import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, ChevronDown, Loader2, Sparkles } from 'lucide-react'
import { worksApi } from '../../api/works'

interface TaskWorkBindingControlProps {
  taskId: string
  workId?: string | null
  episodeLabel?: string | null
  currentWorkTitle?: string | null
  fallbackLabel?: string | null
  compact?: boolean
  triggerTestId?: string
  onSaved?: () => void
}

export function TaskWorkBindingControl({
  taskId,
  workId,
  episodeLabel,
  currentWorkTitle,
  fallbackLabel,
  compact = false,
  triggerTestId = 'task-work-binding-trigger',
  onSaved,
}: TaskWorkBindingControlProps) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [draftWorkId, setDraftWorkId] = useState(workId ?? '')
  const [draftEpisode, setDraftEpisode] = useState(episodeLabel ?? '')

  const worksQuery = useQuery({
    queryKey: ['works'],
    queryFn: () => worksApi.list(),
    enabled: open,
  })

  const inferMutation = useMutation({
    mutationFn: () => worksApi.inferFromTask(taskId),
  })

  const bindMutation = useMutation({
    mutationFn: () =>
      worksApi.bindTask(taskId, {
        work_id: draftWorkId || null,
        episode_label: draftWorkId ? draftEpisode.trim() || null : null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task', taskId] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
      onSaved?.()
      setOpen(false)
    },
  })

  const works = useMemo(() => worksQuery.data?.works ?? [], [worksQuery.data?.works])
  const selectedWork = useMemo(
    () => works.find(work => work.id === workId) ?? null,
    [workId, works],
  )
  const displayTitle = currentWorkTitle || selectedWork?.title || null
  const triggerText = workId
    ? `${displayTitle ?? '已绑定作品'}${episodeLabel ? ` · ${episodeLabel}` : ''}`
    : fallbackLabel || '作品：未绑定'
  const candidates = (inferMutation.data?.candidates ?? [])
    .filter(candidate => candidate.work_id)
    .slice(0, 3)

  function applyCandidate(workId: string | null, episode?: string | null) {
    if (!workId) return
    setDraftWorkId(workId)
    setDraftEpisode(episode ?? '')
  }

  function togglePanel() {
    const next = !open
    if (next) {
      setDraftWorkId(workId ?? '')
      setDraftEpisode(episodeLabel ?? '')
    }
    setOpen(next)
  }

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        onClick={togglePanel}
        data-testid={triggerTestId}
        className={`inline-flex min-w-0 items-center gap-1.5 rounded-md border font-medium transition-colors ${
          compact
            ? 'max-w-[320px] border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700 hover:border-indigo-200 hover:bg-indigo-100'
            : 'border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50'
        }`}
        title={triggerText}
      >
        <BookOpen className={compact ? 'h-3 w-3 shrink-0' : 'h-3.5 w-3.5 shrink-0'} />
        <span className="truncate">{triggerText}</span>
        <ChevronDown className={compact ? 'h-3 w-3 shrink-0' : 'h-3.5 w-3.5 shrink-0'} />
      </button>

      {open && (
        <div
          className="absolute left-0 top-full z-30 mt-2 w-[340px] rounded-lg border border-slate-200 bg-white p-3 text-left shadow-xl"
          data-testid="task-work-binding-panel"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-slate-900">绑定作品</div>
            <button
              type="button"
              onClick={() => inferMutation.mutate()}
              disabled={inferMutation.isPending}
              className="inline-flex h-7 items-center gap-1 rounded-md border border-slate-200 px-2 text-[11px] font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              {inferMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Sparkles className="h-3 w-3" />
              )}
              智能推荐
            </button>
          </div>

          <label className="block text-[11px] font-medium text-slate-500" htmlFor={`work-select-${taskId}`}>
            作品
          </label>
          <select
            id={`work-select-${taskId}`}
            value={draftWorkId}
            onChange={event => setDraftWorkId(event.currentTarget.value)}
            className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            data-testid="task-work-select"
          >
            <option value="">不绑定作品</option>
            {works.map(work => (
              <option key={work.id} value={work.id}>
                {work.title}
              </option>
            ))}
          </select>

          <label className="mt-3 block text-[11px] font-medium text-slate-500" htmlFor={`episode-label-${taskId}`}>
            集数 / 期数
          </label>
          <input
            id={`episode-label-${taskId}`}
            value={draftEpisode}
            onChange={event => setDraftEpisode(event.currentTarget.value)}
            placeholder="E03 / S01E02"
            className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2 py-2 text-sm text-slate-800 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            data-testid="task-work-episode-input"
          />

          {worksQuery.isLoading && (
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              加载作品列表
            </div>
          )}

          {candidates.length > 0 && (
            <div className="mt-3 space-y-1.5">
              <div className="text-[11px] font-medium text-slate-500">推荐</div>
              {candidates.map(candidate => (
                <button
                  key={`${candidate.work_id}-${candidate.episode_label ?? ''}`}
                  type="button"
                  onClick={() => applyCandidate(candidate.work_id, candidate.episode_label)}
                  className="flex w-full items-center justify-between gap-2 rounded-md border border-indigo-100 bg-indigo-50 px-2 py-1.5 text-left text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  <span className="min-w-0 truncate">
                    {candidate.title}
                    {candidate.episode_label ? ` · ${candidate.episode_label}` : ''}
                  </span>
                  <span className="shrink-0 font-mono text-[10px]">
                    {Math.round((candidate.score ?? 0) * 100)}%
                  </span>
                </button>
              ))}
            </div>
          )}

          {bindMutation.isError && (
            <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-2 py-1.5 text-xs text-rose-700">
              保存失败，请稍后重试。
            </div>
          )}

          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => bindMutation.mutate()}
              disabled={bindMutation.isPending || worksQuery.isLoading}
              className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
            >
              {bindMutation.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
              保存绑定
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
