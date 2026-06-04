import { useEffect, useMemo, useRef, useState } from 'react'
import type { DubQaReport, DubQaSegment } from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

interface MelSpectrogramCompareProps {
  report: DubQaReport
  selectedId?: string | null
  onSelectSegment?: (segment: DubQaSegment) => void
  embedded?: boolean
}

const LANE_HEIGHT = 64
const CANVAS_WIDTH = 320
const TOTAL_HEIGHT = LANE_HEIGHT * 2 + 4
const INITIAL_PAGE_SIZE = 6

// 8-stop viridis colormap (perceptually uniform, color-blind safe).
// Generated from matplotlib `viridis` reference table.
const VIRIDIS: ReadonlyArray<readonly [number, number, number]> = [
  [68, 1, 84],
  [72, 35, 116],
  [64, 67, 135],
  [52, 94, 141],
  [41, 120, 142],
  [32, 144, 140],
  [34, 167, 132],
  [68, 190, 112],
  [121, 209, 81],
  [189, 222, 38],
  [253, 231, 36],
] as const

function viridisAt(t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(1, t))
  const scaled = clamped * (VIRIDIS.length - 1)
  const idx = Math.floor(scaled)
  const frac = scaled - idx
  const a = VIRIDIS[idx]!
  const b = VIRIDIS[Math.min(VIRIDIS.length - 1, idx + 1)]!
  return [
    Math.round(a[0] + (b[0] - a[0]) * frac),
    Math.round(a[1] + (b[1] - a[1]) * frac),
    Math.round(a[2] + (b[2] - a[2]) * frac),
  ]
}

interface MelLane {
  data: number[][] // shape: [n_mels][n_frames]
  nFrames: number
  durationSec: number
}

function drawSpectrogram(
  ctx: CanvasRenderingContext2D,
  lane: MelLane | null,
  yOffset: number,
  width: number,
  height: number,
): void {
  if (!lane || lane.nFrames === 0) {
    ctx.fillStyle = '#f1f5f9'
    ctx.fillRect(0, yOffset, width, height)
    return
  }
  const nMels = lane.data.length
  const nFrames = lane.nFrames

  // Off-screen draw at native resolution then scale up via image data, so the
  // expensive per-pixel viridis lookup is only nMels * nFrames calls.
  const native = ctx.createImageData(nFrames, nMels)
  for (let band = 0; band < nMels; band += 1) {
    // Flip vertically so high mel band is at the top of the lane.
    const row = lane.data[nMels - 1 - band]!
    for (let frame = 0; frame < nFrames; frame += 1) {
      const value = row[frame] ?? 0
      const [r, g, b] = viridisAt(value / 255)
      const offset = (band * nFrames + frame) * 4
      native.data[offset] = r
      native.data[offset + 1] = g
      native.data[offset + 2] = b
      native.data[offset + 3] = 255
    }
  }

  // Stamp the native-resolution image then stretch to (width, height).
  const off = document.createElement('canvas')
  off.width = nFrames
  off.height = nMels
  const offCtx = off.getContext('2d')
  if (!offCtx) return
  offCtx.putImageData(native, 0, 0)
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'low'
  ctx.drawImage(off, 0, 0, nFrames, nMels, 0, yOffset, width, height)
}

interface SpectrogramCardProps {
  segment: DubQaSegment
  selected: boolean
  onSelect?: (segment: DubQaSegment) => void
}

function SpectrogramCard({ segment, selected, onSelect }: SpectrogramCardProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const spec = segment.mel_spectrogram

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !spec) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = CANVAS_WIDTH * dpr
    canvas.height = TOTAL_HEIGHT * dpr
    canvas.style.width = `${CANVAS_WIDTH}px`
    canvas.style.height = `${TOTAL_HEIGHT}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, CANVAS_WIDTH, TOTAL_HEIGHT)

    const orig = spec.original
    const dub = spec.dub
    drawSpectrogram(
      ctx,
      orig
        ? { data: orig.data, nFrames: orig.n_frames, durationSec: orig.duration_sec }
        : null,
      0,
      CANVAS_WIDTH,
      LANE_HEIGHT,
    )
    drawSpectrogram(
      ctx,
      dub
        ? { data: dub.data, nFrames: dub.n_frames, durationSec: dub.duration_sec }
        : null,
      LANE_HEIGHT + 4,
      CANVAS_WIDTH,
      LANE_HEIGHT,
    )
    // Thin separator between lanes.
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, LANE_HEIGHT, CANVAS_WIDTH, 4)
  }, [spec])

  if (!spec) return null

  return (
    <button
      type="button"
      onClick={() => onSelect?.(segment)}
      className={cn(
        'group flex flex-col rounded-xl border bg-slate-50/40 p-3 text-left transition',
        'hover:border-slate-300 hover:bg-white hover:shadow-sm',
        selected ? 'border-indigo-400 bg-white ring-2 ring-indigo-200' : 'border-slate-200',
      )}
    >
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="truncate font-mono text-slate-600">{segment.segment_id}</span>
        <span className="text-[11px] text-slate-400">
          {(spec.original?.duration_sec ?? spec.dub?.duration_sec ?? 0).toFixed(2)}s
        </span>
      </div>
      <div className="mt-2 overflow-hidden rounded-md bg-slate-200">
        <canvas ref={canvasRef} className="block h-auto w-full" />
      </div>
      <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
          orig
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" />
          dub
        </span>
      </div>
    </button>
  )
}

function ColorbarLegend({ dbMin, dbMax }: { dbMin: number; dbMax: number }) {
  const stops = useMemo(() => {
    const out: string[] = []
    const N = 16
    for (let i = 0; i < N; i += 1) {
      const t = i / (N - 1)
      const [r, g, b] = viridisAt(t)
      out.push(`rgb(${r}, ${g}, ${b}) ${(t * 100).toFixed(1)}%`)
    }
    return out
  }, [])
  return (
    <div className="flex items-center gap-2 text-[11px] text-slate-500">
      <span>{Math.round(dbMin)} dB</span>
      <span
        className="inline-block h-2 w-24 rounded"
        style={{ background: `linear-gradient(to right, ${stops.join(', ')})` }}
      />
      <span>{Math.round(dbMax)} dB</span>
    </div>
  )
}

export function MelSpectrogramCompare({
  report,
  selectedId,
  onSelectSegment,
  embedded = false,
}: MelSpectrogramCompareProps) {
  const { t } = useI18n()
  const tx = t.evaluation.melCompare
  const [showAll, setShowAll] = useState(false)

  const items = useMemo(
    () => report.segments.filter(seg => !!seg.mel_spectrogram),
    [report.segments],
  )

  if (items.length === 0) return null

  const visible = showAll ? items : items.slice(0, INITIAL_PAGE_SIZE)
  const hiddenCount = items.length - visible.length
  const dbMin = report.mel_meta?.db_min ?? -80
  const dbMax = report.mel_meta?.db_max ?? 0

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
        <ColorbarLegend dbMin={dbMin} dbMax={dbMax} />
      </div>

      <div className="grid gap-3 sm:grid-cols-1 md:grid-cols-2">
        {visible.map(seg => (
          <SpectrogramCard
            key={seg.segment_id}
            segment={seg}
            selected={selectedId === seg.segment_id}
            onSelect={onSelectSegment}
          />
        ))}
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
