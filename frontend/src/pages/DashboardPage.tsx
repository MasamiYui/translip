import { useQuery } from '@tanstack/react-query'
import { tasksApi } from '../api/tasks'
import { atomicToolsApi } from '../api/atomic-tools'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { EmptyState } from '../components/shared/EmptyState'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { Link } from 'react-router-dom'
import { PlusCircle, ArrowRight, Activity, CheckCircle2, XCircle, Layers, Workflow, Wrench } from 'lucide-react'
import type { TaskListResponse, Task } from '../types'
import type { AtomicJobListResponse, AtomicJobRead } from '../types/atomic-tools'
import { useI18n } from '../i18n/useI18n'

type ActivityKind = 'pipeline' | 'atomic'

/** Normalized row shape so pipeline tasks and atomic jobs can share one feed. */
interface ActivityItem {
  kind: ActivityKind
  id: string
  href: string
  name: string
  status: string
  detail: string
  progress: number
  elapsedSec?: number
  timeRef: string
  sortTime: number
}

const PIPELINE_RUNNING_STATES = new Set(['running', 'pending'])
const ATOMIC_RUNNING_STATES = new Set(['running', 'pending'])

function parseTime(value?: string | null): number {
  const ms = value ? Date.parse(value) : NaN
  return Number.isNaN(ms) ? 0 : ms
}

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
        <div className="text-xs font-medium text-[#4b5563] uppercase tracking-wide">{label}</div>
        <div className="mt-0.5 text-2xl font-bold tabular-nums text-[#111827]">{value}</div>
      </div>
    </div>
  )
}

/** Small chip distinguishing pipeline tasks from atomic-tool jobs in the mixed feed. */
function TypeChip({ kind }: { kind: ActivityKind }) {
  const { t } = useI18n()
  const isPipeline = kind === 'pipeline'
  const Icon = isPipeline ? Workflow : Wrench

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${
        isPipeline ? 'bg-[#eef1fd] text-[#3b5bdb]' : 'bg-teal-50 text-teal-600'
      }`}
    >
      <Icon size={11} />
      {isPipeline ? t.dashboard.typePipeline : t.dashboard.typeAtomic}
    </span>
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
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <TypeChip kind="pipeline" />
            <span className="truncate font-semibold text-[#111827]">{task.name}</span>
          </div>
          <div className="mt-0.5 text-xs text-[#9ca3af]">
            {getLanguageLabel(task.source_lang)} → {getLanguageLabel(task.target_lang)}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
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

function ActiveAtomicCard({ job }: { job: AtomicJobRead }) {
  const inputName = job.input_files[0]?.filename ?? job.job_id

  return (
    <Link
      to={`/tools/jobs/${job.job_id}`}
      className="block overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-shadow hover:shadow-[0_4px_12px_rgba(0,0,0,.08)]"
    >
      <div className="flex items-center justify-between border-b border-[#f3f4f6] px-5 py-3.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <TypeChip kind="atomic" />
            <span className="truncate font-semibold text-[#111827]">{job.tool_name}</span>
          </div>
          <div className="mt-0.5 truncate text-xs text-[#9ca3af]">{job.current_step ?? inputName}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          <span className="tabular-nums text-sm font-semibold text-[#374151]">{job.progress_percent.toFixed(0)}%</span>
          <StatusBadge status={job.status} size="sm" />
        </div>
      </div>
      <div className="px-5 py-4">
        <ProgressBar value={job.progress_percent} size="sm" />
      </div>
    </Link>
  )
}

function RecentActivityTable({ items }: { items: ActivityItem[] }) {
  const { t, formatDuration, formatRelativeTime } = useI18n()

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[#374151]">{t.dashboard.recentActivity}</h2>
        <div className="flex items-center gap-4">
          <Link to="/tasks" className="flex items-center gap-1 text-xs font-medium text-[#3b5bdb] hover:underline">
            {t.nav.pipelineTasks} <ArrowRight size={11} />
          </Link>
          <Link to="/tools/jobs" className="flex items-center gap-1 text-xs font-medium text-[#3b5bdb] hover:underline">
            {t.nav.atomicTasks} <ArrowRight size={11} />
          </Link>
        </div>
      </div>

      {/* >= sm: tabular layout with progressive column reveal. */}
      <div className="hidden sm:block overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        <table className="w-full min-w-[480px] md:min-w-[620px] lg:min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-[#f3f4f6] text-left">
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#4b5563] whitespace-nowrap">{t.dashboard.columns.type}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#4b5563] whitespace-nowrap">{t.dashboard.columns.name}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#4b5563] whitespace-nowrap">{t.dashboard.columns.status}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#4b5563] whitespace-nowrap hidden lg:table-cell">{t.dashboard.columns.detail}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#4b5563] whitespace-nowrap hidden md:table-cell">{t.dashboard.columns.duration}</th>
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-[#4b5563] whitespace-nowrap">{t.dashboard.columns.time}</th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr
                key={`${item.kind}-${item.id}`}
                className="border-b border-[#f9fafb] transition-colors last:border-0 hover:bg-[#fafafa]"
              >
                <td className="px-5 py-3.5 whitespace-nowrap"><TypeChip kind={item.kind} /></td>
                <td className="px-5 py-3.5">
                  <Link to={item.href} className="font-medium text-[#111827] hover:text-[#3b5bdb]">
                    {item.name}
                  </Link>
                </td>
                <td className="px-5 py-3.5 whitespace-nowrap"><StatusBadge status={item.status} size="sm" /></td>
                <td className="max-w-[260px] truncate px-5 py-3.5 text-[#6b7280] hidden lg:table-cell">{item.detail}</td>
                <td className="px-5 py-3.5 text-[#6b7280] whitespace-nowrap hidden md:table-cell">{formatDuration(item.elapsedSec)}</td>
                <td className="px-5 py-3.5 text-[#6b7280] whitespace-nowrap">{formatRelativeTime(item.timeRef)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* < sm: card list — preserves all key metadata without horizontal scrolling. */}
      <ul className="sm:hidden space-y-2.5" aria-label={t.dashboard.recentActivity}>
        {items.map(item => (
          <li
            key={`${item.kind}-${item.id}`}
            className="rounded-xl border border-[#e5e7eb] bg-white px-4 py-3 shadow-[0_1px_3px_rgba(0,0,0,.04)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <TypeChip kind={item.kind} />
                  <StatusBadge status={item.status} size="sm" />
                </div>
                <Link
                  to={item.href}
                  className="mt-1.5 block truncate text-sm font-semibold text-[#111827] hover:text-[#3b5bdb]"
                >
                  {item.name}
                </Link>
                <div className="mt-0.5 truncate text-xs text-[#6b7280]">{item.detail}</div>
              </div>
              <div className="shrink-0 text-right text-xs text-[#6b7280] tabular-nums">
                <div>{formatDuration(item.elapsedSec)}</div>
                <div className="mt-0.5 text-[#9ca3af]">{formatRelativeTime(item.timeRef)}</div>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

const POLL_INTERVAL_MS = 5000

/**
 * Smart polling: only re-fetch while there are pipeline tasks or atomic jobs
 * actively running/pending, and never poll when the tab is backgrounded. This
 * eliminates a constant 5s background load on idle dashboards.
 */
function tasksRefetchInterval(query: { state: { data?: TaskListResponse } }): number | false {
  const items = query.state.data?.items ?? []
  return items.some((task) => PIPELINE_RUNNING_STATES.has(task.status)) ? POLL_INTERVAL_MS : false
}

function atomicRefetchInterval(query: { state: { data?: AtomicJobListResponse } }): number | false {
  const items = query.state.data?.items ?? []
  return items.some((job) => ATOMIC_RUNNING_STATES.has(job.status)) ? POLL_INTERVAL_MS : false
}

export function DashboardPage() {
  const { t, getLanguageLabel } = useI18n()
  const { data: allTasks } = useQuery({
    queryKey: ['tasks', 'all'],
    queryFn: () => tasksApi.list({ size: 100 }),
    refetchInterval: tasksRefetchInterval,
    refetchIntervalInBackground: false,
  })
  const { data: atomicJobsPage } = useQuery({
    queryKey: ['atomic-tool-jobs', 'dashboard'],
    queryFn: () => atomicToolsApi.listJobs({ size: 100 }),
    refetchInterval: atomicRefetchInterval,
    refetchIntervalInBackground: false,
  })

  const tasks = allTasks?.items ?? []
  const atomicJobs = atomicJobsPage?.items ?? []

  // Unified stats: pipeline tasks and atomic jobs counted together.
  const total = (allTasks?.total ?? 0) + (atomicJobsPage?.total ?? 0)
  const running =
    tasks.filter(task => task.status === 'running').length +
    atomicJobs.filter(job => job.status === 'running').length
  const succeeded =
    tasks.filter(task => task.status === 'succeeded').length +
    atomicJobs.filter(job => job.status === 'completed').length
  const failed =
    tasks.filter(task => task.status === 'failed').length +
    atomicJobs.filter(job => job.status === 'failed').length

  const activePipelines = tasks.filter(task => PIPELINE_RUNNING_STATES.has(task.status))
  const activeAtomic = atomicJobs.filter(job => ATOMIC_RUNNING_STATES.has(job.status))
  const hasActive = activePipelines.length + activeAtomic.length > 0

  // Merge finished pipeline tasks + atomic jobs into a single time-sorted feed.
  // (Memoization is handled by the React Compiler, so no manual useMemo.)
  const pipelineItems: ActivityItem[] = tasks
    .filter(task => !PIPELINE_RUNNING_STATES.has(task.status))
    .map(task => {
      const timeRef = task.finished_at ?? task.updated_at ?? task.created_at
      return {
        kind: 'pipeline',
        id: task.id,
        href: `/tasks/${task.id}`,
        name: task.name,
        status: task.status,
        detail: `${getLanguageLabel(task.source_lang)} → ${getLanguageLabel(task.target_lang)}`,
        progress: task.overall_progress,
        elapsedSec: task.elapsed_sec,
        timeRef,
        sortTime: parseTime(timeRef),
      }
    })
  const atomicItems: ActivityItem[] = atomicJobs
    .filter(job => !ATOMIC_RUNNING_STATES.has(job.status))
    .map(job => {
      const timeRef = job.finished_at ?? job.updated_at ?? job.created_at
      return {
        kind: 'atomic',
        id: job.job_id,
        href: `/tools/jobs/${job.job_id}`,
        name: job.tool_name,
        status: job.status,
        detail: job.input_files[0]?.filename ?? job.job_id,
        progress: job.progress_percent,
        elapsedSec: job.elapsed_sec ?? undefined,
        timeRef,
        sortTime: parseTime(timeRef),
      }
    })
  const recentItems = [...pipelineItems, ...atomicItems]
    .sort((a, b) => b.sortTime - a.sortTime)
    .slice(0, 8)

  const isEmpty = tasks.length === 0 && atomicJobs.length === 0

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

      {/* In progress: pipeline tasks (with stage graph) and atomic jobs together */}
      {hasActive && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[#374151]">{t.dashboard.activeTasks}</h2>
          <div className="space-y-3">
            {activePipelines.map(task => <ActiveTaskCard key={task.id} task={task} />)}
            {activeAtomic.map(job => <ActiveAtomicCard key={job.job_id} job={job} />)}
          </div>
        </section>
      )}

      {/* Recent activity: mixed pipeline + atomic, most recent first */}
      {recentItems.length > 0 && <RecentActivityTable items={recentItems} />}

      {isEmpty && (
        <EmptyState
          testId="dashboard-empty"
          icon={Layers}
          title={t.dashboard.emptyTitle}
          description={t.dashboard.emptyDescription}
          action={
            <Link
              to="/tasks/new"
              className="inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#3451c7]"
            >
              <PlusCircle size={14} />
              {t.common.createTask}
            </Link>
          }
        />
      )}
    </PageContainer>
  )
}
