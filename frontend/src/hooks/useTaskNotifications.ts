import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { tasksApi } from '../api/tasks'
import { useI18n } from '../i18n/useI18n'

const ACTIVE = new Set(['pending', 'running'])
const TERMINAL = new Set(['succeeded', 'partial_success', 'failed', 'interrupted'])

type FinishedTask = { name: string; status: string }

/**
 * Pure transition detector: returns tasks that were active (pending/running) in
 * `prev` and have since reached a terminal status. Exported for unit testing.
 */
export function diffFinishedTasks(
  prev: Map<string, string>,
  items: { id: string; name: string; status: string }[],
): FinishedTask[] {
  const finished: FinishedTask[] = []
  for (const task of items) {
    const before = prev.get(task.id)
    if (before && ACTIVE.has(before) && TERMINAL.has(task.status)) {
      finished.push({ name: task.name, status: task.status })
    }
  }
  return finished
}

function isOk(status: string): boolean {
  return status === 'succeeded' || status === 'partial_success'
}

/**
 * App-wide watcher (mounted once in MainLayout): polls the task list and, when a
 * task transitions from running/pending to a terminal status, flashes the tab
 * title and fires a browser notification so users who tabbed away during a long
 * pipeline run get told it finished.
 */
export function useTaskNotifications(): void {
  const { t } = useI18n()
  const prev = useRef<Map<string, string>>(new Map())
  const seeded = useRef(false)
  const baseTitle = useRef('')

  const { data } = useQuery({
    queryKey: ['tasks', 'notifications'],
    queryFn: () => tasksApi.list({ page: 1, size: 100 }),
    refetchInterval: 5000,
  })

  useEffect(() => {
    if (!baseTitle.current && typeof document !== 'undefined') {
      baseTitle.current = document.title
    }
    const restore = () => {
      if (baseTitle.current) document.title = baseTitle.current
    }
    window.addEventListener('focus', restore)
    return () => window.removeEventListener('focus', restore)
  }, [])

  useEffect(() => {
    if (!data) return
    const items = data.items ?? []
    const finished = seeded.current ? diffFinishedTasks(prev.current, items) : []
    const next = new Map<string, string>()
    for (const task of items) next.set(task.id, task.status)
    prev.current = next
    seeded.current = true
    if (finished.length === 0) return

    const label = finished.length === 1 ? finished[0].name : String(finished.length)
    if (typeof document !== 'undefined' && document.hidden) {
      document.title = `✓ ${label} · ${baseTitle.current || ''}`.trim()
    }

    if (typeof window !== 'undefined' && 'Notification' in window) {
      const fire = () => {
        for (const task of finished) {
          try {
            // eslint-disable-next-line no-new
            new Notification(isOk(task.status) ? t.notifications.done : t.notifications.failed, {
              body: task.name,
            })
          } catch {
            /* notifications best-effort */
          }
        }
      }
      if (Notification.permission === 'granted') {
        fire()
      } else if (Notification.permission === 'default') {
        void Notification.requestPermission().then(p => {
          if (p === 'granted') fire()
        })
      }
    }
  }, [data, t])
}
