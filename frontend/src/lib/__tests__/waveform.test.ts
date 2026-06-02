import { describe, expect, it } from 'vitest'
import { peaksFromSamples } from '../waveform'

describe('peaksFromSamples', () => {
  it('returns a zero-filled array when there are no samples', () => {
    const peaks = peaksFromSamples(new Float32Array([]), 4)
    expect(Array.from(peaks)).toEqual([0, 0, 0, 0])
  })

  it('returns an empty array for non-positive bucket counts', () => {
    expect(peaksFromSamples(new Float32Array([1, 2, 3]), 0).length).toBe(0)
  })

  it('takes the max absolute amplitude per bucket', () => {
    // 8 samples into 2 buckets -> [max(|0,0.2,-0.5,0.1|), max(|0.9,-0.3,0.4,0|)]
    const samples = new Float32Array([0, 0.2, -0.5, 0.1, 0.9, -0.3, 0.4, 0])
    const peaks = peaksFromSamples(samples, 2)
    expect(peaks[0]).toBeCloseTo(0.5)
    expect(peaks[1]).toBeCloseTo(0.9)
  })

  it('covers all samples even when length is not divisible by buckets', () => {
    const samples = new Float32Array([0.1, 0.2, 0.3, 0.9, 0.4])
    const peaks = peaksFromSamples(samples, 2)
    // last bucket must include the trailing sample
    expect(peaks[1]).toBeCloseTo(0.9)
  })
})
