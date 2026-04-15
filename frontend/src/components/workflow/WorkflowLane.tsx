import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface WorkflowLaneProps {
  label: string
  hint?: string
  children: ReactNode
  compact?: boolean
}

export function WorkflowLane({ label, hint, children, compact = false }: WorkflowLaneProps) {
  return (
    <section
      className={cn(
        'relative rounded-[28px] border border-slate-200/80 bg-white/80 px-4 py-4 shadow-[0_18px_50px_-34px_rgba(15,23,42,0.5)] backdrop-blur',
        compact && 'rounded-[24px] px-3 py-3',
      )}
    >
      <div className={cn('flex items-center justify-between gap-3', compact ? 'mb-2' : 'mb-3')}>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">{label}</div>
          {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
        </div>
      </div>
      {children}
    </section>
  )
}
