import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Clock3, Download, FileAudio2, FileJson2, FileText, Layers3, Loader2, PlayCircle, X } from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import { formatBytes } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import { StatusBadge } from '../shared/StatusBadge'
import { ProgressBar } from '../shared/ProgressBar'
import type { Artifact, TaskStage, WorkflowGraphNode } from '../../types'

type ArtifactPreview =
  | {
      kind: 'audio'
      key: string
      title: string
      href: string
    }
  | {
      kind: 'json'
      key: string
      title: string
      body: string | null
      isLoading: boolean
      error: string | null
      isRaw: boolean
    }

interface WorkflowNodeDrawerProps {
  node: WorkflowGraphNode | null
  stage?: TaskStage | null
  artifacts?: Artifact[]
  taskId?: string
  onClose: () => void
}

export function WorkflowNodeDrawer({ node, stage, artifacts = [], taskId, onClose }: WorkflowNodeDrawerProps) {
  const { t, formatDuration, getStageLabel } = useI18n()
  const [preview, setPreview] = useState<ArtifactPreview | null>(null)

  async function handleLoadManifest() {
    if (!node || !taskId) {
      return
    }
    const key = `manifest:${node.id}`
    if (preview?.key === key) {
      setPreview(null)
      return
    }
    const title = `${getStageLabel(node.id as keyof typeof t.stages)} Manifest`
    setPreview({
      kind: 'json',
      key,
      title,
      body: null,
      isLoading: true,
      error: null,
      isRaw: false,
    })
    try {
      const payload = await tasksApi.getStageManifest(taskId, node.id)
      setPreview({
        kind: 'json',
        key,
        title,
        body: JSON.stringify(payload, null, 2),
        isLoading: false,
        error: null,
        isRaw: false,
      })
    } catch {
      setPreview({
        kind: 'json',
        key,
        title,
        body: null,
        isLoading: false,
        error: t.workflow.drawer.manifestLoadFailed,
        isRaw: false,
      })
    }
  }

  function handlePlayArtifact(artifact: Artifact) {
    if (!taskId) {
      return
    }
    const title = getArtifactFileName(artifact)
    const key = `audio:${artifact.path}`
    setPreview(current =>
      current?.key === key
        ? null
        : {
            kind: 'audio',
            key,
            title,
            href: getArtifactPreviewHref(taskId, artifact.path),
          },
    )
  }

  async function handleViewJsonArtifact(artifact: Artifact) {
    if (!taskId) {
      return
    }
    const title = getArtifactFileName(artifact)
    const key = `json:${artifact.path}`
    if (preview?.key === key) {
      setPreview(null)
      return
    }
    setPreview({
      kind: 'json',
      key,
      title,
      body: null,
      isLoading: true,
      error: null,
      isRaw: false,
    })
    try {
      const response = await fetch(getArtifactPreviewHref(taskId, artifact.path))
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const text = await response.text()
      const formatted = formatJsonArtifactText(text)
      setPreview({
        kind: 'json',
        key,
        title,
        body: formatted.body,
        isLoading: false,
        error: null,
        isRaw: formatted.isRaw,
      })
    } catch {
      setPreview({
        kind: 'json',
        key,
        title,
        body: null,
        isLoading: false,
        error: t.workflow.drawer.jsonLoadFailed,
        isRaw: false,
      })
    }
  }

  return (
    <AnimatePresence>
      {node && (
        <>
          <motion.button
            type="button"
            className="fixed inset-0 z-30 bg-slate-950/20 backdrop-blur-[1px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-slate-200 bg-white"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 260, damping: 28 }}
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                  {t.workflow.drawer.title}
                </div>
                <h3 className="mt-2 text-lg font-semibold text-slate-900">
                  {getStageLabel(node.id as keyof typeof t.stages)}
                </h3>
                <div className="mt-1 text-xs text-slate-500">{node.id}</div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-slate-200 p-1.5 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
                aria-label={t.workflow.drawer.close}
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              {/* Status + required strip */}
              <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
                <StatusBadge status={node.status} />
                <span className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
                  {node.required ? t.workflow.required : t.workflow.optional}
                </span>
              </div>

              {/* Group + Duration */}
              <div className="grid grid-cols-2 divide-x divide-slate-100 border-b border-slate-100">
                <div className="px-5 py-4">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                    <Layers3 size={12} />
                    {t.workflow.drawer.group}
                  </div>
                  <div className="mt-1.5 text-sm font-medium text-slate-700">{t.workflow.lanes[node.group]}</div>
                </div>
                <div className="px-5 py-4">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                    <Clock3 size={12} />
                    {t.workflow.drawer.duration}
                  </div>
                  <div className="mt-1.5 text-sm font-medium text-slate-700">{formatDuration(stage?.elapsed_sec ?? node.elapsed_sec)}</div>
                </div>
              </div>

              {/* Progress */}
              <div className="border-b border-slate-100 px-5 py-4">
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="text-slate-500">{t.workflow.drawer.progress}</span>
                  <span className="font-semibold tabular-nums text-slate-900">{node.progress_percent.toFixed(0)}%</span>
                </div>
                <ProgressBar value={node.progress_percent} size="lg" />
              </div>

              {/* Current step */}
              {(stage?.current_step || node.current_step) && (
                <div className="border-b border-slate-100 px-5 py-4">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                    {t.workflow.drawer.currentStep}
                  </div>
                  <div className="mt-1.5 text-sm text-slate-700">{stage?.current_step ?? node.current_step}</div>
                </div>
              )}

              {/* Error */}
              {(stage?.error_message || node.error_message) && (
                <div className="border-b border-slate-100 border-l-2 border-l-rose-400 bg-rose-50 px-5 py-4">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-rose-600">
                    <AlertTriangle size={12} />
                    {t.workflow.drawer.error}
                  </div>
                  <div className="mt-1.5 text-sm text-rose-700">{stage?.error_message ?? node.error_message}</div>
                </div>
              )}

              {/* Artifacts */}
              <div className="px-5 py-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                    {t.workflow.drawer.artifacts}
                  </div>
                  {taskId && (
                    <button
                      type="button"
                      onClick={handleLoadManifest}
                      disabled={preview?.kind === 'json' && preview.key === `manifest:${node.id}` && preview.isLoading}
                      className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-60"
                    >
                      {preview?.kind === 'json' && preview.key === `manifest:${node.id}` && preview.isLoading ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <FileJson2 size={12} />
                      )}
                      {t.workflow.drawer.viewManifest}
                    </button>
                  )}
                </div>

                {artifacts.length === 0 ? (
                  <div className="text-sm text-slate-400">{t.workflow.drawer.noArtifacts}</div>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {artifacts.map(artifact => (
                      <div key={artifact.path} className="py-2.5 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex min-w-0 items-center gap-2.5">
                            <ArtifactIcon artifact={artifact} />
                            <div className="min-w-0">
                              <div className="truncate font-medium text-slate-700">{getArtifactFileName(artifact)}</div>
                              <div className="text-xs text-slate-400">{formatBytes(artifact.size_bytes)}</div>
                            </div>
                          </div>
                          {taskId && (
                            <div className="ml-3 flex shrink-0 items-center gap-1">
                              {isAudioArtifact(artifact) && (
                                <button
                                  type="button"
                                  onClick={() => handlePlayArtifact(artifact)}
                                  className="rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                                  aria-label={`${t.workflow.drawer.play} ${getArtifactFileName(artifact)}`}
                                  title={`${t.workflow.drawer.play} ${getArtifactFileName(artifact)}`}
                                >
                                  <PlayCircle size={14} />
                                </button>
                              )}
                              {isJsonArtifact(artifact) && (
                                <button
                                  type="button"
                                  onClick={() => handleViewJsonArtifact(artifact)}
                                  className="rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                                  aria-label={`${t.workflow.drawer.view} ${getArtifactFileName(artifact)}`}
                                  title={`${t.workflow.drawer.view} ${getArtifactFileName(artifact)}`}
                                >
                                  <FileJson2 size={14} />
                                </button>
                              )}
                              <a
                                href={`/api/tasks/${taskId}/artifacts/${artifact.path}`}
                                download
                                className="rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                                aria-label={`${t.workflow.drawer.download} ${getArtifactFileName(artifact)}`}
                                title={`${t.workflow.drawer.download} ${getArtifactFileName(artifact)}`}
                              >
                                <Download size={14} />
                              </a>
                            </div>
                          )}
                        </div>
                        {preview && isPreviewForArtifact(preview, artifact) && (
                          <ArtifactPreviewPanel preview={preview} invalidJsonLabel={t.workflow.drawer.jsonInvalid} loadingLabel={t.workflow.drawer.loadingPreview} />
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {preview?.key.startsWith('manifest:') && (
                  <div className="mt-3">
                    <ArtifactPreviewPanel preview={preview} invalidJsonLabel={t.workflow.drawer.jsonInvalid} loadingLabel={t.workflow.drawer.loadingPreview} />
                  </div>
                )}
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function ArtifactIcon({ artifact }: { artifact: Artifact }) {
  if (isAudioArtifact(artifact)) {
    return <FileAudio2 size={15} className="shrink-0 text-blue-500" />
  }
  if (isJsonArtifact(artifact)) {
    return <FileJson2 size={15} className="shrink-0 text-emerald-600" />
  }
  return <FileText size={15} className="shrink-0 text-slate-400" />
}

function ArtifactPreviewPanel({
  preview,
  invalidJsonLabel,
  loadingLabel,
}: {
  preview: ArtifactPreview
  invalidJsonLabel: string
  loadingLabel: string
}) {
  if (preview.kind === 'audio') {
    return (
      <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
        <audio controls preload="metadata" className="h-9 w-full" src={preview.href} />
      </div>
    )
  }

  return (
    <div className="mt-2 overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
      <div className="flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-900 px-3 py-2">
        <div className="min-w-0 truncate text-xs font-medium text-slate-200">{preview.title}</div>
        {preview.isRaw && <div className="shrink-0 text-[10px] font-medium text-amber-300">{invalidJsonLabel}</div>}
      </div>
      {preview.isLoading && (
        <div className="flex items-center gap-2 px-3 py-4 text-xs text-slate-300">
          <Loader2 size={13} className="animate-spin" />
          {loadingLabel}
        </div>
      )}
      {preview.error && <div className="px-3 py-4 text-xs text-rose-300">{preview.error}</div>}
      {preview.body && <pre className="max-h-80 overflow-auto p-3 text-xs leading-5 text-slate-200">{preview.body}</pre>}
    </div>
  )
}

function getArtifactFileName(artifact: Artifact) {
  return artifact.path.split('/').pop() ?? artifact.path
}

function getArtifactPreviewHref(taskId: string, artifactPath: string) {
  return `/api/tasks/${taskId}/artifacts/${artifactPath}?preview=1`
}

function isPreviewForArtifact(preview: ArtifactPreview | null, artifact: Artifact) {
  return preview?.key === `audio:${artifact.path}` || preview?.key === `json:${artifact.path}`
}

function isAudioArtifact(artifact: Artifact) {
  return /\.(wav|mp3|flac|m4a|aac|ogg)$/i.test(artifact.path)
}

function isJsonArtifact(artifact: Artifact) {
  return /\.json$/i.test(artifact.path)
}

function formatJsonArtifactText(text: string) {
  try {
    return {
      body: JSON.stringify(JSON.parse(text), null, 2),
      isRaw: false,
    }
  } catch {
    return {
      body: text,
      isRaw: true,
    }
  }
}
