/**
 * Waveform peak extraction for the dub-evaluation original-vs-dub compare.
 *
 * Decoding happens in the browser via the Web Audio API; the downsampling
 * itself is a pure function so it can be unit-tested without an AudioContext.
 */

/**
 * Reduce raw mono samples to a fixed number of amplitude buckets (one peak per
 * bucket, max |sample| over the window). Float PCM is in [-1, 1], so peaks land
 * in [0, 1]. Returns a zero-filled array when there are no samples.
 */
export function peaksFromSamples(samples: Float32Array, buckets: number): Float32Array {
  const out = new Float32Array(Math.max(0, buckets))
  if (buckets <= 0 || samples.length === 0) return out
  const step = samples.length / buckets
  for (let b = 0; b < buckets; b++) {
    const start = Math.floor(b * step)
    const end = b === buckets - 1 ? samples.length : Math.floor((b + 1) * step)
    let peak = 0
    for (let i = start; i < end; i++) {
      const v = Math.abs(samples[i])
      if (v > peak) peak = v
    }
    out[b] = peak
  }
  return out
}

/** Mix all channels of an AudioBuffer down to a single mono Float32Array. */
export function mixToMono(buffer: AudioBuffer): Float32Array {
  const { numberOfChannels, length } = buffer
  if (numberOfChannels === 1) return buffer.getChannelData(0)
  const mono = new Float32Array(length)
  for (let ch = 0; ch < numberOfChannels; ch++) {
    const data = buffer.getChannelData(ch)
    for (let i = 0; i < length; i++) mono[i] += data[i]
  }
  for (let i = 0; i < length; i++) mono[i] /= numberOfChannels
  return mono
}

/** Downsample a decoded AudioBuffer to `buckets` amplitude peaks. */
export function computePeaks(buffer: AudioBuffer, buckets: number): Float32Array {
  return peaksFromSamples(mixToMono(buffer), buckets)
}

/** A decoded track ready to render: its peaks plus the source duration. */
export interface TrackPeaks {
  peaks: Float32Array
  durationSec: number
}

/**
 * Fetch + decode an audio URL into downsampled peaks. Browser-only (uses
 * AudioContext); callers should guard with try/catch since decoding can fail
 * on unsupported codecs or missing files.
 */
export async function loadTrackPeaks(url: string, buckets: number): Promise<TrackPeaks> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`waveform fetch failed: ${response.status}`)
  const bytes = await response.arrayBuffer()
  const Ctx =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctx) throw new Error('Web Audio API unavailable')
  const ctx = new Ctx()
  try {
    const buffer = await ctx.decodeAudioData(bytes)
    return { peaks: computePeaks(buffer, buckets), durationSec: buffer.duration }
  } finally {
    void ctx.close()
  }
}
