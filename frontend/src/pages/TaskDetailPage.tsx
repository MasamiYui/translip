import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
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
  ListChecks,
  Loader2,
  Mic,
  Mic2,
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
import { DubbingReviewDrawer } from '../components/dubbing-review/DubbingReviewDrawer'
import { SpeakerReviewDrawer } from '../components/speaker-review/SpeakerReviewDrawer'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { WorkflowNodeDrawer } from '../components/workflow/WorkflowNodeDrawer'
import { useWorkflowGraph } from '../hooks/useWorkflowGraph'
import { useWorkflowRuntimeUpdates } from '../hooks/useWorkflowRuntimeUpdates'
import { useI18n } from '../i18n/useI18n'
import { getExportProfileLabel, getOutputIntentLabel, getQualityPresetLabel } from '../lib/taskPresentation'
import { resolveActiveStageId, resolveRerunStage } from './taskDetailSelection'
import type {
  Artifact,
  BilingualExportStrategy,
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
  'asr-ocr-correct': ['asr-ocr-correct/voice/', 'asr-ocr-correct/'],
  'task-b': ['task-b/voice/', 'task-b/'],
  'task-c': ['task-c/voice/', 'task-c/'],
  'ocr-translate': ['ocr-translate/'],
  'task-d': ['task-d/'],
  'task-e': ['task-e/voice/', 'task-e/'],
  'subtitle-erase': ['subtitle-erase/'],
  'task-g': ['task-g/', 'delivery/', 'preview/'],
}

const DOWNLOAD_ICON_BUTTON_CLASS =
  'inline-flex h-5 w-5 shrink-0 items-center justify-center text-slate-400 transition-colors hover:text-slate-600 group-hover:text-slate-600'

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
    exportPreview: true,
    exportDub: false,
    videoLabel: '原始视频',
    audioLabel: '配音+背景混音音轨',
    description: '导出含背景声的正式配音成片，不烧录英文字幕。',
  },
  bilingual_review: {
    subtitleMode: 'bilingual',
    exportPreview: true,
    exportDub: false,
    videoLabel: '原始视频',
    audioLabel: '配音+背景混音音轨',
    description: '保留原视频画面、背景声并叠加中英双语字幕，适合审片。',
  },
  english_subtitle_burned: {
    subtitleMode: 'english_only',
    exportPreview: true,
    exportDub: false,
    videoLabel: '干净画面',
    audioLabel: '配音+背景混音音轨',
    description: '优先使用干净画面、混音音轨并烧录英文字幕，适合正式分发。',
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
  const [isDubbingReviewOpen, setDubbingReviewOpen] = useState(false)
  const [isSpeakerReviewOpen, setSpeakerReviewOpen] = useState(false)
  const [showProfileOverrides, setShowProfileOverrides] = useState(false)
  const [exportProfile, setExportProfile] = useState<TaskExportProfile>('dub_no_subtitles')
  const [subtitleSource, setSubtitleSource] = useState<'ocr' | 'asr'>('ocr')
  const [bilingualExportStrategy, setBilingualExportStrategy] = useState<BilingualExportStrategy>('auto_standard_bilingual')
  const [fontFamily, setFontFamily] = useState('Noto Sans CJK SC')
  const [fontSize, setFontSize] = useState(0)
  const [subtitlePosition, setSubtitlePosition] = useState<'top' | 'bottom'>('bottom')
  const [marginV, setMarginV] = useState(0)
  const [subtitleColor, setSubtitleColor] = useState('#FFFFFF')
  const [outlineColor, setOutlineColor] = useState('#000000')
  const [outlineWidth, setOutlineWidth] = useState(2)
  const [subtitleBold, setSubtitleBold] = useState(false)
  const [previewDurationSec, setPreviewDurationSec] = useState(10)
  const initializedDeliveryTaskIdRef = useRef<string | null>(null)

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
    const taskChanged = initializedDeliveryTaskIdRef.current !== task.id
    if (!taskChanged && isExportDrawerOpen) {
      return
    }
    initializedDeliveryTaskIdRef.current = task.id
    setExportProfile(resolveInitialProfile(task))
    setShowProfileOverrides(false)
    setSubtitleSource(resolveInitialSubtitleSource(task))
    setBilingualExportStrategy(resolveInitialBilingualStrategy(task))
    setFontFamily(task.delivery_config.subtitle_font ?? 'Noto Sans CJK SC')
    setFontSize(task.delivery_config.subtitle_font_size ?? 0)
    setSubtitlePosition(task.delivery_config.subtitle_position ?? 'bottom')
    setMarginV(task.delivery_config.subtitle_margin_v ?? 0)
    setSubtitleColor(task.delivery_config.subtitle_color ?? '#FFFFFF')
    setOutlineColor(task.delivery_config.subtitle_outline_color ?? '#000000')
    setOutlineWidth(task.delivery_config.subtitle_outline_width ?? 2)
    setSubtitleBold(Boolean(task.delivery_config.subtitle_bold))
    setPreviewDurationSec(task.delivery_config.subtitle_preview_duration_sec ?? 10)
  }, [isExportDrawerOpen, task])

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
  const effectiveBilingualExportStrategy = resolveEffectiveBilingualStrategy(task, exportProfile, bilingualExportStrategy)
  const shouldShowHardSubtitleWarning = shouldWarnAboutHardSubtitles(task, exportProfile)
  const canUseCleanRebuildStrategy = task.asset_summary.video.clean.status === 'available'
  const lastExportStrategyLabel = resolveLastExportStrategyLabel(task)
  const correctionSummary = task.transcription_correction_summary
  const canPreview = profileConfig.subtitleMode !== 'none' && Boolean(selectedSubtitleOption)
  const previewVideoPath = resolvePreviewVideoPath(task, exportProfile, effectiveBilingualExportStrategy)

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
      bilingual_export_strategy: effectiveBilingualExportStrategy,
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

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
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

          {/* 流水线图：全宽 */}
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

          {/* 运行控制：图下方横排一行 */}
          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">重跑起点</span>
              <select
                value={rerunStage ?? effectiveRerunStage}
                onChange={event => setRerunStage(event.target.value)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm"
              >
                {(graph?.nodes ?? task.stages.map(stage => ({ id: stage.stage_name }))).map(node => (
                  <option key={node.id} value={node.id}>
                    {getStageLabel(node.id as keyof typeof t.stages)}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={() => rerunMutation.mutate(effectiveRerunStage)}
              disabled={rerunMutation.isPending || task.status === 'running'}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
            >
              {rerunMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
              从所选阶段重跑
            </button>
            <button
              type="button"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending || task.status !== 'running'}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-50 disabled:opacity-50"
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
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-rose-600 transition-colors hover:bg-rose-50 disabled:opacity-50"
            >
              <Trash2 size={14} />
              删除任务
            </button>
          </div>
        </div>

        {correctionSummary?.status === 'available' && (
          <div className="border-b border-slate-100 px-7 py-5">
            <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
              <ScanText size={12} />
              台词校正
            </div>
            <div className="flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 font-medium text-emerald-700">
                已校正 {correctionSummary.corrected_count} 段
              </span>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                保留 ASR {correctionSummary.kept_asr_count} 段
              </span>
              <span className="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-700">
                {correctionSummary.review_count} 段建议复核
              </span>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">
                OCR 漏配 {correctionSummary.ocr_only_count} 条
              </span>
            </div>
            {correctionSummary.algorithm_version && (
              <div className="mt-2 font-mono text-[11px] text-slate-400">{correctionSummary.algorithm_version}</div>
            )}
          </div>
        )}

        <div className="border-b border-slate-100 px-7 py-6">
          <div className="mb-5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            <Wand2 size={12} />
            导出区
            <ReadinessPill status={task.export_readiness.status} />
          </div>

          {/* 主行动区：导出状态 + 成品下载并列 */}
          <div className="grid gap-0 lg:grid-cols-[1fr_1fr]">
            {/* 左：导出状态 + 操作 */}
            <div className="border-b border-slate-100 pb-5 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-8">
              <div className="text-sm leading-6 text-slate-500">{readinessMessage}</div>

              <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                <span>默认导出：<span className="font-medium text-slate-700">{getExportProfileLabel(task.export_readiness.recommended_profile, locale)}</span></span>
                <span className="text-slate-300">·</span>
                <span>成品目标：<span className="font-medium text-slate-700">{getOutputIntentLabel(task.output_intent, locale)}</span></span>
                {task.last_export_summary.status === 'exported' && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span>上次导出：<span className="font-medium text-slate-700">{task.last_export_summary.updated_at ? formatRelativeTime(task.last_export_summary.updated_at) : '刚刚'}</span></span>
                  </>
                )}
              </div>

              {task.export_readiness.blockers.length > 0 && (
                <div className="mt-4 space-y-2.5">
                  {task.export_readiness.blockers.map(blocker => (
                    <div key={blocker.code} className="flex items-start gap-2.5 rounded-lg border-l-2 border-amber-400 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
                      <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div>{blocker.message}</div>
                        <button
                          type="button"
                          onClick={() => handleBlockerAction(blocker)}
                          disabled={rerunMutation.isPending}
                          className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 underline-offset-2 hover:underline disabled:opacity-60"
                        >
                          {rerunMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                          {blocker.action_label}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-5">
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setExportDrawerOpen(true)}
                    disabled={!canOpenExportDrawer}
                    className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Wand2 size={14} />
                    导出成品
                  </button>
                  <button
                    type="button"
                    onClick={() => setSpeakerReviewOpen(true)}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    <Mic2 size={14} />
                    说话人审查
                  </button>
                  <button
                    type="button"
                    onClick={() => setDubbingReviewOpen(true)}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    <ListChecks size={14} />
                    配音返修审查
                  </button>
                  <Link
                    to={`/tasks/${task.id}/dubbing-editor`}
                    className="inline-flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
                  >
                    <Wand2 size={14} />
                    专业配音编辑台
                  </Link>
                </div>
              </div>
            </div>

            {/* 右：最近导出结果 */}
            <div className="pt-5 lg:pl-8 lg:pt-0">
              <div className="text-sm font-semibold text-slate-900">最近导出结果</div>
              {exportFiles.length === 0 ? (
                <div className="mt-2 text-sm text-slate-400">当前还没有导出的成品文件。</div>
              ) : (
                <div className="mt-3 space-y-2">
                  {lastExportStrategyLabel && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                      导出策略：<span className="font-medium text-slate-800">{lastExportStrategyLabel}</span>
                    </div>
                  )}
                  {exportFiles.map(file => (
                    <a
                      key={file.path}
                      href={getArtifactHref(task.id, file.path)}
                      target="_blank"
                      rel="noreferrer"
                      className="flex items-center justify-between gap-4 py-2 text-sm text-slate-700 transition-colors hover:text-slate-900"
                      aria-label={`下载${file.label}`}
                      title={`下载${file.label}`}
                    >
                      <div className="min-w-0">
                        <div className="font-medium">{file.label}</div>
                        <div className="mt-0.5 truncate text-xs text-slate-400">{file.path}</div>
                      </div>
                      <span aria-hidden="true" className={DOWNLOAD_ICON_BUTTON_CLASS}>
                        <Download size={12} />
                      </span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 成品素材清单：紧凑 checklist */}
          <div className="mt-6 border-t border-slate-100 pt-5">
            {(() => {
              const assetItems: Array<{ icon: LucideIcon; title: string; description: string; entry: TaskAssetEntry; href: string | null }> = [
                {
                  icon: Film,
                  title: '原始视频',
                  description: '所有任务的基础输入素材',
                  entry: task.asset_summary.video.original,
                  href: getAssetDownloadHref(task, task.asset_summary.video.original, 'input'),
                },
                {
                  icon: Eraser,
                  title: '干净画面',
                  description: '英文字幕版会优先使用',
                  entry: task.asset_summary.video.clean,
                  href: getAssetDownloadHref(task, task.asset_summary.video.clean),
                },
                {
                  icon: Mic,
                  title: '纯配音音轨',
                  description: '仅包含合成配音，便于单独检查',
                  entry: task.asset_summary.audio.dub,
                  href: getAssetDownloadHref(task, task.asset_summary.audio.dub),
                },
                {
                  icon: Headphones,
                  title: '预览混音音轨',
                  description: '用于快速验证版导出',
                  entry: task.asset_summary.audio.preview,
                  href: getAssetDownloadHref(task, task.asset_summary.audio.preview),
                },
                {
                  icon: ScanText,
                  title: 'OCR 英文字幕',
                  description: '适合画面原有中文字幕翻译',
                  entry: task.asset_summary.subtitles.ocr_translated,
                  href: getAssetDownloadHref(task, task.asset_summary.subtitles.ocr_translated),
                },
                {
                  icon: Captions,
                  title: 'ASR 英文字幕',
                  description: '适合语音转字幕链路',
                  entry: task.asset_summary.subtitles.asr_translated,
                  href: getAssetDownloadHref(task, task.asset_summary.subtitles.asr_translated),
                },
              ]
              const readyCount = assetItems.filter(r => r.entry.status === 'available').length
              return (
                <div>
                  <div className="mb-3 flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-500">成品素材清单</span>
                    <span className="text-xs text-slate-400">
                      <span className="font-semibold text-emerald-600">{readyCount}</span>
                      <span> / {assetItems.length} 就绪</span>
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-8 gap-y-0 lg:grid-cols-3">
                    {assetItems.map(item => (
                      <AssetCheckRow
                        key={item.title}
                        icon={item.icon}
                        title={item.title}
                        description={item.description}
                        entry={item.entry}
                        href={item.href}
                      />
                    ))}
                  </div>
                </div>
              )
            })()}
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

      <DubbingReviewDrawer
        taskId={task.id}
        isOpen={isDubbingReviewOpen}
        onClose={() => setDubbingReviewOpen(false)}
      />

      <SpeakerReviewDrawer
        taskId={task.id}
        isOpen={isSpeakerReviewOpen}
        onClose={() => setSpeakerReviewOpen(false)}
      />

      {isExportDrawerOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30 bg-slate-950/25"
            onClick={() => setExportDrawerOpen(false)}
            aria-label="关闭导出抽屉"
          />
          <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col border-l border-slate-200 bg-white">
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
              <DrawerSection title="1. 默认导出">
                <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3.5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-600">将导出为</span>
                        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-slate-500 ring-1 ring-slate-200">
                          来自成品目标
                        </span>
                      </div>
                      <div className="mt-1.5 text-base font-semibold text-slate-900">
                        {getExportProfileLabel(exportProfile, locale)}
                      </div>
                      <div className="mt-1 text-sm text-slate-500">
                        {getOutputIntentLabel(task.output_intent, locale)}。默认沿用任务目标，仅在本次需要例外导出时再切换其他版本。
                      </div>
                    </div>
                    <button
                      type="button"
                      aria-expanded={showProfileOverrides}
                      aria-controls="delivery-profile-overrides"
                      onClick={() => setShowProfileOverrides(prev => !prev)}
                      className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-800"
                    >
                      {showProfileOverrides ? '收起其他版本' : '切换其他版本'}
                    </button>
                  </div>
                  {showProfileOverrides && (
                    <div id="delivery-profile-overrides" className="mt-4 border-t border-slate-200 pt-4">
                      <div className="grid gap-3 md:grid-cols-2">
                        {(Object.keys(PROFILE_CONFIG) as TaskExportProfile[]).map(profile => (
                          <button
                            key={profile}
                            type="button"
                            onClick={() => setExportProfile(profile)}
                            className={`rounded-xl border p-3.5 text-left transition-colors ${
                              exportProfile === profile
                                ? 'border-blue-500 bg-blue-50 shadow-sm'
                                : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                            }`}
                          >
                            <div className="text-sm font-semibold text-slate-900">{getExportProfileLabel(profile, locale)}</div>
                            <div className="mt-1 text-sm leading-6 text-slate-600">{PROFILE_CONFIG[profile].description}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </DrawerSection>

              <DrawerSection title="2. 确认素材来源">
                {shouldShowHardSubtitleWarning && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-4">
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-amber-900">检测到原片已有中文字幕</div>
                        <div className="mt-1 text-sm leading-6 text-amber-800">
                          如果继续烧录中文，可能出现重复或遮挡。建议保留原片中文字幕，只补英文对照。
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <button
                        type="button"
                        onClick={() => setBilingualExportStrategy('preserve_hard_subtitles_add_english')}
                        className={`rounded-xl border p-3.5 text-left transition-colors ${
                          effectiveBilingualExportStrategy === 'preserve_hard_subtitles_add_english'
                            ? 'border-blue-500 bg-blue-50 shadow-sm'
                            : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                        }`}
                      >
                        <div className="text-sm font-semibold text-slate-900">推荐：保留原字 + 补英文</div>
                        <div className="mt-1 text-sm leading-6 text-slate-600">
                          保留原片中的中文字幕，在另一行补英文，适合快速审片和对照。
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => canUseCleanRebuildStrategy && setBilingualExportStrategy('clean_video_rebuild_bilingual')}
                        disabled={!canUseCleanRebuildStrategy}
                        className={`rounded-xl border p-3.5 text-left transition-colors ${
                          effectiveBilingualExportStrategy === 'clean_video_rebuild_bilingual'
                            ? 'border-blue-500 bg-blue-50 shadow-sm'
                            : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                        } disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400`}
                      >
                        <div className="text-sm font-semibold text-slate-900">清理原字 + 重做双语</div>
                        <div className="mt-1 text-sm leading-6 text-slate-600">
                          先使用干净画面，再由系统统一烧录中英双语字幕，适合需要标准化审片版本时使用。
                        </div>
                        {!canUseCleanRebuildStrategy && (
                          <div className="mt-2 text-xs text-slate-500">当前任务没有干净画面，暂不可用。</div>
                        )}
                      </button>
                    </div>
                  </div>
                )}
                <div className="grid gap-4 md:grid-cols-2">
                  <SourceSummaryCard
                    title="视频底板"
                    value={resolveVideoLabel(profileConfig.videoLabel, effectiveBilingualExportStrategy)}
                    entry={resolveVideoEntry(task, exportProfile, effectiveBilingualExportStrategy)}
                  />
                  <SourceSummaryCard
                    title="音轨来源"
                    value={profileConfig.audioLabel}
                    entry={resolveAudioEntry(task)}
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

function resolveInitialBilingualStrategy(task: Task): BilingualExportStrategy {
  const configuredStrategy = task.delivery_config.bilingual_export_strategy ?? 'auto_standard_bilingual'
  if (
    task.hard_subtitle_status === 'confirmed'
    && configuredStrategy === 'auto_standard_bilingual'
  ) {
    return 'preserve_hard_subtitles_add_english'
  }
  return configuredStrategy
}

function shouldWarnAboutHardSubtitles(task: Task, profile: TaskExportProfile): boolean {
  return profile === 'bilingual_review' && task.hard_subtitle_status === 'confirmed'
}

function resolveEffectiveBilingualStrategy(
  task: Task,
  profile: TaskExportProfile,
  strategy: BilingualExportStrategy,
): BilingualExportStrategy {
  if (profile !== 'bilingual_review') {
    return 'auto_standard_bilingual'
  }
  if (!shouldWarnAboutHardSubtitles(task, profile)) {
    return 'auto_standard_bilingual'
  }
  return strategy
}

function resolvePreviewVideoPath(
  task: Task,
  profile: TaskExportProfile,
  strategy: BilingualExportStrategy,
): string {
  if (
    (profile === 'english_subtitle_burned' || strategy === 'clean_video_rebuild_bilingual')
    && task.asset_summary.video.clean.path
  ) {
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

function resolveVideoEntry(
  task: Task,
  profile: TaskExportProfile,
  strategy: BilingualExportStrategy,
): TaskAssetEntry {
  if (profile === 'english_subtitle_burned' || strategy === 'clean_video_rebuild_bilingual') {
    return task.asset_summary.video.clean
  }
  return task.asset_summary.video.original
}

function resolveVideoLabel(defaultLabel: string, strategy: BilingualExportStrategy): string {
  if (strategy === 'clean_video_rebuild_bilingual') {
    return '干净画面'
  }
  return defaultLabel
}

function resolveAudioEntry(task: Task): TaskAssetEntry {
  return task.asset_summary.audio.preview
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

function getBilingualStrategyLabel(strategy: BilingualExportStrategy): string {
  switch (strategy) {
    case 'preserve_hard_subtitles_add_english':
      return '保留原字 + 补英文'
    case 'clean_video_rebuild_bilingual':
      return '清理原字 + 重做双语'
    default:
      return '标准双语导出'
  }
}

function resolveLastExportStrategyLabel(task: Task): string | null {
  if (task.last_export_summary.status !== 'exported') {
    return null
  }
  if (task.delivery_config.subtitle_mode !== 'bilingual') {
    return null
  }
  return getBilingualStrategyLabel(task.delivery_config.bilingual_export_strategy ?? 'auto_standard_bilingual')
}

function getArtifactHref(taskId: string, path: string): string {
  return `/api/tasks/${taskId}/artifacts/${path}`
}

function getTaskInputHref(taskId: string): string {
  return `/api/tasks/${taskId}/input-file`
}

function getAssetDownloadHref(task: Task, entry: TaskAssetEntry, kind: 'artifact' | 'input' = 'artifact'): string | null {
  if (entry.status !== 'available' || !entry.path) {
    return null
  }

  if (kind === 'input') {
    return getTaskInputHref(task.id)
  }

  return getArtifactHref(task.id, entry.path)
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

function AssetCheckRow({
  icon: Icon,
  title,
  description,
  entry,
  href,
}: {
  icon: LucideIcon
  title: string
  description: string
  entry: TaskAssetEntry
  href: string | null
}) {
  const isAvailable = entry.status === 'available'
  const isFailed = entry.status === 'failed'
  const isBuilding = entry.status === 'building'
  return (
    <div
      className="flex items-center gap-2.5 py-2"
      title={entry.path ? `${description}\n${entry.path}` : description}
    >
      <Icon
        size={13}
        className={isAvailable ? 'text-emerald-500' : isFailed ? 'text-rose-400' : isBuilding ? 'text-blue-400' : 'text-slate-300'}
      />
      <span className={`min-w-0 flex-1 truncate text-sm ${isAvailable ? 'text-slate-700' : 'text-slate-400'}`}>{title}</span>
      {href && (
        <a
          href={href}
          download
          className={DOWNLOAD_ICON_BUTTON_CLASS}
          aria-label={`下载${title}`}
          title={`下载${title}`}
        >
          <Download size={12} />
        </a>
      )}
      {!isAvailable && (
        <span className={`text-xs ${isFailed ? 'text-rose-500' : isBuilding ? 'text-blue-500' : 'text-slate-400'}`}>
          {isFailed ? '失败' : isBuilding ? '生成中' : '缺失'}
        </span>
      )}
    </div>
  )
}

function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
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
