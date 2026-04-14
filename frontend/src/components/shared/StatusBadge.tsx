import { cn } from '../../lib/utils'
import type { TaskStatus, StageStatus } from '../../types'

const STATUS_CONFIG: Record<string, { label: string; dot: string; bg: string; text: string }> = {
  pending: { label: '等待中', dot: 'bg-slate-400', bg: 'bg-slate-100', text: 'text-slate-600' },
  running: { label: '运行中', dot: 'bg-blue-500 animate-pulse', bg: 'bg-blue-50', text: 'text-blue-700' },
  succeeded: { label: '已完成', dot: 'bg-emerald-500', bg: 'bg-emerald-50', text: 'text-emerald-700' },
  failed: { label: '失败', dot: 'bg-red-500', bg: 'bg-red-50', text: 'text-red-700' },
  cached: { label: '已缓存', dot: 'bg-violet-500', bg: 'bg-violet-50', text: 'text-violet-700' },
  skipped: { label: '跳过', dot: 'bg-amber-500', bg: 'bg-amber-50', text: 'text-amber-700' },
}

interface StatusBadgeProps {
  status: TaskStatus | StageStatus | string
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending
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
      {cfg.label}
    </span>
  )
}
