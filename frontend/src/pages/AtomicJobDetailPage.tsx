import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Download,
  ExternalLink,
  Eye,
  FileAudio2,
  FileImage,
  FileJson2,
  FileText,
  FileVideo2,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { atomicToolsApi } from '../api/atomic-tools'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ResultPanel, buildArtifactActions } from '../components/atomic-tools/ResultPanel'
import { CrossToolAction } from '../components/atomic-tools/CrossToolAction'
import { formatBytes } from '../lib/utils'
import { useI18n } from '../i18n/useI18n'
import type { ArtifactInfo } from '../types/atomic-tools'

export function AtomicJobDetailPage() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { t, formatDuration, formatRelativeTime } = useI18n()

  const { data: job } = useQuery({
    queryKey: ['atomic-tool-job-detail', jobId],
    queryFn: () => atomicToolsApi.getJobDetail(jobId),
    enabled: Boolean(jobId),
    refetchInterval: query => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 1000 : false
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => atomicToolsApi.deleteJob(jobId),
    onSuccess: () => navigate('/tools/jobs'),
  })

  const rerunMutation = useMutation({
    mutationFn: () => atomicToolsApi.rerunJob(jobId),
    onSuccess: nextJob => {
      queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] })
      navigate(`/tools/jobs/${nextJob.job_id}`)
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => atomicToolsApi.stopJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['atomic-tool-job-detail', jobId] })
      queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] })
    },
  })

  if (!job) {
    return (
      <PageContainer className={APP_CONTENT_MAX_WIDTH}>
        <div className="py-16 text-center text-sm text-[#9ca3af]">{t.common.loading}</div>
      </PageContainer>
    )
  }

  const canStop = job.status === 'pending' || job.status === 'running'

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/tools/jobs" className="mb-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-[#9ca3af] hover:text-[#374151]">
            <ArrowLeft size={13} />
            {t.atomicJobs.backToJobs}
          </Link>
          <h1 className="text-xl font-bold text-[#111827]">{job.tool_name}</h1>
          <p className="mt-1 font-mono text-xs text-[#9ca3af]">{job.job_id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/tools/${job.tool_id}`}
            className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-xs font-semibold text-[#3b5bdb] transition-all hover:bg-[#f0f3ff]"
          >
            <ExternalLink size={13} />
            {t.atomicJobs.openTool}
          </Link>
          <button
            type="button"
            onClick={() => rerunMutation.mutate()}
            className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-xs font-semibold text-[#374151] transition-all hover:bg-[#f9fafb]"
          >
            <RefreshCw size={13} />
            {t.atomicJobs.rerun}
          </button>
          {canStop ? (
            <button
              type="button"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-white px-3.5 py-2 text-xs font-semibold text-amber-700 transition-all hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <CircleStop size={13} />
              {t.atomicJobs.stop}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => {
              if (confirm(t.atomicJobs.deleteConfirm)) deleteMutation.mutate()
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-red-100 bg-white px-3.5 py-2 text-xs font-semibold text-red-500 transition-all hover:bg-red-50"
          >
            <Trash2 size={13} />
            {t.atomicJobs.delete}
          </button>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.status}</div>
          <StatusBadge status={job.status} />
        </div>
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.progress}</div>
          <div className="flex items-center gap-2">
            <ProgressBar value={job.progress_percent} size="sm" className="flex-1" />
            <span className="text-sm font-semibold tabular-nums text-[#374151]">{job.progress_percent.toFixed(0)}%</span>
          </div>
        </div>
        <Metric label={t.atomicJobs.columns.duration} value={formatDuration(job.elapsed_sec ?? undefined)} />
        <Metric label={t.atomicJobs.columns.createdAt} value={formatRelativeTime(job.created_at)} />
      </section>

      <section className="space-y-5">
        {/* Inputs — full width, compact chips so a single file doesn't stretch a tall empty card */}
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-[#374151]">{t.atomicJobs.sections.inputs}</h2>
          <div className="flex flex-wrap gap-2">
            {job.input_files.map(file => (
              <div
                key={file.file_id}
                className="flex max-w-md items-center gap-3 rounded-lg border border-[#f3f4f6] px-3 py-2.5"
              >
                <FileText size={16} className="shrink-0 text-[#9ca3af]" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-[#111827]">{file.filename}</div>
                  <div className="mt-0.5 text-xs text-[#9ca3af]">
                    {file.content_type} · {formatBytes(file.size_bytes)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Rich result preview (e.g. SubtitleDetectPreview): reuse the same
            ResultPanel as the live tool page so historical jobs opened from
            the atomic tasks list can still see the OCR overlay video. The
            flat artifacts list is suppressed here because the grouped
            ArtifactsPanel below covers the same data more thoughtfully. */}
        <ResultPanel
          toolId={job.tool_id}
          job={job}
          artifacts={job.artifacts}
          getDownloadUrl={filename =>
            job.artifacts.find(item => item.filename === filename)?.download_url ?? ''
          }
          originalVideoUrl={null}
          showArtifactsList={false}
        />

        {/* Outputs — grouped by purpose (primary / preview / diagnostic) so
            the user is not flooded with every keyframe and manifest. */}
        <ArtifactsPanel
          toolId={job.tool_id}
          artifacts={job.artifacts}
          translatedText={
            typeof job.result?.translated_text === 'string' ? job.result.translated_text : null
          }
          title={t.atomicJobs.sections.artifacts}
        />

        {/* Data — params + result are similar-height JSON, so they pair well side by side */}
        <div className="grid gap-5 xl:grid-cols-2">
          <JsonBlock title={t.atomicJobs.sections.params} value={job.params} />
          <JsonBlock title={t.atomicJobs.sections.result} value={job.result ?? {}} />
        </div>
      </section>
    </PageContainer>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{label}</div>
      <div className="text-sm font-semibold text-[#374151]">{value}</div>
    </div>
  )
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
      <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-[#374151]">{title}</h2>
      <pre className="max-h-[360px] overflow-auto rounded-lg border border-[#f3f4f6] bg-[#f8f9fa] p-3 text-xs leading-5 text-[#374151]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

// --- Artifact preview (inline expand), following the WorkflowNodeDrawer pattern ---

type PreviewKind = 'audio' | 'video' | 'image' | 'text'

type ArtifactPreview =
  | { kind: 'audio' | 'video' | 'image'; key: string; href: string }
  | { kind: 'text'; key: string; body: string | null; isLoading: boolean; error: string | null; isRaw: boolean }

type ArtifactCategory = 'primary' | 'preview' | 'diagnostic'

/**
 * Classify an artifact by its filename so we can group the (often noisy) flat
 * list into 3 buckets:
 *
 *   primary    — what downstream pipelines actually consume
 *                (detection.json / erased.mp4 / voice.wav / *.srt / segments.json …)
 *   preview    — visual aids the in-page preview already renders
 *                (kf_*.jpg / keyframes.json / annotated_*.jpg)
 *   diagnostic — reproducibility/debug breadcrumbs
 *                (*-manifest.json / *.log / *_debug.* / raw_*.*)
 *
 * Heuristic-only on purpose: the backend does not yet emit a `category` field
 * on ArtifactInfo, and shipping that would mean a schema change + per-adapter
 * migration. The rules below cover every artifact currently produced by the
 * adapters in src/translip/server/atomic_tools/adapters/. A future revision
 * can replace this with a server-supplied category without changing the UI.
 */
function classifyArtifact(artifact: ArtifactInfo): ArtifactCategory {
  const name = artifact.filename.toLowerCase()
  if (/^kf_\d+\./.test(name) || name === 'keyframes.json' || /^annotated[_-]/.test(name)) {
    return 'preview'
  }
  if (
    /-manifest\.json$/.test(name) ||
    /\.log$/.test(name) ||
    /^raw[_-]/.test(name) ||
    /_debug\./.test(name)
  ) {
    return 'diagnostic'
  }
  return 'primary'
}

const GROUP_ORDER: ArtifactCategory[] = ['primary', 'preview', 'diagnostic']

function ArtifactsPanel({
  toolId,
  artifacts,
  translatedText,
  title,
}: {
  toolId: string
  artifacts: ArtifactInfo[]
  translatedText: string | null
  title: string
}) {
  const { t } = useI18n()
  const [preview, setPreview] = useState<ArtifactPreview | null>(null)

  const grouped = useMemo(() => {
    const buckets: Record<ArtifactCategory, ArtifactInfo[]> = {
      primary: [],
      preview: [],
      diagnostic: [],
    }
    for (const artifact of artifacts) {
      buckets[classifyArtifact(artifact)].push(artifact)
    }
    return buckets
  }, [artifacts])

  async function togglePreview(artifact: ArtifactInfo, kind: PreviewKind) {
    const key = `${kind}:${artifact.filename}`
    if (preview?.key === key) {
      setPreview(null)
      return
    }
    if (kind !== 'text') {
      setPreview({ kind, key, href: artifact.download_url })
      return
    }
    setPreview({ kind: 'text', key, body: null, isLoading: true, error: null, isRaw: false })
    try {
      const response = await fetch(artifact.download_url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const text = await response.text()
      const formatted = formatTextArtifact(text, isJsonArtifact(artifact))
      setPreview({ kind: 'text', key, body: formatted.body, isLoading: false, error: null, isRaw: formatted.isRaw })
    } catch {
      setPreview({ kind: 'text', key, body: null, isLoading: false, error: t.atomicJobs.preview.loadFailed, isRaw: false })
    }
  }

  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
      <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-[#374151]">{title}</h2>
      {artifacts.length === 0 ? (
        <div className="text-sm text-[#9ca3af]">{t.common.notAvailable}</div>
      ) : (
        <div className="space-y-3">
          {GROUP_ORDER.map(category => {
            const items = grouped[category]
            if (items.length === 0) return null
            return (
              <ArtifactGroup
                key={category}
                category={category}
                artifacts={items}
                toolId={toolId}
                translatedText={translatedText}
                preview={preview}
                onPreview={togglePreview}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function ArtifactGroup({
  category,
  artifacts,
  toolId,
  translatedText,
  preview,
  onPreview,
}: {
  category: ArtifactCategory
  artifacts: ArtifactInfo[]
  toolId: string
  translatedText: string | null
  preview: ArtifactPreview | null
  onPreview: (artifact: ArtifactInfo, kind: PreviewKind) => void
}) {
  // Primary is the result the user actually came for: show it expanded. The
  // other two buckets are noisy by nature, so default them to collapsed so
  // the panel starts visually quiet.
  const [open, setOpen] = useState(category === 'primary')

  const groupCfg = useGroupCopy(category)

  return (
    <div className="overflow-hidden rounded-lg border border-[#f3f4f6]">
      <button
        type="button"
        onClick={() => setOpen(prev => !prev)}
        className="flex w-full items-center justify-between gap-3 bg-[#fafbfc] px-3 py-2 text-left transition-colors hover:bg-[#f3f4f6]"
      >
        <div className="flex items-center gap-2">
          {open ? (
            <ChevronDown size={13} className="text-[#9ca3af]" />
          ) : (
            <ChevronRight size={13} className="text-[#9ca3af]" />
          )}
          <span className={`text-xs font-semibold ${groupCfg.titleColor}`}>{groupCfg.title}</span>
          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-mono text-[#6b7280] ring-1 ring-inset ring-[#e5e7eb]">
            {artifacts.length}
          </span>
        </div>
        <span className="truncate text-[11px] text-[#9ca3af]">{groupCfg.hint}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-[#f3f4f6] p-2">
          {artifacts.map(artifact => (
            <ArtifactRow
              key={artifact.filename}
              artifact={artifact}
              toolId={toolId}
              translatedText={translatedText}
              preview={preview}
              onPreview={onPreview}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function useGroupCopy(category: ArtifactCategory) {
  const { t } = useI18n()
  if (category === 'primary') {
    return {
      title: t.atomicJobs.groups.primary.title,
      hint: t.atomicJobs.groups.primary.hint,
      titleColor: 'text-[#111827]',
    }
  }
  if (category === 'preview') {
    return {
      title: t.atomicJobs.groups.preview.title,
      hint: t.atomicJobs.groups.preview.hint,
      titleColor: 'text-[#4b5563]',
    }
  }
  return {
    title: t.atomicJobs.groups.diagnostic.title,
    hint: t.atomicJobs.groups.diagnostic.hint,
    titleColor: 'text-[#4b5563]',
  }
}

function ArtifactRow({
  artifact,
  toolId,
  translatedText,
  preview,
  onPreview,
}: {
  artifact: ArtifactInfo
  toolId: string
  translatedText: string | null
  preview: ArtifactPreview | null
  onPreview: (artifact: ArtifactInfo, kind: PreviewKind) => void
}) {
  const { t } = useI18n()
  const kind = detectPreviewKind(artifact.filename, artifact.content_type)
  const isOpen = kind !== null && preview?.key === `${kind}:${artifact.filename}`
  const crossActions = buildArtifactActions(toolId, artifact, translatedText, t.atomicTools.result)

  return (
    <div className="overflow-hidden rounded-lg border border-[#f3f4f6]">
      <div className="flex items-center justify-between gap-3 px-3 py-2.5">
        {kind ? (
          <button
            type="button"
            onClick={() => onPreview(artifact, kind)}
            className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
            title={t.atomicJobs.preview.preview}
          >
            <ArtifactIcon kind={kind} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-[#111827]">{artifact.filename}</div>
              <div className="mt-0.5 text-xs text-[#9ca3af]">
                {artifact.content_type} · {formatBytes(artifact.size_bytes)}
              </div>
            </div>
          </button>
        ) : (
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <ArtifactIcon kind={null} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-[#111827]">{artifact.filename}</div>
              <div className="mt-0.5 text-xs text-[#9ca3af]">{t.atomicJobs.preview.unavailable}</div>
            </div>
          </div>
        )}
        <div className="flex shrink-0 items-center gap-1">
          {kind && (
            <button
              type="button"
              onClick={() => onPreview(artifact, kind)}
              className="inline-flex items-center gap-1.5 rounded-md border border-[#e5e7eb] px-2.5 py-1.5 text-xs font-semibold text-[#3b5bdb] transition-all hover:bg-[#f0f3ff]"
            >
              {isOpen ? <ChevronDown size={13} /> : <Eye size={13} />}
              {isOpen ? t.atomicJobs.preview.collapse : t.atomicJobs.preview.preview}
            </button>
          )}
          <a
            href={artifact.download_url}
            download
            className="rounded-md p-1.5 text-[#9ca3af] transition-colors hover:bg-[#f3f4f6] hover:text-[#374151]"
            aria-label={`${t.atomicJobs.preview.download} ${artifact.filename}`}
            title={t.atomicJobs.preview.download}
          >
            <Download size={15} />
          </a>
        </div>
      </div>
      {crossActions.length > 0 && (
        <div className="flex flex-wrap gap-2 border-t border-[#f3f4f6] bg-[#fafbfc] px-3 py-2">
          {crossActions.map(action => (
            <CrossToolAction
              key={`${artifact.filename}-${action.targetToolId}-${action.label}`}
              label={action.label}
              targetToolId={action.targetToolId}
              payload={action.payload}
            />
          ))}
        </div>
      )}
      {isOpen && preview && <ArtifactPreviewPanel preview={preview} />}
    </div>
  )
}

function ArtifactIcon({ kind }: { kind: PreviewKind | null }) {
  if (kind === 'audio') return <FileAudio2 size={16} className="shrink-0 text-blue-500" />
  if (kind === 'video') return <FileVideo2 size={16} className="shrink-0 text-violet-500" />
  if (kind === 'image') return <FileImage size={16} className="shrink-0 text-amber-500" />
  if (kind === 'text') return <FileJson2 size={16} className="shrink-0 text-emerald-600" />
  return <FileText size={16} className="shrink-0 text-[#9ca3af]" />
}

function ArtifactPreviewPanel({ preview }: { preview: ArtifactPreview }) {
  const { t } = useI18n()

  if (preview.kind === 'text') {
    return (
      <div className="border-t border-slate-800 bg-slate-950">
        {preview.isRaw && (
          <div className="border-b border-slate-800 bg-slate-900 px-3 py-1.5 text-[10px] font-medium text-amber-300">
            {t.atomicJobs.preview.rawText}
          </div>
        )}
        {preview.isLoading && (
          <div className="flex items-center gap-2 px-3 py-4 text-xs text-slate-300">
            <Loader2 size={13} className="animate-spin" />
            {t.atomicJobs.preview.loading}
          </div>
        )}
        {preview.error && <div className="px-3 py-4 text-xs text-rose-300">{preview.error}</div>}
        {preview.body && <pre className="max-h-[420px] overflow-auto p-3 text-xs leading-5 text-slate-200">{preview.body}</pre>}
      </div>
    )
  }

  if (preview.kind === 'audio') {
    return (
      <div className="border-t border-[#f3f4f6] bg-[#f8f9fa] px-3 py-3">
        <audio controls preload="metadata" className="w-full" src={preview.href} />
      </div>
    )
  }

  if (preview.kind === 'video') {
    return (
      <div className="border-t border-[#f3f4f6] bg-[#0b1020] px-3 py-3">
        <video controls preload="metadata" className="mx-auto max-h-[420px] w-full rounded-lg" src={preview.href} />
      </div>
    )
  }

  return (
    <div className="flex justify-center border-t border-[#f3f4f6] bg-[#f8f9fa] px-3 py-3">
      <img alt="" className="max-h-[420px] max-w-full rounded-lg object-contain" src={preview.href} />
    </div>
  )
}

function detectPreviewKind(filename: string, contentType: string): PreviewKind | null {
  const ct = (contentType ?? '').toLowerCase()
  const name = filename.toLowerCase()
  if (ct.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(name)) return 'image'
  if (ct.startsWith('audio/') || /\.(wav|mp3|flac|m4a|aac|ogg)$/.test(name)) return 'audio'
  if (ct.startsWith('video/') || /\.(mp4|mov|mkv|webm)$/.test(name)) return 'video'
  if (
    ct.includes('json') ||
    ct.includes('subrip') ||
    ct.includes('xml') ||
    ct.includes('yaml') ||
    ct.startsWith('text/') ||
    /\.(json|srt|vtt|txt|md|csv|log|xml|ya?ml|ass)$/.test(name)
  ) {
    return 'text'
  }
  return null
}

function isJsonArtifact(artifact: ArtifactInfo) {
  return /\.json$/i.test(artifact.filename) || artifact.content_type.toLowerCase().includes('json')
}

function formatTextArtifact(text: string, asJson: boolean) {
  if (!asJson) return { body: text, isRaw: false }
  try {
    return { body: JSON.stringify(JSON.parse(text), null, 2), isRaw: false }
  } catch {
    return { body: text, isRaw: true }
  }
}
