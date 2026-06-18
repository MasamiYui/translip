import { useEffect, useMemo, useRef, useState } from 'react'

type WatermarkPosition = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center'

export interface WatermarkPreviewProps {
  videoUrl?: string | null
  imageUrl?: string | null
  mode: 'image' | 'text'
  position: WatermarkPosition
  margin: number
  opacity: number
  scale: number
  text: string
  fontSize: number
  fontColor: string
  strokeColor: string
  strokeOpacity: number
  strokeWidth: number
  copy: {
    title: string
    uploadVideoFirst: string
    imagePlaceholder: string
    textPlaceholder: string
    unsupportedVideo: string
    fontHint: string
    resolutionLabel: (w: number, h: number) => string
  }
}

const POSITION_STYLE: Record<WatermarkPosition, React.CSSProperties> = {
  'top-left': { top: 0, left: 0 },
  'top-right': { top: 0, right: 0 },
  'bottom-left': { bottom: 0, left: 0 },
  'bottom-right': { bottom: 0, right: 0 },
  center: { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' },
}

const POSITION_MARGIN_AXIS: Record<WatermarkPosition, { x: 'left' | 'right' | 'none'; y: 'top' | 'bottom' | 'none' }> = {
  'top-left': { x: 'left', y: 'top' },
  'top-right': { x: 'right', y: 'top' },
  'bottom-left': { x: 'left', y: 'bottom' },
  'bottom-right': { x: 'right', y: 'bottom' },
  center: { x: 'none', y: 'none' },
}

function buildOverlayPositionStyle(
  position: WatermarkPosition,
  marginPx: number,
): React.CSSProperties {
  const base: React.CSSProperties = { position: 'absolute', pointerEvents: 'none' }
  if (position === 'center') {
    return { ...base, ...POSITION_STYLE[position] }
  }
  const axis = POSITION_MARGIN_AXIS[position]
  const style: React.CSSProperties = { ...base }
  if (axis.x === 'left') style.left = `${marginPx}px`
  if (axis.x === 'right') style.right = `${marginPx}px`
  if (axis.y === 'top') style.top = `${marginPx}px`
  if (axis.y === 'bottom') style.bottom = `${marginPx}px`
  return style
}

// The stroke-color picker offers these named colors; map them to hex so the
// preview can apply stroke opacity (CSS named colors can't carry an alpha).
// Keep in sync with the watermarkColor options in ToolPage.
const NAMED_COLOR_HEX: Record<string, string> = {
  white: '#ffffff',
  black: '#000000',
  yellow: '#ffff00',
  red: '#ff0000',
  green: '#008000',
  blue: '#0000ff',
  gray: '#808080',
}

function colorWithAlpha(color: string, alpha: number): string {
  if (!Number.isFinite(alpha) || alpha >= 1) return color
  const a = Math.max(0, Math.min(1, alpha))
  const named = NAMED_COLOR_HEX[color.toLowerCase()]
  const resolved = named ?? color
  if (resolved.startsWith('#') && (resolved.length === 7 || resolved.length === 4)) {
    const hex = resolved.length === 4
      ? `#${resolved[1]}${resolved[1]}${resolved[2]}${resolved[2]}${resolved[3]}${resolved[3]}`
      : resolved
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return `rgba(${r}, ${g}, ${b}, ${a})`
  }
  return color
}

export function WatermarkPreview(props: WatermarkPreviewProps) {
  const {
    videoUrl,
    imageUrl,
    mode,
    position,
    margin,
    opacity,
    scale,
    text,
    fontSize,
    fontColor,
    strokeColor,
    strokeOpacity,
    strokeWidth,
    copy,
  } = props

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [videoSize, setVideoSize] = useState<{ width: number; height: number } | null>(null)
  const [previewWidth, setPreviewWidth] = useState<number>(0)
  const [videoError, setVideoError] = useState(false)
  const [loadedUrl, setLoadedUrl] = useState(videoUrl)

  // Reset error/size when the source changes — done during render (React's
  // "adjust state on prop change" pattern) rather than in an effect, which would
  // cause an extra render pass.
  if (videoUrl !== loadedUrl) {
    setLoadedUrl(videoUrl)
    setVideoError(false)
    setVideoSize(null)
  }

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => setPreviewWidth(el.clientWidth)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const scaleFactor = useMemo(() => {
    if (!videoSize || previewWidth <= 0) return 1
    return previewWidth / videoSize.width
  }, [videoSize, previewWidth])

  const handleLoaded = () => {
    const v = videoRef.current
    if (!v) return
    setVideoSize({ width: v.videoWidth, height: v.videoHeight })
    try {
      const target = Math.min(1, (v.duration || 2) / 2)
      if (Number.isFinite(target)) v.currentTime = target
    } catch {
      // Some streams disallow seek before metadata; ignore.
    }
  }

  const displayedMargin = Math.max(0, Math.round(margin * scaleFactor))
  const displayedFontSize = Math.max(8, Math.round(fontSize * scaleFactor))
  const displayedStrokeWidth = Math.max(0, strokeWidth * scaleFactor)
  const overlayStyle = buildOverlayPositionStyle(position, displayedMargin)
  const strokeFill = colorWithAlpha(strokeColor, strokeOpacity)

  const renderOverlay = () => {
    if (mode === 'image') {
      if (!imageUrl) {
        return (
          <div
            style={{
              ...overlayStyle,
              width: `${Math.max(scale, 0.05) * 100}%`,
              aspectRatio: '3 / 1',
              border: '1px dashed rgba(255,255,255,0.7)',
              borderRadius: 6,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.85)',
              fontSize: 11,
              padding: 4,
              textShadow: '0 1px 2px rgba(0,0,0,0.6)',
              opacity,
            }}
          >
            {copy.imagePlaceholder}
          </div>
        )
      }
      return (
        <img
          src={imageUrl}
          alt="watermark"
          style={{
            ...overlayStyle,
            width: `${Math.max(scale, 0.01) * 100}%`,
            height: 'auto',
            opacity,
            userSelect: 'none',
          }}
          draggable={false}
        />
      )
    }
    const renderedText = text.trim() || copy.textPlaceholder
    return (
      <span
        style={{
          ...overlayStyle,
          whiteSpace: 'pre',
          fontSize: `${displayedFontSize}px`,
          color: fontColor,
          opacity,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif',
          fontWeight: 700,
          lineHeight: 1.1,
          // paint-order ensures the stroke is painted behind the fill (drawtext-like).
          paintOrder: 'stroke fill',
          WebkitTextStroke:
            displayedStrokeWidth > 0 ? `${displayedStrokeWidth}px ${strokeFill}` : undefined,
        }}
      >
        {renderedText}
      </span>
    )
  }

  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-[#6b7280]">
          {copy.title}
        </div>
        {videoSize && (
          <div className="text-[11px] text-[#9ca3af]">
            {copy.resolutionLabel(videoSize.width, videoSize.height)}
          </div>
        )}
      </div>
      <div
        ref={containerRef}
        className="relative w-full overflow-hidden rounded-lg bg-black"
        style={{ aspectRatio: videoSize ? `${videoSize.width} / ${videoSize.height}` : '16 / 9' }}
      >
        {videoUrl && !videoError ? (
          <video
            ref={videoRef}
            src={videoUrl}
            muted
            playsInline
            controls
            preload="metadata"
            onLoadedMetadata={handleLoaded}
            onError={() => setVideoError(true)}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center px-4 text-center text-xs text-white/70">
            {videoUrl && videoError ? copy.unsupportedVideo : copy.uploadVideoFirst}
          </div>
        )}
        {videoUrl && !videoError && renderOverlay()}
      </div>
      {mode === 'text' && (
        <div className="mt-2 text-[11px] text-[#9ca3af]">{copy.fontHint}</div>
      )}
    </div>
  )
}

export default WatermarkPreview
