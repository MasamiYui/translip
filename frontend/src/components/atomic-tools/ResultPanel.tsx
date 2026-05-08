import { Download, FileText } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import { CrossToolAction } from './CrossToolAction'
import type { AtomicToolPrefill } from '../../lib/atomicToolPrefill'
import type { ArtifactInfo, AtomicJob } from '../../types/atomic-tools'

interface ResultPanelProps {
  toolId: string
  job: AtomicJob | null
  artifacts: ArtifactInfo[]
  getDownloadUrl: (filename: string) => string
}

export function ResultPanel({ toolId, job, artifacts, getDownloadUrl }: ResultPanelProps) {
  const { t } = useI18n()
  if (!job) return null

  const translatedText =
    typeof job.result?.translated_text === 'string' ? job.result.translated_text : null

  const sideBySide = buildSubtitleEraseCompare(toolId, job, artifacts, getDownloadUrl, {
    compareTitle: t.atomicTools.result.compareTitle,
    compareOriginal: t.atomicTools.result.compareOriginal,
    compareErased: t.atomicTools.result.compareErased,
    quickMetrics: t.atomicTools.result.quickMetrics,
  })

  return (
    <section className="space-y-4 rounded-3xl border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-900">{t.atomicTools.result.title}</h3>
        <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{job.status}</div>
      </div>

      {job.result && (
        <div className="rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-200">
          <pre className="overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(job.result, null, 2)}
          </pre>
        </div>
      )}

      {translatedText && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
            <FileText size={16} />
            {t.atomicTools.result.translatedText}
          </div>
          <p className="whitespace-pre-wrap text-sm leading-6 text-slate-600">{translatedText}</p>
          <div className="mt-3">
            <CrossToolAction
              label={t.atomicTools.result.toTts}
              targetToolId="tts"
              payload={{ text: translatedText }}
            />
          </div>
        </div>
      )}

      {sideBySide}

      <div className="grid gap-4 md:grid-cols-2">
        {artifacts.map(artifact => (
          <div key={artifact.filename} className="rounded-2xl border border-slate-200 p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-slate-900">{artifact.filename}</div>
                <div className="text-xs text-slate-500">{artifact.content_type}</div>
              </div>
              <a
                href={getDownloadUrl(artifact.filename)}
                className="inline-flex items-center gap-1 text-sm font-medium text-blue-600"
              >
                <Download size={16} />
                {t.atomicTools.actions.download}
              </a>
            </div>

            {isAudioFile(artifact.filename, artifact.content_type) && (
              <audio controls className="w-full" src={getDownloadUrl(artifact.filename)} />
            )}

            {isVideoFile(artifact.filename, artifact.content_type) && (
              <video controls className="w-full rounded-xl" src={getDownloadUrl(artifact.filename)} />
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              {buildArtifactActions(toolId, artifact, translatedText, t.atomicTools.result).map(action => (
                <CrossToolAction
                  key={`${artifact.filename}-${action.targetToolId}-${action.label}`}
                  label={action.label}
                  targetToolId={action.targetToolId}
                  payload={action.payload}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function isAudioFile(filename: string, contentType: string) {
  return contentType.startsWith('audio/') || /\.(wav|mp3|flac|m4a|aac|ogg)$/i.test(filename)
}

function isVideoFile(filename: string, contentType: string) {
  return contentType.startsWith('video/') || /\.(mp4|mov|mkv|webm)$/i.test(filename)
}

function buildArtifactActions(
  toolId: string,
  artifact: ArtifactInfo,
  translatedText: string | null,
  labels: {
    toTts: string
    toTranscription: string
    toMixing: string
    toTranslation: string
    toMuxing: string
    toSubtitleErase: string
  },
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
    return [
      buildArtifactAction(labels.toTranslation, 'translation', {
        files: { file: { file_id: fileId, filename: artifact.filename } },
      }),
    ]
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

  if (toolId === 'subtitle-erase' && /erased\.(mp4|mov|mkv)$/i.test(artifact.filename)) {
    return [
      buildArtifactAction(labels.toMuxing, 'muxing', {
        files: { video_file: { file_id: fileId, filename: artifact.filename } },
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
) {
  if (toolId !== 'subtitle-erase') return null
  const erased = artifacts.find(item => /erased\.(mp4|mov|mkv|webm)$/i.test(item.filename))
  if (!erased) return null

  const result = job.result ?? {}
  const sourceUrl = typeof result.source_url === 'string' ? result.source_url : null
  const metrics = result.quick_metrics as Record<string, unknown> | null | undefined

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 text-sm font-medium text-slate-700">{labels.compareTitle}</div>
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs uppercase tracking-widest text-slate-400">{labels.compareOriginal}</div>
          {sourceUrl ? (
            <video controls className="w-full rounded-xl" src={sourceUrl} />
          ) : (
            <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-slate-300 text-xs text-slate-400">
              —
            </div>
          )}
        </div>
        <div>
          <div className="mb-1 text-xs uppercase tracking-widest text-slate-400">{labels.compareErased}</div>
          <video controls className="w-full rounded-xl" src={getDownloadUrl(erased.filename)} />
        </div>
      </div>
      {metrics && typeof metrics === 'object' && (
        <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-white px-3 py-2 text-xs text-slate-600 md:grid-cols-4">
          <div className="col-span-2 text-[11px] uppercase tracking-widest text-slate-400 md:col-span-4">
            {labels.quickMetrics}
          </div>
          {Object.entries(metrics).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-2">
              <span className="text-slate-400">{key}</span>
              <span className="font-mono text-slate-700">
                {typeof value === 'number' ? value.toFixed(3) : String(value)}
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
