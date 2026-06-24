import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Maximize2, Pause, Play, Volume2, VolumeX } from 'lucide-react'

export interface SubtitleDetectPreviewLabels {
  panelTitle: string
  showBox: string
  showText: string
  usePolygon: string
  activeOnly: string
  eventListTitle: string
  emptyEvents: string
  keyframeSelect: string
  noSource: string
  loading: string
  confidence: string
  position: string
  language: string
  errorLoad: string
  play: string
  pause: string
  mute: string
  unmute: string
  playbackRate: string
  fullscreen: string
}

interface DetectionEvent {
  event_id?: string | null
  start_time?: number | null
  end_time?: number | null
  start?: number | null
  end?: number | null
  text?: string | null
  confidence?: number | null
  box?: number[] | null
  box_full_extent?: number[] | null
  polygon?: number[][] | null
  position?: string | null
  language?: string | null
}

interface DetectionPayload {
  video?: { width?: number; height?: number; fps?: number; total_frames?: number } | null
  events?: DetectionEvent[]
  results?: DetectionEvent[]
}

interface KeyframeRecord {
  frame_index: number
  timestamp: number
  image: string
  event_ids: string[]
}

interface KeyframesPayload {
  video?: { width?: number; height?: number; fps?: number; total_frames?: number } | null
  frames?: KeyframeRecord[]
}

interface VideoMeta {
  width: number
  height: number
  fps: number
  total_frames: number
}

export interface SubtitleDetectPreviewProps {
  labels: SubtitleDetectPreviewLabels
  videoUrl: string | null
  detectionUrl: string | null
  keyframesUrl: string | null
  resolveKeyframeUrl: (filename: string) => string
  videoMeta: VideoMeta | null
}

// Overlay palette tuned for "tool HUD on top of arbitrary video frames".
// `#38bdf8` (sky-400) reads on most cinematic frames without competing with
// warm hard subs; `#fbbf24` (amber-400) keeps the selected accent legible
// against the default cool color without going neon-pink-bright.
const COLOR_DEFAULT = '#38bdf8'
const COLOR_DEFAULT_FILL = 'rgba(56, 189, 248, 0.10)'
const COLOR_SELECTED = '#fbbf24'
const COLOR_SELECTED_FILL = 'rgba(251, 191, 36, 0.14)'
const CHIP_BG = 'rgba(15, 23, 42, 0.78)'

const PLAYBACK_RATE_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const

// Rough char-width estimate so we can size the SVG text chip without a
// canvas / measureText round-trip. CJK glyphs are ~1ch, ASCII ~0.55ch at the
// 11px label size we use below.
function estimateChipWidth(text: string, fontSize = 11): number {
  let units = 0
  for (const ch of text) {
    units += /[\u3000-\u9fff\uff00-\uffef]/.test(ch) ? 1 : 0.55
  }
  return Math.max(24, Math.round(units * fontSize) + 12)
}

function eventTime(ev: DetectionEvent): { start: number; end: number } {
  const start = typeof ev.start_time === 'number' ? ev.start_time : typeof ev.start === 'number' ? ev.start : 0
  const end = typeof ev.end_time === 'number' ? ev.end_time : typeof ev.end === 'number' ? ev.end : start
  return { start, end }
}

function eventKey(ev: DetectionEvent, idx: number): string {
  return (ev.event_id && String(ev.event_id)) || `evt-${idx}`
}

function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.floor(seconds)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function SubtitleDetectPreview({
  labels,
  videoUrl,
  detectionUrl,
  keyframesUrl,
  resolveKeyframeUrl,
  videoMeta,
}: SubtitleDetectPreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const overlayWrapRef = useRef<HTMLDivElement | null>(null)

  const [showBox, setShowBox] = useState(true)
  const [showText, setShowText] = useState(true)
  // Polygon = PaddleOCR's per-frame text outline (tight, accurate). Box =
  // post-merge stable region across multiple frames — visually misleading for
  // short / variable-width lines because it stays at the band's union extent.
  // Default to polygon so users see what was actually detected this frame.
  const [usePolygon, setUsePolygon] = useState(true)
  const [activeOnly, setActiveOnly] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [displaySize, setDisplaySize] = useState<{ w: number; h: number }>({ w: 0, h: 0 })
  const [isPlaying, setIsPlaying] = useState(false)
  const [duration, setDuration] = useState(0)
  const [muted, setMuted] = useState(false)
  const [playbackRate, setPlaybackRate] = useState<number>(1)

  // detection.json: full event list with geometry. We refetch lazily because
  // the URL only changes when a new job completes.
  const detectionQuery = useQuery<DetectionPayload>({
    queryKey: ['subtitle-detect-preview', 'detection', detectionUrl],
    queryFn: async () => {
      if (!detectionUrl) throw new Error('no detection url')
      const resp = await fetch(detectionUrl)
      if (!resp.ok) throw new Error(`detection.json HTTP ${resp.status}`)
      return (await resp.json()) as DetectionPayload
    },
    enabled: Boolean(detectionUrl),
    staleTime: 60_000,
  })

  // keyframes.json is optional — older jobs may not have it.
  const keyframesQuery = useQuery<KeyframesPayload>({
    queryKey: ['subtitle-detect-preview', 'keyframes', keyframesUrl],
    queryFn: async () => {
      if (!keyframesUrl) throw new Error('no keyframes url')
      const resp = await fetch(keyframesUrl)
      if (!resp.ok) throw new Error(`keyframes.json HTTP ${resp.status}`)
      return (await resp.json()) as KeyframesPayload
    },
    enabled: Boolean(keyframesUrl),
    staleTime: 60_000,
    retry: 0,
  })

  const detection = detectionQuery.data
  const events: DetectionEvent[] = useMemo(
    () => detection?.events ?? detection?.results ?? [],
    [detection],
  )
  const keyframes: KeyframeRecord[] = keyframesQuery.data?.frames ?? []

  // Intrinsic video size resolves in this order:
  //   1. video_meta from the tool result (most authoritative)
  //   2. detection.json's video block
  //   3. the HTMLVideoElement's videoWidth/Height after metadata loads
  const intrinsic = useMemo(() => {
    if (videoMeta && videoMeta.width > 0 && videoMeta.height > 0) {
      return { w: videoMeta.width, h: videoMeta.height }
    }
    const v = detection?.video
    if (v && v.width && v.height) return { w: v.width, h: v.height }
    const el = videoRef.current
    if (el && el.videoWidth > 0 && el.videoHeight > 0) {
      return { w: el.videoWidth, h: el.videoHeight }
    }
    return { w: 0, h: 0 }
  }, [videoMeta, detection?.video, displaySize])

  // Observe the video element's actual rendered size to keep the overlay aligned
  // through window resize / responsive layout changes.
  useLayoutEffect(() => {
    const el = videoRef.current
    if (!el) return
    const measure = () => {
      const rect = el.getBoundingClientRect()
      setDisplaySize({ w: Math.round(rect.width), h: Math.round(rect.height) })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    el.addEventListener('loadedmetadata', measure)
    return () => {
      ro.disconnect()
      el.removeEventListener('loadedmetadata', measure)
    }
  }, [videoUrl])

  // Drive the overlay off the <video> currentTime. requestAnimationFrame keeps
  // the redraw smooth without spamming React state on every browser frame.
  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    let raf = 0
    const tick = () => {
      setCurrentTime(el.currentTime)
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
    el.addEventListener('timeupdate', stop)
    return () => {
      el.removeEventListener('play', start)
      el.removeEventListener('pause', stop)
      el.removeEventListener('seeked', stop)
      el.removeEventListener('timeupdate', stop)
      if (raf) window.cancelAnimationFrame(raf)
    }
  }, [videoUrl])

  // Sync custom-controls state (isPlaying / duration / muted / playbackRate)
  // with the underlying <video> element so the toolbar always reflects truth
  // even if the user mutes via keyboard shortcuts or seeks via the SVG list.
  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    const syncPlay = () => setIsPlaying(true)
    const syncPause = () => setIsPlaying(false)
    const syncDuration = () => {
      const d = el.duration
      setDuration(Number.isFinite(d) ? d : 0)
    }
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

  const activeEvents = useMemo(() => {
    return events.filter(ev => {
      const { start, end } = eventTime(ev)
      return currentTime >= start && currentTime <= end + 0.001
    })
  }, [events, currentTime])

  const visibleEvents = useMemo(() => {
    if (!showBox && !showText) return []
    if (activeOnly) return activeEvents
    return events
  }, [showBox, showText, activeOnly, activeEvents, events])

  const seekTo = (ev: DetectionEvent, idx: number) => {
    const el = videoRef.current
    if (!el) return
    const { start, end } = eventTime(ev)
    el.currentTime = (start + end) / 2.0
    setSelectedId(eventKey(ev, idx))
    el.pause()
  }

  const handleKeyframeSelect = (value: string) => {
    if (!value) return
    const idx = Number(value)
    if (!Number.isFinite(idx)) return
    const frame = keyframes[idx]
    if (!frame) return
    const el = videoRef.current
    if (el) el.currentTime = frame.timestamp
  }

  const togglePlay = () => {
    const el = videoRef.current
    if (!el) return
    if (el.paused || el.ended) {
      void el.play()
    } else {
      el.pause()
    }
  }

  const toggleMute = () => {
    const el = videoRef.current
    if (!el) return
    el.muted = !el.muted
  }

  const handleSeekChange = (value: number) => {
    const el = videoRef.current
    if (!el) return
    if (!Number.isFinite(value)) return
    el.currentTime = Math.max(0, Math.min(value, duration || el.duration || value))
  }

  const handlePlaybackRateChange = (value: string) => {
    const rate = Number(value)
    if (!Number.isFinite(rate) || rate <= 0) return
    const el = videoRef.current
    if (el) el.playbackRate = rate
  }

  const handleFullscreen = () => {
    const wrap = overlayWrapRef.current
    if (!wrap) return
    if (document.fullscreenElement) {
      void document.exitFullscreen()
    } else if (wrap.requestFullscreen) {
      void wrap.requestFullscreen()
    }
  }

  const scaleX = intrinsic.w > 0 ? displaySize.w / intrinsic.w : 1
  const scaleY = intrinsic.h > 0 ? displaySize.h / intrinsic.h : 1
  const posterUrl = keyframes.length > 0 ? resolveKeyframeUrl(keyframes[0].image) : undefined

  const isLoading = detectionQuery.isLoading
  const loadError = detectionQuery.isError ? labels.errorLoad : null

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-700">{labels.panelTitle}</div>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
          <label className="inline-flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={showBox}
              onChange={e => setShowBox(e.target.checked)}
              className="accent-blue-600"
            />
            <span>{labels.showBox}</span>
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={showText}
              onChange={e => setShowText(e.target.checked)}
              className="accent-blue-600"
            />
            <span>{labels.showText}</span>
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={usePolygon}
              onChange={e => setUsePolygon(e.target.checked)}
              className="accent-blue-600"
            />
            <span>{labels.usePolygon}</span>
          </label>
          <label className="inline-flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={e => setActiveOnly(e.target.checked)}
              className="accent-blue-600"
            />
            <span>{labels.activeOnly}</span>
          </label>
          {keyframes.length > 0 && (
            <select
              defaultValue=""
              onChange={e => handleKeyframeSelect(e.target.value)}
              className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700"
              aria-label={labels.keyframeSelect}
            >
              <option value="" disabled>
                {labels.keyframeSelect}
              </option>
              {keyframes.map((kf, idx) => (
                <option key={`${kf.frame_index}-${idx}`} value={idx}>
                  #{idx + 1} · {kf.timestamp.toFixed(2)}s · {kf.event_ids.length}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          <div
            ref={overlayWrapRef}
            className="relative w-full overflow-hidden rounded-xl bg-black"
            style={{ aspectRatio: intrinsic.w > 0 && intrinsic.h > 0 ? `${intrinsic.w} / ${intrinsic.h}` : '16 / 9' }}
          >
            {videoUrl ? (
              <video
                ref={videoRef}
                src={videoUrl}
                poster={posterUrl}
                onClick={togglePlay}
                className="absolute inset-0 h-full w-full cursor-pointer"
              />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-300">
                {labels.noSource}
              </div>
            )}
            {videoUrl && displaySize.w > 0 && displaySize.h > 0 && (showBox || showText) && (
              <svg
                className="pointer-events-none absolute inset-0"
                width={displaySize.w}
                height={displaySize.h}
                viewBox={`0 0 ${displaySize.w} ${displaySize.h}`}
              >
                <defs>
                  {/* Soft outer glow makes the overlay feel like a HUD rather
                      than a flat photoshop annotation, and it survives both
                      bright and dark backgrounds. */}
                  <filter id="sd-glow" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="1.2" result="blur" />
                    <feMerge>
                      <feMergeNode in="blur" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                {visibleEvents.map((ev, idx) => {
                  const key = eventKey(ev, idx)
                  const selected = selectedId === key
                  const stroke = selected ? COLOR_SELECTED : COLOR_DEFAULT
                  const fillColor = selected ? COLOR_SELECTED_FILL : COLOR_DEFAULT_FILL
                  const strokeWidth = selected ? 2 : 1.5
                  // PaddleOCR detection output is normally a 4-pt quadrilateral,
                  // but the merger occasionally simplifies it down to the two
                  // baseline endpoints (`[[x_left, y], [x_right, y]]`). When
                  // that happens we synthesize a tight rectangle around the
                  // text by reusing the box's vertical extent — that way the
                  // polygon path still renders the *real* text width instead
                  // of falling through to the (over-padded) stable box.
                  const rawPolygon = ev.polygon
                  let polygon: number[][] | null = null
                  if (rawPolygon && rawPolygon.length >= 3) {
                    polygon = rawPolygon
                  } else if (rawPolygon && rawPolygon.length === 2 && ev.box && ev.box.length === 4) {
                    const [pa, pb] = rawPolygon
                    const xs = [pa[0] ?? 0, pb[0] ?? 0].sort((a, b) => a - b)
                    const [, y1, , y2] = ev.box
                    polygon = [
                      [xs[0], y1],
                      [xs[1], y1],
                      [xs[1], y2],
                      [xs[0], y2],
                    ]
                  }

                  // Resolve a single anchor rect (x, y, w, h) so the text chip
                  // logic doesn't have to care whether we drew polygon or box.
                  let anchor: { x: number; y: number; w: number; h: number } | null = null
                  if (showBox && usePolygon && polygon) {
                    const xs = polygon.map(p => (p[0] ?? 0) * scaleX)
                    const ys = polygon.map(p => (p[1] ?? 0) * scaleY)
                    const ax = Math.min(...xs)
                    const ay = Math.min(...ys)
                    anchor = { x: ax, y: ay, w: Math.max(...xs) - ax, h: Math.max(...ys) - ay }
                  } else {
                    const box = ev.box ?? ev.box_full_extent
                    if (!box || box.length !== 4) return null
                    const [x1, y1, x2, y2] = box
                    anchor = {
                      x: x1 * scaleX,
                      y: y1 * scaleY,
                      w: Math.max(0, (x2 - x1) * scaleX),
                      h: Math.max(0, (y2 - y1) * scaleY),
                    }
                  }

                  // Build the chip placement once and reuse it for both
                  // polygon and box branches. Chip prefers above the anchor;
                  // when the anchor hugs the top edge we flip it under so the
                  // label is never clipped by the video frame.
                  const text = String(ev.text ?? '').slice(0, 40)
                  const confidence =
                    typeof ev.confidence === 'number' ? ev.confidence.toFixed(2) : null
                  const labelStr = confidence ? `${text} · ${confidence}` : text
                  const chipH = 18
                  const chipW = estimateChipWidth(labelStr, 11)
                  const chipFlipDown = anchor.y - chipH - 6 < 0
                  let chipX = anchor.x
                  if (chipX + chipW > displaySize.w) chipX = displaySize.w - chipW - 2
                  if (chipX < 2) chipX = 2
                  const chipY = chipFlipDown ? anchor.y + anchor.h + 6 : anchor.y - chipH - 6

                  const shapeNode =
                    showBox && usePolygon && polygon ? (
                      <polygon
                        points={polygon
                          .map(pair => `${(pair[0] ?? 0) * scaleX},${(pair[1] ?? 0) * scaleY}`)
                          .join(' ')}
                        stroke={stroke}
                        strokeWidth={strokeWidth}
                        fill={fillColor}
                        opacity={0.95}
                        filter="url(#sd-glow)"
                      />
                    ) : showBox ? (
                      <rect
                        x={anchor.x}
                        y={anchor.y}
                        width={anchor.w}
                        height={anchor.h}
                        rx={3}
                        ry={3}
                        stroke={stroke}
                        strokeWidth={strokeWidth}
                        fill={fillColor}
                        opacity={0.95}
                        filter="url(#sd-glow)"
                      />
                    ) : null

                  return (
                    <g key={key}>
                      {shapeNode}
                      {showText && text && (
                        <g style={{ transition: 'opacity 180ms ease' }}>
                          <rect
                            x={chipX}
                            y={chipY}
                            width={chipW}
                            height={chipH}
                            rx={4}
                            ry={4}
                            fill={CHIP_BG}
                            stroke={stroke}
                            strokeWidth={0.75}
                            opacity={0.95}
                          />
                          <text
                            x={chipX + 6}
                            y={chipY + chipH - 5}
                            fill="#f8fafc"
                            fontSize={11}
                            fontFamily="ui-sans-serif, -apple-system, system-ui, sans-serif"
                            fontWeight={500}
                          >
                            {text}
                          </text>
                          {confidence && (
                            <text
                              x={chipX + chipW - 6}
                              y={chipY + chipH - 5}
                              fill={stroke}
                              fontSize={10}
                              fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
                              textAnchor="end"
                              opacity={0.85}
                            >
                              {confidence}
                            </text>
                          )}
                        </g>
                      )}
                    </g>
                  )
                })}
              </svg>
            )}
          </div>
          {videoUrl && (
            <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-700">
              <button
                type="button"
                onClick={togglePlay}
                aria-label={isPlaying ? labels.pause : labels.play}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-slate-900 text-white hover:bg-slate-700"
              >
                {isPlaying ? <Pause size={14} /> : <Play size={14} />}
              </button>
              <input
                type="range"
                min={0}
                max={duration > 0 ? duration : 0}
                step={0.05}
                value={Math.min(currentTime, duration || currentTime)}
                onChange={e => handleSeekChange(Number(e.target.value))}
                disabled={duration <= 0}
                className="h-1 flex-1 min-w-[120px] cursor-pointer accent-blue-600"
                aria-label={labels.play}
              />
              <span className="font-mono text-[11px] tabular-nums text-slate-500">
                {formatClock(currentTime)} / {formatClock(duration)}
              </span>
              <button
                type="button"
                onClick={toggleMute}
                aria-label={muted ? labels.unmute : labels.mute}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
              >
                {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </button>
              <select
                value={String(playbackRate)}
                onChange={e => handlePlaybackRateChange(e.target.value)}
                aria-label={labels.playbackRate}
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
                aria-label={labels.fullscreen}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-100"
              >
                <Maximize2 size={14} />
              </button>
            </div>
          )}
          <div className="mt-1 text-[11px] uppercase tracking-widest text-slate-400">
            t = {currentTime.toFixed(2)}s · {activeEvents.length} active
          </div>
        </div>

        <div className="flex max-h-[420px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-3 py-2 text-[11px] uppercase tracking-widest text-slate-400">
            {labels.eventListTitle} · {events.length}
          </div>
          <div className="flex-1 overflow-y-auto">
            {isLoading && (
              <div className="px-3 py-6 text-center text-xs text-slate-400">{labels.loading}</div>
            )}
            {loadError && (
              <div className="px-3 py-6 text-center text-xs text-rose-500">{loadError}</div>
            )}
            {!isLoading && !loadError && events.length === 0 && (
              <div className="px-3 py-6 text-center text-xs text-slate-400">{labels.emptyEvents}</div>
            )}
            {!isLoading && !loadError && events.length > 0 && (
              <ul className="divide-y divide-slate-100 text-xs">
                {events.map((ev, idx) => {
                  const key = eventKey(ev, idx)
                  const { start, end } = eventTime(ev)
                  const isActive = currentTime >= start && currentTime <= end + 0.001
                  const isSelected = selectedId === key
                  return (
                    <li
                      key={key}
                      className={`cursor-pointer px-3 py-2 transition-colors ${
                        isSelected
                          ? 'bg-emerald-50'
                          : isActive
                            ? 'bg-amber-50'
                            : 'hover:bg-slate-50'
                      }`}
                      onClick={() => seekTo(ev, idx)}
                    >
                      <div className="flex items-baseline justify-between gap-2 text-[11px] text-slate-500">
                        <span className="font-mono">
                          {start.toFixed(2)}s → {end.toFixed(2)}s
                        </span>
                        {typeof ev.confidence === 'number' && (
                          <span className="font-mono">
                            {labels.confidence} {ev.confidence.toFixed(2)}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 break-words text-sm text-slate-800">
                        {(ev.text || '').toString() || '—'}
                      </div>
                      <div className="mt-0.5 flex flex-wrap gap-x-3 text-[11px] text-slate-400">
                        {ev.position && (
                          <span>
                            {labels.position} {ev.position}
                          </span>
                        )}
                        {ev.language && (
                          <span>
                            {labels.language} {ev.language}
                          </span>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
