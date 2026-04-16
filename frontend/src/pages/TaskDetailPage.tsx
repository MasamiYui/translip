import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, PlayCircle, RotateCcw, Sparkles, Square, Trash2, Wand2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { PageContainer } from '../components/layout/PageContainer'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { WorkflowNodeDrawer } from '../components/workflow/WorkflowNodeDrawer'
import { useWorkflowGraph } from '../hooks/useWorkflowGraph'
import { useWorkflowRuntimeUpdates } from '../hooks/useWorkflowRuntimeUpdates'
import { formatBytes } from '../lib/utils'
import { subscribeToProgress } from '../api/progress'
import type { Artifact, Task, TaskConfig } from '../types'
import { useI18n } from '../i18n/useI18n'
import { resolveActiveStageId, resolveRerunStage } from './taskDetailSelection'

const ARTIFACT_PREFIX: Record<string, string[]> = {
  stage1: ['stage1/', 'voice/', 'background/'],
  'ocr-detect': ['ocr-detect/'],
  'task-a': ['task-a/voice/', 'task-a/'],
  'task-b': ['task-b/voice/', 'task-b/'],
  'task-c': ['task-c/voice/', 'task-c/'],
  'ocr-translate': ['ocr-translate/'],
  'task-d': ['task-d/'],
  'task-e': ['task-e/voice/', 'task-e/'],
  'subtitle-erase': ['subtitle-erase/'],
  'task-g': ['task-g/', 'delivery/'],
}

export function TaskDetailPage() {
  const { t, formatDuration, getStageLabel } = useI18n()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedNodeId, setSelectedNodeId] = useState<string | null | undefined>(undefined)
  const [rerunStage, setRerunStage] = useState<string | undefined>(undefined)
  const [subtitleMode, setSubtitleMode] = useState<'none' | 'chinese_only' | 'english_only' | 'bilingual'>('none')
  const [subtitleSource, setSubtitleSource] = useState<'ocr' | 'asr'>('ocr')
  const [fontFamily, setFontFamily] = useState('Noto Sans')
  const [fontSize, setFontSize] = useState(0)
  const [subtitlePosition, setSubtitlePosition] = useState<'top' | 'bottom'>('bottom')
  const [marginV, setMarginV] = useState(0)
  const [subtitleColor, setSubtitleColor] = useState('#FFFFFF')
  const [outlineColor, setOutlineColor] = useState('#000000')
  const [outlineWidth, setOutlineWidth] = useState(2)
  const [subtitleBold, setSubtitleBold] = useState(false)
  const [previewPathOverride, setPreviewPathOverride] = useState<string>('')

  const { data: task, refetch } = useQuery({
    queryKey: ['task', id],
    queryFn: () => tasksApi.get(id!),
    refetchInterval: (query) => {
      const data = query.state.data as Task | undefined
      return data?.status === 'running' || data?.status === 'pending' ? 3000 : false
    },
  })

  const templateId = normalizeTemplateId(task?.config.template)
  const { graph } = useWorkflowGraph(id ?? '', Boolean(id))
  useWorkflowRuntimeUpdates(id, task?.status === 'running')

  const { data: artifactsData } = useQuery({
    queryKey: ['artifacts', id],
    queryFn: () => tasksApi.listArtifacts(id!),
    enabled: Boolean(id),
    refetchInterval: task?.status === 'running' ? 4000 : false,
  })

  useEffect(() => {
    if (!id || !task) return
    if (task.status !== 'running') return
    const unsub = subscribeToProgress(id, event => {
      refetch()
      if (event.type === 'done') {
        queryClient.invalidateQueries({ queryKey: ['task-graph', id] })
        queryClient.invalidateQueries({ queryKey: ['artifacts', id] })
      }
    })
    return unsub
  }, [id, queryClient, refetch, task])

  const stopMutation = useMutation({
    mutationFn: () => tasksApi.stop(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', id] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => tasksApi.delete(id!),
    onSuccess: () => navigate('/tasks'),
  })

  const rerunMutation = useMutation({
    mutationFn: () => tasksApi.rerun(id!, effectiveRerunStage),
    onSuccess: newTask => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/tasks/${newTask.id}`)
    },
  })

  const previewMutation = useMutation({
    mutationFn: (payload: Parameters<typeof tasksApi.createSubtitlePreview>[1]) => tasksApi.createSubtitlePreview(id!, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['artifacts', id] }),
  })

  const composeMutation = useMutation({
    mutationFn: (payload: Parameters<typeof tasksApi.composeDelivery>[1]) => tasksApi.composeDelivery(id!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', id] })
      queryClient.invalidateQueries({ queryKey: ['task', id] })
    },
  })

  const elapsedSec = task?.elapsed_sec
  const artifacts: Artifact[] = artifactsData?.artifacts ?? []
  const activeStageId = resolveActiveStageId(selectedNodeId, task?.current_stage, graph)
  const effectiveRerunStage = resolveRerunStage(rerunStage, task?.current_stage, graph)
  const selectedNode = graph?.nodes.find(node => node.id === activeStageId) ?? null
  const selectedStage = activeStageId && task
    ? task.stages.find(stage => stage.stage_name === activeStageId) ?? null
    : null
  const isUserArtifact = (a: Artifact) => !a.path.endsWith('.ass') && !a.path.includes('.delivery-subtitles/')
  const selectedArtifacts = selectedNode
    ? artifacts.filter(artifact => (ARTIFACT_PREFIX[selectedNode.id] ?? []).some(prefix => artifact.path.startsWith(prefix)) && isUserArtifact(artifact))
    : []

  const deliveryPolicy = [
    task?.config.video_source,
    task?.config.audio_source,
    task?.config.subtitle_source,
  ].filter(Boolean).join(' · ')

  const preferredSubtitlePath = useMemo(() => {
    const targetLang = task?.target_lang ?? 'en'
    const candidates = subtitleSource === 'ocr'
      ? [
          'ocr-translate/ocr_subtitles.en.srt',
          `ocr-translate/ocr_subtitles.${targetLang}.srt`,
        ]
      : [
          `task-c/voice/translation.${targetLang}.srt`,
          `task-c/translation.${targetLang}.srt`,
        ]
    return artifacts.find(artifact => candidates.some(candidate => artifact.path.endsWith(candidate)))?.path ?? ''
  }, [artifacts, subtitleSource, task?.target_lang])

  const previewTargetPath = previewPathOverride || preferredSubtitlePath
  const deliveryConfig = task?.delivery_config ?? {}

  const previewVideoArtifact = useMemo(
    () => artifacts.find(artifact => artifact.path.endsWith('subtitle-preview.mp4')) ?? null,
    [artifacts],
  )

  const previewFiles = artifacts.filter(artifact => isUserArtifact(artifact) && (artifact.path.startsWith('task-g/') || artifact.path.startsWith('delivery/'))).slice(0, 4)
  const finalVideoArtifacts = previewFiles.filter(artifact => artifact.suffix === '.mp4')

  useEffect(() => {
    if (!task) return
    setSubtitleMode((deliveryConfig.subtitle_mode as typeof subtitleMode | undefined) ?? 'none')
    setSubtitleSource((deliveryConfig.subtitle_render_source as typeof subtitleSource | undefined) ?? 'ocr')
    setFontFamily(deliveryConfig.subtitle_font ?? 'Noto Sans')
    setFontSize(deliveryConfig.subtitle_font_size ?? 0)
    setSubtitlePosition((deliveryConfig.subtitle_position as typeof subtitlePosition | undefined) ?? 'bottom')
    setMarginV(deliveryConfig.subtitle_margin_v ?? 0)
    setSubtitleColor(deliveryConfig.subtitle_color ?? '#FFFFFF')
    setOutlineColor(deliveryConfig.subtitle_outline_color ?? '#000000')
    setOutlineWidth(deliveryConfig.subtitle_outline_width ?? 2)
    setSubtitleBold(Boolean(deliveryConfig.subtitle_bold))
  }, [
    task?.id,
    deliveryConfig.subtitle_bold,
    deliveryConfig.subtitle_color,
    deliveryConfig.subtitle_font,
    deliveryConfig.subtitle_font_size,
    deliveryConfig.subtitle_margin_v,
    deliveryConfig.subtitle_mode,
    deliveryConfig.subtitle_outline_color,
    deliveryConfig.subtitle_outline_width,
    deliveryConfig.subtitle_position,
    deliveryConfig.subtitle_render_source,
  ])

  if (!task) {
    return (
      <PageContainer className="max-w-4xl py-20 text-center text-slate-400">
        <div className="text-lg">{t.taskDetail.loading}</div>
      </PageContainer>
    )
  }

  return (
    <PageContainer className="max-w-6xl">
      {/* Back link */}
      <Link to="/tasks" className="mb-5 flex w-fit items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600">
        <ArrowLeft size={14} />
        {t.taskDetail.backToList}
      </Link>

      {/* Unified panel */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">

        {/* ── Title section ── */}
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{task.name}</h1>
              <div className="mt-1 font-mono text-xs text-slate-400">{task.id}</div>
            </div>
            <div className="flex items-center gap-2.5">
              <StatusBadge status={task.status} />
              <span className="border-l border-slate-200 pl-2.5 text-xs font-medium text-slate-400 uppercase tracking-widest">
                {t.workflow.templates[templateId]}
              </span>
            </div>
          </div>
        </div>

        {/* ── Progress + meta section ── */}
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="mb-4 flex items-baseline gap-3">
            <span className="text-4xl font-bold tabular-nums text-slate-900">
              {task.overall_progress.toFixed(0)}%
            </span>
            <span className="text-sm text-slate-400">{t.taskDetail.overallProgress}</span>
          </div>
          <ProgressBar
            value={task.overall_progress}
            size="lg"
            color={
              task.status === 'succeeded'
                ? 'bg-emerald-500'
                : task.status === 'partial_success'
                  ? 'bg-amber-500'
                  : task.status === 'failed'
                    ? 'bg-rose-500'
                    : 'bg-sky-500'
            }
          />
          {task.error_message && (
            <div className="mt-4 border-l-2 border-rose-400 bg-rose-50 py-2.5 pl-4 pr-4 text-sm text-rose-700">
              {task.error_message}
            </div>
          )}
          <div className="mt-5 flex flex-wrap gap-x-8 gap-y-3">
            <MetaItem
              label={t.workflow.runtimeTitle}
              value={
                task.status === 'running'
                  ? t.taskDetail.runningFor(formatDuration(elapsedSec))
                  : formatDuration(task.elapsed_sec)
              }
            />
            <MetaItem label={t.newTask.summary.direction} value={`${task.source_lang} → ${task.target_lang}`} />
            <MetaItem label={t.newTask.summary.template} value={t.workflow.templates[templateId]} />
            <MetaItem label={t.newTask.summary.deliveryPolicy} value={deliveryPolicy || t.common.notAvailable} />
            {task.current_stage && (
              <MetaItem
                label={t.taskDetail.currentStage('')}
                value={selectedNode ? getStageLabel(selectedNode.id as keyof typeof t.stages) : getStageLabel((task.current_stage) as keyof typeof t.stages)}
              />
            )}
          </div>
        </div>

        {/* ── Pipeline graph section ── */}
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            <Sparkles size={12} />
            {t.workflow.runtimeTitle}
          </div>
          {graph ? (
            <PipelineGraph
              graph={graph}
              activeStage={activeStageId ?? undefined}
              onStageClick={nodeId => {
                setSelectedNodeId(nodeId)
                setRerunStage(nodeId)
              }}
              showLegend
            />
          ) : (
            <PipelineGraph
              stages={task.stages}
              templateId={templateId}
              activeStage={activeStageId ?? undefined}
              onStageClick={nodeId => {
                setSelectedNodeId(nodeId)
                setRerunStage(nodeId)
              }}
              showLegend
            />
          )}
        </div>

        {/* ── Delivery composer ── */}
        <div className="border-b border-slate-100 px-7 py-6">
          <div className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            <Wand2 size={12} />
            Delivery Composer
          </div>
          <div className="grid gap-6 lg:grid-cols-[1.25fr_0.95fr]">
            <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-5 shadow-sm">
              <div className="grid gap-4 md:grid-cols-2">
                <ComposerField label="字幕模式">
                  <select value={subtitleMode} onChange={event => setSubtitleMode(event.target.value as typeof subtitleMode)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="none">不压字幕</option>
                    <option value="chinese_only">仅中文</option>
                    <option value="english_only">仅英文（擦中文）</option>
                    <option value="bilingual">中英双语</option>
                  </select>
                </ComposerField>
                <ComposerField label="英文字幕来源">
                  <select value={subtitleSource} onChange={event => setSubtitleSource(event.target.value as typeof subtitleSource)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="ocr">OCR 翻译</option>
                    <option value="asr">ASR 翻译</option>
                  </select>
                </ComposerField>
                <ComposerField label="字体">
                  <input value={fontFamily} onChange={event => setFontFamily(event.target.value)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
                <ComposerField label="字号（0=自动）">
                  <input value={fontSize} onChange={event => setFontSize(Number(event.target.value) || 0)} type="number" className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
                <ComposerField label="位置">
                  <select value={subtitlePosition} onChange={event => setSubtitlePosition(event.target.value as typeof subtitlePosition)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                    <option value="bottom">底部</option>
                    <option value="top">顶部</option>
                  </select>
                </ComposerField>
                <ComposerField label="垂直边距（0=自动）">
                  <input value={marginV} onChange={event => setMarginV(Number(event.target.value) || 0)} type="number" className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
                <ComposerField label="字幕颜色">
                  <input value={subtitleColor} onChange={event => setSubtitleColor(event.target.value)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
                <ComposerField label="描边颜色">
                  <input value={outlineColor} onChange={event => setOutlineColor(event.target.value)} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
                <ComposerField label="描边宽度">
                  <input value={outlineWidth} onChange={event => setOutlineWidth(Number(event.target.value) || 2)} type="number" className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
                <ComposerField label="字幕路径预览（可留空）">
                  <input value={previewPathOverride} onChange={event => setPreviewPathOverride(event.target.value)} placeholder={preferredSubtitlePath || '自动从产物推断'} className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                </ComposerField>
              </div>
              <label className="mt-4 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={subtitleBold} onChange={event => setSubtitleBold(event.target.checked)} />
                加粗字幕
              </label>
              <div className="mt-3 space-y-2 text-xs text-slate-500">
                <StatusBadge status={previewMutation.isSuccess ? 'succeeded' : previewMutation.isError ? 'failed' : previewMutation.isPending ? 'running' : 'pending'} size="sm" />
                <StatusBadge status={composeMutation.isSuccess ? 'succeeded' : composeMutation.isError ? 'failed' : composeMutation.isPending ? 'running' : 'pending'} size="sm" />
                {preferredSubtitlePath ? <div>自动识别字幕：{preferredSubtitlePath}</div> : <div>当前未识别到可预览字幕文件。</div>}
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  onClick={() => previewMutation.mutate({
                    input_video_path: task.input_path,
                    subtitle_path: previewTargetPath,
                    font_family: fontFamily,
                    font_size: fontSize,
                    primary_color: subtitleColor,
                    outline_color: outlineColor,
                    outline_width: outlineWidth,
                    position: subtitlePosition,
                    margin_v: marginV,
                    bold: subtitleBold,
                    duration_sec: 10,
                  })}
                  disabled={!previewTargetPath || previewMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-sm font-medium text-sky-700 transition hover:bg-sky-100 disabled:opacity-50"
                >
                  <PlayCircle size={16} />
                  {previewMutation.isPending ? '预览生成中…' : '生成字幕预览'}
                </button>
                <button
                  onClick={() => composeMutation.mutate({
                    subtitle_mode: subtitleMode,
                    subtitle_source: subtitleSource,
                    font_family: fontFamily,
                    font_size: fontSize,
                    primary_color: subtitleColor,
                    outline_color: outlineColor,
                    outline_width: outlineWidth,
                    position: subtitlePosition,
                    margin_v: marginV,
                    bold: subtitleBold,
                    bilingual_chinese_position: 'bottom',
                    bilingual_english_position: 'top',
                    export_preview: true,
                    export_dub: true,
                  })}
                  disabled={composeMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:opacity-50"
                >
                  <Sparkles size={16} />
                  {composeMutation.isPending ? '成品生成中…' : '生成成品视频'}
                </button>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 text-sm font-semibold text-slate-900">预览与导出结果</div>
              {previewVideoArtifact ? (
                <video controls className="mb-4 w-full rounded-xl border border-slate-200 bg-black" src={`/api/tasks/${task.id}/artifacts/${previewVideoArtifact.path}`} />
              ) : (
                <div className="mb-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-400">生成字幕预览后，这里会直接播放结果。</div>
              )}
              <div className="space-y-2">
                {finalVideoArtifacts.map(artifact => (
                  <a key={artifact.path} href={`/api/tasks/${task.id}/artifacts/${artifact.path}`} className="flex items-center justify-between rounded-xl border border-slate-100 px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-50">
                    <span className="truncate">{artifact.path.split('/').pop()}</span>
                    <span className="ml-3 shrink-0 text-xs text-slate-400">{formatBytes(artifact.size_bytes)}</span>
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Artifacts + Actions section ── */}
        <div className="grid sm:grid-cols-2 sm:divide-x divide-y sm:divide-y-0 divide-slate-100">
          {/* Delivery Artifacts */}
          <div className="px-7 py-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
              Delivery Artifacts
            </div>
            {previewFiles.length === 0 ? (
              <div className="text-sm text-slate-400">{t.workflow.drawer.noArtifacts}</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {previewFiles.map(artifact => (
                  <div key={artifact.path} className="flex items-center justify-between py-2.5 text-sm">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-700">{artifact.path.split('/').pop()}</div>
                      <div className="text-xs text-slate-400">{formatBytes(artifact.size_bytes)}</div>
                    </div>
                    <a
                      href={`/api/tasks/${task.id}/artifacts/${artifact.path}`}
                      download
                      className="ml-3 shrink-0 rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                    >
                      <Download size={14} />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="px-7 py-5">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
              {t.taskDetail.actions}
            </div>
            <div className="flex flex-wrap gap-2.5">
              <div className="flex items-center gap-2">
                <select
                  value={effectiveRerunStage}
                  onChange={event => setRerunStage(event.target.value)}
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-300"
                >
                  {task.stages.map(stage => (
                    <option key={stage.stage_name} value={stage.stage_name}>
                      {getStageLabel(stage.stage_name as keyof typeof t.stages)}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => rerunMutation.mutate()}
                  disabled={rerunMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded-md border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100 disabled:opacity-50"
                >
                  <RotateCcw size={13} />
                  {t.taskDetail.rerunFromStage}
                </button>
              </div>

              {(task.status === 'running' || task.status === 'pending') && (
                <button
                  onClick={() => stopMutation.mutate()}
                  className="inline-flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100"
                >
                  <Square size={13} />
                  {t.taskDetail.stopTask}
                </button>
              )}

              <button
                onClick={() => {
                  if (confirm(t.taskDetail.deleteConfirm)) deleteMutation.mutate()
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-700 transition-colors hover:bg-rose-100"
              >
                <Trash2 size={13} />
                {t.taskDetail.deleteTask}
              </button>
            </div>
          </div>
        </div>

      </div>

      <WorkflowNodeDrawer
        node={selectedNode}
        stage={selectedStage}
        artifacts={selectedArtifacts}
        taskId={task.id}
        onClose={() => setSelectedNodeId(null)}
      />
    </PageContainer>
  )
}

function normalizeTemplateId(value: unknown): TaskConfig['template'] {
  if (
    value === 'asr-dub-basic' ||
    value === 'asr-dub+ocr-subs' ||
    value === 'asr-dub+ocr-subs+erase'
  ) {
    return value
  }
  return 'asr-dub-basic'
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-slate-700">{value}</div>
    </div>
  )
}

function ComposerField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      {children}
    </label>
  )
}
