import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import type { TaskStatus, StageStatus } from '../../types'
import type { StatusKey } from '../../i18n/formatters'

const STATUS_CONFIG: Record<string, { dot: string; bg: string; text: string }> = {
  pending: { dot: 'bg-[#9ca3af]', bg: 'bg-[#f3f4f6]', text: 'text-[#4b5563]' },
  running: { dot: 'bg-[#3b5bdb] animate-pulse', bg: 'bg-blue-50', text: 'text-[#3b5bdb]' },
  succeeded: { dot: 'bg-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-700' },
  completed: { dot: 'bg-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-700' },
  partial_success: { dot: 'bg-amber-500', bg: 'bg-amber-50', text: 'text-amber-700' },
  failed: { dot: 'bg-red-400', bg: 'bg-red-50', text: 'text-red-600' },
  cancelled: { dot: 'bg-[#9ca3af]', bg: 'bg-[#f3f4f6]', text: 'text-[#6b7280]' },
  interrupted: { dot: 'bg-amber-500', bg: 'bg-amber-50', text: 'text-amber-700' },
  cached: { dot: 'bg-violet-500', bg: 'bg-violet-50', text: 'text-violet-700' },
  skipped: { dot: 'bg-[#9ca3af]', bg: 'bg-[#f3f4f6]', text: 'text-[#6b7280]' },
}

interface StatusBadgeProps {
  status: TaskStatus | StageStatus | string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const { getStatusLabel } = useI18n()
  const key: StatusKey = status in STATUS_CONFIG ? (status as StatusKey) : 'pending'
  const cfg = STATUS_CONFIG[key] ?? STATUS_CONFIG.pending

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        cfg.bg,
        cfg.text,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs',
      )}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', cfg.dot)} />
      {getStatusLabel(key)}
    </span>
  )
}
