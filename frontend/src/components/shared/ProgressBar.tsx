import { cn } from '../../lib/utils'

interface ProgressBarProps {
  value: number // 0-100
  size?: 'sm' | 'md' | 'lg'
  color?: string
  className?: string
}

export function ProgressBar({ value, size = 'md', color, className }: ProgressBarProps) {
  const heights = { sm: 'h-1.5', md: 'h-2', lg: 'h-3' }
  const pct = Math.max(0, Math.min(100, value))

  return (
    <div className={cn('w-full bg-slate-100 rounded-full overflow-hidden', heights[size], className)}>
      <div
        className={cn(
          'h-full rounded-full transition-all duration-500',
          color ?? 'bg-blue-500',
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
