import { useNavigate } from 'react-router-dom'
import { Download, ExternalLink, Filter, Sparkles } from 'lucide-react'
import type {
  DubQaReport,
  RemediationActionGroup,
  RemediationExecutor,
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
}: {
  taskId: string
  report: DubQaReport
  onFocusSegments: (segmentIds: string[], label: string) => void
}) {
  const { t } = useI18n()
  const tr = t.evaluation.remediation
  const navigate = useNavigate()
  const plan = report.remediation

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
        <button
          type="button"
          onClick={exportPlan}
          title={tr.exportHint}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-[#e5e7eb] px-2.5 py-1.5 text-xs font-medium text-[#374151] hover:bg-[#f9fafb]"
        >
          <Download size={13} /> {tr.export}
        </button>
      </div>

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
