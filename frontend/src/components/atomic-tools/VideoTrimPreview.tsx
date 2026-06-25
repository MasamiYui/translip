import { useEffect, useRef, useState } from 'react'
import { ChevronFirst, ChevronLast, Maximize2, Pause, Play, RotateCcw, Scissors, Volume2, VolumeX } from 'lucide-react'

export interface VideoTrimPreviewCopy {
  title: string
  uploadFirst: string
  unsupported: string
  hint: string
  setIn: string
  setOut: string
  jumpToIn: string
  jumpToOut: string
  playSelection: string
  reset: string
  startLabel: string
  endLabel: string
  durationLabel: string
  play: string
  pause: string
  mute: string
  unmute: string
  playbackRate: string
  fullscreen: string
}

export interface VideoTrimPreviewProps {
  videoUrl: string | null
  /** Current in-point (seconds). */
  startSec: number
  /** Current out-point (seconds), or null = "until the end of the file". */
  endSec: number | null
  /** Report a new [start, end] selection back to the form (single source of truth). */
  onChange: (startSec: number, endSec: number | null) => void
  copy: VideoTrimPreviewCopy
}

const PLAYBACK_RATE_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const
// Keep the in-point strictly before the out-point so the window is never empty.
const MIN_GAP = 0.1

const round3 = (value: number) => Math.round(value * 1000) / 1000
const clamp = (value: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, value))

function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00.0'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

export function VideoTrimPreview({ videoUrl, startSec, endSec, onChange, copy }: VideoTrimPreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const trackRef = useRef<HTMLDivElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  // Out-point at which "play selection" should auto-pause (null = not previewing).
  const stopAtRef = useRef<number | null>(null)

  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [muted, setMuted] = useState(false)
  const [playbackRate, setPlaybackRate] = useState(1)
  const [videoError, setVideoError] = useState(false)
  const [loadedUrl, setLoadedUrl] = useState(videoUrl)
  const [dragging, setDragging] = useState<null | 'in' | 'out'>(null)
  // Local cache for the in/out values *while* the user drags a handle. We avoid
  // calling onChange on every pointermove (which would re-render the whole
  // ToolPage at 60–120Hz) and instead commit once on pointerup.
  const [dragStart, setDragStart] = useState<number | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)

  // Reset transient state when the source changes (render-time "adjust on prop
  // change" — avoids an extra effect pass).
  if (videoUrl !== loadedUrl) {
    setLoadedUrl(videoUrl)
    setVideoError(false)
    setDuration(0)
    setCurrentTime(0)
  }

  const hasTimeline = duration > 0 && !videoError
  // While the user drags, prefer the local (uncommitted) values so the timeline
  // tracks the pointer without round-tripping through the parent on every move.
  const propStart = clamp(startSec || 0, 0, duration > 0 ? duration : startSec || 0)
  const propEffEnd = endSec != null && Number.isFinite(endSec) ? endSec : duration
  const safeStart = dragStart != null ? dragStart : propStart
  const effEnd = dragEnd != null ? dragEnd : propEffEnd
  const selDuration = Math.max(0, effEnd - safeStart)

  // Keep the toolbar/playhead in sync with the underlying <video>.
  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    const syncPlay = () => setIsPlaying(true)
    const syncPause = () => setIsPlaying(false)
    const syncDuration = () => setDuration(Number.isFinite(el.duration) ? el.duration : 0)
    const syncVolume = () => setMuted(el.muted)
    const syncRate = () => setPlaybackRate(el.playbackRate)
    syncDuration()
    syncVolume()
    syncRate()
    el.addEventListener('play', syncPlay)
    el.addEventListener('pause', syncPause)
    el.addEventListener('loadedmetadata', syncDuration)
    el.addEventListener('durationchange', syncDuration)
    el.addEventListener('volumechange', syncVolume)
    el.addEventListener('ratechange', syncRate)
    return () => {
      el.removeEventListener('play', syncPlay)
      el.removeEventListener('pause', syncPause)
      el.removeEventListener('loadedmetadata', syncDuration)
      el.removeEventListener('durationchange', syncDuration)
      el.removeEventListener('volumechange', syncVolume)
      el.removeEventListener('ratechange', syncRate)
    }
  }, [videoUrl])

  // Drive the playhead off currentTime; rAF while playing keeps it smooth, and
  // it enforces the "play selection" auto-pause at the out-point.
  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    let raf = 0
    const tick = () => {
      setCurrentTime(el.currentTime)
      const stopAt = stopAtRef.current
      if (stopAt != null && el.currentTime >= stopAt) {
        el.pause()
        stopAtRef.current = null
      }
      raf = window.requestAnimationFrame(tick)
    }
    const start = () => {
      if (!raf) raf = window.requestAnimationFrame(tick)
    }
    const stop = () => {
      if (raf) {
        window.cancelAnimationFrame(raf)
        raf = 0
      }
      setCurrentTime(el.currentTime)
    }
    el.addEventListener('play', start)
    el.addEventListener('pause', stop)
    el.addEventListener('seeked', stop)
    return () => {
      el.removeEventListener('play', start)
      el.removeEventListener('pause', stop)
      el.removeEventListener('seeked', stop)
      if (raf) window.cancelAnimationFrame(raf)
    }
  }, [videoUrl])

  const timeFromClientX = (clientX: number): number => {
    const track = trackRef.current
    if (!track || duration <= 0) return 0
    const rect = track.getBoundingClientRect()
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1)
    return ratio * duration
  }

  const beginDrag = (which: 'in' | 'out') => (event: React.PointerEvent) => {
    event.preventDefault()
    event.stopPropagation()
    try {
      ;(event.target as HTMLElement).setPointerCapture(event.pointerId)
    } catch {
      // Pointer capture is best-effort; dragging still works without it.
    }
    // Seed the drag cache from the current committed values so the first
    // pointermove already has a sane baseline (avoids a one-frame jump if the
    // user releases without moving).
    setDragStart(propStart)
    setDragEnd(propEffEnd)
    setDragging(which)
  }

  const onHandleMove = (event: React.PointerEvent) => {
    if (!dragging || duration <= 0) return
    const t = timeFromClientX(event.clientX)
    if (dragging === 'in') {
      setDragStart(round3(clamp(t, 0, effEnd - MIN_GAP)))
    } else {
      setDragEnd(round3(clamp(t, safeStart + MIN_GAP, duration)))
    }
  }

  const endDrag = (event: React.PointerEvent) => {
    if (!dragging) return
    try {
      ;(event.target as HTMLElement).releasePointerCapture(event.pointerId)
    } catch {
      /* ignore */
    }
    // Commit the cached drag value back to the parent exactly once, then
    // release the local cache so the timeline goes back to mirroring props.
    const committedStart = dragStart != null ? dragStart : propStart
    const committedEnd = dragEnd != null ? dragEnd : propEffEnd
    // Preserve the "until end of file" intent: if the user didn't move the out
    // handle and the original endSec was null, keep it null.
    const nextEnd = dragging === 'in' && endSec == null ? null : committedEnd
    setDragging(null)
    setDragStart(null)
    setDragEnd(null)
    onChange(committedStart, nextEnd)
  }

  const seekToTrack = (event: React.PointerEvent) => {
    if (dragging) return
    const el = videoRef.current
    if (!el) return
    el.currentTime = timeFromClientX(event.clientX)
  }

  const togglePlay = () => {
    const el = videoRef.current
    if (!el) return
    stopAtRef.current = null
    if (el.paused || el.ended) void el.play()
    else el.pause()
  }

  const toggleMute = () => {
    const el = videoRef.current
    if (el) el.muted = !el.muted
  }

  const handleRate = (value: string) => {
    const rate = Number(value)
    const el = videoRef.current
    if (el && Number.isFinite(rate) && rate > 0) el.playbackRate = rate
  }

  const handleFullscreen = () => {
    const wrap = wrapRef.current
    if (!wrap) return
    if (document.fullscreenElement) void document.exitFullscreen()
    else if (wrap.requestFullscreen) void wrap.requestFullscreen()
  }

  const setIn = () => {
    const el = videoRef.current
    if (!el) return
    onChange(round3(clamp(el.currentTime, 0, effEnd - MIN_GAP)), endSec)
  }

  const setOut = () => {
    const el = videoRef.current
    if (!el) return
    onChange(safeStart, round3(clamp(el.currentTime, safeStart + MIN_GAP, duration)))
  }

  const jumpToIn = () => {
    const el = videoRef.current
    if (el) el.currentTime = safeStart
  }

  const jumpToOut = () => {
    const el = videoRef.current
    if (el) el.currentTime = effEnd
  }

  const playSelection = () => {
    const el = videoRef.current
    if (!el) return
    el.currentTime = safeStart
    stopAtRef.current = effEnd
    void el.play()
  }

  const resetSelection = () => onChange(0, null)

  const pct = (value: number) => (duration > 0 ? clamp((value / duration) * 100, 0, 100) : 0)

  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-[#6b7280]">{copy.title}</div>
        {hasTimeline && (
          <div className="font-mono text-[11px] tabular-nums text-[#9ca3af]">
            {formatClock(currentTime)} / {formatClock(duration)}
          </div>
        )}
      </div>

      <div
        ref={wrapRef}
        className="relative w-full overflow-hidden rounded-lg bg-black"
        style={{ aspectRatio: '16 / 9' }}
      >
        {videoUrl && !videoError ? (
          <video
            ref={videoRef}
            src={videoUrl}
            playsInline
            onClick={togglePlay}
            onError={() => setVideoError(true)}
            preload="metadata"
            className="h-full w-full cursor-pointer object-contain"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center px-4 text-center text-xs text-white/70">
            {videoUrl && videoError ? copy.unsupported : copy.uploadFirst}
          </div>
        )}
      </div>

      {/* Transport + trim controls only make sense once we know the duration. */}
      {hasTimeline && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700">
            <button
              type="button"
              onClick={togglePlay}
              aria-label={isPlaying ? copy.pause : copy.play}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-slate-900 text-white hover:bg-slate-700"
            >
              {isPlaying ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <button
              type="button"
              onClick={jumpToIn}
              aria-label={copy.jumpToIn}
              title={copy.jumpToIn}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
            >
              <ChevronFirst size={14} />
            </button>
            <button
              type="button"
              onClick={jumpToOut}
              aria-label={copy.jumpToOut}
              title={copy.jumpToOut}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
            >
              <ChevronLast size={14} />
            </button>
            <div className="mx-1 h-5 w-px bg-slate-200" />
            <button
              type="button"
              onClick={playSelection}
              className="inline-flex h-7 items-center gap-1.5 rounded-md border border-blue-200 bg-blue-50 px-2.5 font-medium text-blue-700 hover:bg-blue-100"
            >
              <Play size={12} />
              {copy.playSelection}
            </button>
            <div className="flex-1" />
            <button
              type="button"
              onClick={toggleMute}
              aria-label={muted ? copy.unmute : copy.mute}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
            >
              {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
            <select
              value={String(playbackRate)}
              onChange={event => handleRate(event.target.value)}
              aria-label={copy.playbackRate}
              className="h-7 rounded-md border border-slate-200 bg-white px-1.5 text-[11px] text-slate-700"
            >
              {PLAYBACK_RATE_OPTIONS.map(rate => (
                <option key={rate} value={rate}>
                  {rate}x
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleFullscreen}
              aria-label={copy.fullscreen}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
            >
              <Maximize2 size={14} />
            </button>
          </div>

          {/* Timeline: doubles as the seek bar (click to seek) and the trim
              selector (drag the in/out handles). */}
          <div className="mt-3 px-2">
            <div
              ref={trackRef}
              onPointerDown={seekToTrack}
              className="relative h-10 cursor-pointer rounded-md bg-slate-100"
            >
              {/* Selected window. */}
              <div
                className="pointer-events-none absolute inset-y-0 border-x-2 border-blue-500 bg-blue-500/20"
                style={{ left: `${pct(safeStart)}%`, width: `${Math.max(0, pct(effEnd) - pct(safeStart))}%` }}
              />
              {/* Playhead. */}
              <div
                className="pointer-events-none absolute inset-y-0 w-0.5 -translate-x-1/2 bg-rose-500"
                style={{ left: `${pct(currentTime)}%` }}
              />
              {/* In handle. */}
              <div
                role="slider"
                aria-label={copy.setIn}
                aria-valuenow={Math.round(safeStart)}
                tabIndex={0}
                onPointerDown={beginDrag('in')}
                onPointerMove={onHandleMove}
                onPointerUp={endDrag}
                className="absolute inset-y-0 z-10 w-3 -translate-x-1/2 cursor-ew-resize rounded-l bg-blue-600 shadow ring-1 ring-white/50"
                style={{ left: `${pct(safeStart)}%`, touchAction: 'none' }}
              />
              {/* Out handle. */}
              <div
                role="slider"
                aria-label={copy.setOut}
                aria-valuenow={Math.round(effEnd)}
                tabIndex={0}
                onPointerDown={beginDrag('out')}
                onPointerMove={onHandleMove}
                onPointerUp={endDrag}
                className="absolute inset-y-0 z-10 w-3 -translate-x-1/2 cursor-ew-resize rounded-r bg-blue-600 shadow ring-1 ring-white/50"
                style={{ left: `${pct(effEnd)}%`, touchAction: 'none' }}
              />
            </div>
            <p className="mt-1.5 text-[11px] leading-4 text-slate-400">{copy.hint}</p>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={setIn}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <Scissors size={13} />
              {copy.setIn}
            </button>
            <button
              type="button"
              onClick={setOut}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <Scissors size={13} />
              {copy.setOut}
            </button>
            <button
              type="button"
              onClick={resetSelection}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-medium text-slate-500 hover:bg-slate-50"
            >
              <RotateCcw size={13} />
              {copy.reset}
            </button>
          </div>
        </>
      )}

      {/* Precise numeric entry — also the fallback when the browser can't decode
          the uploaded format (no timeline, but the cut still works server-side). */}
      {(hasTimeline || videoError) && (
        <div className="mt-3 grid grid-cols-3 gap-2">
          <NumberCell
            label={copy.startLabel}
            value={safeStart}
            onChange={value =>
              onChange(round3(Math.max(0, hasTimeline ? Math.min(value, effEnd - MIN_GAP) : value)), endSec)
            }
          />
          <NumberCell
            label={copy.endLabel}
            value={endSec != null ? effEnd : NaN}
            placeholder={hasTimeline ? duration.toFixed(1) : undefined}
            onChange={value =>
              onChange(safeStart, round3(hasTimeline ? clamp(value, safeStart + MIN_GAP, duration) : Math.max(value, safeStart + MIN_GAP)))
            }
          />
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1.5">
            <div className="text-[10px] uppercase tracking-wide text-slate-400">{copy.durationLabel}</div>
            <div className="font-mono text-sm tabular-nums text-slate-700">
              {hasTimeline ? `${selDuration.toFixed(1)}s` : '—'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function NumberCell({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  placeholder?: string
}) {
  return (
    <label className="block rounded-lg border border-slate-200 bg-white px-2 py-1.5">
      <span className="block text-[10px] uppercase tracking-wide text-slate-400">{label}</span>
      <input
        type="number"
        min={0}
        step={0.1}
        value={Number.isFinite(value) ? value : ''}
        placeholder={placeholder}
        onChange={event => {
          const next = event.target.value
          if (next === '') return
          const parsed = Number(next)
          if (Number.isFinite(parsed)) onChange(parsed)
        }}
        className="w-full bg-transparent font-mono text-sm tabular-nums text-slate-700 outline-none"
      />
    </label>
  )
}

export default VideoTrimPreview
