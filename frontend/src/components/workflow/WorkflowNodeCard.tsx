import { motion, useReducedMotion } from 'framer-motion'
import { AudioWaveform, Captions, Eraser, PackageCheck } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import type { WorkflowGraphNode } from '../../types'

const STATUS_STYLES: Record<WorkflowGraphNode['status'], string> = {
  pending: 'border-slate-200 bg-white/95 text-slate-500 shadow-sm',
  running: 'border-sky-400/70 bg-linear-to-br from-sky-50 via-white to-blue-100 text-sky-800 shadow-[0_16px_45px_-24px_rgba(14,165,233,0.8)]',
  succeeded: 'border-emerald-300 bg-linear-to-br from-emerald-50 via-white to-lime-50 text-emerald-800 shadow-[0_16px_45px_-26px_rgba(16,185,129,0.75)]',
  cached: 'border-violet-300 bg-linear-to-br from-violet-50 via-white to-fuchsia-50 text-violet-800 shadow-[0_16px_45px_-26px_rgba(139,92,246,0.75)]',
  failed: 'border-rose-300 bg-linear-to-br from-rose-50 via-white to-red-50 text-rose-800 shadow-[0_16px_45px_-24px_rgba(244,63,94,0.75)]',
  skipped: 'border-amber-300 bg-linear-to-br from-amber-50 via-white to-orange-50 text-amber-800 shadow-[0_16px_45px_-24px_rgba(245,158,11,0.6)]',
}

const GROUP_ICON: Record<WorkflowGraphNode['group'], typeof AudioWaveform> = {
  'audio-spine': AudioWaveform,
  'ocr-subtitles': Captions,
  'video-cleanup': Eraser,
  delivery: PackageCheck,
}

interface WorkflowNodeCardProps {
  node: WorkflowGraphNode
  selected?: boolean
  compact?: boolean
  onClick?: (nodeId: string) => void
}

export function WorkflowNodeCard({ node, selected = false, compact = false, onClick }: WorkflowNodeCardProps) {
  const { getStageLabel, getStageShortLabel, getStatusLabel, t } = useI18n()
  const reduceMotion = useReducedMotion()
  const Icon = GROUP_ICON[node.group]
  const label = compact
    ? getStageShortLabel(node.id as keyof typeof t.stageShort)
    : getStageLabel(node.id as keyof typeof t.stages)
  const statusLabel = getStatusLabel(node.status as keyof typeof t.status)

  if (compact) {
    return (
      <motion.button
        type="button"
        layout={!reduceMotion}
        whileHover={reduceMotion ? undefined : { y: -2, scale: 1.02 }}
        whileTap={reduceMotion ? undefined : { scale: 0.98 }}
        onClick={() => onClick?.(node.id)}
        className={cn(
          'relative flex w-full flex-col items-center gap-2 overflow-hidden rounded-2xl border px-2 py-3 text-center transition-all duration-200',
          STATUS_STYLES[node.status],
          selected && 'ring-2 ring-sky-400/70 ring-offset-2 ring-offset-white',
        )}
      >
        {/* Required/optional indicator */}
        <span
          className={cn(
            'absolute right-2 top-2 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest leading-none',
            node.required
              ? 'bg-slate-200/90 text-slate-500'
              : 'border border-dashed border-slate-300/80 text-slate-400',
          )}
        >
          {node.required ? t.workflow.required : t.workflow.optional}
        </span>

        {/* Icon */}
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/85 text-current shadow-sm">
          <Icon size={16} />
        </div>

        {/* Label */}
        <div className="w-full px-1 text-[11px] font-semibold leading-tight text-current/90 line-clamp-2">
          {label}
        </div>

        {/* Status chip — only when not pending */}
        {node.status !== 'pending' && (
          <div className="flex items-center gap-1 text-[10px] font-medium text-current/70">
            {node.status === 'running' && (
              <span className="font-bold">{node.progress_percent.toFixed(0)}%</span>
            )}
            {node.status !== 'running' && (
              <span>{statusLabel}</span>
            )}
          </div>
        )}

        {/* Progress bar */}
        {node.status === 'running' && (
          <div className="mt-0.5 w-full overflow-hidden rounded-full bg-white/55 px-1">
            <motion.div
              className="h-1 rounded-full bg-sky-500"
              initial={false}
              animate={{ width: `${node.progress_percent}%` }}
              transition={{ duration: reduceMotion ? 0 : 0.45, ease: 'easeOut' }}
            />
          </div>
        )}

        {/* Running shimmer */}
        {node.status === 'running' && !reduceMotion && (
          <motion.div
            className="pointer-events-none absolute inset-0 rounded-2xl bg-linear-to-r from-transparent via-white/25 to-transparent"
            animate={{ x: ['-115%', '115%'] }}
            transition={{ duration: 1.6, ease: 'linear', repeat: Infinity }}
          />
        )}
      </motion.button>
    )
  }

  return (
    <motion.button
      type="button"
      layout={!reduceMotion}
      whileHover={reduceMotion ? undefined : { y: -2, scale: 1.01 }}
      whileTap={reduceMotion ? undefined : { scale: 0.99 }}
      onClick={() => onClick?.(node.id)}
      className={cn(
        'relative w-full overflow-hidden rounded-[22px] border px-4 py-3 text-left transition-all duration-200 min-h-[132px]',
        STATUS_STYLES[node.status],
        selected && 'ring-2 ring-sky-400/70 ring-offset-2 ring-offset-white',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/80 text-current shadow-sm">
            <Icon size={16} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
              {node.id}
            </div>
            <div className="mt-1 line-clamp-2 text-sm font-semibold text-current">
              {label}
            </div>
          </div>
        </div>
        <span
          className={cn(
            'shrink-0 rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em]',
            node.required
              ? 'border-slate-200 bg-white/80 text-slate-500'
              : 'border-dashed border-slate-300 bg-white/65 text-slate-400',
          )}
        >
          {node.required ? t.workflow.required : t.workflow.optional}
        </span>
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 text-xs">
        <span className="font-medium text-current/80">{statusLabel}</span>
        <span className="font-semibold text-current">
          {node.status === 'running'
            ? `${node.progress_percent.toFixed(0)}%`
            : node.status === 'cached'
              ? t.pipeline.cached
              : node.status === 'pending'
                ? t.pipeline.pending
                : node.status === 'failed'
                  ? '✕'
                  : '✓'}
        </span>
      </div>

      {(node.current_step || node.error_message) && (
        <div className="mt-2 line-clamp-2 rounded-2xl bg-white/65 px-3 py-2 text-[11px] text-current/80 shadow-inner">
          {node.error_message ?? node.current_step}
        </div>
      )}

      {node.status === 'running' && (
        <div className="mt-3 overflow-hidden rounded-full bg-white/55">
          <motion.div
            className="h-1.5 rounded-full bg-sky-500"
            initial={false}
            animate={{ width: `${node.progress_percent}%` }}
            transition={{ duration: reduceMotion ? 0 : 0.45, ease: 'easeOut' }}
          />
        </div>
      )}

      {node.status === 'running' && !reduceMotion && (
        <motion.div
          className="pointer-events-none absolute inset-0 rounded-[22px] bg-linear-to-r from-transparent via-white/25 to-transparent"
          animate={{ x: ['-115%', '115%'] }}
          transition={{ duration: 1.6, ease: 'linear', repeat: Infinity }}
        />
      )}
    </motion.button>
  )
}
