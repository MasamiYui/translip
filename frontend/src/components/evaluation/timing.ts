import type { DubQaSegment } from '../../api/evaluation'

export type TimingKind = 'undubbed' | 'overflow' | 'underflow' | 'onTime' | 'unknown'

export interface TimingInfo {
  kind: TimingKind
  windowSec: number | null
  /** The dub's actual footprint on the final timeline (post atempo/stretch). */
  dubSec: number | null
  /** dubSec - windowSec (positive = the dub overruns its window). */
  deltaSec: number | null
  /** dubSec / windowSec. */
  footprintRatio: number | null
  /** duration_ratio = generated/source — the raw TTS pacing pressure (≈ atempo). */
  stretchRatio: number | null
  fitStrategy: string | null
  durationStatus: string | null
}

/** Counts as on-time when the dub footprint is within ±6% of the window. */
const DEADZONE = 0.06

function num(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function span(start: number | null | undefined, end: number | null | undefined): number | null {
  const a = num(start)
  const b = num(end)
  return a != null && b != null && b > a ? b - a : null
}

/** The dub's real footprint, preferring final placement, then fit, then estimate. */
function dubFootprint(seg: DubQaSegment): number | null {
  const placed = span(seg.placement_start, seg.placement_end)
  if (placed != null) return placed
  const fitted = num(seg.fitted_duration_sec)
  if (fitted != null) return fitted
  const generated = num(seg.generated_duration_sec)
  if (generated != null) return generated
  const source = num(seg.source_duration_sec)
  const ratio = num(seg.duration_ratio)
  if (source != null && ratio != null) return source * ratio
  return null
}

/** Pure: derive the timing geometry + verdict for one segment. Unit-tested. */
export function classifyTiming(seg: DubQaSegment): TimingInfo {
  const windowSec = num(seg.duration) ?? span(seg.start, seg.end)
  const dubSec = dubFootprint(seg)
  const stretchRatio = num(seg.duration_ratio)
  const base: Omit<TimingInfo, 'kind' | 'deltaSec' | 'footprintRatio'> = {
    windowSec,
    dubSec,
    stretchRatio,
    fitStrategy: seg.fit_strategy ?? null,
    durationStatus: seg.duration_status ?? null,
  }

  if (!seg.placed || dubSec == null || dubSec <= 0) {
    return { ...base, kind: 'undubbed', deltaSec: null, footprintRatio: null }
  }
  if (windowSec == null || windowSec <= 0) {
    return { ...base, kind: 'unknown', deltaSec: null, footprintRatio: null }
  }
  const footprintRatio = dubSec / windowSec
  const deltaSec = dubSec - windowSec
  let kind: TimingKind = 'onTime'
  if (footprintRatio > 1 + DEADZONE) kind = 'overflow'
  else if (footprintRatio < 1 - DEADZONE) kind = 'underflow'
  return { ...base, kind, deltaSec, footprintRatio }
}
