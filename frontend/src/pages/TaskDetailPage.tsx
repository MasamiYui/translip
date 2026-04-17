import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Captions,
  Download,
  Eraser,
  Film,
  Headphones,
  Loader2,
  Mic,
  PlayCircle,
  RotateCcw,
  ScanText,
  Sparkles,
  Square,
  Trash2,
  Wand2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { subscribeToProgress } from '../api/progress'
import { PageContainer } from '../components/layout/PageContainer'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { WorkflowNodeDrawer } from '../components/workflow/WorkflowNodeDrawer'
import { useWorkflowGraph } from '../hooks/useWorkflowGraph'
import { useWorkflowRuntimeUpdates } from '../hooks/useWorkflowRuntimeUpdates'
import { useI18n } from '../i18n/useI18n'
import { getExportProfileLabel, getOutputIntentLabel, getQualityPresetLabel } from '../lib/taskPresentation'
import { formatBytes } from '../lib/utils'
import { resolveActiveStageId, resolveRerunStage } from './taskDetailSelection'
import type {
  Artifact,
  Task,
  TaskAssetEntry,
  TaskConfig,
  TaskDeliveryConfig,
  TaskExportBlocker,
  TaskExportProfile,
} from '../types'

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
  'task-g': ['task-g/', 'delivery/', 'preview/'],
}

const PROFILE_CONFIG: Record<
  TaskExportProfile,
  {
    subtitleMode: TaskDeliveryConfig['subtitle_mode']
    exportPreview: boolean
    exportDub: boolean
    videoLabel: string
    audioLabel: string
    description: string
  }
> = {
  dub_no_subtitles: {
    subtitleMode: 'none',
    exportPreview: false,
    exportDub: true,
    videoLabel: '原始视频',
    audioLabel: '正式配音音轨',
    description: '导出正式配音成片，不烧录英文字幕。',
  },
  bilingual_review: {
    subtitleMode: 'bilingual',
    exportPreview: false,
    exportDub: true,
    videoLabel: '原始视频',
    audioLabel: '正式配音音轨',
    description: '保留原视频画面并叠加中英双语字幕，适合审片。',
  },
  english_subtitle_burned: {
    subtitleMode: 'english_only',
    exportPreview: false,
    exportDub: true,
    videoLabel: '干净画面',
    audioLabel: '正式配音音轨',
    description: '优先使用干净画面并烧录英文字幕，适合正式分发。',
  },
  preview_only: {
    subtitleMode: 'none',
    exportPreview: true,
    exportDub: false,
    videoLabel: '原始视频',
    audioLabel: '预览混音音轨',
    description: '快速生成可看片预览，优先验证整体结果。',
  },
}

export function TaskDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { t, formatDuration, formatRelativeTime, getLanguageLabel, getStageLabel, locale } = useI18n()

  const [selectedNodeId, setSelectedNodeId] = useState<string | null | undefined>(undefined)
  const [rerunStage, setRerunStage] = useState<string | undefined>(undefined)
  const [isExportDrawerOpen, setExportDrawerOpen] = useState(false)
  const [exportProfile, setExportProfile] = useState<TaskExportProfile>('dub_no_subtitles')
  const [subtitleSource, setSubtitleSource] = useState<'ocr' | 'asr'>('ocr')
  const [fontFamily, setFontFamily] = useState('Noto Sans CJK SC')
  const [fontSize, setFontSize] = useState(0)
  const [subtitlePosition, setSubtitlePosition] = useState<'top' | 'bottom'>('bottom')
  const [marginV, setMarginV] = useState(0)
  const [subtitleColor, setSubtitleColor] = useState('#FFFFFF')
  const [outlineColor, setOutlineColor] = useState('#000000')
  const [outlineWidth, setOutlineWidth] = useState(2)
  const [subtitleBold, setSubtitleBold] = useState(false)
  const [previewDurationSec, setPreviewDurationSec] = useState(10)

  const { data: task, refetch } = useQuery({
    queryKey: ['task', id],
    queryFn: () => tasksApi.get(id!),
    enabled: Boolean(id),
    refetchInterval: query => {
      const current = query.state.data as Task | undefined
      return current?.status === 'running' || current?.status === 'pending' ? 3000 : false
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
    if (!id || !task || task.status !== 'running') {
      return
    }
    const unsubscribe = subscribeToProgress(id, event => {
      refetch()
      if (event.type === 'done') {
        queryClient.invalidateQueries({ queryKey: ['task-graph', id] })
        queryClient.invalidateQueries({ queryKey: ['artifacts', id] })
      }
    })
    return unsubscribe
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
    mutationFn: (fromStage: string) => tasksApi.rerun(id!, fromStage),
    onSuccess: newTask => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/tasks/${newTask.id}`)
    },
  })

  const previewMutation = useMutation({
    mutationFn: (payload: Parameters<typeof tasksApi.createSubtitlePreview>[1]) =>
      tasksApi.createSubtitlePreview(id!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', id] })
      queryClient.invalidateQueries({ queryKey: ['task', id] })
    },
  })

  const composeMutation = useMutation({
    mutationFn: (payload: Parameters<typeof tasksApi.composeDelivery>[1]) =>
      tasksApi.composeDelivery(id!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', id] })
      queryClient.invalidateQueries({ queryKey: ['task', id] })
    },
  })

  const artifacts: Artifact[] = artifactsData?.artifacts ?? []
  const activeStageId = resolveActiveStageId(selectedNodeId, task?.current_stage, graph)
  const effectiveRerunStage = resolveRerunStage(rerunStage, task?.current_stage, graph)
  const detailNode = selectedNodeId
    ? graph?.nodes.find(node => node.id === selectedNodeId) ?? null
    : null
  const detailStage = selectedNodeId && task
    ? task.stages.find(stage => stage.stage_name === selectedNodeId) ?? null
    : null
  const artifactStageId = selectedNodeId ?? activeStageId
  const artifactNode = graph?.nodes.find(node => node.id === artifactStageId) ?? null

  const selectedArtifacts = artifactNode
    ? artifacts.filter(artifact => isUserArtifact(artifact) && (ARTIFACT_PREFIX[artifactNode.id] ?? []).some(prefix => artifact.path.startsWith(prefix)))
    : []

  useEffect(() => {
    if (!task) {
      return
    }
    setExportProfile(resolveInitialProfile(task))
    setSubtitleSource(resolveInitialSubtitleSource(task))
    setFontFamily(task.delivery_config.subtitle_font ?? 'Noto Sans CJK SC')
    setFontSize(task.delivery_config.subtitle_font_size ?? 0)
    setSubtitlePosition(task.delivery_config.subtitle_position ?? 'bottom')
    setMarginV(task.delivery_config.subtitle_margin_v ?? 0)
    setSubtitleColor(task.delivery_config.subtitle_color ?? '#FFFFFF')
    setOutlineColor(task.delivery_config.subtitle_outline_color ?? '#000000')
    setOutlineWidth(task.delivery_config.subtitle_outline_width ?? 2)
    setSubtitleBold(Boolean(task.delivery_config.subtitle_bold))
    setPreviewDurationSec(task.delivery_config.subtitle_preview_duration_sec ?? 10)
  }, [task])

  const profileConfig = PROFILE_CONFIG[exportProfile]
  const subtitleOptions = useMemo(() => {
    if (!task) {
      return []
    }
    const options: Array<{ value: 'ocr' | 'asr'; label: string; path: string }> = []
    if (task.asset_summary.subtitles.ocr_translated.path) {
      options.push({ value: 'ocr', label: 'OCR 翻译字幕', path: task.asset_summary.subtitles.ocr_translated.path })
    }
    if (task.asset_summary.subtitles.asr_translated.path) {
      options.push({ value: 'asr', label: 'ASR 翻译字幕', path: task.asset_summary.subtitles.asr_translated.path })
    }
    return options
  }, [task])

  useEffect(() => {
    if (subtitleOptions.length === 0) {
      return
    }
    if (!subtitleOptions.some(option => option.value === subtitleSource)) {
      setSubtitleSource(subtitleOptions[0].value)
    }
  }, [subtitleOptions, subtitleSource])

  const selectedSubtitleOption = subtitleOptions.find(option => option.value === subtitleSource) ?? null
  const previewArtifact = artifacts.find(artifact => artifact.path.endsWith('subtitle-preview.mp4')) ?? null
  const exportFiles = task?.last_export_summary.files ?? []

  if (!task) {
    return (
      <PageContainer className="max-w-4xl py-20 text-center text-slate-400">
        <div className="text-lg">{t.taskDetail.loading}</div>
      </PageContainer>
    )
  }

  const readinessMessage = getReadinessMessage(task)
  const canOpenExportDrawer = task.export_readiness.status === 'ready' || task.export_readiness.status === 'exported'
  const canPreview = profileConfig.subtitleMode !== 'none' && Boolean(selectedSubtitleOption)
  const previewVideoPath = resolvePreviewVideoPath(task, exportProfile)

  function handlePreview() {
    if (!selectedSubtitleOption) {
      return
    }
    previewMutation.mutate({
      input_video_path: previewVideoPath,
      subtitle_path: selectedSubtitleOption.path,
      font_family: fontFamily,
      font_size: fontSize,
      primary_color: subtitleColor,
      outline_color: outlineColor,
      outline_width: outlineWidth,
      position: subtitlePosition,
      margin_v: marginV,
      bold: subtitleBold,
      duration_sec: previewDurationSec,
    })
  }

  function handleExport() {
    composeMutation.mutate({
      subtitle_mode: profileConfig.subtitleMode,
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
      bilingual_english_position: subtitlePosition,
      export_preview: profileConfig.exportPreview,
      export_dub: profileConfig.exportDub,
    })
  }

  function handleBlockerAction(blocker: TaskExportBlocker) {
    const stage = blockerActionToStage(blocker.action, effectiveRerunStage)
    if (!stage) {
      return
    }
    rerunMutation.mutate(stage)
  }

  return (
    <PageContainer className="max-w-6xl">
      <Link to="/tasks" className="mb-5 flex w-fit items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600">
        <ArrowLeft size={14} />
        {t.taskDetail.backToList}
      </Link>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{task.name}</h1>
              <div className="mt-1 font-mono text-xs text-slate-400">{task.id}</div>
            </div>
            <div className="flex items-center gap-2.5">
              <StatusBadge status={task.status} />
              <span className="border-l border-slate-200 pl-2.5 text-xs font-medium uppercase tracking-widest text-slate-400">
                {t.workflow.templates[templateId]}
              </span>
            </div>
          </div>
        </div>

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
          <div className="mt-5 grid gap-x-8 gap-y-3 md:grid-cols-2 xl:grid-cols-5">
            <MetaItem
              label={t.workflow.runtimeTitle}
              value={
                task.status === 'running'
                  ? t.taskDetail.runningFor(formatDuration(task.elapsed_sec))
                  : formatDuration(task.elapsed_sec)
              }
            />
            <MetaItem label={t.newTask.summary.direction} value={`${getLanguageLabel(task.source_lang)} → ${getLanguageLabel(task.target_lang)}`} />
            <MetaItem label="成品目标" value={getOutputIntentLabel(task.output_intent, locale)} />
            <MetaItem label="质量档位" value={getQualityPresetLabel(task.quality_preset, locale)} />
            <MetaItem
              label={t.taskDetail.currentStage('')}
              value={task.current_stage ? getStageLabel(task.current_stage as keyof typeof t.stages) : t.common.notAvailable}
            />
          </div>
        </div>

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

        <div className="border-b border-slate-100 px-7 py-6">
          <div className="mb-4 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            <Wand2 size={12} />
            导出区
          </div>
          <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-lg font-semibold text-slate-900">导出状态</div>
                    <div className="mt-1 text-sm leading-6 text-slate-600">{readinessMessage}</div>
                  </div>
                  <ReadinessPill status={task.export_readiness.status} />
                </div>

                <div className="mt-4 flex flex-wrap gap-3">
                  <QuickInfoChip label="推荐版本" value={getExportProfileLabel(task.export_readiness.recommended_profile, locale)} />
                  <QuickInfoChip label="当前意图" value={getOutputIntentLabel(task.output_intent, locale)} />
                  <QuickInfoChip label="上次导出" value={task.last_export_summary.status === 'exported' ? '已生成' : '尚未导出'} />
                </div>

                {task.export_readiness.blockers.length > 0 && (
                  <div className="mt-5 space-y-3">
                    {task.export_readiness.blockers.map(blocker => (
                      <div key={blocker.code} className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                        <div className="flex items-start gap-2">
                          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div>{blocker.message}</div>
                            <div className="mt-3">
                              <button
                                type="button"
                                onClick={() => handleBlockerAction(blocker)}
                                disabled={rerunMutation.isPending}
                                className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-800 transition-colors hover:bg-amber-100 disabled:opacity-60"
                              >
                                {rerunMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                                {blocker.action_label}
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className="mt-5 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => setExportDrawerOpen(true)}
                    disabled={!canOpenExportDrawer}
                    className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Wand2 size={16} />
                    导出成品
                  </button>
                  {task.last_export_summary.status === 'exported' && (
                    <span className="inline-flex items-center rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
                      最近一次导出时间：{task.last_export_summary.updated_at ? formatRelativeTime(task.last_export_summary.updated_at) : '刚刚'}
                    </span>
                  )}
                </div>
              </div>

              {(() => {
                const assetRows: Array<{ icon: LucideIcon; title: string; description: string; entry: TaskAssetEntry }> = [
                  { icon: Film, title: '原始视频', description: '所有任务的基础输入素材', entry: task.asset_summary.video.original },
                  { icon: Eraser, title: '干净画面', description: '英文字幕版会优先使用', entry: task.asset_summary.video.clean },
                  { icon: Mic, title: '正式配音音轨', description: '用于正式成片导出', entry: task.asset_summary.audio.dub },
                  { icon: Headphones, title: '预览混音音轨', description: '用于快速验证版导出', entry: task.asset_summary.audio.preview },
                  { icon: ScanText, title: 'OCR 英文字幕', description: '适合画面原有中文字幕翻译', entry: task.asset_summary.subtitles.ocr_translated },
                  { icon: Captions, title: 'ASR 英文字幕', description: '适合语音转字幕链路', entry: task.asset_summary.subtitles.asr_translated },
                ]
                const readyCount = assetRows.filter(r => r.entry.status === 'available').length
                return (
                  <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
                      <div className="text-sm font-semibold text-slate-900">成品素材清单</div>
                      <div className="text-xs text-slate-500">
                        已就绪{' '}
                        <span className="font-semibold text-emerald-600">{readyCount}</span>
                        <span className="text-slate-400"> / {assetRows.length}</span>
                      </div>
                    </div>
                    <ul className="divide-y divide-slate-100">
                      {assetRows.map(row => (
                        <AssetStatusRow
                          key={row.title}
                          icon={row.icon}
                          title={row.title}
                          description={row.description}
                          entry={row.entry}
                        />
                      ))}
                    </ul>
                  </div>
                )
              })()}
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="text-sm font-semibold text-slate-900">最近导出结果</div>
                {exportFiles.length === 0 ? (
                  <div className="mt-3 text-sm text-slate-500">当前还没有导出的成品文件。</div>
                ) : (
                  <div className="mt-4 space-y-3">
                    {exportFiles.map(file => (
                      <a
                        key={file.path}
                        href={getArtifactHref(task.id, file.path)}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-700 transition-colors hover:bg-slate-50"
                      >
                        <div>
                          <div className="font-medium text-slate-900">{file.label}</div>
                          <div className="mt-1 text-xs text-slate-500">{file.path}</div>
                        </div>
                        <Download size={16} />
                      </a>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 text-sm font-semibold text-slate-900">运行控制</div>
                <div className="space-y-3">
                  <label className="block">
                    <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">重跑起点</div>
                    <select
                      value={rerunStage ?? effectiveRerunStage}
                      onChange={event => setRerunStage(event.target.value)}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      {(graph?.nodes ?? task.stages.map(stage => ({ id: stage.stage_name }))).map(node => (
                        <option key={node.id} value={node.id}>
                          {getStageLabel(node.id as keyof typeof t.stages)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => rerunMutation.mutate(effectiveRerunStage)}
                      disabled={rerunMutation.isPending || task.status === 'running'}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
                    >
                      {rerunMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                      从所选阶段重跑
                    </button>
                    <button
                      type="button"
                      onClick={() => stopMutation.mutate()}
                      disabled={stopMutation.isPending || task.status !== 'running'}
                      className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100 disabled:opacity-50"
                    >
                      <Square size={14} />
                      停止任务
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (confirm('确认删除这个任务吗？')) {
                          deleteMutation.mutate()
                        }
                      }}
                      disabled={deleteMutation.isPending || task.status === 'running'}
                      className="inline-flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 transition-colors hover:bg-rose-100 disabled:opacity-50"
                    >
                      <Trash2 size={14} />
                      删除任务
                    </button>
                  </div>
                </div>
              </div>

              {selectedArtifacts.length > 0 && (
                <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="mb-3 text-sm font-semibold text-slate-900">当前阶段产物</div>
                  <div className="space-y-2">
                    {selectedArtifacts.slice(0, 5).map(artifact => (
                      <div key={artifact.path} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm">
                        <div className="min-w-0">
                          <div className="truncate text-slate-900">{artifact.path}</div>
                          <div className="text-xs text-slate-500">{formatBytes(artifact.size_bytes)}</div>
                        </div>
                        <a
                          href={getArtifactHref(task.id, artifact.path)}
                          className="ml-3 shrink-0 text-slate-400 transition-colors hover:text-slate-700"
                        >
                          <Download size={14} />
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <WorkflowNodeDrawer
        node={detailNode}
        stage={detailStage}
        artifacts={selectedArtifacts}
        taskId={task.id}
        onClose={() => setSelectedNodeId(null)}
      />

      {isExportDrawerOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30 bg-slate-950/25"
            onClick={() => setExportDrawerOpen(false)}
            aria-label="关闭导出抽屉"
          />
          <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-[0_24px_80px_-38px_rgba(15,23,42,0.65)]">
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">导出向导</div>
                <h2 className="mt-2 text-xl font-semibold text-slate-900">导出成品</h2>
                <div className="mt-1 text-sm text-slate-500">保持现有视觉风格，只把复杂配置收敛到这里。</div>
              </div>
              <button
                type="button"
                onClick={() => setExportDrawerOpen(false)}
                className="rounded-md border border-slate-200 p-1.5 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
              >
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
              <DrawerSection title="1. 选择导出版本">
                <div className="grid gap-3 md:grid-cols-2">
                  {(Object.keys(PROFILE_CONFIG) as TaskExportProfile[]).map(profile => (
                    <button
                      key={profile}
                      type="button"
                      onClick={() => setExportProfile(profile)}
                      className={`rounded-xl border p-4 text-left transition-colors ${
                        exportProfile === profile
                          ? 'border-blue-500 bg-blue-50 shadow-sm'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className="text-sm font-semibold text-slate-900">{getExportProfileLabel(profile, locale)}</div>
                      <div className="mt-1.5 text-sm leading-6 text-slate-600">{PROFILE_CONFIG[profile].description}</div>
                    </button>
                  ))}
                </div>
              </DrawerSection>

              <DrawerSection title="2. 确认素材来源">
                <div className="grid gap-4 md:grid-cols-2">
                  <SourceSummaryCard
                    title="视频底板"
                    value={profileConfig.videoLabel}
                    entry={resolveVideoEntry(task, exportProfile)}
                  />
                  <SourceSummaryCard
                    title="音轨来源"
                    value={profileConfig.audioLabel}
                    entry={resolveAudioEntry(task, exportProfile)}
                  />
                </div>

                {profileConfig.subtitleMode !== 'none' ? (
                  <label className="block">
                    <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">英文字幕来源</div>
                    <select
                      value={subtitleSource}
                      onChange={event => setSubtitleSource(event.target.value as 'ocr' | 'asr')}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                    >
                      {subtitleOptions.map(option => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    {selectedSubtitleOption && (
                      <div className="mt-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                        当前字幕文件：{selectedSubtitleOption.path}
                      </div>
                    )}
                  </label>
                ) : (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-500">
                    当前导出版本不需要烧录英文字幕。
                  </div>
                )}
              </DrawerSection>

              <DrawerSection title="3. 选择字幕样式">
                {profileConfig.subtitleMode === 'none' ? (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-500">
                    当前导出版本不需要字幕样式配置。
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2">
                    <DrawerField label="字体">
                      <input
                        value={fontFamily}
                        onChange={event => setFontFamily(event.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                    <DrawerField label="字号（0=自动推荐）">
                      <input
                        type="number"
                        value={fontSize}
                        onChange={event => setFontSize(Number(event.target.value) || 0)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                    <DrawerField label="字幕位置">
                      <select
                        value={subtitlePosition}
                        onChange={event => setSubtitlePosition(event.target.value as 'top' | 'bottom')}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      >
                        <option value="top">顶部</option>
                        <option value="bottom">底部</option>
                      </select>
                    </DrawerField>
                    <DrawerField label="垂直边距（0=自动推荐）">
                      <input
                        type="number"
                        value={marginV}
                        onChange={event => setMarginV(Number(event.target.value) || 0)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                    <DrawerField label="字幕颜色">
                      <input
                        value={subtitleColor}
                        onChange={event => setSubtitleColor(event.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                    <DrawerField label="描边颜色">
                      <input
                        value={outlineColor}
                        onChange={event => setOutlineColor(event.target.value)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                    <DrawerField label="描边宽度">
                      <input
                        type="number"
                        step="0.5"
                        value={outlineWidth}
                        onChange={event => setOutlineWidth(Number(event.target.value) || 0)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                    <DrawerField label="字幕加粗">
                      <label className="flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700">
                        <input
                          type="checkbox"
                          checked={subtitleBold}
                          onChange={event => setSubtitleBold(event.target.checked)}
                        />
                        使用加粗字幕
                      </label>
                    </DrawerField>
                  </div>
                )}
              </DrawerSection>

              <DrawerSection title="4. 预览并导出">
                <div className="space-y-4">
                  {profileConfig.subtitleMode !== 'none' && (
                    <DrawerField label="预览时长（秒）">
                      <input
                        type="number"
                        min="3"
                        max="30"
                        value={previewDurationSec}
                        onChange={event => setPreviewDurationSec(Number(event.target.value) || 10)}
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
                      />
                    </DrawerField>
                  )}

                  <div className="flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={handlePreview}
                      disabled={!canPreview || previewMutation.isPending}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
                    >
                      {previewMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <PlayCircle size={15} />}
                      生成字幕预览
                    </button>
                    <button
                      type="button"
                      onClick={handleExport}
                      disabled={composeMutation.isPending}
                      className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
                    >
                      {composeMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                      导出成品
                    </button>
                  </div>

                  {previewArtifact && (
                    <a
                      href={getArtifactHref(task.id, previewArtifact.path)}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-700 transition-colors hover:bg-slate-50"
                    >
                      <div>
                        <div className="font-medium text-slate-900">最新字幕预览</div>
                        <div className="mt-1 text-xs text-slate-500">{previewArtifact.path}</div>
                      </div>
                      <Download size={16} />
                    </a>
                  )}

                  {(previewMutation.isError || composeMutation.isError) && (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {previewMutation.isError
                        ? '字幕预览生成失败，请检查素材来源和样式配置。'
                        : '成品导出失败，请检查任务产物是否完整。'}
                    </div>
                  )}
                </div>
              </DrawerSection>
            </div>
          </aside>
        </>
      )}
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

function resolveInitialProfile(task: Task): TaskExportProfile {
  if (task.last_export_summary.profile) {
    return task.last_export_summary.profile
  }
  const mode = task.delivery_config.subtitle_mode
  if (mode === 'english_only') {
    return 'english_subtitle_burned'
  }
  if (mode === 'bilingual') {
    return 'bilingual_review'
  }
  if (task.output_intent === 'fast_validation') {
    return 'preview_only'
  }
  return task.export_readiness.recommended_profile
}

function resolveInitialSubtitleSource(task: Task): 'ocr' | 'asr' {
  if (task.delivery_config.subtitle_render_source) {
    return task.delivery_config.subtitle_render_source
  }
  if (task.asset_summary.subtitles.ocr_translated.path) {
    return 'ocr'
  }
  return 'asr'
}

function resolvePreviewVideoPath(task: Task, profile: TaskExportProfile): string {
  if (profile === 'english_subtitle_burned' && task.asset_summary.video.clean.path) {
    return resolveTaskPath(task, task.asset_summary.video.clean.path)
  }
  return task.input_path
}

function resolveTaskPath(task: Task, path: string): string {
  if (path.startsWith('/')) {
    return path
  }
  return `${task.output_root.replace(/\/$/, '')}/${path}`
}

function resolveVideoEntry(task: Task, profile: TaskExportProfile): TaskAssetEntry {
  if (profile === 'english_subtitle_burned') {
    return task.asset_summary.video.clean
  }
  return task.asset_summary.video.original
}

function resolveAudioEntry(task: Task, profile: TaskExportProfile): TaskAssetEntry {
  if (profile === 'preview_only') {
    return task.asset_summary.audio.preview
  }
  return task.asset_summary.audio.dub
}

function blockerActionToStage(action: string, fallbackStage: string): string | null {
  switch (action) {
    case 'rerun_subtitle_erase':
      return 'subtitle-erase'
    case 'rerun_subtitle_generation':
      return 'task-c'
    case 'rerun_audio_pipeline':
      return 'task-e'
    case 'rerun_task':
      return fallbackStage
    default:
      return null
  }
}

function getReadinessMessage(task: Task): string {
  switch (task.export_readiness.summary) {
    case 'ready_for_export':
      return '当前素材已经满足推荐导出条件，可以直接生成成品视频。'
    case 'already_exported':
      return '当前任务已经导出过成品，你可以继续调整样式并重新导出。'
    case 'task_running':
      return '任务仍在运行中，关键素材生成完毕后这里会自动开放导出。'
    case 'task_failed':
      return '任务尚未成功完成，请先处理失败阶段后再导出。'
    default:
      return '当前还缺少导出所需素材，请先补齐对应链路。'
  }
}

function getArtifactHref(taskId: string, path: string): string {
  return `/api/tasks/${taskId}/artifacts/${path}`
}

function isUserArtifact(artifact: Artifact) {
  return !artifact.path.endsWith('.ass') && !artifact.path.includes('.delivery-subtitles/')
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-slate-700">{value}</div>
    </div>
  )
}

function ReadinessPill({ status }: { status: Task['export_readiness']['status'] }) {
  const cls = {
    ready: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    exported: 'border-blue-200 bg-blue-50 text-blue-700',
    blocked: 'border-amber-200 bg-amber-50 text-amber-700',
    not_ready: 'border-slate-200 bg-slate-100 text-slate-600',
    exporting: 'border-blue-200 bg-blue-50 text-blue-700',
  }[status]

  const label = {
    ready: '可直接导出',
    exported: '已导出',
    blocked: '存在阻塞',
    not_ready: '等待素材',
    exporting: '导出中',
  }[status]

  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

function QuickInfoChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="whitespace-nowrap rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm">
      <span className="text-slate-400">{label}：</span>
      <span className="font-medium text-slate-700">{value}</span>
    </div>
  )
}

function AssetStatusRow({
  icon: Icon,
  title,
  description,
  entry,
}: {
  icon: LucideIcon
  title: string
  description: string
  entry: TaskAssetEntry
}) {
  const isAvailable = entry.status === 'available'
  return (
    <li className="flex items-center gap-4 px-5 py-3.5">
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
          isAvailable ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-50 text-slate-400'
        }`}
      >
        <Icon size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-medium text-slate-900">{title}</span>
            <span className="truncate text-xs text-slate-400">· {description}</span>
          </div>
          <AssetStatusPill status={entry.status} />
        </div>
        <div
          className="mt-1 truncate font-mono text-[11px] text-slate-400"
          title={entry.path ?? undefined}
        >
          {entry.path ?? '当前还没有生成对应文件'}
        </div>
      </div>
    </li>
  )
}

function AssetStatusPill({ status }: { status: TaskAssetEntry['status'] }) {
  const cls = {
    available: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    missing: 'border-slate-200 bg-slate-100 text-slate-600',
    building: 'border-blue-200 bg-blue-50 text-blue-700',
    failed: 'border-rose-200 bg-rose-50 text-rose-700',
  }[status]

  const label = {
    available: '已就绪',
    missing: '缺失',
    building: '生成中',
    failed: '失败',
  }[status]

  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {label}
    </span>
  )
}

function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      {children}
    </section>
  )
}

function DrawerField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      {children}
    </label>
  )
}

function SourceSummaryCard({
  title,
  value,
  entry,
}: {
  title: string
  value: string
  entry: TaskAssetEntry
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-slate-900">{title}</div>
        <AssetStatusPill status={entry.status} />
      </div>
      <div className="mt-2 text-sm text-slate-700">{value}</div>
      <div className="mt-2 text-xs text-slate-500">{entry.path ?? '当前还没有对应素材'}</div>
    </div>
  )
}
