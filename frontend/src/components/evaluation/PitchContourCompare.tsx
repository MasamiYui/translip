import { useMemo, useState } from 'react'
import type { DubQaReport, DubQaSegment } from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

interface PitchContourCompareProps {
  report: DubQaReport
  selectedId?: string | null
  onSelectSegment?: (segment: DubQaSegment) => void
  embedded?: boolean
}

const CHART_HEIGHT = 96
const CHART_PAD_TOP = 8
const CHART_PAD_BOTTOM = 16
const ORIG_COLOR = '#94a3b8'
const DUB_COLOR = '#3b5bdb'
const INITIAL_PAGE_SIZE = 6

interface SegmentPitch {
  segment: DubQaSegment
  duration: number
  origVoiced: number[]
  dubVoiced: number[]
  semitoneShift: number | null
  hzMin: number
  hzMax: number
}

function hzToY(hz: number, hzMin: number, hzMax: number, height: number): number {
  if (hzMax <= hzMin) return height / 2
  const lo = Math.log(hzMin)
  const hi = Math.log(hzMax)
  const ratio = (Math.log(hz) - lo) / (hi - lo)
  const usable = height - CHART_PAD_TOP - CHART_PAD_BOTTOM
  return CHART_PAD_TOP + (1 - ratio) * usable
}

function buildPath(
  times: number[],
  hz: (number | null)[],
  duration: number,
  hzMin: number,
  hzMax: number,
  width: number,
): string {
  if (times.length === 0 || duration <= 0) return ''
  const segments: string[] = []
  let pen = false
  for (let i = 0; i < times.length; i += 1) {
    const t = times[i] ?? 0
    const f = hz[i]
    if (f == null || !Number.isFinite(f)) {
      pen = false
      continue
    }
    const x = Math.min(width, Math.max(0, (t / duration) * width))
    const y = hzToY(f, hzMin, hzMax, CHART_HEIGHT)
    segments.push(`${pen ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`)
    pen = true
  }
  return segments.join(' ')
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[mid - 1]! + sorted[mid]!) / 2 : sorted[mid]!
}

function semitones(a: number, b: number): number {
  return 12 * Math.log2(a / b)
}

function buildSegmentPitch(segment: DubQaSegment): SegmentPitch | null {
  const contour = segment.pitch_contour
  if (!contour) return null
  const orig = contour.original
  const dub = contour.dub
  const allHz: number[] = []
  const origVoiced: number[] = []
  const dubVoiced: number[] = []
  for (const hz of orig.hz) {
    if (hz != null && Number.isFinite(hz)) {
      origVoiced.push(hz)
      allHz.push(hz)
    }
  }
  for (const hz of dub.hz) {
    if (hz != null && Number.isFinite(hz)) {
      dubVoiced.push(hz)
      allHz.push(hz)
    }
  }
  if (allHz.length === 0) return null

  const start = typeof segment.start === 'number' ? segment.start : 0
  const end = typeof segment.end === 'number' ? segment.end : 0
  const duration =
    typeof segment.duration === 'number' && segment.duration > 0
      ? segment.duration
      : Math.max(end - start, 0.001)

  const minObserved = Math.min(...allHz)
  const maxObserved = Math.max(...allHz)
  // Pad the y-axis a third of an octave on each side so curves don't graze the edges.
  const hzMin = Math.max(50, minObserved / Math.pow(2, 1 / 3))
  const hzMax = Math.min(1200, maxObserved * Math.pow(2, 1 / 3))

  const origMedian = median(origVoiced)
  const dubMedian = median(dubVoiced)
  const semitoneShift =
    origMedian != null && dubMedian != null && origMedian > 0 && dubMedian > 0
      ? semitones(dubMedian, origMedian)
      : null

  return {
    segment,
    duration,
    origVoiced,
    dubVoiced,
    semitoneShift,
    hzMin,
    hzMax,
  }
}

function formatHz(hz: number): string {
  return hz >= 100 ? `${Math.round(hz)} Hz` : `${hz.toFixed(1)} Hz`
}

function formatSemitone(value: number | null): string {
  if (value == null) return '—'
  const cents = Math.round(value * 100)
  const sign = cents > 0 ? '+' : ''
  return `${sign}${cents} ¢`
}

function semitoneBadgeColor(value: number | null): string {
  if (value == null) return 'bg-slate-100 text-slate-600 ring-slate-200'
  const abs = Math.abs(value)
  if (abs <= 1) return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (abs <= 2.5) return 'bg-amber-50 text-amber-700 ring-amber-200'
  return 'bg-rose-50 text-rose-700 ring-rose-200'
}

export function PitchContourCompare({
  report,
  selectedId,
  onSelectSegment,
  embedded = false,
}: PitchContourCompareProps) {
  const { t } = useI18n()
  const tx = t.evaluation.pitchCompare
  const [showAll, setShowAll] = useState(false)

  const items = useMemo(() => {
    const out: SegmentPitch[] = []
    for (const seg of report.segments) {
      const p = buildSegmentPitch(seg)
      if (p) out.push(p)
    }
    return out
  }, [report.segments])

  if (items.length === 0) {
    return null
  }

  const visible = showAll ? items : items.slice(0, INITIAL_PAGE_SIZE)
  const hiddenCount = items.length - visible.length

  return (
    <div
      className={cn(
        !embedded && 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm',
      )}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-900">{tx.title}</h3>
          <p className="mt-1 text-sm text-slate-500">{tx.subtitle}</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 bg-slate-400" />
            {tx.legendOriginal}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4" style={{ background: DUB_COLOR }} />
            {tx.legendDub}
          </span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-1 md:grid-cols-2">
        {visible.map(item => {
          const seg = item.segment
          const isSelected = selectedId === seg.segment_id
          const width = 360
          const origPath = buildPath(
            seg.pitch_contour!.original.times,
            seg.pitch_contour!.original.hz,
            item.duration,
            item.hzMin,
            item.hzMax,
            width,
          )
          const dubPath = buildPath(
            seg.pitch_contour!.dub.times,
            seg.pitch_contour!.dub.hz,
            item.duration,
            item.hzMin,
            item.hzMax,
            width,
          )
          const yMid = hzToY(
            Math.sqrt(item.hzMin * item.hzMax),
            item.hzMin,
            item.hzMax,
            CHART_HEIGHT,
          )
          return (
            <button
              key={seg.segment_id}
              type="button"
              onClick={() => onSelectSegment?.(seg)}
              className={cn(
                'group flex flex-col rounded-xl border bg-slate-50/40 p-3 text-left transition',
                'hover:border-slate-300 hover:bg-white hover:shadow-sm',
                isSelected
                  ? 'border-indigo-400 bg-white ring-2 ring-indigo-200'
                  : 'border-slate-200',
              )}
            >
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="truncate font-mono text-slate-600">{seg.segment_id}</span>
                <span
                  className={cn(
                    'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] ring-1',
                    semitoneBadgeColor(item.semitoneShift),
                  )}
                  title={tx.semitoneTooltip}
                >
                  {formatSemitone(item.semitoneShift)}
                </span>
              </div>
              <div className="mt-2 overflow-hidden rounded-md bg-white">
                <svg viewBox={`0 0 ${width} ${CHART_HEIGHT}`} className="h-24 w-full">
                  <line
                    x1={0}
                    x2={width}
                    y1={yMid}
                    y2={yMid}
                    stroke="#e2e8f0"
                    strokeDasharray="3 3"
                  />
                  {origPath ? (
                    <path
                      d={origPath}
                      fill="none"
                      stroke={ORIG_COLOR}
                      strokeWidth={1.5}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  ) : null}
                  {dubPath ? (
                    <path
                      d={dubPath}
                      fill="none"
                      stroke={DUB_COLOR}
                      strokeWidth={1.75}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  ) : null}
                </svg>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
                <span>
                  {formatHz(item.hzMin)} ↕ {formatHz(item.hzMax)}
                </span>
                <span>
                  {item.duration.toFixed(2)}s
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {hiddenCount > 0 ? (
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:border-slate-300 hover:text-slate-800"
          >
            {tx.showAll.replace('{n}', String(hiddenCount))}
          </button>
        </div>
      ) : null}
      {items.length > INITIAL_PAGE_SIZE && showAll ? (
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            onClick={() => setShowAll(false)}
            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-500 hover:border-slate-300"
          >
            {tx.collapse}
          </button>
        </div>
      ) : null}
    </div>
  )
}
