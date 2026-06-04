import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Download, ExternalLink, Filter, Loader2, Sparkles, Wand2 } from 'lucide-react'
import {
  evaluationApi,
  type AutoFixJob,
  type DubQaReport,
  type RemediationActionGroup,
  type RemediationExecutor,
} from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

/** Executors that an automated loop can run end-to-end without a human. */
const AUTO_EXECUTORS: RemediationExecutor[] = ['repair', 'render']

function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/**
 * "Next optimizations" — turns the evaluation's per-segment defects into a
 * prioritized, actionable plan. Human-facing (ranked fixes + why-blocked +
 * locate-segments) and AI-facing (export the structured remediation plan that
 * drives run-dub-repair / an optimization loop).
 */
export function RemediationPanel({
  taskId,
  report,
  onFocusSegments,
  onApplied,
}: {
  taskId: string
  report: DubQaReport
  onFocusSegments: (segmentIds: string[], label: string) => void
  onApplied: () => void
}) {
  const { t } = useI18n()
  const tr = t.evaluation.remediation
  const navigate = useNavigate()
  const plan = report.remediation

  const repairSegs = plan?.repair_directive?.segment_ids ?? []
  const [jobId, setJobId] = useState<string | null>(null)
  const appliedRef = useRef(false)

  const startFix = useMutation({
    mutationFn: () => evaluationApi.autoFix(taskId, { segment_ids: repairSegs }),
    onSuccess: job => {
      appliedRef.current = false
      setJobId(job.id)
    },
  })
  const jobQuery = useQuery({
    queryKey: ['auto-fix', taskId, jobId],
    enabled: !!jobId,
    queryFn: () => evaluationApi.getAutoFix(taskId, jobId!),
    refetchInterval: q => {
      const s = (q.state.data as AutoFixJob | undefined)?.status
      return s === 'pending' || s === 'running' ? 3000 : false
    },
  })
  const job = jobQuery.data
  const fixing = startFix.isPending || job?.status === 'pending' || job?.status === 'running'

  // Which of the 4 steps (plan → repair → render → evaluate) the worker is on,
  // and which iterative round it is running.
  const progress = job?.progress
  const phaseKey = progress?.phase as keyof typeof tr.autoFixPhase | undefined
  const phaseLabel = (phaseKey && tr.autoFixPhase[phaseKey]) || tr.autoFixing
  const step = progress?.step ?? 0
  const totalSteps = progress?.total ?? 4
  const round = progress?.round ?? 0
  const totalRounds = progress?.total_rounds ?? 0

  // When a fix lands, refresh the evaluation once so the improved report loads.
  useEffect(() => {
    if (job?.status === 'succeeded' && !appliedRef.current) {
      appliedRef.current = true
      onApplied()
    }
  }, [job?.status, onApplied])

  if (!plan || plan.summary.problem_count === 0) {
    return (
      <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-4 text-center text-sm text-emerald-700">
        {tr.none}
      </div>
    )
  }

  const openEditor = () => navigate(`/tasks/${encodeURIComponent(taskId)}/dubbing-editor`)
  const exportPlan = () => downloadJson(`remediation_plan.${report.target_lang}.json`, plan)

  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-lg bg-[#3b5bdb]/10 text-[#3b5bdb]">
            <Sparkles size={15} />
          </div>
          <div>
            <div className="text-sm font-semibold text-[#111827]">{tr.title}</div>
            <div className="text-xs text-[#9ca3af]">{tr.subtitle}</div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {repairSegs.length > 0 && (
            <button
              type="button"
              onClick={() => startFix.mutate()}
              disabled={fixing}
              title={tr.autoFixHint}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-white',
                fixing ? 'cursor-not-allowed bg-[#9aa7e8]' : 'bg-[#3b5bdb] hover:bg-[#324bc0]',
              )}
            >
              {fixing ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />}
              {fixing ? tr.autoFixing : tr.autoFix}
            </button>
          )}
          <button
            type="button"
            onClick={exportPlan}
            title={tr.exportHint}
            className="flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] px-2.5 py-1.5 text-xs font-medium text-[#374151] hover:bg-[#f9fafb]"
          >
            <Download size={13} /> {tr.export}
          </button>
        </div>
      </div>

      {/* Auto-fix progress — phase label + 4-step bar while running */}
      {fixing && (
        <div className="mb-3 rounded-lg bg-[#eef1fe] px-3 py-2">
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium text-[#3b5bdb]">
            <span className="flex items-center gap-1.5">
              <Loader2 size={11} className="animate-spin" />
              {round > 0 && totalRounds > 0 && (
                <span className="rounded bg-[#3b5bdb]/10 px-1.5 py-0.5 tabular-nums">
                  {tr.roundProgress(round, totalRounds)}
                </span>
              )}
              {phaseLabel}
            </span>
            {step > 0 && <span className="tabular-nums opacity-70">{step}/{totalSteps}</span>}
          </div>
          <div className="flex gap-1">
            {Array.from({ length: totalSteps }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  'h-1 flex-1 rounded-full transition-colors',
                  i < step ? 'bg-[#3b5bdb]' : 'bg-[#c7d0f5]',
                )}
              />
            ))}
          </div>
        </div>
      )}

      {/* Auto-fix outcome */}
      {job?.status === 'succeeded' && job.result && (
        <div
          className={cn(
            'mb-3 rounded-lg px-3 py-2 text-xs font-medium',
            job.result.rolled_back
              ? 'bg-amber-50 text-amber-700'
              : (job.result.repaired_count ?? 0) > 0
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-[#f3f4f6] text-[#6b7280]',
          )}
        >
          {job.result.rolled_back
            ? tr.autoFixRolledBack(job.result.before_score ?? 0, job.result.after_score ?? 0)
            : (job.result.repaired_count ?? 0) > 0
              ? tr.autoFixResult(
                  job.result.before_score ?? 0,
                  job.result.after_score ?? 0,
                  job.result.repaired_count ?? 0,
                )
              : tr.autoFixNoChange(job.result.before_score ?? 0, job.result.after_score ?? 0)}
          {(job.result.rounds_run ?? 0) > 1 && (
            <span className="opacity-70"> · {tr.roundsSummary(job.result.rounds_run ?? 0)}</span>
          )}
        </div>
      )}
      {job?.status === 'failed' && (
        <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{tr.autoFixFailed}</div>
      )}

      {/* Summary */}
      <div className="mb-3 text-xs text-[#6b7280]">
        {tr.summary(plan.summary.auto_fixable_count, plan.summary.manual_count)}
      </div>

      {/* Why blocked — gate → segments */}
      {plan.delivery_blockers.length > 0 && (
        <div className="mb-3 rounded-lg bg-red-50/60 px-3 py-2">
          <div className="mb-1.5 text-[11px] font-semibold text-red-700">{tr.blockedTitle}</div>
          <div className="flex flex-wrap gap-1.5">
            {plan.delivery_blockers.map(b => {
              const label = tr.gateLabel[b.gate as keyof typeof tr.gateLabel] ?? b.gate
              const clickable = b.segment_ids.length > 0
              return (
                <button
                  key={b.gate}
                  type="button"
                  disabled={!clickable}
                  onClick={() => clickable && onFocusSegments(b.segment_ids, label)}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
                    clickable
                      ? 'bg-white text-red-600 ring-1 ring-red-200 hover:bg-red-100'
                      : 'cursor-default bg-white text-red-500 ring-1 ring-red-100',
                  )}
                >
                  {label}
                  {b.count > 0 && <span className="opacity-70">·{b.count}</span>}
                  {clickable && <Filter size={10} className="opacity-60" />}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Ranked action groups */}
      <div className="flex flex-col gap-1.5">
        {plan.actions.map(group => (
          <ActionRow
            key={group.action}
            group={group}
            onFocus={() =>
              onFocusSegments(
                group.segment_ids,
                tr.actionLabel[group.action as keyof typeof tr.actionLabel] ?? group.action,
              )
            }
            onOpenEditor={openEditor}
          />
        ))}
      </div>
    </div>
  )
}

function ActionRow({
  group,
  onFocus,
  onOpenEditor,
}: {
  group: RemediationActionGroup
  onFocus: () => void
  onOpenEditor: () => void
}) {
  const { t } = useI18n()
  const tr = t.evaluation.remediation
  const isAuto = AUTO_EXECUTORS.includes(group.executor)
  const label = tr.actionLabel[group.action as keyof typeof tr.actionLabel] ?? group.action
  const hint = tr.actionHint[group.action as keyof typeof tr.actionHint] ?? ''
  const executorLabel = tr.executorLabel[group.executor as keyof typeof tr.executorLabel] ?? group.executor

  return (
    <div className="flex items-center gap-3 rounded-lg border border-[#f3f4f6] px-3 py-2 hover:bg-[#f9fafb]">
      <span className={cn('h-2 w-2 shrink-0 rounded-full', isAuto ? 'bg-emerald-500' : 'bg-amber-500')} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-[#111827]">{label}</span>
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10px] font-medium',
              isAuto ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-700',
            )}
          >
            {executorLabel}
          </span>
          <span className="text-[11px] text-[#9ca3af]">{tr.affected(group.count)}</span>
        </div>
        <div className="truncate text-[11px] text-[#9ca3af]">{hint}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onFocus}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[#6b7280] hover:bg-[#eef0f2]"
        >
          <Filter size={11} /> {tr.viewSegments}
        </button>
        <button
          type="button"
          onClick={onOpenEditor}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[#3b5bdb] hover:bg-[#3b5bdb]/10"
        >
          {tr.goEditor} <ExternalLink size={11} />
        </button>
      </div>
    </div>
  )
}
