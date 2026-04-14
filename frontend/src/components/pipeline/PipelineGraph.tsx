import { cn } from '../../lib/utils'
import { STAGE_LABELS, STAGE_ORDER } from '../../lib/utils'
import type { TaskStage } from '../../types'

const STATUS_NODE_STYLE: Record<string, string> = {
  pending: 'border-2 border-dashed border-slate-300 bg-white text-slate-400',
  running: 'border-2 border-blue-500 bg-blue-50 text-blue-700',
  succeeded: 'border-2 border-emerald-400 bg-emerald-50 text-emerald-700',
  cached: 'border-2 border-violet-400 bg-violet-50 text-violet-700',
  failed: 'border-2 border-red-400 bg-red-50 text-red-700',
  skipped: 'border-2 border-amber-400 bg-amber-50 text-amber-700',
}

interface PipelineGraphProps {
  stages: TaskStage[]
  activeStage?: string
  onStageClick?: (stageName: string) => void
}

export function PipelineGraph({ stages, activeStage, onStageClick }: PipelineGraphProps) {
  const stageMap = new Map(stages.map(s => [s.stage_name, s]))

  const rows = [
    ['stage1', 'task-a', 'task-b', 'task-c'],
    ['task-d', 'task-e', 'task-g'],
  ]

  return (
    <div className="space-y-3">
      {rows.map((row, rowIdx) => (
        <div key={rowIdx} className="flex items-center gap-2 flex-wrap">
          {row.map((stageName, i) => {
            const stage = stageMap.get(stageName)
            const status = stage?.status ?? 'pending'
            const isActive = stageName === activeStage
            const shortName = stageName === 'stage1' ? 'Stage 1' : stageName.toUpperCase()
            const pct = stage?.progress_percent ?? 0

            return (
              <div key={stageName} className="flex items-center gap-2">
                <button
                  onClick={() => onStageClick?.(stageName)}
                  className={cn(
                    'relative rounded-xl px-3 py-2 min-w-[90px] text-center transition-all cursor-pointer',
                    STATUS_NODE_STYLE[status],
                    isActive && 'ring-2 ring-blue-400 ring-offset-1',
                  )}
                >
                  <div className="text-xs font-semibold">{shortName}</div>
                  {status === 'running' && (
                    <div className="text-xs mt-0.5">{pct.toFixed(0)}%</div>
                  )}
                  {status === 'succeeded' && (
                    <div className="text-xs mt-0.5">✓</div>
                  )}
                  {status === 'cached' && (
                    <div className="text-xs mt-0.5">缓存</div>
                  )}
                  {status === 'failed' && (
                    <div className="text-xs mt-0.5">✕</div>
                  )}
                  {status === 'pending' && (
                    <div className="text-xs mt-0.5">···</div>
                  )}
                  {status === 'running' && isActive && (
                    <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-blue-500 rounded-full animate-pulse" />
                  )}
                </button>
                {i < row.length - 1 && (
                  <span className="text-slate-300 text-sm">→</span>
                )}
              </div>
            )
          })}
          {rowIdx === 0 && <span className="text-slate-300 text-sm">→</span>}
        </div>
      ))}
    </div>
  )
}
