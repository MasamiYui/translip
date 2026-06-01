import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Gauge, ChevronRight } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { StatusBadge } from '../components/shared/StatusBadge'
import { useI18n } from '../i18n/useI18n'
import type { Task } from '../types'

const EVALUABLE_STATUSES = new Set(['succeeded', 'partial_success', 'completed', 'failed'])

export function EvaluationPage() {
  const { t } = useI18n()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['evaluation-tasks'],
    queryFn: () => tasksApi.list({ size: 200 }),
  })

  const tasks: Task[] = useMemo(() => {
    const items = data?.items ?? []
    // Surface tasks that have (or could have) a rendered dub to evaluate.
    return items.filter(task => EVALUABLE_STATUSES.has(task.status) || task.overall_progress > 0)
  }, [data])

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} px-6 py-6`}>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#3b5bdb]/10 text-[#3b5bdb]">
          <Gauge size={20} />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-[#111827]">{t.evaluation.title}</h1>
          <p className="text-sm text-[#6b7280]">{t.evaluation.subtitle}</p>
        </div>
      </div>

      {isLoading ? (
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-8 text-center text-sm text-[#9ca3af]">
          {t.evaluation.loadingReport}
        </div>
      ) : tasks.length === 0 ? (
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-8 text-center text-sm text-[#9ca3af]">
          {t.evaluation.noTasks}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#f3f4f6] text-left text-xs text-[#9ca3af]">
                <th className="px-4 py-3 font-medium">{t.evaluation.pickTask}</th>
                <th className="px-4 py-3 font-medium">{t.evaluation.status}</th>
                <th className="px-4 py-3 font-medium">{t.evaluation.createdAt}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {tasks.map(task => (
                <tr
                  key={task.id}
                  onClick={() => navigate(`/evaluation/${task.id}`)}
                  className="cursor-pointer border-b border-[#f9fafb] transition-colors hover:bg-[#f9fafb]"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-[#111827]">{task.name}</div>
                    <div className="text-xs text-[#9ca3af]">
                      {task.source_lang} → {task.target_lang} · {task.id}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={task.status} size="sm" />
                  </td>
                  <td className="px-4 py-3 text-xs text-[#6b7280]">
                    {new Date(task.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right text-[#cbd5e1]">
                    <ChevronRight size={16} className="inline" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageContainer>
  )
}
