import { describe, expect, it } from 'vitest'
import type { DubQaSegment } from '../../../api/evaluation'
import { classifyTiming } from '../timing'

function seg(overrides: Partial<DubQaSegment>): DubQaSegment {
  return {
    segment_id: 's1',
    source_text: '原文',
    target_text: 'target',
    backread_text: '',
    placed: true,
    qa_flags: [],
    dropout_token_count: 0,
    dropout_total_tokens: 0,
    dropout_ratio: 0,
    issue_tags: [],
    severity: 'ok',
    ...overrides,
  }
}

describe('classifyTiming', () => {
  it('flags an unplaced segment as undubbed', () => {
    const info = classifyTiming(seg({ placed: false, start: 1, end: 4 }))
    expect(info.kind).toBe('undubbed')
    expect(info.windowSec).toBeCloseTo(3)
    expect(info.dubSec).toBeNull()
  })

  it('detects overflow from the placement footprint', () => {
    const info = classifyTiming(
      seg({ start: 0, end: 3, duration: 3, placement_start: 0, placement_end: 4.1, duration_status: 'failed' }),
    )
    expect(info.kind).toBe('overflow')
    expect(info.dubSec).toBeCloseTo(4.1)
    expect(info.deltaSec).toBeCloseTo(1.1)
  })

  it('detects underflow', () => {
    const info = classifyTiming(seg({ duration: 3, placement_start: 0, placement_end: 2 }))
    expect(info.kind).toBe('underflow')
    expect(info.deltaSec).toBeCloseTo(-1)
  })

  it('treats a near-equal footprint as on-time (within deadzone)', () => {
    const info = classifyTiming(seg({ duration: 3, fitted_duration_sec: 3.05 }))
    expect(info.kind).toBe('onTime')
  })

  it('falls back to source_duration * duration_ratio when no placement/fit data', () => {
    const info = classifyTiming(seg({ duration: 2, source_duration_sec: 2, duration_ratio: 1.5 }))
    expect(info.dubSec).toBeCloseTo(3)
    expect(info.kind).toBe('overflow')
    expect(info.stretchRatio).toBeCloseTo(1.5)
  })

  it('reports unknown when the window is missing', () => {
    const info = classifyTiming(seg({ start: null, end: null, fitted_duration_sec: 2 }))
    expect(info.kind).toBe('unknown')
  })
})
