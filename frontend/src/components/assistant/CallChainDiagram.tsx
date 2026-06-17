import { useState } from 'react'
import { ArrowRight, Check, Loader2, Pencil, X } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'
import type { AssistantPlan, PlanStep, RunState } from '../../types/assistant'
import { FALLBACK_TOOL_ICON, TOOL_META } from './toolMeta'

interface CallChainDiagramProps {
  plan: AssistantPlan
  runState?: RunState | null
  editable?: boolean
  onChange?: (plan: AssistantPlan) => void
}

type NodeStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

const STATUS_STYLES: Record<NodeStatus, { box: string; chip: string }> = {
  pending: { box: 'border-[#e4e9f0] bg-white', chip: 'bg-[#f3f4f6] text-[#6b7280]' },
  running: { box: 'border-[#3b5bdb] bg-[#f0f3ff] shadow-[0_0_0_3px_rgba(59,91,219,0.12)]', chip: 'bg-blue-50 text-[#3b5bdb]' },
  completed: { box: 'border-emerald-300 bg-emerald-50', chip: 'bg-emerald-100 text-emerald-700' },
  failed: { box: 'border-red-300 bg-red-50', chip: 'bg-red-100 text-red-600' },
  cancelled: { box: 'border-amber-300 bg-amber-50', chip: 'bg-amber-100 text-amber-700' },
}

function normalizeStatus(status: string | undefined): NodeStatus {
  if (status === 'running' || status === 'completed' || status === 'failed' || status === 'cancelled') {
    return status
  }
  return 'pending'
}

function coerceValue(original: unknown, raw: string): unknown {
  if (typeof original === 'number') {
    const n = Number(raw)
    return Number.isNaN(n) ? raw : n
  }
  if (typeof original === 'boolean') return raw === 'true'
  return raw
}

export function CallChainDiagram({ plan, runState, editable = false, onChange }: CallChainDiagramProps) {
  const { t, locale } = useI18n()
  const [editingId, setEditingId] = useState<string | null>(null)

  const statusLabel: Record<NodeStatus, string> = {
    pending: t.assistant.statusPending,
    running: t.assistant.statusRunning,
    completed: t.assistant.statusCompleted,
    failed: t.assistant.statusFailed,
    cancelled: t.assistant.statusCancelled,
  }

  function stepStatus(step: PlanStep): NodeStatus {
    const rs = runState?.steps.find(s => s.id === step.id)
    return normalizeStatus(rs?.status)
  }

  function updateParam(stepId: string, key: string, value: unknown) {
    const next: AssistantPlan = {
      ...plan,
      steps: plan.steps.map(s =>
        s.id === stepId ? { ...s, params: { ...s.params, [key]: value } } : s,
      ),
    }
    onChange?.(next)
  }

  return (
    <div className="flex flex-wrap items-stretch gap-2" data-testid="call-chain-diagram">
      {plan.steps.map((step, index) => {
        const meta = TOOL_META[step.tool_id]
        const Icon = meta?.icon ?? FALLBACK_TOOL_ICON
        const status = stepStatus(step)
        const styles = STATUS_STYLES[status]
        const label = step.title || (meta ? (locale === 'zh-CN' ? meta.zh : meta.en) : step.tool_id)
        const paramKeys = Object.keys(step.params)
        const isEditing = editingId === step.id

        return (
          <div key={step.id} className="flex items-stretch gap-2">
            <div
              className={cn(
                'relative flex w-44 flex-col rounded-xl border p-3 transition-all',
                styles.box,
              )}
              data-testid={`chain-node-${step.id}`}
              data-status={status}
            >
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#3b5bdb]/10 text-[#3b5bdb]">
                  <Icon size={16} />
                </span>
                <span className="truncate text-sm font-semibold text-[#1f2937]" title={label}>
                  {label}
                </span>
              </div>

              <div className="mt-1.5 flex items-center gap-1">
                <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium', styles.chip)}>
                  {status === 'running' && <Loader2 size={11} className="animate-spin" />}
                  {status === 'completed' && <Check size={11} />}
                  {statusLabel[status]}
                </span>
              </div>

              {step.rationale && (
                <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-[#6b7280]" title={step.rationale}>
                  {step.rationale}
                </p>
              )}

              {paramKeys.length > 0 && !isEditing && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {paramKeys.map(key => (
                    <span key={key} className="rounded bg-[#f3f4f6] px-1.5 py-0.5 text-[10px] text-[#4b5563]">
                      {key}: {String(step.params[key])}
                    </span>
                  ))}
                </div>
              )}

              {editable && paramKeys.length > 0 && (
                <button
                  type="button"
                  onClick={() => setEditingId(isEditing ? null : step.id)}
                  className="mt-2 inline-flex items-center gap-1 self-start rounded-md border border-[#e4e9f0] px-2 py-0.5 text-[11px] text-[#4b5563] transition-colors hover:bg-[#f3f4f6]"
                >
                  {isEditing ? <X size={11} /> : <Pencil size={11} />}
                  {t.assistant.editParams}
                </button>
              )}

              {editable && isEditing && (
                <div className="mt-2 space-y-1.5 border-t border-[#eef1f6] pt-2">
                  {paramKeys.length === 0 && (
                    <p className="text-[11px] text-[#9ca3af]">{t.assistant.noEditableParams}</p>
                  )}
                  {paramKeys.map(key => {
                    const value = step.params[key]
                    if (typeof value === 'boolean') {
                      return (
                        <label key={key} className="flex items-center justify-between gap-2 text-[11px] text-[#4b5563]">
                          <span className="truncate" title={key}>{key}</span>
                          <input
                            type="checkbox"
                            checked={value}
                            aria-label={key}
                            onChange={e => updateParam(step.id, key, e.target.checked)}
                          />
                        </label>
                      )
                    }
                    return (
                      <label key={key} className="block text-[11px] text-[#4b5563]">
                        <span className="mb-0.5 block truncate" title={key}>{key}</span>
                        <input
                          type="text"
                          defaultValue={String(value)}
                          aria-label={key}
                          onChange={e => updateParam(step.id, key, coerceValue(value, e.target.value))}
                          className="w-full rounded border border-[#e4e9f0] px-1.5 py-1 text-[11px] focus:border-[#3b5bdb] focus:outline-none"
                        />
                      </label>
                    )
                  })}
                </div>
              )}
            </div>

            {index < plan.steps.length - 1 && (
              <div className="flex items-center text-[#c0c6d4]">
                <ArrowRight size={18} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
