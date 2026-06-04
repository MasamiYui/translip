import { useMemo, useState } from 'react'
import type { DubQaSegment } from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

const AXIS_KEYS = ['timbre', 'intelligibility', 'pacing', 'issueFree', 'coverage'] as const
type AxisKey = (typeof AXIS_KEYS)[number]

interface SpeakerProfile {
  speakerId: string
  segmentCount: number
  axes: Record<AxisKey, number>
  raw: Record<AxisKey, number | null>
}

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

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(1, value))
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null
  let sum = 0
  for (const v of values) sum += v
  return sum / values.length
}

/** Pacing axis: 1.0 = perfect; map |1 − ratio| to a [0,1] score (>0.65 = 0). */
function pacingScore(ratio: number): number {
  const dev = Math.abs(1 - ratio)
  if (dev >= 0.65) return 0
  return 1 - dev / 0.65
}

/**
 * Aggregates per-speaker metrics into 5 normalized [0, 1] axes:
 * - timbre: mean speaker_similarity
 * - intelligibility: mean text_similarity
 * - pacing: 1 − |1 − duration_ratio| / 0.65 (clamped)
 * - issueFree: share of segments without issue tags
 * - coverage: share of segments with a dub audio attached
 */
export function aggregateSpeakerProfiles(segments: DubQaSegment[]): SpeakerProfile[] {
  const grouped = new Map<string, DubQaSegment[]>()
  for (const seg of segments) {
    const key = (seg.speaker_id ?? '').trim() || '—'
    const list = grouped.get(key)
    if (list) list.push(seg)
    else grouped.set(key, [seg])
  }

  const profiles: SpeakerProfile[] = []
  for (const [speakerId, segs] of grouped) {
    const timbreVals = segs
      .map(s => s.speaker_similarity)
      .filter((v): v is number => typeof v === 'number')
    const intelligibilityVals = segs
      .map(s => s.text_similarity)
      .filter((v): v is number => typeof v === 'number')
    const pacingVals = segs
      .map(s => s.duration_ratio)
      .filter((v): v is number => typeof v === 'number')
    const issueFreeRatio = segs.filter(s => s.issue_tags.length === 0).length / segs.length
    const coverageRatio = segs.filter(s => !!s.dub_audio_path).length / segs.length

    const timbreMean = mean(timbreVals)
    const intelligibilityMean = mean(intelligibilityVals)
    const pacingMean = mean(pacingVals.map(pacingScore))

    profiles.push({
      speakerId,
      segmentCount: segs.length,
      axes: {
        timbre: clamp01(timbreMean ?? 0),
        intelligibility: clamp01(intelligibilityMean ?? 0),
        pacing: clamp01(pacingMean ?? 0),
        issueFree: clamp01(issueFreeRatio),
        coverage: clamp01(coverageRatio),
      },
      raw: {
        timbre: timbreMean,
        intelligibility: intelligibilityMean,
        pacing: mean(pacingVals),
        issueFree: issueFreeRatio,
        coverage: coverageRatio,
      },
    })
  }

  profiles.sort((a, b) => {
    if (b.segmentCount !== a.segmentCount) return b.segmentCount - a.segmentCount
    return a.speakerId.localeCompare(b.speakerId)
  })
  return profiles
}

const VIEWBOX = 380
const CENTER = VIEWBOX / 2
const RADIUS = 110
const RINGS = 4

function axisPoint(axisIndex: number, axisCount: number, value: number): { x: number; y: number } {
  const angle = -Math.PI / 2 + (axisIndex * 2 * Math.PI) / axisCount
  const r = RADIUS * value
  return {
    x: CENTER + r * Math.cos(angle),
    y: CENTER + r * Math.sin(angle),
  }
}

function formatRaw(axis: AxisKey, raw: number | null): string {
  if (raw === null) return '—'
  if (axis === 'pacing') return raw.toFixed(2)
  return `${Math.round(raw * 100)}%`
}

export function SpeakerRadar({ segments, embedded = false }: { segments: DubQaSegment[]; embedded?: boolean }) {
  const { t } = useI18n()
  const tr = t.evaluation.speakerRadar
  const profiles = useMemo(() => aggregateSpeakerProfiles(segments), [segments])
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [hovered, setHovered] = useState<string | null>(null)

  if (profiles.length === 0) {
    return (
      <div
        className={cn(
          'p-4 text-center text-xs text-[#9ca3af]',
          !embedded && 'rounded-xl border border-[#e5e7eb] bg-white',
        )}
      >
        {tr.empty}
      </div>
    )
  }

  const axisCount = AXIS_KEYS.length
  const allHidden = profiles.every(p => hidden.has(p.speakerId))

  const toggle = (id: string) => {
    setHidden(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  const toggleAll = () => {
    setHidden(allHidden ? new Set() : new Set(profiles.map(p => p.speakerId)))
  }

  const rings = Array.from({ length: RINGS }, (_, i) => (i + 1) / RINGS)
  const axisAnchors = AXIS_KEYS.map((_, i) => axisPoint(i, axisCount, 1))
  const labelAnchors = AXIS_KEYS.map((_, i) => axisPoint(i, axisCount, 1.18))

  return (
    <div
      className={cn(
        'p-4',
        !embedded && 'rounded-xl border border-[#e5e7eb] bg-white',
        embedded && 'p-0',
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-[#111827]">{tr.title}</div>
          <div className="text-[11px] text-[#9ca3af]">{tr.subtitle}</div>
        </div>
        <button
          type="button"
          onClick={toggleAll}
          className="rounded-md border border-[#e5e7eb] px-2 py-1 text-[11px] font-medium text-[#6b7280] hover:bg-[#f9fafb]"
        >
          {allHidden ? tr.showAll : tr.hideAll}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[auto_1fr] md:items-center">
        <div className="flex justify-center">
          <svg
            viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
            className="h-[300px] w-[300px] max-w-full"
            role="img"
            aria-label={tr.title}
          >
            {/* concentric rings */}
            {rings.map(r => (
              <polygon
                key={r}
                points={AXIS_KEYS.map((_, i) => {
                  const p = axisPoint(i, axisCount, r)
                  return `${p.x},${p.y}`
                }).join(' ')}
                fill="none"
                stroke="#e5e7eb"
                strokeWidth={1}
              />
            ))}
            {/* axes */}
            {axisAnchors.map((p, i) => (
              <line
                key={i}
                x1={CENTER}
                y1={CENTER}
                x2={p.x}
                y2={p.y}
                stroke="#e5e7eb"
                strokeWidth={1}
              />
            ))}
            {/* axis labels */}
            {AXIS_KEYS.map((axis, i) => {
              const p = labelAnchors[i]
              const anchor =
                Math.abs(p.x - CENTER) < 1 ? 'middle' : p.x > CENTER ? 'start' : 'end'
              return (
                <text
                  key={axis}
                  x={p.x}
                  y={p.y}
                  fontSize={11}
                  fill="#6b7280"
                  textAnchor={anchor}
                  dominantBaseline="middle"
                >
                  <title>{tr.axisHints[axis]}</title>
                  {tr.axes[axis]}
                </text>
              )
            })}

            {/* polygons (sorted so the hovered one renders on top) */}
            {[...profiles]
              .sort((a, b) => {
                const ah = hovered === a.speakerId ? 1 : 0
                const bh = hovered === b.speakerId ? 1 : 0
                return ah - bh
              })
              .map((profile, idx) => {
                if (hidden.has(profile.speakerId)) return null
                const color = PALETTE[profiles.indexOf(profile) % PALETTE.length]
                const isHovered = hovered === profile.speakerId
                const points = AXIS_KEYS.map((axis, i) => {
                  const p = axisPoint(i, axisCount, profile.axes[axis])
                  return `${p.x},${p.y}`
                }).join(' ')
                return (
                  <g
                    key={profile.speakerId}
                    onMouseEnter={() => setHovered(profile.speakerId)}
                    onMouseLeave={() => setHovered(null)}
                  >
                    <polygon
                      points={points}
                      fill={color}
                      fillOpacity={isHovered ? 0.32 : 0.16}
                      stroke={color}
                      strokeWidth={isHovered ? 2 : 1.5}
                    />
                    {AXIS_KEYS.map((axis, i) => {
                      const p = axisPoint(i, axisCount, profile.axes[axis])
                      return (
                        <circle
                          key={`${profile.speakerId}-${axis}-${idx}`}
                          cx={p.x}
                          cy={p.y}
                          r={isHovered ? 3.2 : 2.4}
                          fill={color}
                        />
                      )
                    })}
                  </g>
                )
              })}
          </svg>
        </div>

        <div className="flex flex-col gap-2">
          {profiles.map(profile => {
            const color = PALETTE[profiles.indexOf(profile) % PALETTE.length]
            const isHidden = hidden.has(profile.speakerId)
            return (
              <div
                key={profile.speakerId}
                onMouseEnter={() => setHovered(profile.speakerId)}
                onMouseLeave={() => setHovered(null)}
                className={cn(
                  'flex items-center gap-3 rounded-lg border px-3 py-2 transition-colors',
                  isHidden
                    ? 'border-[#f3f4f6] bg-[#f9fafb] opacity-60'
                    : 'border-[#e5e7eb] bg-white hover:border-[#d1d5db]',
                )}
              >
                <button
                  type="button"
                  onClick={() => toggle(profile.speakerId)}
                  className="flex items-center gap-2 text-left"
                  aria-pressed={!isHidden}
                  aria-label={`toggle ${profile.speakerId}`}
                >
                  <span
                    className={cn(
                      'h-3 w-3 shrink-0 rounded-full border',
                      isHidden ? 'border-[#d1d5db] bg-white' : 'border-transparent',
                    )}
                    style={isHidden ? undefined : { background: color }}
                  />
                  <span className="text-xs font-semibold text-[#111827]">{profile.speakerId}</span>
                  <span className="text-[10px] text-[#9ca3af]">
                    {profile.segmentCount} {tr.segmentSuffix}
                  </span>
                </button>
                <div className="ml-auto grid grid-cols-5 gap-1.5">
                  {AXIS_KEYS.map(axis => (
                    <div
                      key={axis}
                      title={`${tr.axes[axis]} · ${tr.axisHints[axis]}`}
                      className="flex flex-col items-center"
                    >
                      <span className="text-[10px] font-medium text-[#374151]">
                        {formatRaw(axis, profile.raw[axis])}
                      </span>
                      <span className="mt-0.5 h-1 w-6 rounded-full bg-[#f3f4f6]">
                        <span
                          className="block h-full rounded-full"
                          style={{
                            width: `${Math.round(profile.axes[axis] * 100)}%`,
                            background: color,
                          }}
                        />
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
