import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  HardDrive,
  Loader2,
  RefreshCw,
  RotateCcw,
  Trash2,
  X,
} from 'lucide-react'
import { cacheApi } from '../../api/config'
import { tasksApi } from '../../api/tasks'
import { ProgressBar } from '../shared/ProgressBar'
import { useI18n } from '../../i18n/useI18n'
import { formatBytes } from '../../lib/utils'
import type {
  CacheBreakdown,
  CacheBreakdownItem,
  CacheGroupKind,
  CacheMigrateTask,
  Task,
} from '../../types'

const GROUP_ORDER: CacheGroupKind[] = ['model', 'hub', 'pipeline', 'temp']

interface BackendError {
  detail?: { code?: string; message?: string } | string
}

function pickErrorCode(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: BackendError } })?.response?.data?.detail
  if (detail && typeof detail === 'object') {
    return detail.code
  }
  return undefined
}

function pickErrorMessage(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: BackendError } })?.response?.data?.detail
  if (detail && typeof detail === 'object') {
    return detail.message
  }
  if (typeof detail === 'string') {
    return detail
  }
  return (err as Error)?.message
}

export function CacheSection() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [showDetails, setShowDetails] = useState(false)
  const [dialog, setDialog] = useState<null | 'change' | 'migrate' | 'cleanup'>(null)
  const [pipelineCleanupItem, setPipelineCleanupItem] = useState<CacheBreakdownItem | null>(null)
  const [activeMigration, setActiveMigration] = useState<CacheMigrateTask | null>(null)
  const [toast, setToast] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const needsBreakdown = showDetails || dialog === 'cleanup'
  const breakdownQuery = useQuery({
    queryKey: ['cache-breakdown'],
    queryFn: cacheApi.getBreakdown,
    enabled: needsBreakdown,
    refetchOnWindowFocus: false,
    staleTime: 0,
    gcTime: 0,
    retry: 1,
  })

  useEffect(() => {
    if (!needsBreakdown) return
    if (breakdownQuery.isFetching) return
    if (breakdownQuery.data) return
    breakdownQuery.refetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsBreakdown])

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['system-info'] })
    queryClient.invalidateQueries({ queryKey: ['cache-breakdown'] })
  }

  const removeItemMutation = useMutation({
    mutationFn: (key: string) => cacheApi.removeItem(key),
    onSuccess: data => {
      setToast({ kind: 'ok', text: `${t.settings.cache.itemActionClean} ✓ ${formatBytes(data.freed_bytes)}` })
      refresh()
    },
    onError: err => {
      const code = pickErrorCode(err)
      const errs = t.settings.cache.errors as Record<string, string>
      setToast({ kind: 'err', text: errs[code ?? 'generic'] ?? errs.generic })
    },
  })

  const cleanupMutation = useMutation({
    mutationFn: (keys: string[]) => cacheApi.cleanup(keys),
    onSuccess: data => {
      setToast({ kind: 'ok', text: `${t.settings.cache.cleanupAll} ✓ ${formatBytes(data.freed_bytes)}` })
      setDialog(null)
      refresh()
    },
    onError: err => {
      const errs = t.settings.cache.errors as Record<string, string>
      setToast({ kind: 'err', text: pickErrorMessage(err) ?? errs.generic })
    },
  })

  const pipelineTaskCleanupMutation = useMutation({
    mutationFn: async (taskIds: string[]) => {
      for (const taskId of taskIds) {
        await tasksApi.delete(taskId, true)
      }
      return { count: taskIds.length }
    },
    onSuccess: data => {
      setToast({ kind: 'ok', text: t.settings.cache.pipelineTasksCleaned(data.count) })
      setPipelineCleanupItem(null)
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      refresh()
    },
    onError: err => {
      const errs = t.settings.cache.errors as Record<string, string>
      setToast({ kind: 'err', text: pickErrorMessage(err) ?? errs.generic })
    },
  })

  const setDirMutation = useMutation({
    mutationFn: (target: string) => cacheApi.setDir(target),
    onSuccess: () => {
      setToast({ kind: 'ok', text: t.settings.cache.noticeRestart })
      setDialog(null)
      refresh()
    },
    onError: err => {
      const errs = t.settings.cache.errors as Record<string, string>
      const code = pickErrorCode(err)
      setToast({ kind: 'err', text: errs[code ?? 'generic'] ?? errs.generic })
    },
  })

  const resetMutation = useMutation({
    mutationFn: () => cacheApi.resetDefault(),
    onSuccess: () => {
      setToast({ kind: 'ok', text: t.settings.cache.noticeRestart })
      refresh()
    },
    onError: err => {
      const errs = t.settings.cache.errors as Record<string, string>
      setToast({ kind: 'err', text: pickErrorMessage(err) ?? errs.generic })
    },
  })

  const migrateStart = useMutation({
    mutationFn: ({ target, mode, switchAfter }: { target: string; mode: 'move' | 'copy'; switchAfter: boolean }) =>
      cacheApi.startMigrate(target, mode, switchAfter),
    onSuccess: task => {
      setActiveMigration(task)
      setDialog(null)
    },
    onError: err => {
      const errs = t.settings.cache.errors as Record<string, string>
      const code = pickErrorCode(err)
      setToast({ kind: 'err', text: errs[code ?? 'generic'] ?? errs.generic })
    },
  })

  // Polling migration progress
  useEffect(() => {
    if (!activeMigration) return
    if (activeMigration.status !== 'running' && activeMigration.status !== 'pending') return
    const id = activeMigration.task_id
    const timer = window.setInterval(async () => {
      try {
        const next = await cacheApi.pollMigrate(id)
        setActiveMigration(next)
        if (next.status !== 'running' && next.status !== 'pending') {
          window.clearInterval(timer)
          queryClient.invalidateQueries({ queryKey: ['system-info'] })
          queryClient.invalidateQueries({ queryKey: ['cache-breakdown'] })
        }
      } catch {
        window.clearInterval(timer)
      }
    }, 800)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeMigration?.task_id, activeMigration?.status])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4000)
    return () => window.clearTimeout(timer)
  }, [toast])

  const breakdown = breakdownQuery.data
  const grouped = useMemo(() => groupItems(breakdown?.items ?? []), [breakdown])

  return (
    <div className="border-b border-slate-100 px-6 py-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
          {t.settings.cache.sectionTitle}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowDetails(s => !s)}
            data-testid="cache-toggle-details"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            {showDetails ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {showDetails ? t.settings.cache.hideDetails : t.settings.cache.viewDetails}
          </button>
          <button
            type="button"
            onClick={() => setDialog('change')}
            data-testid="cache-change-dir"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            <FolderOpen size={12} />
            {t.settings.cache.changeDir}
          </button>
          <button
            type="button"
            onClick={() => setDialog('migrate')}
            data-testid="cache-migrate"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            <HardDrive size={12} />
            {t.settings.cache.migrate}
          </button>
          <button
            type="button"
            onClick={() => setDialog('cleanup')}
            data-testid="cache-cleanup"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
          >
            <Trash2 size={12} />
            {t.settings.cache.cleanupAll}
          </button>
          <button
            type="button"
            onClick={() => {
              if (window.confirm(t.settings.cache.resetConfirm)) {
                resetMutation.mutate()
              }
            }}
            data-testid="cache-reset-default"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
          >
            <RotateCcw size={12} />
            {t.settings.cache.resetDefault}
          </button>
        </div>
      </div>

      {activeMigration && (
        <MigrationProgressBanner
          task={activeMigration}
          onCancel={async () => {
            try {
              await cacheApi.cancelMigrate(activeMigration.task_id)
            } catch {
              /* swallow */
            }
          }}
          onDismiss={() => setActiveMigration(null)}
        />
      )}

      {showDetails && (
        <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4" data-testid="cache-breakdown">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-medium text-slate-700">{t.settings.cache.breakdownTitle}</div>
            <button
              type="button"
              onClick={() => breakdownQuery.refetch()}
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
              aria-label={t.settings.cache.reload}
            >
              <RefreshCw size={12} />
              {t.settings.cache.reload}
            </button>
          </div>

          {breakdownQuery.isFetching && !breakdown ? (
            <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
              <Loader2 size={14} className="animate-spin" />
              {t.settings.cache.breakdownLoading}
            </div>
          ) : breakdown && Array.isArray(breakdown.items) && breakdown.items.length > 0 ? (
            <div className="space-y-4">
              {GROUP_ORDER.map(group => {
                const items = grouped[group] ?? []
                if (items.length === 0) return null
                const subtotal = items.reduce((acc, it) => acc + it.bytes, 0)
                return (
                  <div key={group}>
                    <div className="mb-1.5 flex items-center justify-between text-[11px] uppercase tracking-widest text-slate-400">
                      <span>{t.settings.cache.groupLabels[group]}</span>
                      <span>{formatBytes(subtotal)}</span>
                    </div>
                    <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
                      {items.map(item => (
                        <li
                          key={item.key}
                          data-testid={`cache-item-${item.key}`}
                          className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 text-slate-800">
                              <span className="truncate">{item.label}</span>
                              {!item.present && (
                                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                                  empty
                                </span>
                              )}
                            </div>
                            {item.paths[0] && (
                              <div className="truncate font-mono text-[11px] text-slate-400">{item.paths[0]}</div>
                            )}
                          </div>
                          <div className="shrink-0 text-xs text-slate-500">{formatBytes(item.bytes)}</div>
                          <button
                            type="button"
                            disabled={
                              !item.removable
                              || !item.present
                              || removeItemMutation.isPending
                              || pipelineTaskCleanupMutation.isPending
                            }
                            onClick={() => {
                              if (item.key === 'pipeline_outputs') {
                                setPipelineCleanupItem(item)
                                return
                              }
                              const confirmText = t.settings.cache.itemActionCleanConfirm(item.label, formatBytes(item.bytes))
                              if (window.confirm(confirmText)) {
                                removeItemMutation.mutate(item.key)
                              }
                            }}
                            data-testid={`cache-item-clean-${item.key}`}
                            className="inline-flex shrink-0 items-center gap-1 rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-600 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Trash2 size={11} />
                            {t.settings.cache.itemActionClean}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
              <div className="flex items-center justify-between border-t border-slate-200 pt-3 text-xs text-slate-500">
                <span>HF Hub</span>
                <span className="font-mono">{breakdown.huggingface_hub_dir ?? '—'}</span>
              </div>
            </div>
          ) : breakdownQuery.isError ? (
            <div className="space-y-2 py-4 text-sm">
              <div className="text-rose-600">
                {(breakdownQuery.error as Error | null)?.message ?? 'Failed to load'}
              </div>
              <button
                type="button"
                onClick={() => breakdownQuery.refetch()}
                className="rounded border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
              >
                {t.settings.cache.reload}
              </button>
            </div>
          ) : (
            <div className="py-6 text-sm text-slate-400">{t.settings.cache.breakdownEmpty}</div>
          )}
        </div>
      )}

      {dialog === 'change' && (
        <PathDialog
          title={t.settings.cache.changeDirTitle}
          hint={t.settings.cache.changeDirHint}
          submitLabel={t.settings.cache.submit}
          onClose={() => setDialog(null)}
          onSubmit={async target => {
            try {
              await setDirMutation.mutateAsync(target)
            } catch (err) {
              const code = pickErrorCode(err)
              const errs = t.settings.cache.errors as Record<string, string>
              throw new Error(errs[code ?? 'generic'] ?? errs.generic)
            }
          }}
        />
      )}

      {dialog === 'migrate' && (
        <MigrateDialog
          onClose={() => setDialog(null)}
          onSubmit={async ({ target, mode, switchAfter }) => {
            try {
              await migrateStart.mutateAsync({ target, mode, switchAfter })
            } catch (err) {
              const code = pickErrorCode(err)
              const errs = t.settings.cache.errors as Record<string, string>
              throw new Error(errs[code ?? 'generic'] ?? errs.generic)
            }
          }}
        />
      )}

      {dialog === 'cleanup' && (
        <CleanupDialog
          breakdown={breakdown ?? null}
          loading={breakdownQuery.isFetching && !breakdown}
          onClose={() => setDialog(null)}
          onSubmit={async keys => {
            await cleanupMutation.mutateAsync(keys)
          }}
        />
      )}

      {pipelineCleanupItem && (
        <PipelineTasksCleanupDialog
          pipelineItem={pipelineCleanupItem}
          onClose={() => setPipelineCleanupItem(null)}
          onSubmit={async taskIds => {
            await pipelineTaskCleanupMutation.mutateAsync(taskIds)
          }}
        />
      )}

      {toast && (
        <div
          data-testid="cache-toast"
          className={`mt-3 rounded-md px-3 py-2 text-xs ${
            toast.kind === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
          }`}
          role="status"
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}

function groupItems(items: CacheBreakdownItem[]) {
  const out: Record<CacheGroupKind, CacheBreakdownItem[]> = {
    model: [],
    hub: [],
    pipeline: [],
    temp: [],
  }
  for (const item of items) {
    out[item.group]?.push(item)
  }
  return out
}

function MigrationProgressBanner({
  task,
  onCancel,
  onDismiss,
}: {
  task: CacheMigrateTask
  onCancel: () => void | Promise<void>
  onDismiss: () => void
}) {
  const { t } = useI18n()
  const total = task.progress.total_bytes
  const copied = task.progress.copied_bytes
  const pct = total > 0 ? (copied / total) * 100 : task.status === 'succeeded' ? 100 : 0
  const isActive = task.status === 'running' || task.status === 'pending'
  const errs = t.settings.cache.errors as Record<string, string>

  return (
    <div className="mb-4 rounded-lg border border-slate-200 bg-white p-4" data-testid="cache-migration-banner">
      <div className="mb-2 flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 text-slate-700">
          {isActive && <Loader2 size={14} className="animate-spin text-blue-500" />}
          <span className="font-medium">{t.settings.cache.progressLabel}</span>
          <span data-testid="cache-migration-status" className="text-xs text-slate-400">
            {task.status === 'succeeded'
              ? t.settings.cache.progressDone
              : task.status === 'failed'
              ? t.settings.cache.progressFailed
              : task.status === 'cancelled'
              ? t.settings.cache.progressCancelled
              : `${pct.toFixed(0)}%`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isActive ? (
            <button
              type="button"
              onClick={onCancel}
              data-testid="cache-migration-cancel"
              className="inline-flex items-center gap-1 rounded border border-rose-200 px-2 py-1 text-xs text-rose-600 hover:bg-rose-50"
            >
              <X size={11} />
              {t.settings.cache.progressCancel}
            </button>
          ) : (
            <button
              type="button"
              onClick={onDismiss}
              className="inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
            >
              <X size={11} />
            </button>
          )}
        </div>
      </div>
      <ProgressBar value={pct} size="sm" />
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
        <div>{t.settings.cache.copiedOf(formatBytes(copied), formatBytes(total))}</div>
        <div className="text-right">{t.settings.cache.speed(formatBytes(task.progress.speed_bps))}</div>
      </div>
      {task.progress.current_file && isActive && (
        <div className="mt-1 truncate font-mono text-[11px] text-slate-400">
          {t.settings.cache.currentFile(task.progress.current_file)}
        </div>
      )}
      {task.error && (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-rose-600">
          <AlertTriangle size={12} />
          {errs[task.error] ?? task.error}
        </div>
      )}
    </div>
  )
}

function ModalShell({
  title,
  children,
  onClose,
  testId,
}: {
  title: string
  children: React.ReactNode
  onClose: () => void
  testId?: string
}) {
  return (
    <div
      role="dialog"
      data-testid={testId}
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/30 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100"
          >
            <X size={14} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function PipelineTasksCleanupDialog({
  pipelineItem,
  onClose,
  onSubmit,
}: {
  pipelineItem: CacheBreakdownItem
  onClose: () => void
  onSubmit: (taskIds: string[]) => Promise<void>
}) {
  const { t } = useI18n()
  const pipelineRoot = pipelineItem.paths[0] ?? ''
  const tasksQuery = useQuery({
    queryKey: ['cache-pipeline-tasks', pipelineRoot],
    queryFn: () => tasksApi.list({ page: 1, size: 100 }),
    refetchOnWindowFocus: false,
    retry: 1,
  })
  const tasks = useMemo(
    () => (tasksQuery.data?.items ?? []).filter(task => isPipelineTask(task, pipelineRoot)),
    [pipelineRoot, tasksQuery.data?.items],
  )
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const seededRef = useRef(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (seededRef.current) return
    if (tasks.length === 0) return
    seededRef.current = true
    setSelected(Object.fromEntries(tasks.map(task => [task.id, isTaskDeletable(task)])))
  }, [tasks])

  const selectedTaskIds = Object.entries(selected).filter(([, v]) => v).map(([k]) => k)

  return (
    <ModalShell title={t.settings.cache.pipelineTasksTitle} onClose={onClose} testId="cache-pipeline-tasks-dialog">
      <p className="mb-3 text-xs text-slate-500">{t.settings.cache.pipelineTasksHint}</p>
      {pipelineRoot && (
        <div className="mb-3 truncate rounded bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-400">
          {pipelineRoot}
        </div>
      )}
      {tasksQuery.isFetching && !tasksQuery.data ? (
        <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
          <Loader2 size={14} className="animate-spin" />
          {t.settings.cache.breakdownLoading}
        </div>
      ) : tasks.length === 0 ? (
        <div className="py-4 text-sm text-slate-400">{t.settings.cache.pipelineTasksEmpty}</div>
      ) : (
        <ul className="max-h-80 space-y-1 overflow-y-auto">
          {tasks.map(task => (
            <li
              key={task.id}
              className="flex items-center justify-between gap-3 rounded border border-slate-100 px-3 py-2 text-sm"
            >
              <label className="min-w-0 flex flex-1 items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!selected[task.id]}
                  disabled={!isTaskDeletable(task)}
                  onChange={e => setSelected(s => ({ ...s, [task.id]: e.target.checked }))}
                  data-testid={`cache-pipeline-task-checkbox-${task.id}`}
                />
                <span className="min-w-0">
                  <span className="block truncate text-slate-700">{task.name}</span>
                  <span className="block truncate font-mono text-[11px] text-slate-400">
                    {task.id} · {task.status}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {error && <div className="mt-2 text-xs text-rose-600">{error}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
        >
          {t.settings.cache.cancel}
        </button>
        <button
          type="button"
          disabled={submitting || tasksQuery.isFetching || selectedTaskIds.length === 0}
          data-testid="cache-pipeline-tasks-submit"
          onClick={async () => {
            setError(null)
            setSubmitting(true)
            try {
              await onSubmit(selectedTaskIds)
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setSubmitting(false)
            }
          }}
          className="rounded bg-rose-600 px-3 py-1.5 text-xs text-white hover:bg-rose-700 disabled:opacity-50"
        >
          {submitting ? t.settings.cache.submitting : t.settings.cache.cleanupSelectedTasks(selectedTaskIds.length)}
        </button>
      </div>
    </ModalShell>
  )
}

function isPipelineTask(task: Task, pipelineRoot: string): boolean {
  if (!pipelineRoot) return false
  const root = pipelineRoot.replace(/\/+$/, '')
  const outputRoot = task.output_root.replace(/\/+$/, '')
  return outputRoot === root || outputRoot.startsWith(`${root}/`)
}

function isTaskDeletable(task: Task): boolean {
  return task.status !== 'running'
}

function PathDialog({
  title,
  hint,
  submitLabel,
  onClose,
  onSubmit,
  initialValue = '',
}: {
  title: string
  hint: string
  submitLabel: string
  onClose: () => void
  onSubmit: (target: string) => Promise<void>
  initialValue?: string
}) {
  const { t } = useI18n()
  const [value, setValue] = useState(initialValue)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => inputRef.current?.focus(), [])

  return (
    <ModalShell title={title} onClose={onClose} testId="cache-change-dialog">
      <p className="mb-3 text-xs text-slate-500">{hint}</p>
      <label className="mb-1 block text-xs text-slate-500">{t.settings.cache.targetPath}</label>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder={t.settings.cache.targetPlaceholder}
        data-testid="cache-target-input"
        className="w-full rounded border border-slate-200 px-3 py-2 font-mono text-xs focus:border-blue-400 focus:outline-none"
      />
      {error && <div className="mt-2 text-xs text-rose-600" data-testid="cache-dialog-error">{error}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
        >
          {t.settings.cache.cancel}
        </button>
        <button
          type="button"
          disabled={submitting || !value.trim()}
          data-testid="cache-dialog-submit"
          onClick={async () => {
            setError(null)
            setSubmitting(true)
            try {
              await onSubmit(value.trim())
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setSubmitting(false)
            }
          }}
          className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {submitting ? t.settings.cache.submitting : submitLabel}
        </button>
      </div>
    </ModalShell>
  )
}

function MigrateDialog({
  onClose,
  onSubmit,
}: {
  onClose: () => void
  onSubmit: (params: { target: string; mode: 'move' | 'copy'; switchAfter: boolean }) => Promise<void>
}) {
  const { t } = useI18n()
  const [target, setTarget] = useState('')
  const [mode, setMode] = useState<'move' | 'copy'>('move')
  const [switchAfter, setSwitchAfter] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  return (
    <ModalShell title={t.settings.cache.migrateTitle} onClose={onClose} testId="cache-migrate-dialog">
      <p className="mb-3 text-xs text-slate-500">{t.settings.cache.migrateHint}</p>

      <label className="mb-1 block text-xs text-slate-500">{t.settings.cache.targetPath}</label>
      <input
        type="text"
        value={target}
        onChange={e => setTarget(e.target.value)}
        placeholder={t.settings.cache.targetPlaceholder}
        data-testid="cache-target-input"
        className="w-full rounded border border-slate-200 px-3 py-2 font-mono text-xs focus:border-blue-400 focus:outline-none"
      />

      <div className="mt-3 text-xs text-slate-500">{t.settings.cache.migrateMode}</div>
      <div className="mt-1 flex gap-3 text-xs">
        <label className="flex items-center gap-1.5">
          <input type="radio" checked={mode === 'move'} onChange={() => setMode('move')} />
          {t.settings.cache.modeMove}
        </label>
        <label className="flex items-center gap-1.5">
          <input type="radio" checked={mode === 'copy'} onChange={() => setMode('copy')} />
          {t.settings.cache.modeCopy}
        </label>
      </div>

      <label className="mt-3 flex items-center gap-1.5 text-xs text-slate-600">
        <input
          type="checkbox"
          checked={switchAfter}
          onChange={e => setSwitchAfter(e.target.checked)}
          data-testid="cache-switch-after"
        />
        {t.settings.cache.switchAfter}
      </label>

      {error && <div className="mt-2 text-xs text-rose-600" data-testid="cache-dialog-error">{error}</div>}

      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
        >
          {t.settings.cache.cancel}
        </button>
        <button
          type="button"
          disabled={submitting || !target.trim()}
          data-testid="cache-dialog-submit"
          onClick={async () => {
            setError(null)
            setSubmitting(true)
            try {
              await onSubmit({ target: target.trim(), mode, switchAfter })
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setSubmitting(false)
            }
          }}
          className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {submitting ? t.settings.cache.submitting : t.settings.cache.submit}
        </button>
      </div>
    </ModalShell>
  )
}

function CleanupDialog({
  breakdown,
  loading,
  onClose,
  onSubmit,
}: {
  breakdown: CacheBreakdown | null
  loading: boolean
  onClose: () => void
  onSubmit: (keys: string[]) => Promise<void>
}) {
  const { t } = useI18n()
  const items = Array.isArray(breakdown?.items) ? breakdown.items : []
  const removable = items.filter(it => it.removable && it.present && it.bytes > 0)
  const [selected, setSelected] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(removable.map(it => [it.key, true])),
  )
  const seededRef = useRef(removable.length > 0)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Seed selection when items become available after the dialog opened.
  useEffect(() => {
    if (seededRef.current) return
    if (removable.length === 0) return
    seededRef.current = true
    setSelected(Object.fromEntries(removable.map(it => [it.key, true])))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [removable.length])

  const total = removable
    .filter(it => selected[it.key])
    .reduce((acc, it) => acc + it.bytes, 0)
  const selectedKeys = Object.entries(selected).filter(([, v]) => v).map(([k]) => k)

  return (
    <ModalShell title={t.settings.cache.cleanupAllTitle} onClose={onClose} testId="cache-cleanup-dialog">
      <p className="mb-3 text-xs text-slate-500">{t.settings.cache.cleanupAllHint}</p>
      {loading ? (
        <div className="flex items-center gap-2 py-6 text-sm text-slate-400">
          <Loader2 size={14} className="animate-spin" />
          {t.settings.cache.breakdownLoading}
        </div>
      ) : removable.length === 0 ? (
        <div className="py-4 text-sm text-slate-400">{t.settings.cache.breakdownEmpty}</div>
      ) : (
        <ul className="max-h-72 space-y-1 overflow-y-auto">
          {removable.map(item => (
            <li key={item.key} className="flex items-center justify-between gap-3 rounded border border-slate-100 px-3 py-2 text-sm">
              <label className="flex flex-1 items-center gap-2">
                <input
                  type="checkbox"
                  checked={!!selected[item.key]}
                  onChange={e => setSelected(s => ({ ...s, [item.key]: e.target.checked }))}
                  data-testid={`cache-cleanup-checkbox-${item.key}`}
                />
                <span className="truncate text-slate-700">{item.label}</span>
              </label>
              <span className="shrink-0 text-xs text-slate-500">{formatBytes(item.bytes)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3 text-right text-xs text-slate-500">
        Σ {formatBytes(total)}
      </div>
      {error && <div className="mt-2 text-xs text-rose-600">{error}</div>}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
        >
          {t.settings.cache.cancel}
        </button>
        <button
          type="button"
          disabled={submitting || loading || selectedKeys.length === 0}
          data-testid="cache-cleanup-submit"
          onClick={async () => {
            setError(null)
            setSubmitting(true)
            try {
              await onSubmit(selectedKeys)
            } catch (e) {
              setError((e as Error).message)
            } finally {
              setSubmitting(false)
            }
          }}
          className="rounded bg-rose-600 px-3 py-1.5 text-xs text-white hover:bg-rose-700 disabled:opacity-50"
        >
          {submitting ? t.settings.cache.submitting : t.settings.cache.cleanupSelected(selectedKeys.length)}
        </button>
      </div>
    </ModalShell>
  )
}
