import { Download, FileText, CheckCircle2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../../i18n/useI18n'
import { CommentaryReview } from './CommentaryReview'
import { CrossToolAction } from './CrossToolAction'
import { SubtitleDetectPreview, type SubtitleDetectPreviewLabels } from './SubtitleDetectPreview'
import type { ArtifactInfo, AtomicJob } from '../../types/atomic-tools'
import type { AtomicToolPrefill } from '../../lib/atomicToolPrefill'

interface ResultPanelProps {
  toolId: string
  job: AtomicJob | null
  artifacts: ArtifactInfo[]
  getDownloadUrl: (filename: string) => string
  originalVideoUrl?: string | null
  /**
   * Render the flat artifacts card list at the bottom of this panel.
   *
   * Default `true` keeps the live ToolPage experience unchanged. The job
   * detail page passes `false` because it owns a richer, grouped ArtifactsPanel
   * directly below and we want to avoid showing the same artifacts twice.
   */
  showArtifactsList?: boolean
}

export type ArtifactActionLabels = {
  toTts: string
  toTranscription: string
  toMixing: string
  toTranslation: string
  toMuxing: string
  toSubtitleErase: string
  toTranscriptCorrection: string
  toVideoAnalyze: string
  toProbe: string
  toSeparation: string
}

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  completed: { label: 'COMPLETED', color: 'text-emerald-600', dot: 'bg-emerald-500' },
  running: { label: 'RUNNING', color: 'text-blue-600', dot: 'bg-blue-500' },
  failed: { label: 'FAILED', color: 'text-red-500', dot: 'bg-red-500' },
  pending: { label: 'PENDING', color: 'text-[#9ca3af]', dot: 'bg-[#d1d5db]' },
}

export function ResultPanel({
  toolId,
  job,
  artifacts,
  getDownloadUrl,
  originalVideoUrl,
  showArtifactsList = true,
}: ResultPanelProps) {
  const { t } = useI18n()
  if (!job) return null

  const translatedText =
    typeof job.result?.translated_text === 'string' ? job.result.translated_text : null

  const statusCfg = STATUS_CONFIG[job.status] ?? { label: job.status.toUpperCase(), color: 'text-[#6b7280]', dot: 'bg-[#9ca3af]' }

  const sideBySide = buildSubtitleEraseCompare(toolId, job, artifacts, getDownloadUrl, {
    compareTitle: t.atomicTools.result.compareTitle,
    compareOriginal: t.atomicTools.result.compareOriginal,
    compareErased: t.atomicTools.result.compareErased,
    quickMetrics: t.atomicTools.result.quickMetrics,
  }, originalVideoUrl ?? null)

  const subtitleDetectPreview = buildSubtitleDetectPreview(
    toolId,
    job,
    artifacts,
    getDownloadUrl,
    originalVideoUrl ?? null,
    {
      panelTitle: t.atomicTools.result.subtitleDetectPreview.panelTitle,
      showBox: t.atomicTools.result.subtitleDetectPreview.showBox,
      showText: t.atomicTools.result.subtitleDetectPreview.showText,
      usePolygon: t.atomicTools.result.subtitleDetectPreview.usePolygon,
      activeOnly: t.atomicTools.result.subtitleDetectPreview.activeOnly,
      eventListTitle: t.atomicTools.result.subtitleDetectPreview.eventListTitle,
      emptyEvents: t.atomicTools.result.subtitleDetectPreview.emptyEvents,
      keyframeSelect: t.atomicTools.result.subtitleDetectPreview.keyframeSelect,
      noSource: t.atomicTools.result.subtitleDetectPreview.noSource,
      loading: t.atomicTools.result.subtitleDetectPreview.loading,
      confidence: t.atomicTools.result.subtitleDetectPreview.confidence,
      position: t.atomicTools.result.subtitleDetectPreview.position,
      language: t.atomicTools.result.subtitleDetectPreview.language,
      errorLoad: t.atomicTools.result.subtitleDetectPreview.errorLoad,
      play: t.atomicTools.result.subtitleDetectPreview.play,
      pause: t.atomicTools.result.subtitleDetectPreview.pause,
      mute: t.atomicTools.result.subtitleDetectPreview.mute,
      unmute: t.atomicTools.result.subtitleDetectPreview.unmute,
      playbackRate: t.atomicTools.result.subtitleDetectPreview.playbackRate,
      fullscreen: t.atomicTools.result.subtitleDetectPreview.fullscreen,
    },
  )

  const commentaryReviewArtifact =
    toolId === 'commentary-script' && job.status === 'completed'
      ? artifacts.find(item => /commentary\.json$/i.test(item.filename))
      : undefined

  return (
    <section className="space-y-4">
      {/* Result header card */}
      <div className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-[#111827] uppercase tracking-wide">{t.atomicTools.result.title}</h3>
          <div className={`flex items-center gap-1.5 text-xs font-semibold ${statusCfg.color}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${statusCfg.dot}`} />
            {statusCfg.label}
          </div>
        </div>

        {job.status === 'completed' && !job.result && (
          <div className="flex items-center gap-2 text-sm text-emerald-600">
            <CheckCircle2 size={16} />
            <span className="font-medium">处理完成</span>
          </div>
        )}

        {job.result && (
          <details className="group">
            <summary className="cursor-pointer list-none text-xs font-semibold text-[#9ca3af] hover:text-[#374151] transition-colors flex items-center gap-1.5">
              <span className="group-open:hidden">▶ 查看 JSON</span>
              <span className="hidden group-open:inline">▼ 收起 JSON</span>
            </summary>
            <div className="mt-3 rounded-lg bg-[#f8f9fa] border border-[#e5e7eb] p-4 text-[11px] leading-5 font-mono text-[#374151] overflow-x-auto">
              <pre className="whitespace-pre-wrap">{JSON.stringify(job.result, null, 2)}</pre>
            </div>
          </details>
        )}
      </div>

      {/* Translated text */}
      {translatedText && (
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#374151]">
            <FileText size={15} className="text-[#9ca3af]" />
            {t.atomicTools.result.translatedText}
          </div>
          <p className="whitespace-pre-wrap text-sm leading-6 text-[#4b5563]">{translatedText}</p>
          <div className="mt-4 pt-4 border-t border-[#f3f4f6]">
            <CrossToolAction
              label={t.atomicTools.result.toTts}
              targetToolId="tts"
              payload={{ text: translatedText }}
            />
          </div>
        </div>
      )}

      {sideBySide}

      {subtitleDetectPreview}

      {commentaryReviewArtifact && (
        <CommentaryReview
          key={commentaryReviewArtifact.filename}
          commentaryUrl={getDownloadUrl(commentaryReviewArtifact.filename)}
          labels={t.atomicTools.commentary.review}
        />
      )}

      {/* Artifacts */}
      {showArtifactsList && artifacts.length > 0 && (
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">输出文件</div>
          {artifacts.map(artifact => (
            <div key={artifact.filename} className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-[#111827] truncate">{artifact.filename}</div>
                  <div className="text-xs text-[#9ca3af] mt-0.5">{artifact.content_type}</div>
                </div>
                <a
                  href={getDownloadUrl(artifact.filename)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-[#e5e7eb] px-3 py-1.5 text-xs font-semibold text-[#3b5bdb] transition-all hover:bg-[#f0f3ff]"
                >
                  <Download size={13} />
                  {t.atomicTools.actions.download}
                </a>
              </div>

              {isAudioFile(artifact.filename, artifact.content_type) && (
                <audio controls className="w-full mt-1" src={getDownloadUrl(artifact.filename)} />
              )}

              {isVideoFile(artifact.filename, artifact.content_type) && (
                <video controls className="w-full mt-1 rounded-lg" src={getDownloadUrl(artifact.filename)} />
              )}

              {buildArtifactActions(toolId, artifact, translatedText, t.atomicTools.result).length > 0 && (
                <div className="mt-3 pt-3 border-t border-[#f3f4f6] flex flex-wrap gap-2">
                  {buildArtifactActions(toolId, artifact, translatedText, t.atomicTools.result).map(action => (
                    <CrossToolAction
                      key={`${artifact.filename}-${action.targetToolId}-${action.label}`}
                      label={action.label}
                      targetToolId={action.targetToolId}
                      payload={action.payload}
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function isAudioFile(filename: string, contentType: string) {
  return contentType.startsWith('audio/') || /\.(wav|mp3|flac|m4a|aac|ogg)$/i.test(filename)
}

function isVideoFile(filename: string, contentType: string) {
  return contentType.startsWith('video/') || /\.(mp4|mov|mkv|webm)$/i.test(filename)
}

export function buildArtifactActions(
  toolId: string,
  artifact: ArtifactInfo,
  translatedText: string | null,
  labels: ArtifactActionLabels,
) {
  const fileId = artifact.file_id ?? undefined
  if (!fileId) return []

  if (toolId === 'separation' && /^voice\./i.test(artifact.filename)) {
    return [
      buildArtifactAction(labels.toTranscription, 'transcription', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
      buildArtifactAction(labels.toMixing, 'mixing', {
        files: { voice_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'separation' && /^background\./i.test(artifact.filename)) {
    return [
      buildArtifactAction(labels.toMixing, 'mixing', {
        files: { background_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'transcription') {
    const actions = [
      buildArtifactAction(labels.toTranslation, 'translation', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
    if (/\.json$/i.test(artifact.filename)) {
      actions.push(
        buildArtifactAction(labels.toTranscriptCorrection, 'transcript-correction', {
          files: { segments_file: { file_id: fileId, filename: artifact.filename } },
        }),
      )
    }
    return actions
  }

  if (toolId === 'tts') {
    return [
      buildArtifactAction(labels.toMixing, 'mixing', {
        files: { voice_file: { file_id: fileId, filename: artifact.filename } },
      }),
      buildArtifactAction(labels.toMuxing, 'muxing', {
        files: { audio_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'mixing') {
    return [
      buildArtifactAction(labels.toMuxing, 'muxing', {
        files: { audio_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'translation' && translatedText) {
    return [buildArtifactAction(labels.toTts, 'tts', { text: translatedText })]
  }

  if (toolId === 'subtitle-detect' && /detection\.json$/i.test(artifact.filename)) {
    return [
      buildArtifactAction(labels.toSubtitleErase, 'subtitle-erase', {
        files: { detection_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'subtitle-detect' && /ocr_events\.json$/i.test(artifact.filename)) {
    return [
      buildArtifactAction(labels.toTranscriptCorrection, 'transcript-correction', {
        files: { ocr_events_file: { file_id: fileId, filename: artifact.filename } },
      }),
      // Vision triage of the detected text (subtitle vs scene text vs watermark).
      buildArtifactAction(labels.toVideoAnalyze, 'video-analyze', {
        files: { detection_file: { file_id: fileId, filename: artifact.filename } },
        params: { task: 'ocr-classify' },
      }),
    ]
  }

  if (toolId === 'video-analyze' && /ocr_events\.classified\.json$/i.test(artifact.filename)) {
    // Classified events drive transcript correction with non-dialogue text excluded.
    return [
      buildArtifactAction(labels.toTranscriptCorrection, 'transcript-correction', {
        files: { ocr_events_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'subtitle-erase' && /erased\.(mp4|mov|mkv)$/i.test(artifact.filename)) {
    return [
      buildArtifactAction(labels.toMuxing, 'muxing', {
        files: { video_file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'm3u8-to-mp4' && /\.(mp4|mkv)$/i.test(artifact.filename)) {
    // The converted video drops straight into the downstream dubbing tools.
    return [
      buildArtifactAction(labels.toProbe, 'probe', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
      buildArtifactAction(labels.toTranscription, 'transcription', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
      buildArtifactAction(labels.toSeparation, 'separation', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  if (toolId === 'video-trim' && /\.(mp4|mkv)$/i.test(artifact.filename)) {
    // The trimmed clip is a fresh source for the rest of the pipeline.
    return [
      buildArtifactAction(labels.toProbe, 'probe', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
      buildArtifactAction(labels.toTranscription, 'transcription', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
      buildArtifactAction(labels.toSeparation, 'separation', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
  }

  return []
}

function buildSubtitleEraseCompare(
  toolId: string,
  job: AtomicJob,
  artifacts: ArtifactInfo[],
  getDownloadUrl: (filename: string) => string,
  labels: { compareTitle: string; compareOriginal: string; compareErased: string; quickMetrics: string },
  originalVideoUrl: string | null,
) {
  if (toolId !== 'subtitle-erase') return null
  const erased = artifacts.find(item => /erased\.(mp4|mov|mkv|webm)$/i.test(item.filename))
  if (!erased) return null

  const result = job.result ?? {}
  const sourceUrlFromResult = typeof result.source_url === 'string' ? result.source_url : null
  const sourceUrl = sourceUrlFromResult ?? originalVideoUrl
  const metricsRaw = (result.quick_metrics ?? result.metrics) as Record<string, unknown> | null | undefined
  const metrics = metricsRaw && typeof metricsRaw === 'object' ? metricsRaw : null

  return (
    <SubtitleEraseCompare
      labels={labels}
      sourceUrl={sourceUrl ?? null}
      erasedUrl={getDownloadUrl(erased.filename)}
      metrics={metrics}
    />
  )
}

function SubtitleEraseCompare({
  labels,
  sourceUrl,
  erasedUrl,
  metrics,
}: {
  labels: { compareTitle: string; compareOriginal: string; compareErased: string; quickMetrics: string }
  sourceUrl: string | null
  erasedUrl: string
  metrics: Record<string, unknown> | null
}) {
  const originalRef = useRef<HTMLVideoElement | null>(null)
  const erasedRef = useRef<HTMLVideoElement | null>(null)
  const [synced, setSynced] = useState(true)
  const syncingRef = useRef(false)

  useEffect(() => {
    if (!synced) return
    const original = originalRef.current
    const erased = erasedRef.current
    if (!original || !erased) return

    const mirror = (source: HTMLVideoElement, target: HTMLVideoElement, kind: 'play' | 'pause' | 'seek' | 'rate') => {
      if (syncingRef.current) return
      syncingRef.current = true
      try {
        if (kind === 'play' && target.paused) void target.play().catch(() => undefined)
        if (kind === 'pause' && !target.paused) target.pause()
        if (kind === 'seek') target.currentTime = source.currentTime
        if (kind === 'rate') target.playbackRate = source.playbackRate
      } finally {
        syncingRef.current = false
      }
    }

    const onPlayO = () => mirror(original, erased, 'play')
    const onPauseO = () => mirror(original, erased, 'pause')
    const onSeekO = () => mirror(original, erased, 'seek')
    const onRateO = () => mirror(original, erased, 'rate')
    const onPlayE = () => mirror(erased, original, 'play')
    const onPauseE = () => mirror(erased, original, 'pause')
    const onSeekE = () => mirror(erased, original, 'seek')
    const onRateE = () => mirror(erased, original, 'rate')

    original.addEventListener('play', onPlayO)
    original.addEventListener('pause', onPauseO)
    original.addEventListener('seeked', onSeekO)
    original.addEventListener('ratechange', onRateO)
    erased.addEventListener('play', onPlayE)
    erased.addEventListener('pause', onPauseE)
    erased.addEventListener('seeked', onSeekE)
    erased.addEventListener('ratechange', onRateE)

    return () => {
      original.removeEventListener('play', onPlayO)
      original.removeEventListener('pause', onPauseO)
      original.removeEventListener('seeked', onSeekO)
      original.removeEventListener('ratechange', onRateO)
      erased.removeEventListener('play', onPlayE)
      erased.removeEventListener('pause', onPauseE)
      erased.removeEventListener('seeked', onSeekE)
      erased.removeEventListener('ratechange', onRateE)
    }
  }, [synced, sourceUrl, erasedUrl])

  const handlePlayBoth = () => {
    const original = originalRef.current
    const erased = erasedRef.current
    if (original && erased) {
      original.currentTime = 0
      erased.currentTime = 0
      void original.play().catch(() => undefined)
      void erased.play().catch(() => undefined)
    }
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-700">{labels.compareTitle}</div>
        <div className="flex items-center gap-3">
          {sourceUrl && (
            <label className="inline-flex items-center gap-1.5 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={synced}
                onChange={event => setSynced(event.target.checked)}
                className="accent-blue-600"
              />
              <span>同步播放</span>
            </label>
          )}
          {sourceUrl && (
            <button
              type="button"
              onClick={handlePlayBoth}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 transition hover:bg-slate-100"
            >
              ▶ 同步重播
            </button>
          )}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs uppercase tracking-widest text-slate-400">{labels.compareOriginal}</div>
          {sourceUrl ? (
            <video ref={originalRef} controls className="w-full rounded-xl bg-black" src={sourceUrl} />
          ) : (
            <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-slate-300 text-xs text-slate-400">
              —
            </div>
          )}
        </div>
        <div>
          <div className="mb-1 text-xs uppercase tracking-widest text-slate-400">{labels.compareErased}</div>
          <video ref={erasedRef} controls className="w-full rounded-xl bg-black" src={erasedUrl} />
        </div>
      </div>
      {metrics && (
        <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-white px-3 py-2 text-xs text-slate-600 md:grid-cols-4">
          <div className="col-span-2 text-[11px] uppercase tracking-widest text-slate-400 md:col-span-4">
            {labels.quickMetrics}
          </div>
          {Object.entries(metrics).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-2">
              <span className="text-slate-400">{key}</span>
              <span className="font-mono text-slate-700">
                {typeof value === 'number'
                  ? Number.isFinite(value)
                    ? value.toFixed(3)
                    : String(value)
                  : typeof value === 'object' && value !== null
                    ? JSON.stringify(value)
                    : String(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function buildArtifactAction(label: string, targetToolId: string, payload: AtomicToolPrefill) {
  return { label, targetToolId, payload }
}

function buildSubtitleDetectPreview(
  toolId: string,
  job: AtomicJob,
  artifacts: ArtifactInfo[],
  getDownloadUrl: (filename: string) => string,
  originalVideoUrl: string | null,
  labels: SubtitleDetectPreviewLabels,
) {
  if (toolId !== 'subtitle-detect') return null
  if (job.status !== 'completed') return null

  const detectionArtifact = artifacts.find(item => /detection\.json$/i.test(item.filename))
  // Without detection.json there is nothing to draw on top of the video.
  if (!detectionArtifact) return null

  const keyframesArtifact = artifacts.find(item => /keyframes\.json$/i.test(item.filename))
  const result = (job.result ?? {}) as Record<string, unknown>
  const resultSource = typeof result.source_url === 'string' ? result.source_url : null
  // When the user lands on a historical job from the atomic tasks list, the
  // in-memory blob URL from the upload step is long gone. Fall back to the
  // dedicated backend route that streams the originally uploaded file by id.
  const sourceFileId =
    typeof result.source_file_id === 'string' && result.source_file_id.length > 0
      ? result.source_file_id
      : null
  const remoteFallback = sourceFileId ? `/api/atomic-tools/files/${sourceFileId}` : null
  const videoUrl = resultSource ?? originalVideoUrl ?? remoteFallback

  const videoMetaRaw = result.video_meta as Record<string, unknown> | undefined
  const videoMeta =
    videoMetaRaw && typeof videoMetaRaw === 'object'
      ? {
          width: Number(videoMetaRaw.width) || 0,
          height: Number(videoMetaRaw.height) || 0,
          fps: Number(videoMetaRaw.fps) || 0,
          total_frames: Number(videoMetaRaw.total_frames) || 0,
        }
      : null

  return (
    <SubtitleDetectPreview
      labels={labels}
      videoUrl={videoUrl ?? null}
      detectionUrl={getDownloadUrl(detectionArtifact.filename)}
      keyframesUrl={keyframesArtifact ? getDownloadUrl(keyframesArtifact.filename) : null}
      resolveKeyframeUrl={filename => getDownloadUrl(filename)}
      videoMeta={videoMeta}
    />
  )
}
