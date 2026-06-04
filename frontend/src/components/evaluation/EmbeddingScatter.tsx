import { useMemo, useState } from 'react'
import type { DubQaReport, DubQaSegment } from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

const PALETTE = [
  '#3b5bdb',
  '#0ea5e9',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
]

interface ProjectedPoint {
  kind: 'segment' | 'reference'
  speakerId: string
  segment?: DubQaSegment
  x: number
  y: number
  raw: number[]
  /** Cosine similarity vs the speaker's reference (only for segments). */
  cosineToRef?: number
}

interface ProjectionResult {
  points: ProjectedPoint[]
  speakers: string[]
  varianceRatios: [number, number]
  totalVariance: number
}

function dot(a: number[], b: number[]): number {
  let s = 0
  for (let i = 0; i < a.length; i++) s += a[i] * b[i]
  return s
}

function norm(a: number[]): number {
  return Math.sqrt(dot(a, a)) || 1
}

function cosineSim(a: number[], b: number[]): number {
  const denom = norm(a) * norm(b)
  if (denom === 0) return 0
  return dot(a, b) / denom
}

/**
 * Compute the top principal component of a centered matrix via power
 * iteration. Returns the (already L2-normalized) eigenvector.
 */
function powerIteration(centered: number[][], iterations = 40): number[] {
  const dim = centered[0]?.length ?? 0
  if (dim === 0) return []
  // Deterministic seed so the projection is stable across renders.
  let v = Array.from({ length: dim }, (_, i) => Math.sin(i + 1))
  let v_norm = norm(v)
  v = v.map(x => x / v_norm)

  for (let iter = 0; iter < iterations; iter++) {
    // Av = X^T X v  computed without materializing X^T X (n×d×n approach).
    const xv: number[] = centered.map(row => dot(row, v))
    const next = new Array<number>(dim).fill(0)
    for (let i = 0; i < centered.length; i++) {
      const row = centered[i]
      const c = xv[i]
      for (let j = 0; j < dim; j++) next[j] += row[j] * c
    }
    v_norm = norm(next)
    if (v_norm === 0) return v
    v = next.map(x => x / v_norm)
  }
  return v
}

/**
 * Project each row of X onto the top-2 principal components.
 * Returns the 2D coordinates plus the explained-variance ratio for each axis.
 *
 * For our dub-qa use this is preferable to t-SNE / UMAP because:
 * - it has zero hyperparameters (so the picture is reproducible across reruns)
 * - on ECAPA embeddings the first two PCs already separate speakers well
 * - it's tiny — runs in a few ms for typical (~hundreds of segments) loads.
 */
function pcaProject(matrix: number[][]): {
  coords: Array<[number, number]>
  varianceRatios: [number, number]
  totalVariance: number
} {
  const n = matrix.length
  const dim = matrix[0]?.length ?? 0
  if (n === 0 || dim === 0) {
    return { coords: [], varianceRatios: [0, 0], totalVariance: 0 }
  }
  // 1) Center
  const mean = new Array<number>(dim).fill(0)
  for (const row of matrix) for (let j = 0; j < dim; j++) mean[j] += row[j]
  for (let j = 0; j < dim; j++) mean[j] /= n
  const centered = matrix.map(row => row.map((v, j) => v - mean[j]))

  // Total variance (sum of squared norms across all rows).
  let totalVar = 0
  for (const row of centered) totalVar += dot(row, row)

  // 2) First PC.
  const v1 = powerIteration(centered)
  const proj1 = centered.map(row => dot(row, v1))
  const var1 = proj1.reduce((acc, x) => acc + x * x, 0)

  // 3) Deflate: subtract the projection onto v1 from every row, then power-iterate again.
  const deflated = centered.map((row, i) => row.map((value, j) => value - proj1[i] * v1[j]))
  const v2 = powerIteration(deflated)
  const proj2 = centered.map(row => dot(row, v2))
  const var2 = proj2.reduce((acc, x) => acc + x * x, 0)

  const coords: Array<[number, number]> = proj1.map((x, i) => [x, proj2[i]])
  const ratios: [number, number] = [
    totalVar > 0 ? var1 / totalVar : 0,
    totalVar > 0 ? var2 / totalVar : 0,
  ]
  return { coords, varianceRatios: ratios, totalVariance: totalVar }
}

function buildProjection(report: DubQaReport): ProjectionResult | null {
  const segs = (report.segments ?? []).filter(
    s => Array.isArray(s.speaker_embedding) && (s.speaker_embedding?.length ?? 0) > 0,
  )
  const refs = report.reference_embeddings ?? {}
  const refKeys = Object.keys(refs).filter(k => Array.isArray(refs[k]) && refs[k].length > 0)

  if (segs.length === 0 && refKeys.length === 0) return null

  // Build the full matrix: [...segments, ...references]. The ordering matters
  // because we re-attach metadata in the same order after the PCA call.
  const matrix: number[][] = []
  for (const seg of segs) matrix.push(seg.speaker_embedding as number[])
  for (const k of refKeys) matrix.push(refs[k])

  const { coords, varianceRatios, totalVariance } = pcaProject(matrix)
  if (coords.length === 0) return null

  const speakers = new Set<string>()
  const points: ProjectedPoint[] = []
  segs.forEach((seg, i) => {
    const speakerId = seg.speaker_id ?? '—'
    speakers.add(speakerId)
    const ref = refs[speakerId]
    points.push({
      kind: 'segment',
      speakerId,
      segment: seg,
      x: coords[i][0],
      y: coords[i][1],
      raw: seg.speaker_embedding as number[],
      cosineToRef: ref ? cosineSim(seg.speaker_embedding as number[], ref) : undefined,
    })
  })
  refKeys.forEach((k, i) => {
    speakers.add(k)
    const idx = segs.length + i
    points.push({
      kind: 'reference',
      speakerId: k,
      x: coords[idx][0],
      y: coords[idx][1],
      raw: refs[k],
    })
  })

  return {
    points,
    speakers: Array.from(speakers).sort((a, b) => a.localeCompare(b)),
    varianceRatios,
    totalVariance,
  }
}

const VIEWBOX = 360
const PADDING = 18
const PLOT_SIZE = VIEWBOX - PADDING * 2

interface Props {
  report: DubQaReport
  selectedId?: string | null
  onSelectSegment?: (segment: DubQaSegment) => void
}

export function EmbeddingScatter({ report, selectedId, onSelectSegment }: Props) {
  const { t } = useI18n()
  const tr = t.evaluation.embeddingScatter
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [hiddenSpeakers, setHiddenSpeakers] = useState<Set<string>>(new Set())

  const projection = useMemo(() => buildProjection(report), [report])

  const colorFor = useMemo(() => {
    const map = new Map<string, string>()
    if (!projection) return map
    projection.speakers.forEach((sp, i) => map.set(sp, PALETTE[i % PALETTE.length]))
    return map
  }, [projection])

  // Compute viewport bounds with a 5% margin so points don't kiss the border.
  const transform = useMemo(() => {
    if (!projection || projection.points.length === 0) return null
    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity
    for (const p of projection.points) {
      if (p.x < minX) minX = p.x
      if (p.x > maxX) maxX = p.x
      if (p.y < minY) minY = p.y
      if (p.y > maxY) maxY = p.y
    }
    const dx = Math.max(maxX - minX, 1e-6)
    const dy = Math.max(maxY - minY, 1e-6)
    const margin = 0.06
    return {
      xToPx: (x: number) => PADDING + ((x - minX) / dx) * PLOT_SIZE * (1 - margin * 2) + PLOT_SIZE * margin,
      yToPx: (y: number) =>
        PADDING + ((maxY - y) / dy) * PLOT_SIZE * (1 - margin * 2) + PLOT_SIZE * margin,
    }
  }, [projection])

  if (!projection || !transform) {
    return (
      <div className="rounded-xl border border-[#e5e7eb] bg-white p-4 text-center text-xs text-[#9ca3af]">
        {tr.empty}
      </div>
    )
  }

  const segmentCount = projection.points.filter(p => p.kind === 'segment').length
  const refCount = projection.points.filter(p => p.kind === 'reference').length

  const toggleSpeaker = (sp: string) => {
    setHiddenSpeakers(prev => {
      const next = new Set(prev)
      if (next.has(sp)) next.delete(sp)
      else next.add(sp)
      return next
    })
  }

  // We render references on top of segments, and the hovered/selected one on
  // top of the rest, so they remain visible even in a dense cluster.
  const segmentPoints = projection.points.filter(p => p.kind === 'segment')
  const refPoints = projection.points.filter(p => p.kind === 'reference')

  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-[#111827]">{tr.title}</div>
          <div className="text-[11px] text-[#9ca3af]">{tr.subtitle}</div>
        </div>
        <div className="text-right text-[10px] text-[#6b7280]">
          <div>
            {tr.info}: <span className="text-[#374151]">{segmentCount}</span> {tr.infoSegments} ·{' '}
            <span className="text-[#374151]">{projection.speakers.length}</span> {tr.infoSpeakers}
          </div>
          <div className="mt-0.5">
            {tr.infoVariance}:{' '}
            <span className="text-[#374151]">
              {(projection.varianceRatios[0] * 100).toFixed(1)}% / {(projection.varianceRatios[1] * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[auto_1fr] md:items-start">
        <div className="flex justify-center">
          <svg
            viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
            className="h-[340px] w-[340px] max-w-full"
            role="img"
            aria-label={tr.title}
          >
            {/* outer plot frame */}
            <rect
              x={PADDING}
              y={PADDING}
              width={PLOT_SIZE}
              height={PLOT_SIZE}
              fill="#fafafa"
              stroke="#e5e7eb"
              strokeWidth={1}
              rx={6}
            />
            {/* axes labels */}
            <text x={VIEWBOX - PADDING} y={VIEWBOX - PADDING + 12} textAnchor="end" fontSize={9} fill="#9ca3af">
              PC1 ({(projection.varianceRatios[0] * 100).toFixed(1)}%)
            </text>
            <text
              x={PADDING - 6}
              y={PADDING + 4}
              textAnchor="end"
              fontSize={9}
              fill="#9ca3af"
              transform={`rotate(-90 ${PADDING - 6} ${PADDING + 4})`}
            >
              PC2 ({(projection.varianceRatios[1] * 100).toFixed(1)}%)
            </text>

            {/* segment dots */}
            {segmentPoints.map(p => {
              if (hiddenSpeakers.has(p.speakerId)) return null
              const isSelected = p.segment?.segment_id === selectedId
              const isHovered = p.segment?.segment_id === hoveredId
              const color = colorFor.get(p.speakerId) ?? '#6b7280'
              return (
                <circle
                  key={`seg-${p.segment?.segment_id}`}
                  cx={transform.xToPx(p.x)}
                  cy={transform.yToPx(p.y)}
                  r={isSelected || isHovered ? 5 : 3}
                  fill={color}
                  fillOpacity={isHovered ? 0.95 : 0.65}
                  stroke={isSelected ? '#111827' : 'white'}
                  strokeWidth={isSelected ? 2 : 1}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredId(p.segment?.segment_id ?? null)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => p.segment && onSelectSegment?.(p.segment)}
                >
                  <title>
                    {`${p.segment?.segment_id ?? ''} · ${tr.hover.speaker}: ${p.speakerId}` +
                      (typeof p.cosineToRef === 'number'
                        ? ` · ${tr.hover.sim}: ${p.cosineToRef.toFixed(2)}`
                        : '')}
                  </title>
                </circle>
              )
            })}

            {/* reference markers (diamond, drawn on top) */}
            {refPoints.map(p => {
              if (hiddenSpeakers.has(p.speakerId)) return null
              const cx = transform.xToPx(p.x)
              const cy = transform.yToPx(p.y)
              const color = colorFor.get(p.speakerId) ?? '#6b7280'
              const r = 7
              return (
                <g key={`ref-${p.speakerId}`}>
                  <polygon
                    points={`${cx},${cy - r} ${cx + r},${cy} ${cx},${cy + r} ${cx - r},${cy}`}
                    fill="white"
                    stroke={color}
                    strokeWidth={2}
                  />
                  <polygon
                    points={`${cx},${cy - (r - 3)} ${cx + (r - 3)},${cy} ${cx},${cy + (r - 3)} ${cx - (r - 3)},${cy}`}
                    fill={color}
                  />
                  <title>{`${tr.legend.reference}: ${p.speakerId}`}</title>
                </g>
              )
            })}
          </svg>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[#6b7280]">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-[#6b7280]" />
              {tr.legend.segment}
            </span>
            <span className="inline-flex items-center gap-1">
              <svg width={10} height={10} viewBox="0 0 10 10">
                <polygon
                  points="5,1 9,5 5,9 1,5"
                  fill="white"
                  stroke="#6b7280"
                  strokeWidth={1.5}
                />
              </svg>
              {tr.legend.reference}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {projection.speakers.map(sp => {
              const color = colorFor.get(sp) ?? '#6b7280'
              const isHidden = hiddenSpeakers.has(sp)
              const segmentsInSpeaker = segmentPoints.filter(p => p.speakerId === sp).length
              return (
                <button
                  key={sp}
                  type="button"
                  onClick={() => toggleSpeaker(sp)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors',
                    isHidden
                      ? 'border-[#e5e7eb] bg-[#f9fafb] text-[#9ca3af]'
                      : 'border-[#e5e7eb] bg-white text-[#374151] hover:border-[#d1d5db]',
                  )}
                >
                  <span
                    className="inline-block h-2 w-2 rounded-full border"
                    style={
                      isHidden
                        ? { borderColor: '#d1d5db', background: 'white' }
                        : { borderColor: 'transparent', background: color }
                    }
                  />
                  <span>{sp}</span>
                  <span className="text-[#9ca3af]">{segmentsInSpeaker}</span>
                </button>
              )
            })}
          </div>
          {refCount === 0 ? null : (
            <div className="text-[10px] text-[#9ca3af]">
              ◇ × {refCount} reference{refCount === 1 ? '' : 's'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
