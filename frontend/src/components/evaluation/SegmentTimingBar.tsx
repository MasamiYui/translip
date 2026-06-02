import type { DubQaSegment } from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'
import { classifyTiming, type TimingInfo } from './timing'

function pct(value: number, scale: number): number {
  if (scale <= 0) return 0
  return Math.max(0, Math.min(100, (value / scale) * 100))
}

function formatDelta(deltaSec: number): string {
  const sign = deltaSec >= 0 ? '+' : '−'
  return `${sign}${Math.abs(deltaSec).toFixed(1)}s`
}

const FILL_BY_STATUS: Record<string, string> = {
  failed: 'bg-red-400',
  review: 'bg-amber-400',
  passed: 'bg-emerald-400',
}

function dubFill(info: TimingInfo): string {
  if (info.durationStatus && FILL_BY_STATUS[info.durationStatus]) {
    return FILL_BY_STATUS[info.durationStatus]
  }
  return info.kind === 'overflow' || info.kind === 'underflow' ? 'bg-amber-400' : 'bg-emerald-400'
}

/**
 * Per-segment duration-deviation bar: original window (top) vs the dub's actual
 * placed footprint (bottom). Overflow extends past the window in red; underflow
 * leaves the window outline unfilled; an undubbed line shows an empty dashed bar.
 */
export function SegmentTimingBar({
  segment,
  variant = 'compact',
  className,
}: {
  segment: DubQaSegment
  variant?: 'compact' | 'full'
  className?: string
}) {
  const { t } = useI18n()
  const tt = t.evaluation.timing
  const info = classifyTiming(segment)
  const { windowSec, dubSec, kind } = info

  if (windowSec == null && dubSec == null) {
    return <span className={cn('text-[11px] text-[#9ca3af]', className)}>{tt.noData}</span>
  }

  const scale = Math.max(windowSec ?? 0, dubSec ?? 0) || 1
  const winPct = windowSec != null ? pct(windowSec, scale) : 0
  const dubPct = dubSec != null ? pct(dubSec, scale) : 0
  const basePct = Math.min(winPct, dubPct)
  const overflowPct = Math.max(0, dubPct - winPct)
  const barH = variant === 'full' ? 'h-2.5' : 'h-1.5'

  const strategyKey = (info.fitStrategy ?? 'unknown') as keyof typeof tt.strategyMap
  const strategyLabel = tt.strategyMap[strategyKey] ?? info.fitStrategy
  const showStretch = info.stretchRatio != null && Math.abs(info.stretchRatio - 1) >= 0.1

  const deltaText =
    kind === 'undubbed'
      ? tt.undubbed
      : kind === 'unknown'
        ? '—'
        : info.deltaSec != null && Math.abs(info.deltaSec) >= 0.05
          ? formatDelta(info.deltaSec)
          : tt.onTime
  const deltaColor =
    kind === 'undubbed'
      ? 'text-red-600'
      : kind === 'overflow'
        ? 'text-red-600'
        : kind === 'underflow'
          ? 'text-amber-600'
          : 'text-emerald-600'

  return (
    <div className={cn(variant === 'full' ? 'w-full' : 'w-[150px]', className)}>
      <div className="flex flex-col gap-[3px]">
        {/* Window row */}
        <div className={cn('relative w-full rounded-full bg-[#f1f3f5]', barH)}>
          <div
            className={cn('absolute left-0 top-0 rounded-full bg-slate-300', barH)}
            style={{ width: `${winPct}%` }}
          />
        </div>
        {/* Dub row: outline of the window + fill + red overflow tail */}
        <div className={cn('relative w-full rounded-full bg-[#f1f3f5]', barH)}>
          {windowSec != null && (
            <div
              className={cn('absolute left-0 top-0 rounded-full border border-dashed border-slate-300', barH)}
              style={{ width: `${winPct}%` }}
            />
          )}
          {kind === 'undubbed' ? (
            <div
              className={cn('absolute left-0 top-0 rounded-full border border-dashed border-red-300', barH)}
              style={{ width: `${winPct}%` }}
            />
          ) : (
            <>
              <div
                className={cn('absolute left-0 top-0 rounded-l-full', dubFill(info), basePct >= 99.5 && 'rounded-r-full', barH)}
                style={{ width: `${basePct}%` }}
              />
              {overflowPct > 0 && (
                <div
                  className={cn('absolute top-0 rounded-r-full bg-red-500', barH)}
                  style={{ left: `${winPct}%`, width: `${overflowPct}%` }}
                />
              )}
            </>
          )}
        </div>
      </div>

      <div className="mt-1 flex items-center gap-1.5 text-[10px] leading-none">
        <span className={cn('font-medium', deltaColor)}>{deltaText}</span>
        {showStretch && (
          <span className="text-[#9ca3af]">×{info.stretchRatio!.toFixed(2)}</span>
        )}
        {variant === 'full' && strategyLabel && strategyLabel !== '—' && (
          <span className="rounded bg-[#f3f4f6] px-1 py-0.5 text-[#6b7280]">{strategyLabel}</span>
        )}
      </div>

      {variant === 'full' && (
        <dl className="mt-2 grid grid-cols-2 gap-y-1 text-[11px]">
          <dt className="text-[#9ca3af]">{tt.window}</dt>
          <dd className="text-right font-medium text-[#374151]">
            {windowSec != null ? `${windowSec.toFixed(2)}s` : '—'}
          </dd>
          <dt className="text-[#9ca3af]">{tt.dub}</dt>
          <dd className={cn('text-right font-medium', deltaColor)}>
            {dubSec != null ? `${dubSec.toFixed(2)}s` : '—'}
          </dd>
        </dl>
      )}
    </div>
  )
}
