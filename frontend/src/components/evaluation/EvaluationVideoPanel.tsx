import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, Crosshair, SkipBack, SkipForward } from 'lucide-react'
import {
  taskArtifactUrl,
  taskInputFileUrl,
  type DubQaReport,
  type DubQaSegment,
} from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

type Track = 'original' | 'dubbed' | 'background'

const STORAGE_KEY = 'evaluation-video-panel:expanded'

function useIsVideoSrc(src: string): { ready: boolean; isVideo: boolean } {
  const { data, isFetched } = useQuery({
    queryKey: ['media-kind', src],
    queryFn: async () => {
      try {
        const res = await fetch(src, { method: 'HEAD' })
        const ct = res.headers.get('Content-Type') ?? ''
        return ct.startsWith('video/')
      } catch {
        return true
      }
    },
    staleTime: Infinity,
    gcTime: Infinity,
  })
  return { ready: isFetched, isVideo: data ?? true }
}

function relInputPath(report: DubQaReport, key: string): string | null {
  const value = report.input?.[key]
  return typeof value === 'string' && value.length > 0 ? value : null
}

function formatTime(sec: number): string {
  if (!Number.isFinite(sec) || sec < 0) return '0:00.0'
  const m = Math.floor(sec / 60)
  const s = sec - m * 60
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

interface Props {
  taskId: string
  report: DubQaReport
  segments: DubQaSegment[]
  selectedId: string | null
  onSelectSegment: (segment: DubQaSegment) => void
  /**
   * When true, the panel is rendered without its own header/collapse control
   * (e.g. when it lives inside the Diagnostics tabbed card). The body is
   * always visible in this mode.
   */
  embedded?: boolean
}

/**
 * Diagnostic-only video panel for the evaluation detail page.
 *
 * Intentionally NOT a full editor:
 *   - No clip-level editing, mixing, or timeline drag.
 *   - Plays the original video and lets the reviewer A/B between original
 *     audio, the rendered dub mix, and the pure background bed to triage
 *     problem segments.
 *
 * Sync model: the <video> is the time master; when a non-original track is
 * selected, the video is muted and a hidden <audio> plays that track (dub
 * mix or background bed), kept aligned to video.currentTime via the standard
 * play/pause/seek events plus a low-frequency drift correction.
 */
export function EvaluationVideoPanel({
  taskId,
  report,
  segments,
  selectedId,
  onSelectSegment,
  embedded = false,
}: Props) {
  const { t } = useI18n()
  const tx = t.evaluation.videoPanel

  const inputSrc = useMemo(() => taskInputFileUrl(taskId), [taskId])
  const dubRelPath = relInputPath(report, 'dub_voice')
  const dubSrc = dubRelPath ? taskArtifactUrl(taskId, dubRelPath) : null
  const bgRelPath = relInputPath(report, 'background')
  const bgSrc = bgRelPath ? taskArtifactUrl(taskId, bgRelPath) : null

  const { ready: kindReady, isVideo } = useIsVideoSrc(inputSrc)

  const [expanded, setExpanded] = useState<boolean>(() => {
    if (embedded) return true
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) === '1'
  })
  const toggleExpanded = () => {
    setExpanded(prev => {
      const next = !prev
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
      } catch {
        /* ignore quota / private mode */
      }
      return next
    })
  }

  const [track, setTrack] = useState<Track>('original')
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  const videoRef = useRef<HTMLVideoElement>(null)
  const extraAudioRef = useRef<HTMLAudioElement>(null)

  // The audio source for the active non-original track (null on 'original').
  const extraSrc = track === 'dubbed' ? dubSrc : track === 'background' ? bgSrc : null

  const problemSegments = useMemo(
    () => segments.filter(s => s.issue_tags.length > 0 && typeof s.start === 'number'),
    [segments],
  )

  const selected = useMemo(
    () => segments.find(s => s.segment_id === selectedId) ?? null,
    [segments, selectedId],
  )

  useEffect(() => {
    if (!expanded) return
    if (!selected || typeof selected.start !== 'number') return
    const v = videoRef.current
    if (!v) return
    v.currentTime = selected.start
    setCurrentTime(selected.start)
  }, [expanded, selected])

  useEffect(() => {
    if (track === 'original') return
    const v = videoRef.current
    const a = extraAudioRef.current
    if (!v || !a) return

    const syncPlay = () => {
      a.currentTime = v.currentTime
      void a.play().catch(() => undefined)
    }
    const syncPause = () => {
      a.pause()
    }
    const syncSeek = () => {
      a.currentTime = v.currentTime
    }
    const syncRate = () => {
      a.playbackRate = v.playbackRate
    }

    v.addEventListener('play', syncPlay)
    v.addEventListener('pause', syncPause)
    v.addEventListener('seeked', syncSeek)
    v.addEventListener('ratechange', syncRate)

    // If switching tracks mid-playback, start the new audio immediately rather
    // than waiting for the next play event (the video is muted in this mode).
    a.playbackRate = v.playbackRate
    if (!v.paused) {
      a.currentTime = v.currentTime
      void a.play().catch(() => undefined)
    }

    const driftId = window.setInterval(() => {
      if (v.paused) return
      const drift = a.currentTime - v.currentTime
      if (Math.abs(drift) > 0.06) {
        a.currentTime = v.currentTime
      }
    }, 250)

    return () => {
      v.removeEventListener('play', syncPlay)
      v.removeEventListener('pause', syncPause)
      v.removeEventListener('seeked', syncSeek)
      v.removeEventListener('ratechange', syncRate)
      window.clearInterval(driftId)
      a.pause()
    }
  }, [track])

  const onTimeUpdate = () => {
    const v = videoRef.current
    if (!v) return
    setCurrentTime(v.currentTime)
  }

  const onLoadedMetadata = () => {
    const v = videoRef.current
    if (!v) return
    setDuration(v.duration || 0)
  }

  const seekTo = (sec: number) => {
    const v = videoRef.current
    if (!v) return
    v.currentTime = sec
    setCurrentTime(sec)
  }

  const jumpToProblem = (direction: 1 | -1) => {
    if (problemSegments.length === 0) return
    const ordered = [...problemSegments].sort(
      (a, b) => (a.start ?? 0) - (b.start ?? 0),
    )
    let target: DubQaSegment | null = null
    if (direction === 1) {
      target = ordered.find(s => (s.start ?? 0) > currentTime + 0.01) ?? ordered[0]
    } else {
      const earlier = ordered.filter(s => (s.start ?? 0) < currentTime - 0.01)
      target = earlier.length > 0 ? earlier[earlier.length - 1] : ordered[ordered.length - 1]
    }
    if (target) {
      seekTo(target.start ?? 0)
      onSelectSegment(target)
    }
  }

  if (kindReady && !isVideo) {
    if (embedded) {
      return (
        <div className="rounded-lg bg-[#f9fafb] px-4 py-6 text-center text-xs text-[#9ca3af]">
          {tx.noVideo}
        </div>
      )
    }
    return (
      <div className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-5 py-3 text-xs text-[#9ca3af]">
        {tx.noVideo}
      </div>
    )
  }

  const body = (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
      <div>
        <video
          ref={videoRef}
          src={inputSrc}
          controls
          playsInline
          preload="metadata"
          muted={track !== 'original'}
          className="aspect-video w-full rounded-lg bg-black"
          onTimeUpdate={onTimeUpdate}
          onLoadedMetadata={onLoadedMetadata}
        />
        {extraSrc && (
          <audio
            ref={extraAudioRef}
            src={extraSrc}
            preload="metadata"
            className="hidden"
          />
        )}

        <SegmentTimeline
          duration={duration}
          currentTime={currentTime}
          problems={problemSegments}
          selectedId={selectedId}
          onSeek={(sec, seg) => {
            seekTo(sec)
            if (seg) onSelectSegment(seg)
          }}
        />
      </div>

      <aside className="flex flex-col gap-3 text-xs">
        <div>
          <div className="mb-1.5 font-medium text-[#6b7280]">{tx.track}</div>
          <div className="inline-flex rounded-lg border border-[#e5e7eb] p-0.5">
            <TrackTab
              active={track === 'original'}
              onClick={() => setTrack('original')}
              label={tx.trackOriginal}
            />
            <TrackTab
              active={track === 'dubbed'}
              disabled={!dubSrc}
              title={!dubSrc ? tx.noDubbed : undefined}
              onClick={() => dubSrc && setTrack('dubbed')}
              label={tx.trackDubbed}
            />
            <TrackTab
              active={track === 'background'}
              disabled={!bgSrc}
              title={!bgSrc ? tx.noBackground : undefined}
              onClick={() => bgSrc && setTrack('background')}
              label={tx.trackBackground}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => jumpToProblem(-1)}
            disabled={problemSegments.length === 0}
            className={cn(
              'flex items-center gap-1 rounded-md px-2.5 py-1.5 font-medium',
              problemSegments.length === 0
                ? 'cursor-not-allowed bg-[#f3f4f6] text-[#cbd5e1]'
                : 'border border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]',
            )}
          >
            <SkipBack size={12} /> {tx.prevProblem}
          </button>
          <button
            type="button"
            onClick={() => jumpToProblem(1)}
            disabled={problemSegments.length === 0}
            className={cn(
              'flex items-center gap-1 rounded-md px-2.5 py-1.5 font-medium',
              problemSegments.length === 0
                ? 'cursor-not-allowed bg-[#f3f4f6] text-[#cbd5e1]'
                : 'border border-[#e5e7eb] bg-white text-[#374151] hover:bg-[#f9fafb]',
            )}
          >
            {tx.nextProblem} <SkipForward size={12} />
          </button>
          <button
            type="button"
            onClick={() => {
              if (selected && typeof selected.start === 'number') seekTo(selected.start)
            }}
            disabled={!selected}
            className={cn(
              'flex items-center gap-1 rounded-md px-2.5 py-1.5 font-medium',
              !selected
                ? 'cursor-not-allowed bg-[#f3f4f6] text-[#cbd5e1]'
                : 'border border-[#3b5bdb]/30 bg-[#3b5bdb]/5 text-[#3b5bdb] hover:bg-[#3b5bdb]/10',
            )}
          >
            <Crosshair size={12} /> {tx.jumpToSelected}
          </button>
        </div>

        <div className="rounded-lg bg-[#f9fafb] px-2.5 py-2 text-[#6b7280]">
          <div className="flex items-center justify-between">
            <span>{tx.currentSegment}</span>
            <span className="font-mono tabular-nums">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
          {selected ? (
            <div className="mt-1 truncate text-[#374151]">
              {selected.target_text || selected.source_text || selected.segment_id}
            </div>
          ) : (
            <div className="mt-1 text-[#9ca3af]">{tx.noSelection}</div>
          )}
        </div>

        <div className="flex items-center gap-1.5 text-[#9ca3af]">
          <span className="inline-block h-2 w-3 rounded-sm bg-amber-400" />
          {tx.issueLegend} ({problemSegments.length})
        </div>
      </aside>
    </div>
  )

  if (embedded) {
    return body
  }

  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
      <header className="flex items-center justify-between gap-3 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold text-[#111827]">{tx.title}</h2>
          <p className="text-xs text-[#9ca3af]">{tx.subtitle}</p>
        </div>
        <button
          type="button"
          onClick={toggleExpanded}
          aria-expanded={expanded}
          className="flex items-center gap-1.5 rounded-md border border-[#e5e7eb] bg-white px-2.5 py-1.5 text-xs font-medium text-[#374151] hover:bg-[#f9fafb]"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {expanded ? tx.collapse : tx.expand}
        </button>
      </header>

      {expanded && <div className="border-t border-[#f3f4f6] px-5 py-4">{body}</div>}
    </section>
  )
}

function TrackTab({
  active,
  disabled,
  title,
  onClick,
  label,
}: {
  active: boolean
  disabled?: boolean
  title?: string
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'rounded-md px-2.5 py-1 font-medium transition-colors',
        disabled && 'cursor-not-allowed text-[#cbd5e1]',
        !disabled && active && 'bg-[#3b5bdb] text-white',
        !disabled && !active && 'text-[#6b7280] hover:bg-[#f3f4f6]',
      )}
    >
      {label}
    </button>
  )
}

function SegmentTimeline({
  duration,
  currentTime,
  problems,
  selectedId,
  onSeek,
}: {
  duration: number
  currentTime: number
  problems: DubQaSegment[]
  selectedId: string | null
  onSeek: (sec: number, seg: DubQaSegment | null) => void
}) {
  const ref = useRef<HTMLDivElement>(null)

  const onClickTrack = (e: ReactMouseEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el || duration <= 0) return
    const rect = el.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    const sec = Math.max(0, Math.min(duration, ratio * duration))
    onSeek(sec, null)
  }

  if (duration <= 0) {
    return <div className="mt-3 h-6 rounded-md bg-[#f3f4f6]" aria-hidden />
  }

  const playhead = Math.max(0, Math.min(1, currentTime / duration)) * 100

  return (
    <div
      ref={ref}
      onClick={onClickTrack}
      className="relative mt-3 h-6 cursor-pointer overflow-hidden rounded-md bg-[#f3f4f6]"
      role="slider"
      aria-valuemin={0}
      aria-valuemax={duration}
      aria-valuenow={currentTime}
    >
      {problems.map(seg => {
        const start = seg.start ?? 0
        const end = seg.end ?? start
        const left = (start / duration) * 100
        const width = Math.max(0.4, ((end - start) / duration) * 100)
        const active = seg.segment_id === selectedId
        return (
          <button
            key={seg.segment_id}
            type="button"
            onClick={e => {
              e.stopPropagation()
              onSeek(start, seg)
            }}
            title={`${formatTime(start)} – ${formatTime(end)} · ${seg.severity}`}
            className={cn(
              'absolute top-0 h-full',
              active ? 'bg-[#3b5bdb]/80' : 'bg-amber-400/80 hover:bg-amber-500',
            )}
            style={{ left: `${left}%`, width: `${width}%` }}
            aria-label={`segment ${seg.segment_id}`}
          />
        )
      })}
      <div
        className="pointer-events-none absolute top-0 h-full w-px bg-[#111827]"
        style={{ left: `${playhead}%` }}
      />
    </div>
  )
}
