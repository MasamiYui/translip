import { useQuery } from '@tanstack/react-query'
import { tasksApi } from '../api/tasks'
import { atomicToolsApi } from '../api/atomic-tools'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { Link } from 'react-router-dom'
import { PlusCircle, ArrowRight, Activity, CheckCircle2, XCircle, Layers } from 'lucide-react'
import type { Task } from '../types'
import type { AtomicJobRead } from '../types/atomic-tools'
import { useI18n } from '../i18n/useI18n'

interface StatCardProps {
  label: string
  value: number | string
  icon: React.ElementType
  iconColor: string
  iconBg: string
}

function StatCard({ label, value, icon: Icon, iconColor, iconBg }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-xl bg-white border border-[#e5e7eb] px-5 py-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${iconBg}`}>
        <Icon size={18} className={iconColor} />
      </div>
      <div>
        <div className="text-xs font-medium text-[#9ca3af] uppercase tracking-wide">{label}</div>
        <div className="mt-0.5 text-2xl font-bold tabular-nums text-[#111827]">{value}</div>
      </div>
    </div>
  )
}

function ActiveTaskCard({ task }: { task: Task }) {
  const { getLanguageLabel } = useI18n()

  return (
    <Link
      to={`/tasks/${task.id}`}
      className="block overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-shadow hover:shadow-[0_4px_12px_rgba(0,0,0,.08)]"
    >
      <div className="flex items-center justify-between border-b border-[#f3f4f6] px-5 py-3.5">
        <div>
          <div className="font-semibold text-[#111827]">{task.name}</div>
          <div className="mt-0.5 text-xs text-[#9ca3af]">
            {getLanguageLabel(task.source_lang)} → {getLanguageLabel(task.target_lang)}
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <span className="tabular-nums text-sm font-semibold text-[#374151]">{task.overall_progress.toFixed(0)}%</span>
          <StatusBadge status={task.status} size="sm" />
        </div>
      </div>
      <div className="px-5 py-4">
        <ProgressBar value={task.overall_progress} size="sm" className="mb-4" />
        <PipelineGraph
          stages={task.stages}
          templateId={(typeof task.config.template === 'string' ? task.config.template : 'asr-dub-basic') as 'asr-dub-basic' | 'asr-dub+ocr-subs' | 'asr-dub+ocr-subs+erase'}
          activeStage={task.current_stage ?? undefined}
          compact
        />
      </div>
    </Link>
  )
}

function RecentAtomicJobsTable({ jobs }: { jobs: AtomicJobRead[] }) {
  const { t, formatDuration, formatRelativeTime } = useI18n()

  if (jobs.length === 0) return null

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[#374151]">{t.dashboard.recentAtomicJobs}</h2>
        <Link to="/tools/jobs" className="flex items-center gap-1 text-xs font-medium text-[#3b5bdb] hover:underline">
          {t.common.all} <ArrowRight size={11} />
        </Link>
      </div>
      <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#f3f4f6] text-left">
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.tool}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.status}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.input}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.duration}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.createdAt}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map(job => (
              <tr key={job.job_id} className="border-b border-[#f9fafb] transition-colors last:border-0 hover:bg-[#fafafa]">
                <td className="px-5 py-3.5">
                  <Link to={`/tools/jobs/${job.job_id}`} className="font-medium text-[#111827] hover:text-[#3b5bdb]">
                    {job.tool_name}
                  </Link>
                </td>
                <td className="px-5 py-3.5">
                  <StatusBadge status={job.status} size="sm" />
                </td>
                <td className="max-w-[240px] truncate px-5 py-3.5 text-[#6b7280]">
                  {job.input_files[0]?.filename ?? job.job_id}
                </td>
                <td className="px-5 py-3.5 text-[#6b7280]">{formatDuration(job.elapsed_sec ?? undefined)}</td>
                <td className="px-5 py-3.5 text-[#9ca3af]">{formatRelativeTime(job.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function DashboardPage() {
  const { t, formatDuration, formatRelativeTime, getLanguageLabel } = useI18n()
  const { data: allTasks } = useQuery({
    queryKey: ['tasks', 'all'],
    queryFn: () => tasksApi.list({ size: 100 }),
    refetchInterval: 5000,
  })
  const { data: recentAtomicJobs = [] } = useQuery({
    queryKey: ['atomic-tool-jobs', 'recent'],
    queryFn: () => atomicToolsApi.listRecentJobs(5),
    refetchInterval: 5000,
  })

  const tasks = allTasks?.items ?? []
  const total = allTasks?.total ?? 0
  const running = tasks.filter(t => t.status === 'running').length
  const succeeded = tasks.filter(t => t.status === 'succeeded').length
  const failed = tasks.filter(t => t.status === 'failed').length
  const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'pending')
  const recentDone = tasks
    .filter(t => t.status === 'succeeded' || t.status === 'failed')
    .slice(0, 5)

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-6`}>
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[#111827]">{t.dashboard.title}</h1>
          <p className="mt-0.5 text-sm text-[#9ca3af]">{t.dashboard.subtitle ?? ''}</p>
        </div>
        <Link
          to="/tasks/new"
          className="flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] hover:shadow-[0_4px_12px_rgba(59,91,219,.3)]"
        >
          <PlusCircle size={14} />
          {t.common.createTask}
        </Link>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label={t.dashboard.totalTasks}
          value={total}
          icon={Layers}
          iconBg="bg-[#f3f4f6]"
          iconColor="text-[#6b7280]"
        />
        <StatCard
          label={t.dashboard.running}
          value={running}
          icon={Activity}
          iconBg="bg-blue-50"
          iconColor="text-blue-600"
        />
        <StatCard
          label={t.dashboard.completed}
          value={succeeded}
          icon={CheckCircle2}
          iconBg="bg-emerald-50"
          iconColor="text-emerald-600"
        />
        <StatCard
          label={t.dashboard.failed}
          value={failed}
          icon={XCircle}
          iconBg="bg-red-50"
          iconColor="text-red-500"
        />
      </div>

      {/* Active tasks */}
      {activeTasks.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-[#374151] uppercase tracking-wide">{t.dashboard.activeTasks}</h2>
            <Link to="/tasks" className="flex items-center gap-1 text-xs font-medium text-[#3b5bdb] hover:underline">
              {t.common.all} <ArrowRight size={11} />
            </Link>
          </div>
          <div className="space-y-3">
            {activeTasks.map(t => <ActiveTaskCard key={t.id} task={t} />)}
          </div>
        </section>
      )}

      {/* Recent completed */}
      {recentDone.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-[#374151] uppercase tracking-wide mb-3">{t.dashboard.recentCompleted}</h2>
          <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#f3f4f6] text-left">
                  <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.dashboard.columns.name}</th>
                  <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.dashboard.columns.status}</th>
                  <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.dashboard.columns.language}</th>
                  <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.dashboard.columns.duration}</th>
                  <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.dashboard.columns.completedAt}</th>
                </tr>
              </thead>
              <tbody>
                {recentDone.map(t => (
                  <tr
                    key={t.id}
                    className="border-b border-[#f9fafb] hover:bg-[#fafafa] cursor-pointer transition-colors last:border-0"
                    onClick={() => window.location.href = `/tasks/${t.id}`}
                  >
                    <td className="px-5 py-3.5 font-medium text-[#111827]">{t.name}</td>
                    <td className="px-5 py-3.5"><StatusBadge status={t.status} size="sm" /></td>
                    <td className="px-5 py-3.5 text-[#6b7280]">
                      {getLanguageLabel(t.source_lang)} → {getLanguageLabel(t.target_lang)}
                    </td>
                    <td className="px-5 py-3.5 text-[#6b7280]">{formatDuration(t.elapsed_sec)}</td>
                    <td className="px-5 py-3.5 text-[#9ca3af]">{formatRelativeTime(t.finished_at ?? t.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <RecentAtomicJobsTable jobs={recentAtomicJobs} />

      {tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[#d1d5db] bg-white py-20 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#f3f4f6]">
            <Layers size={24} className="text-[#9ca3af]" />
          </div>
          <div className="text-base font-semibold text-[#374151]">{t.dashboard.emptyTitle}</div>
          <div className="mt-1 text-sm text-[#9ca3af] mb-6">{t.dashboard.emptyDescription}</div>
          <Link
            to="/tasks/new"
            className="inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#3451c7]"
          >
            <PlusCircle size={14} />
            {t.common.createTask}
          </Link>
        </div>
      )}
    </PageContainer>
  )
}
