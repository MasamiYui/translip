import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Maximize2, ZoomIn, ZoomOut } from 'lucide-react'
import {
  taskArtifactUrl,
  type DubQaReport,
  type DubQaSegment,
} from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'
import { loadTrackPeaks, type TrackPeaks } from '../../lib/waveform'

const BUCKETS = 4000
const LANE_HEIGHT = 44
const RULER_HEIGHT = 20
const GUTTER = '4.5rem' // w-16 label + gap-2 == 72px
const TICK_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900]

interface LoadedTracks {
  original?: TrackPeaks
  dub?: TrackPeaks
}

interface View {
  total: number
  start: number
  end: number
}

function relPath(report: DubQaReport, key: 'original_voice' | 'dub_voice'): string | null {
  const value = report.input?.[key]
  return typeof value === 'string' && value.length > 0 ? value : null
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

function niceStep(rough: number): number {
  for (const s of TICK_STEPS) if (s >= rough) return s
  return TICK_STEPS[TICK_STEPS.length - 1]
}

function formatTick(sec: number, step: number): string {
  let m = Math.floor(sec / 60)
  let s = sec - m * 60
  if (step >= 1) {
    s = Math.round(s)
    if (s >= 60) {
      m += 1
      s -= 60
    }
    return `${m}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

/** Draw the visible time window [viewStart, viewEnd] of a track's peaks. */
function drawTrack(
  canvas: HTMLCanvasElement,
  track: TrackPeaks,
  viewStart: number,
  viewEnd: number,
  color: string,
) {
  const dpr = window.devicePixelRatio || 1
  const cssWidth = canvas.clientWidth
  const cssHeight = canvas.clientHeight
  canvas.width = Math.floor(cssWidth * dpr)
  canvas.height = Math.floor(cssHeight * dpr)
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, cssWidth, cssHeight)
  const dur = viewEnd - viewStart
  const { peaks, durationSec } = track
  if (dur <= 0 || peaks.length === 0 || durationSec <= 0) return

  const mid = cssHeight / 2
  ctx.fillStyle = color
  const cols = Math.max(1, Math.floor(cssWidth))
  for (let x = 0; x < cols; x++) {
    const t = viewStart + (x / cols) * dur
    if (t < 0 || t > durationSec) continue
    const bucket = clamp(Math.floor((t / durationSec) * peaks.length), 0, peaks.length - 1)
    const h = Math.max(0.5, peaks[bucket] * (cssHeight / 2 - 1))
    ctx.fillRect(x, mid - h, 1, h * 2)
  }
}

function Lane({
  label,
  track,
  viewStart,
  viewEnd,
  color,
  emptyLabel,
}: {
  label: string
  track?: TrackPeaks
  viewStart: number
  viewEnd: number
  color: string
  emptyLabel: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const wrap = wrapRef.current
    const canvas = canvasRef.current
    if (!wrap || !canvas) return
    const render = () => {
      if (!track) {
        const ctx = canvas.getContext('2d')
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height)
        return
      }
      drawTrack(canvas, track, viewStart, viewEnd, color)
    }
    render()
    const ro = new ResizeObserver(render)
    ro.observe(wrap)
    return () => ro.disconnect()
  }, [track, viewStart, viewEnd, color])

  return (
    <div className="flex items-stretch gap-2">
      <div className="flex w-16 shrink-0 items-center text-[11px] font-medium text-[#6b7280]">{label}</div>
      <div ref={wrapRef} className="relative flex-1 overflow-hidden rounded-md bg-[#f8fafc]" style={{ height: LANE_HEIGHT }}>
        {track ? (
          <canvas ref={canvasRef} className="h-full w-full" />
        ) : (
          <div className="flex h-full items-center justify-center text-[10px] text-[#cbd5e1]">{emptyLabel}</div>
        )}
      </div>
    </div>
  )
}

const TIMBRE_LANE_HEIGHT = 22

type TimbreBucket = 'good' | 'review' | 'bad' | 'unknown'

function timbreBucket(score: number | null | undefined): TimbreBucket {
  if (typeof score !== 'number' || Number.isNaN(score)) return 'unknown'
  if (score >= 0.45) return 'good'
  if (score >= 0.25) return 'review'
  return 'bad'
}

/** Maps a [-1, 1] cosine score into a continuous green→amber→red fill. */
function timbreFill(score: number | null | undefined): string {
  const bucket = timbreBucket(score)
  if (bucket === 'unknown') return '#e5e7eb'
  // Clamp similarity into the visually meaningful range [0, 0.7].
  const s = Math.max(0, Math.min(0.7, score as number))
  // Hue: 0 (red) at s=0 → 50 (amber) at 0.25 → 140 (green) at 0.45+.
  const hue = s < 0.25 ? (s / 0.25) * 50 : 50 + ((Math.min(s, 0.45) - 0.25) / 0.2) * 90
  const sat = bucket === 'review' ? 75 : 70
  const light = bucket === 'good' ? 45 : bucket === 'review' ? 55 : 58
  return `hsl(${hue.toFixed(0)} ${sat}% ${light}%)`
}

/**
 * Visualizes per-segment timbre similarity (cosine of ECAPA-TDNN speaker
 * embeddings) along the same time axis as the waveforms. Green = match,
 * amber = needs review, red = mismatch, grey = no data.
 */
function TimbreLane({
  label,
  segments,
  viewStart,
  viewEnd,
  selectedId,
  emptyLabel,
}: {
  label: string
  segments: DubQaSegment[]
  viewStart: number
  viewEnd: number
  selectedId?: string | null
  emptyLabel: string
}) {
  const visibleDur = viewEnd - viewStart
  const ranged = segments.filter(
    s => typeof s.start === 'number' && typeof s.end === 'number' && (s.end as number) > (s.start as number),
  )
  const hasAny = ranged.some(s => typeof s.speaker_similarity === 'number')
  return (
    <div className="flex items-stretch gap-2">
      <div className="flex w-16 shrink-0 items-center text-[11px] font-medium text-[#6b7280]">{label}</div>
      <div
        className="relative flex-1 overflow-hidden rounded-md bg-[#f8fafc]"
        style={{ height: TIMBRE_LANE_HEIGHT }}
      >
        {!hasAny || visibleDur <= 0 ? (
          <div className="flex h-full items-center justify-center text-[10px] text-[#cbd5e1]">{emptyLabel}</div>
        ) : (
          ranged.map(seg => {
            const left = (((seg.start as number) - viewStart) / visibleDur) * 100
            const width = (((seg.end as number) - (seg.start as number)) / visibleDur) * 100
            if (left + width < 0 || left > 100) return null
            const active = seg.segment_id === selectedId
            const score = seg.speaker_similarity
            const fill = timbreFill(score)
            const tip =
              typeof score === 'number'
                ? `${score.toFixed(2)} · ${timbreBucket(score)}`
                : timbreBucket(score)
            return (
              <div
                key={seg.segment_id}
                title={tip}
                className={cn(
                  'absolute top-0 h-full',
                  active ? 'ring-1 ring-[#3b5bdb] ring-inset' : undefined,
                )}
                style={{
                  left: `${left}%`,
                  width: `${Math.max(width, 0.4)}%`,
                  background: fill,
                  opacity: active ? 1 : 0.85,
                }}
              />
            )
          })
        )}
      </div>
    </div>
  )
}

function TimbreLegend({
  labels,
}: {
  labels: { good: string; review: string; bad: string; unknown: string }
}) {
  const items: Array<{ key: TimbreBucket; label: string; color: string }> = [
    { key: 'good', label: labels.good, color: timbreFill(0.6) },
    { key: 'review', label: labels.review, color: timbreFill(0.35) },
    { key: 'bad', label: labels.bad, color: timbreFill(0.1) },
    { key: 'unknown', label: labels.unknown, color: '#e5e7eb' },
  ]
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[#6b7280]">
      {items.map(item => (
        <span key={item.key} className="inline-flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ background: item.color }}
            aria-hidden="true"
          />
          {item.label}
        </span>
      ))}
    </div>
  )
}

/** Time-axis ruler aligned with the lanes (shares the same left gutter + plot width). */
function Ruler({ view }: { view: View }) {
  const dur = view.end - view.start
  const step = niceStep(dur / 8)
  const ticks: number[] = []
  if (dur > 0) {
    for (let t = Math.ceil(view.start / step) * step; t <= view.end + 1e-6; t += step) {
      ticks.push(Number(t.toFixed(3)))
    }
  }
  return (
    <div className="flex gap-2">
      <div className="w-16 shrink-0" />
      <div
        className="relative flex-1 overflow-hidden border-b border-[#eef0f2]"
        style={{ height: RULER_HEIGHT }}
      >
        {ticks.map(t => {
          const left = ((t - view.start) / dur) * 100
          if (left > 99.5) return null
          return (
            <div
              key={t}
              className="absolute inset-y-0 flex flex-col justify-between"
              style={{ left: `${left}%` }}
            >
              <span className="whitespace-nowrap pl-0.5 text-[10px] leading-none text-[#6b7280]">
                {formatTick(t, step)}
              </span>
              <span className="h-1.5 w-px bg-[#cbd5e1]" />
            </div>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Original-vs-dub waveform comparison with a time-axis ruler, scroll-to-zoom
 * (anchored at the cursor) and drag-to-pan. Decodes the isolated original vocal
 * and the full dub track in the browser, draws them aligned on one time axis, and
 * overlays clickable per-segment bands (gaps in the dub lane are undubbed spots).
 */
export function WaveformCompare({
  taskId,
  report,
  segments,
  selectedId,
  onSelectSegment,
  embedded = false,
}: {
  taskId: string
  report: DubQaReport
  segments: DubQaSegment[]
  selectedId?: string | null
  onSelectSegment: (seg: DubQaSegment) => void
  embedded?: boolean
}) {
  const { t } = useI18n()
  const tc = t.evaluation.compare

  const originalUrl = useMemo(() => {
    const rel = relPath(report, 'original_voice')
    return rel ? taskArtifactUrl(taskId, rel) : null
  }, [report, taskId])
  const dubUrl = useMemo(() => {
    const rel = relPath(report, 'dub_voice')
    return rel ? taskArtifactUrl(taskId, rel) : null
  }, [report, taskId])

  const tracksQuery = useQuery({
    queryKey: ['waveform-compare', taskId, originalUrl, dubUrl],
    enabled: !!(originalUrl || dubUrl),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    queryFn: async (): Promise<LoadedTracks> => {
      const load = async (url: string | null) => {
        if (!url) return undefined
        try {
          return await loadTrackPeaks(url, BUCKETS)
        } catch {
          return undefined
        }
      }
      const [original, dub] = await Promise.all([load(originalUrl), load(dubUrl)])
      return { original, dub }
    },
  })

  const tracks: LoadedTracks = tracksQuery.data ?? {}
  const totalDuration = Math.max(tracks.original?.durationSec ?? 0, tracks.dub?.durationSec ?? 0)

  // View is derived from `totalDuration`: a stored view only applies to the same
  // total, so a freshly loaded/changed track resets to full-span without an effect.
  const [storedView, setStoredView] = useState<View | null>(null)
  const view: View =
    storedView && storedView.total === totalDuration
      ? storedView
      : { total: totalDuration, start: 0, end: totalDuration }
  const viewRef = useRef(view)
  viewRef.current = view

  const overlayRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ startX: number; startView: View } | null>(null)
  const movedRef = useRef(false)
  const [grabbing, setGrabbing] = useState(false)

  const minDur = totalDuration > 0 ? Math.min(totalDuration, Math.max(0.3, totalDuration / 300)) : 0
  const visibleDur = view.end - view.start
  const isZoomed = totalDuration > 0 && visibleDur < totalDuration - 1e-6

  const setWindow = (start: number, dur: number) => {
    const d = clamp(dur, minDur, totalDuration)
    const s = clamp(start, 0, totalDuration - d)
    setStoredView({ total: totalDuration, start: s, end: s + d })
  }
  const zoomAround = (frac: number, factor: number) => {
    const cur = viewRef.current
    const dur = cur.end - cur.start
    const anchor = cur.start + frac * dur
    const newDur = clamp(dur * factor, minDur, totalDuration)
    setWindow(anchor - frac * newDur, newDur)
  }

  // Native wheel listener (passive:false) so we can preventDefault while zooming.
  useEffect(() => {
    const el = overlayRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (totalDuration <= 0) return
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      const frac = clamp((e.clientX - rect.left) / rect.width, 0, 1)
      zoomAround(frac, e.deltaY < 0 ? 0.82 : 1 / 0.82)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
    // zoomAround/setWindow read live state via viewRef; only totalDuration matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalDuration])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (totalDuration <= 0 || e.button !== 0) return
    dragRef.current = { startX: e.clientX, startView: viewRef.current }
    movedRef.current = false
    setGrabbing(true)
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const rect = e.currentTarget.getBoundingClientRect()
    const dx = e.clientX - drag.startX
    if (Math.abs(dx) > 3) movedRef.current = true
    const dur = drag.startView.end - drag.startView.start
    setWindow(drag.startView.start - (dx / rect.width) * dur, dur)
  }
  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return
    // A click (no meaningful drag) selects the segment under the cursor.
    if (!movedRef.current && totalDuration > 0) {
      const rect = e.currentTarget.getBoundingClientRect()
      const frac = clamp((e.clientX - rect.left) / rect.width, 0, 1)
      const tClick = view.start + frac * (view.end - view.start)
      const hit = segments.find(
        s =>
          typeof s.start === 'number' &&
          typeof s.end === 'number' &&
          tClick >= s.start &&
          tClick <= s.end,
      )
      if (hit) onSelectSegment(hit)
    }
    dragRef.current = null
    setGrabbing(false)
    e.currentTarget.releasePointerCapture?.(e.pointerId)
  }

  if (!originalUrl && !dubUrl) {
    return (
      <div
        className={cn(
          'p-4 text-center text-xs text-[#9ca3af]',
          !embedded && 'rounded-xl border border-[#e5e7eb] bg-white',
        )}
      >
        {tc.unavailable}
      </div>
    )
  }

  const state: 'loading' | 'ready' | 'error' = tracksQuery.isPending
    ? 'loading'
    : tracks.original || tracks.dub
      ? 'ready'
      : 'error'

  const markerSegments =
    state === 'ready' && totalDuration > 0
      ? segments.filter(s => typeof s.start === 'number' && typeof s.end === 'number' && s.end! > s.start!)
      : []

  return (
    <div
      className={cn(
        'p-4',
        !embedded && 'rounded-xl border border-[#e5e7eb] bg-white',
        embedded && 'p-0',
      )}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-[#111827]">{tc.title}</div>
        <div className="flex items-center gap-2">
          <span className="hidden text-[11px] text-[#9ca3af] sm:inline">{tc.hint}</span>
          {state === 'ready' && totalDuration > 0 && (
            <div className="flex items-center gap-0.5 rounded-lg border border-[#e5e7eb] p-0.5">
              <ZoomButton title={tc.zoomOut} disabled={!isZoomed} onClick={() => zoomAround(0.5, 1 / 0.7)}>
                <ZoomOut size={14} />
              </ZoomButton>
              <ZoomButton title={tc.zoomIn} disabled={visibleDur <= minDur + 1e-6} onClick={() => zoomAround(0.5, 0.7)}>
                <ZoomIn size={14} />
              </ZoomButton>
              <ZoomButton title={tc.reset} disabled={!isZoomed} onClick={() => setWindow(0, totalDuration)}>
                <Maximize2 size={14} />
              </ZoomButton>
            </div>
          )}
        </div>
      </div>

      {state === 'loading' && (
        <div className="flex h-[120px] items-center justify-center gap-2 text-xs text-[#9ca3af]">
          <Loader2 size={14} className="animate-spin" /> {tc.loading}
        </div>
      )}
      {state === 'error' && (
        <div className="flex h-[80px] items-center justify-center text-xs text-[#9ca3af]">{tc.decodeError}</div>
      )}

      {state === 'ready' && (
        <div className="relative">
          <div className="relative">
            <Ruler view={view} />
            <div className="mt-1 flex flex-col gap-2">
              <Lane
                label={tc.originalTrack}
                track={tracks.original}
                viewStart={view.start}
                viewEnd={view.end}
                color="#94a3b8"
                emptyLabel={tc.decodeError}
              />
              <Lane
                label={tc.dubTrack}
                track={tracks.dub}
                viewStart={view.start}
                viewEnd={view.end}
                color="#6366f1"
                emptyLabel={tc.decodeError}
              />
            </div>

            {/* Interaction + clickable per-segment bands over the plot (clears the label gutter). */}
            <div
              ref={overlayRef}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              className={cn(
                'absolute top-0 bottom-0 right-0 touch-none select-none',
                isZoomed ? (grabbing ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-pointer',
              )}
              style={{ left: GUTTER }}
            >
              <div className="pointer-events-none absolute inset-x-0" style={{ top: RULER_HEIGHT, bottom: 0 }}>
                {markerSegments.map(seg => {
                  const left = ((seg.start! - view.start) / visibleDur) * 100
                  const width = ((seg.end! - seg.start!) / visibleDur) * 100
                  if (left + width < 0 || left > 100) return null
                  const active = seg.segment_id === selectedId
                  const undubbed = seg.issue_tags.includes('undubbed')
                  return (
                    <div
                      key={seg.segment_id}
                      className={cn(
                        'absolute top-0 h-full border-l',
                        active
                          ? 'border-[#3b5bdb] bg-[#3b5bdb]/10'
                          : undubbed
                            ? 'border-red-200 bg-red-400/5'
                            : 'border-transparent',
                      )}
                      style={{ left: `${left}%`, width: `${Math.max(width, 0.4)}%` }}
                    />
                  )
                })}
              </div>
            </div>
          </div>

          {/* Per-segment timbre similarity heat-bar (sits below the waveforms,
              outside the wave overlay so its tooltips remain hoverable). */}
          <div className="mt-2">
            <TimbreLane
              label={tc.timbreTrack}
              segments={markerSegments}
              viewStart={view.start}
              viewEnd={view.end}
              selectedId={selectedId}
              emptyLabel={tc.decodeError}
            />
            <div className="mt-1.5 flex justify-end pl-18">
              <TimbreLegend
                labels={{
                  good: tc.timbreLegendGood,
                  review: tc.timbreLegendReview,
                  bad: tc.timbreLegendBad,
                  unknown: tc.timbreLegendUnknown,
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ZoomButton({
  title,
  disabled,
  onClick,
  children,
}: {
  title: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex h-6 w-6 items-center justify-center rounded-md text-[#6b7280] transition-colors',
        disabled ? 'cursor-not-allowed opacity-40' : 'hover:bg-[#f3f4f6] hover:text-[#374151]',
      )}
    >
      {children}
    </button>
  )
}
