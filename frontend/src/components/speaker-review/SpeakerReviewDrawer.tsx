import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  BookUser,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Loader2,
  Pencil,
  Pause,
  Play,
  Repeat,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Undo2,
  UploadCloud,
  UserRound,
  Users,
  Volume2,
  Wand2,
  X,
} from 'lucide-react'

import { tasksApi } from '../../api/tasks'
import { TaskWorkBindingControl } from '../task-work-binding/TaskWorkBindingControl'
import type {
  SpeakerPersonaBrief,
  SpeakerReviewDecisionPayload,
  SpeakerReviewResponse,
  SpeakerReviewSegment,
  SpeakerReviewSpeaker,
  SuggestFromGlobalCandidate,
  SuggestFromGlobalMatch,
} from '../../types'
import {
  buildSegmentRelabelDecision,
  buildSpeakerChoices,
  findActiveTranscriptSegment,
  sortTranscriptSegments,
} from './speakerReviewTimeline'

function formatTimeSec(sec?: number | null): string {
  const safe = Math.max(0, sec ?? 0)
  const minutes = Math.floor(safe / 60)
  const seconds = safe - minutes * 60
  return `${minutes}:${seconds.toFixed(1).padStart(4, '0')}`
}

function riskColor(risk?: string | null): string {
  if (risk === 'high') return 'border-rose-200 bg-rose-50 text-rose-700'
  if (risk === 'medium') return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-emerald-200 bg-emerald-50 text-emerald-700'
}

function riskLevelLabel(risk?: string | null): string {
  if (risk === 'high') return '高风险'
  if (risk === 'medium') return '中风险'
  return '低风险'
}

function riskLevelDescription(risk?: string | null): string {
  if (risk === 'high') return '需要优先核对，可能影响说话人归属或后续音色克隆'
  if (risk === 'medium') return '存在可疑边界、样本或时长模式，建议检查'
  return '未检测到明显异常'
}

function riskFlagTone(flag: string): 'slate' | 'amber' | 'rose' {
  if (flag.includes('single') || flag.includes('very_long') || flag.includes('sandwiched')) {
    return 'rose'
  }
  if (flag.includes('low') || flag.includes('short') || flag.includes('boundary')) {
    return 'amber'
  }
  return 'slate'
}

function riskFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    single_segment_speaker: '单段说话人',
    low_sample_speaker: '说话人样本不足',
    mostly_short_segments: '短句偏多',
    sparse_long_timing: '长时间戳稀疏',
    no_reference_safe_segment: '无安全参考段',
    single_segment_run: '单段连续块',
    short_run: '短连续块',
    sandwiched_run: '夹心孤岛',
    rapid_turn_boundary: '快速切换边界',
    short_segment: '短句',
    long_timing_short_text: '长时长短文本',
    very_long_segment: '超长片段',
    speaker_boundary_risk: '边界风险',
    speaker_sample_risk: '说话人样本风险',
  }
  return labels[flag] ?? flag
}

function riskFlagsLabel(flags: string[]): string {
  if (flags.length === 0) return '无明显风险'
  return flags.map(riskFlagLabel).join('、')
}

function actionLabel(action?: string | null): string {
  const labels: Record<string, string> = {
    keep_independent: '保持当前说话人',
    relabel: '改说话人',
    relabel_to_previous_speaker: '归到上一句说话人',
    relabel_to_next_speaker: '归到下一句说话人',
    merge_speaker: '合并说话人',
    mark_non_cloneable: '标记为不可克隆',
    merge_to_previous_speaker: '合并到上一句说话人',
    merge_to_next_speaker: '合并到下一句说话人',
    merge_to_surrounding_speaker: '合并到前后同一说话人',
  }
  return labels[action ?? ''] ?? action ?? '未知动作'
}

function speakerColor(label: string): string {
  const colors = [
    '#2563eb',
    '#dc2626',
    '#059669',
    '#9333ea',
    '#d97706',
    '#0891b2',
    '#be123c',
    '#4f46e5',
  ]
  let hash = 0
  for (let index = 0; index < label.length; index += 1) {
    hash = (hash * 31 + label.charCodeAt(index)) >>> 0
  }
  return colors[hash % colors.length]
}

function personaOf(
  data: SpeakerReviewResponse | undefined,
  speakerLabel: string | undefined | null,
): SpeakerPersonaBrief | null {
  if (!data || !speakerLabel) return null
  return data.personas?.by_speaker?.[speakerLabel] ?? null
}

function displayLabel(
  data: SpeakerReviewResponse | undefined,
  speakerLabel: string | undefined | null,
): string {
  if (!speakerLabel) return '无'
  const persona = personaOf(data, speakerLabel)
  return persona?.name || speakerLabel
}

function decisionLabel(segment?: SpeakerReviewSegment | null): string | null {
  const decision = segment?.decision
  if (!decision) return null
  if (decision.decision === 'keep_independent') return '已确认'
  if (decision.target_speaker_label) return `已改为 ${decision.target_speaker_label}`
  return `已决策：${actionLabel(decision.decision)}`
}

function buildKeepDecision(segment: SpeakerReviewSegment): SpeakerReviewDecisionPayload {
  return {
    item_id: segment.segment_id,
    item_type: 'segment',
    decision: 'keep_independent',
    source_speaker_label: segment.speaker_label,
    segment_ids: [segment.segment_id],
    payload: {
      source_speaker: segment.speaker_label,
      source: 'video_timeline',
    },
  }
}

function statusCopy(data?: SpeakerReviewResponse): string {
  if (!data) return '正在加载说话人核对数据'
  const summary = data.summary
  return `${summary.segment_count} 句台词 · ${summary.speaker_count} 位说话人 · ${summary.decision_count} 个决策`
}

function workBindingCopy(data?: SpeakerReviewResponse): string | null {
  const binding = data?.work_binding
  if (!binding) return null
  const title = binding.work?.title
  if (title) {
    return binding.episode_label ? `${title} · ${binding.episode_label}` : title
  }
  const candidate = binding.candidates?.[0]
  if (candidate?.title) {
    return candidate.episode_label
      ? `可能作品：${candidate.title} · ${candidate.episode_label}`
      : `可能作品：${candidate.title}`
  }
  return null
}

export function SpeakerReviewDrawer({
  taskId,
  isOpen,
  onClose,
  onRerunFromTaskB,
}: {
  taskId: string
  isOpen: boolean
  onClose: () => void
  onRerunFromTaskB?: () => void
}) {
  const queryClient = useQueryClient()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const activeSegmentRef = useRef<SpeakerReviewSegment | null>(null)
  const transcriptRef = useRef<HTMLDivElement | null>(null)
  const rowRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const [playheadSec, setPlayheadSec] = useState(0)
  const [durationSec, setDurationSec] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [videoError, setVideoError] = useState<string | null>(null)
  const [applyResult, setApplyResult] = useState<string | null>(null)
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null)
  const [renamingSpeaker, setRenamingSpeaker] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [filterMode, setFilterMode] = useState<'all' | 'undecided' | 'risk' | 'decided'>('all')
  const [autoAdvance, setAutoAdvance] = useState(true)
  const [riskDetailsOpen, setRiskDetailsOpen] = useState(false)
  const [loopActiveSegment, setLoopActiveSegment] = useState(false)

  const reviewQuery = useQuery({
    queryKey: ['speaker-review', taskId],
    queryFn: () => tasksApi.getSpeakerReview(taskId),
    enabled: isOpen,
  })

  const decisionMutation = useMutation({
    mutationFn: (payload: SpeakerReviewDecisionPayload) =>
      tasksApi.saveSpeakerReviewDecision(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const deleteDecisionMutation = useMutation({
    mutationFn: (itemId: string) => tasksApi.deleteSpeakerReviewDecision(taskId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => tasksApi.applySpeakerReviewDecisions(taskId),
    onSuccess: data => {
      setApplyResult(`已应用 ${data.summary?.changed_segment_count ?? ''} 个片段决策`)
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const createPersonaMutation = useMutation({
    mutationFn: (payload: { name: string; bindings: string[] }) =>
      tasksApi.createSpeakerPersona(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const updatePersonaMutation = useMutation({
    mutationFn: (payload: { personaId: string; name: string }) =>
      tasksApi.updateSpeakerPersona(taskId, payload.personaId, { name: payload.name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const importFromGlobalMutation = useMutation({
    mutationFn: (payload: { persona_ids: string[]; bindings_by_id?: Record<string, string[]> }) =>
      tasksApi.importPersonasFromGlobal(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const exportToGlobalMutation = useMutation({
    mutationFn: () => tasksApi.exportTaskPersonasToGlobal(taskId, { overwrite: true }),
  })

  const [globalMatches, setGlobalMatches] = useState<SuggestFromGlobalMatch[]>([])
  const [globalMatchesLoading, setGlobalMatchesLoading] = useState(false)
  const [exportFlash, setExportFlash] = useState<string | null>(null)
  const [bindingPersonaId, setBindingPersonaId] = useState<string | null>(null)

  const sortedSegments = useMemo(
    () => sortTranscriptSegments(reviewQuery.data?.segments ?? []),
    [reviewQuery.data?.segments],
  )
  const filterCounts = useMemo(() => {
    let undecided = 0
    let risk = 0
    let decided = 0
    for (const seg of sortedSegments) {
      if (seg.decision) decided += 1
      else undecided += 1
      if ((seg.risk_level === 'high' || seg.risk_level === 'medium') || (seg.risk_flags && seg.risk_flags.length > 0)) {
        risk += 1
      }
    }
    return { all: sortedSegments.length, undecided, risk, decided }
  }, [sortedSegments])
  const matchesFilter = useCallback(
    (segment: SpeakerReviewSegment, mode: typeof filterMode) => {
      if (mode === 'all') return true
      if (mode === 'undecided') return !segment.decision
      if (mode === 'decided') return Boolean(segment.decision)
      if (mode === 'risk') {
        return (
          segment.risk_level === 'high' ||
          segment.risk_level === 'medium' ||
          (segment.risk_flags?.length ?? 0) > 0
        )
      }
      return true
    },
    [],
  )
  const filteredSegments = useMemo(
    () => sortedSegments.filter(seg => matchesFilter(seg, filterMode)),
    [sortedSegments, filterMode, matchesFilter],
  )
  const playheadSegment = useMemo(
    () => findActiveTranscriptSegment(sortedSegments, playheadSec),
    [sortedSegments, playheadSec],
  )
  const selectedSegment = useMemo(
    () => sortedSegments.find(segment => segment.segment_id === selectedSegmentId) ?? null,
    [selectedSegmentId, sortedSegments],
  )
  const activeSegment = selectedSegment ?? playheadSegment
  const activeIndex = useMemo(
    () =>
      activeSegment
        ? sortedSegments.findIndex(segment => segment.segment_id === activeSegment.segment_id)
        : -1,
    [activeSegment, sortedSegments],
  )
  const previousSegment = activeIndex > 0 ? sortedSegments[activeIndex - 1] : null
  const nextSegment =
    activeIndex >= 0 && activeIndex + 1 < sortedSegments.length
      ? sortedSegments[activeIndex + 1]
      : null
  const speakerChoices = useMemo(
    () => buildSpeakerChoices(reviewQuery.data?.speakers ?? [], activeSegment, 7),
    [reviewQuery.data?.speakers, activeSegment],
  )

  const videoSrc = `/api/tasks/${taskId}/dubbing-editor/video-preview`

  const seekToSegment = useCallback((segment: SpeakerReviewSegment, autoplay = false) => {
    const video = videoRef.current
    if (!video) return
    activeSegmentRef.current = segment
    setSelectedSegmentId(segment.segment_id)
    video.currentTime = Math.max(0, segment.start + 0.01)
    setPlayheadSec(video.currentTime)
    if (autoplay) {
      video.play().catch(() => setVideoError('视频播放失败，请检查浏览器是否允许播放'))
    }
  }, [])

  const jumpBy = useCallback(
    (delta: number) => {
      if (!sortedSegments.length) return
      const baseIndex = activeIndex < 0 ? 0 : activeIndex
      const next = sortedSegments[Math.max(0, Math.min(sortedSegments.length - 1, baseIndex + delta))]
      seekToSegment(next)
    },
    [activeIndex, seekToSegment, sortedSegments],
  )

  const jumpToNextMatching = useCallback(
    (mode: typeof filterMode) => {
      if (!sortedSegments.length) return false
      const startIdx = activeIndex < 0 ? -1 : activeIndex
      for (let offset = 1; offset <= sortedSegments.length; offset += 1) {
        const idx = (startIdx + offset) % sortedSegments.length
        const candidate = sortedSegments[idx]
        if (matchesFilter(candidate, mode)) {
          seekToSegment(candidate)
          return true
        }
      }
      return false
    },
    [activeIndex, matchesFilter, seekToSegment, sortedSegments],
  )

  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play().catch(() => setVideoError('视频播放失败，请检查浏览器是否允许播放'))
    } else {
      video.pause()
    }
  }, [])

  const saveDecision = useCallback(
    (payload: SpeakerReviewDecisionPayload) => {
      decisionMutation.mutate(payload, {
        onSuccess: () => {
          if (autoAdvance) {
            const advanced = jumpToNextMatching('undecided')
            if (!advanced) jumpToNextMatching('risk')
          }
        },
      })
    },
    [autoAdvance, decisionMutation, jumpToNextMatching],
  )

  const undoDecision = useCallback(
    (segment: SpeakerReviewSegment) => {
      if (!segment.decision) return
      deleteDecisionMutation.mutate(segment.segment_id)
    },
    [deleteDecisionMutation],
  )

  const assignActiveSpeaker = useCallback(
    (speakerLabel: string) => {
      const segment = activeSegmentRef.current ?? activeSegment
      if (!segment) return
      const payload =
        speakerLabel === segment.speaker_label
          ? buildKeepDecision(segment)
          : buildSegmentRelabelDecision(segment, speakerLabel)
      saveDecision(payload)
    },
    [activeSegment, saveDecision],
  )

  const startRenameSpeaker = useCallback(
    (speakerLabel: string) => {
      setRenamingSpeaker(speakerLabel)
      setRenameDraft(displayLabel(reviewQuery.data, speakerLabel) === speakerLabel ? '' : displayLabel(reviewQuery.data, speakerLabel))
    },
    [reviewQuery.data],
  )

  const cancelRenameSpeaker = useCallback(() => {
    setRenamingSpeaker(null)
    setRenameDraft('')
  }, [])

  const commitRenameSpeaker = useCallback(async () => {
    const speakerLabel = renamingSpeaker
    const name = renameDraft.trim()
    if (!speakerLabel || !name) {
      cancelRenameSpeaker()
      return
    }
    const persona = personaOf(reviewQuery.data, speakerLabel)
    if (persona?.persona_id) {
      await updatePersonaMutation.mutateAsync({ personaId: persona.persona_id, name })
    } else {
      await createPersonaMutation.mutateAsync({ name, bindings: [speakerLabel] })
    }
    cancelRenameSpeaker()
  }, [
    cancelRenameSpeaker,
    createPersonaMutation,
    renameDraft,
    renamingSpeaker,
    reviewQuery.data,
    updatePersonaMutation,
  ])

  useEffect(() => {
    if (!activeSegment) return
    activeSegmentRef.current = activeSegment
    const row = rowRefs.current[activeSegment.segment_id]
    row?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [activeSegment])

  const fetchGlobalMatches = useCallback(async () => {
    setGlobalMatchesLoading(true)
    try {
      const result = await tasksApi.suggestPersonasFromGlobal(taskId, {})
      setGlobalMatches(result.matches ?? [])
    } catch {
      setGlobalMatches([])
    } finally {
      setGlobalMatchesLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    if (!isOpen) return
    if (reviewQuery.data?.status !== 'available') return
    fetchGlobalMatches()
  }, [isOpen, reviewQuery.data?.status, fetchGlobalMatches])

  const bindGlobalPersona = useCallback(
    async (candidate: SuggestFromGlobalCandidate, speakerLabel: string) => {
      if (!candidate.persona_id) return
      setBindingPersonaId(candidate.persona_id)
      try {
        await importFromGlobalMutation.mutateAsync({
          persona_ids: [candidate.persona_id],
          bindings_by_id: { [candidate.persona_id]: [speakerLabel] },
        })
        setExportFlash(`已绑定角色：${candidate.name}`)
      } finally {
        setBindingPersonaId(null)
      }
    },
    [importFromGlobalMutation],
  )

  const pushToGlobalLibrary = useCallback(async () => {
    try {
      const result = await exportToGlobalMutation.mutateAsync()
      const exported = result.exported?.length ?? 0
      setExportFlash(
        exported > 0 ? `已保存 ${exported} 个角色到角色库` : '角色库已同步（无新增角色）',
      )
      fetchGlobalMatches()
    } catch {
      setExportFlash('保存到角色库失败，请稍后重试')
    }
  }, [exportToGlobalMutation, fetchGlobalMatches])

  useEffect(() => {
    if (!exportFlash) return
    const timer = window.setTimeout(() => setExportFlash(null), 3500)
    return () => window.clearTimeout(timer)
  }, [exportFlash])

  useEffect(() => {
    if (!isOpen) return
    const handler = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key === ' ') {
        const target = event.target as HTMLElement | null
        if (target && target.closest && target.closest('button')) return
        event.preventDefault()
        togglePlay()
        return
      }
      if (event.key === 'j' || event.key === 'ArrowDown') {
        event.preventDefault()
        jumpBy(1)
        return
      }
      if (event.key === 'k' || event.key === 'ArrowUp') {
        event.preventDefault()
        jumpBy(-1)
        return
      }
      if (event.key === 'n' || event.key === 'N') {
        event.preventDefault()
        if (event.shiftKey) {
          jumpToNextMatching('risk')
        } else {
          jumpToNextMatching('undecided')
        }
        return
      }
      if (event.key === 'l' || event.key === 'L') {
        event.preventDefault()
        setLoopActiveSegment(prev => !prev)
        return
      }
      if (event.key === '[') {
        event.preventDefault()
        if (previousSegment) assignActiveSpeaker(previousSegment.speaker_label)
        return
      }
      if (event.key === ']') {
        event.preventDefault()
        if (nextSegment) assignActiveSpeaker(nextSegment.speaker_label)
        return
      }
      if (/^[1-9]$/.test(event.key)) {
        const choice = speakerChoices[Number(event.key) - 1]
        if (!choice) return
        event.preventDefault()
        assignActiveSpeaker(choice.speaker_label)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [
    assignActiveSpeaker,
    isOpen,
    jumpBy,
    jumpToNextMatching,
    nextSegment,
    onClose,
    previousSegment,
    speakerChoices,
    togglePlay,
  ])

  if (!isOpen) return null

  return (
    <div
      className="fixed bottom-0 left-0 right-0 top-[var(--app-header-height,60px)] z-20 flex bg-slate-100 md:left-[var(--sidebar-offset,220px)]"
      data-testid="speaker-review-drawer"
    >
      <div className="flex h-full w-full flex-col overflow-hidden bg-slate-100">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4">
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            title="返回任务详情"
            data-testid="close-drawer"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <h2 className="truncate text-sm font-semibold text-slate-950">说话人核对</h2>
              {reviewQuery.data && (
                <TaskWorkBindingControl
                  taskId={taskId}
                  workId={reviewQuery.data.work_binding?.work_id}
                  episodeLabel={reviewQuery.data.work_binding?.episode_label}
                  currentWorkTitle={reviewQuery.data.work_binding?.work?.title}
                  fallbackLabel={workBindingCopy(reviewQuery.data)}
                  compact
                  triggerTestId="speaker-review-work-binding"
                  onSaved={() => {
                    reviewQuery.refetch()
                    fetchGlobalMatches()
                  }}
                />
              )}
            </div>
            <div className="truncate text-xs text-slate-500">{statusCopy(reviewQuery.data)}</div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {exportFlash && (
              <span
                className="max-w-72 truncate rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-emerald-700"
                data-testid="character-library-flash"
              >
                {exportFlash}
              </span>
            )}
            {applyResult && (
              <span className="max-w-80 truncate text-xs text-emerald-700" data-testid="apply-result">
                {applyResult}
              </span>
            )}
            {onRerunFromTaskB && (
              <button
                type="button"
                onClick={onRerunFromTaskB}
                className="flex h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 hover:bg-slate-50"
              >
                <RotateCcw size={14} /> 从 Task B 重跑
              </button>
            )}
            <button
              type="button"
              onClick={pushToGlobalLibrary}
              disabled={exportToGlobalMutation.isPending}
              className="flex h-8 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              title="把当前任务里的角色保存到全局角色库"
              data-testid="push-to-character-library"
            >
              {exportToGlobalMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <UploadCloud size={14} />
              )}
              保存到角色库
            </button>
            <button
              type="button"
              onClick={() => applyMutation.mutate()}
              disabled={applyMutation.isPending || (reviewQuery.data?.summary.decision_count ?? 0) <= 0}
              className="flex h-8 items-center gap-1 rounded-md bg-emerald-600 px-3 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="apply-decisions"
            >
              {applyMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check size={14} />}
              应用决策
            </button>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800"
              aria-label="关闭"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        {reviewQuery.isLoading ? (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            加载说话人核对数据
          </div>
        ) : reviewQuery.data?.status !== 'available' ? (
          <div className="flex flex-1 items-center justify-center text-sm text-slate-500">
            当前任务没有可核对的说话人数据
          </div>
        ) : (
          <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_360px] gap-3 p-3">
            <section className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="relative flex min-h-0 flex-1 items-center justify-center bg-black">
                <video
                  ref={videoRef}
                  src={videoSrc}
                  className="h-full max-h-full w-full max-w-full object-contain"
                  preload="metadata"
                  playsInline
                  data-testid="speaker-review-video"
                  onLoadedMetadata={event => {
                    setDurationSec(event.currentTarget.duration || 0)
                    setVideoError(null)
                  }}
                  onTimeUpdate={event => {
                    const currentTime = event.currentTarget.currentTime
                    setPlayheadSec(currentTime)
                    const selected = activeSegmentRef.current
                    if (loopActiveSegment && selected && currentTime >= selected.end) {
                      event.currentTarget.currentTime = Math.max(0, selected.start + 0.01)
                      return
                    }
                    if (
                      event.currentTarget.paused &&
                      selected &&
                      (currentTime < selected.start || currentTime >= selected.end)
                    ) {
                      return
                    }
                    const currentSegment = findActiveTranscriptSegment(sortedSegments, currentTime)
                    if (currentSegment) {
                      activeSegmentRef.current = currentSegment
                      setSelectedSegmentId(currentSegment.segment_id)
                    }
                  }}
                  onPlay={() => setIsPlaying(true)}
                  onPause={() => setIsPlaying(false)}
                  onEnded={() => setIsPlaying(false)}
                  onError={() => setVideoError('视频加载失败，无法打开原视频预览')}
                />

                {!isPlaying && (
                  <button
                    type="button"
                    onClick={togglePlay}
                    className="absolute inset-0 flex items-center justify-center bg-black/10"
                    data-testid="video-play-overlay"
                  >
                    <span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/85 text-slate-900 shadow-lg">
                      <Play className="ml-1 h-7 w-7" />
                    </span>
                  </button>
                )}

                {activeSegment && (
                  <div className="pointer-events-none absolute bottom-8 left-1/2 w-[min(820px,90%)] -translate-x-1/2 text-center">
                    <div className="inline-flex max-w-full items-center gap-2 rounded-md bg-black/70 px-4 py-2 text-white shadow-lg backdrop-blur">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: speakerColor(activeSegment.speaker_label) }}
                      />
                      <span className="shrink-0 text-xs font-semibold">
                        {displayLabel(reviewQuery.data, activeSegment.speaker_label)}
                      </span>
                      <span className="min-w-0 truncate text-sm">{activeSegment.text}</span>
                    </div>
                  </div>
                )}

                {videoError && (
                  <div className="absolute top-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                    {videoError}
                  </div>
                )}
              </div>

              <VideoControls
                isPlaying={isPlaying}
                playheadSec={playheadSec}
                durationSec={durationSec}
                onTogglePlay={togglePlay}
                onJumpPrevious={() => jumpBy(-1)}
                onJumpNext={() => jumpBy(1)}
                onSeek={sec => {
                  if (videoRef.current) videoRef.current.currentTime = sec
                  setPlayheadSec(sec)
                  const currentSegment = findActiveTranscriptSegment(sortedSegments, sec)
                  if (currentSegment) {
                    activeSegmentRef.current = currentSegment
                    setSelectedSegmentId(currentSegment.segment_id)
                  }
                }}
              />

              <TranscriptTimeline
                data={reviewQuery.data}
                segments={filteredSegments}
                totalSegments={sortedSegments.length}
                filterMode={filterMode}
                filterCounts={filterCounts}
                onChangeFilter={setFilterMode}
                autoAdvance={autoAdvance}
                onToggleAutoAdvance={() => setAutoAdvance(v => !v)}
                activeSegment={activeSegment}
                playheadSec={playheadSec}
                durationSec={durationSec}
                rowRefs={rowRefs}
                scrollRef={transcriptRef}
                onSelect={segment => seekToSegment(segment)}
                onUndoDecision={undoDecision}
              />
            </section>

            <aside className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white">
              <DecisionPanel
                data={reviewQuery.data}
                activeSegment={activeSegment}
                previousSegment={previousSegment}
                nextSegment={nextSegment}
                speakers={reviewQuery.data?.speakers ?? []}
                speakerChoices={speakerChoices}
                saving={
                  decisionMutation.isPending ||
                  createPersonaMutation.isPending ||
                  updatePersonaMutation.isPending
                }
                renamingSpeaker={renamingSpeaker}
                renameDraft={renameDraft}
                riskDetailsOpen={riskDetailsOpen}
                onToggleRiskDetails={() => setRiskDetailsOpen(v => !v)}
                loopActiveSegment={loopActiveSegment}
                onToggleLoop={() => setLoopActiveSegment(v => !v)}
                onAssign={assignActiveSpeaker}
                onKeep={() => activeSegment && saveDecision(buildKeepDecision(activeSegment))}
                onUndoDecision={() => activeSegment && undoDecision(activeSegment)}
                onStartRename={startRenameSpeaker}
                onChangeRename={setRenameDraft}
                onCommitRename={commitRenameSpeaker}
                onCancelRename={cancelRenameSpeaker}
                globalMatches={globalMatches}
                onBindGlobalCandidate={bindGlobalPersona}
                onRefreshGlobalMatches={fetchGlobalMatches}
                bindingPersonaId={bindingPersonaId}
                globalMatchesLoading={globalMatchesLoading}
              />
            </aside>
          </main>
        )}
      </div>
    </div>
  )
}

function VideoControls({
  isPlaying,
  playheadSec,
  durationSec,
  onTogglePlay,
  onJumpPrevious,
  onJumpNext,
  onSeek,
}: {
  isPlaying: boolean
  playheadSec: number
  durationSec: number
  onTogglePlay: () => void
  onJumpPrevious: () => void
  onJumpNext: () => void
  onSeek: (sec: number) => void
}) {
  const progress = durationSec > 0 ? Math.min(100, Math.max(0, (playheadSec / durationSec) * 100)) : 0
  return (
    <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
      <input
        type="range"
        min={0}
        max={durationSec || 0}
        step={0.05}
        value={durationSec > 0 ? Math.min(playheadSec, durationSec) : 0}
        onChange={event => onSeek(Number(event.currentTarget.value))}
        className="h-1.5 w-full cursor-pointer accent-blue-600"
        aria-label="视频播放进度"
        data-testid="video-progress"
        style={{
          background: `linear-gradient(90deg, #2563eb ${progress}%, #e2e8f0 ${progress}%)`,
        }}
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={onTogglePlay}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700"
          data-testid="video-play-toggle"
        >
          {isPlaying ? <Pause size={15} /> : <Play size={15} className="ml-0.5" />}
        </button>
        <button
          type="button"
          onClick={onJumpPrevious}
          className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          title="上一句 (K)"
        >
          <ChevronLeft size={16} />
        </button>
        <button
          type="button"
          onClick={onJumpNext}
          className="flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          title="下一句 (J)"
        >
          <ChevronRight size={16} />
        </button>
        <span className="font-mono text-xs tabular-nums text-slate-500">
          {formatTimeSec(playheadSec)} / {formatTimeSec(durationSec)}
        </span>
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
          <Volume2 size={14} />
          <span>空格 播放 · J/K 切句 · N 下一未决 · 1-7 改人 · L 循环 · [/] 归上下句</span>
        </div>
      </div>
    </div>
  )
}

function RiskLevelBadge({ level }: { level?: string | null }) {
  const label = riskLevelLabel(level)
  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${riskColor(level)}`}
      title={`${label}：${riskLevelDescription(level)}`}
    >
      {label}
    </span>
  )
}

function RiskFlagPill({ flag }: { flag: string }) {
  const tone = riskFlagTone(flag)
  const cls = {
    slate: 'border-slate-200 bg-slate-100 text-slate-600',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    rose: 'border-rose-200 bg-rose-50 text-rose-700',
  }[tone]
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {riskFlagLabel(flag)}
    </span>
  )
}

function RiskFlagList({
  flags,
  emptyCopy = '无明显风险',
}: {
  flags: string[]
  emptyCopy?: ReactNode
}) {
  if (flags.length === 0) {
    return <span className="text-xs text-slate-400">{emptyCopy}</span>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {flags.map(flag => (
        <RiskFlagPill key={flag} flag={flag} />
      ))}
    </div>
  )
}

function ActiveRiskSummary({ segment }: { segment: SpeakerReviewSegment }) {
  return (
    <div
      className="mt-3 rounded-md border border-slate-200 bg-white p-3 text-xs"
      data-testid="active-risk-summary"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-semibold text-slate-900">风险等级</div>
          <div className="mt-1 leading-5 text-slate-500">{riskLevelDescription(segment.risk_level)}</div>
        </div>
        <RiskLevelBadge level={segment.risk_level} />
      </div>
      <div className="mt-3">
        <div className="mb-1.5 font-semibold text-slate-900">风险点</div>
        <RiskFlagList flags={segment.risk_flags} />
      </div>
    </div>
  )
}

function TranscriptTimeline({
  data,
  segments,
  totalSegments,
  filterMode,
  filterCounts,
  onChangeFilter,
  autoAdvance,
  onToggleAutoAdvance,
  activeSegment,
  playheadSec,
  durationSec,
  rowRefs,
  scrollRef,
  onSelect,
  onUndoDecision,
}: {
  data?: SpeakerReviewResponse
  segments: SpeakerReviewSegment[]
  totalSegments: number
  filterMode: 'all' | 'undecided' | 'risk' | 'decided'
  filterCounts: { all: number; undecided: number; risk: number; decided: number }
  onChangeFilter: (mode: 'all' | 'undecided' | 'risk' | 'decided') => void
  autoAdvance: boolean
  onToggleAutoAdvance: () => void
  activeSegment: SpeakerReviewSegment | null
  playheadSec: number
  durationSec: number
  rowRefs: MutableRefObject<Record<string, HTMLButtonElement | null>>
  scrollRef: MutableRefObject<HTMLDivElement | null>
  onSelect: (segment: SpeakerReviewSegment) => void
  onUndoDecision: (segment: SpeakerReviewSegment) => void
}) {
  const timelineDuration = Math.max(durationSec, ...segments.map(segment => segment.end), 1)
  const filterTabs: Array<{ key: 'all' | 'undecided' | 'risk' | 'decided'; label: string; count: number }> = [
    { key: 'all', label: '全部', count: filterCounts.all },
    { key: 'undecided', label: '未决策', count: filterCounts.undecided },
    { key: 'risk', label: '有风险', count: filterCounts.risk },
    { key: 'decided', label: '已决策', count: filterCounts.decided },
  ]
  return (
    <div className="flex h-72 shrink-0 flex-col border-t border-slate-200 bg-slate-50">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-4 py-1.5">
        <span className="text-xs font-semibold text-slate-900">同步台词轨</span>
        <div
          className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 p-0.5"
          data-testid="transcript-filter-tabs"
          role="tablist"
          aria-label="台词过滤"
        >
          {filterTabs.map(tab => {
            const active = filterMode === tab.key
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onChangeFilter(tab.key)}
                data-testid={`filter-tab-${tab.key}`}
                className={`flex h-6 items-center gap-1 rounded px-2 text-[11px] font-medium transition ${
                  active
                    ? 'bg-white text-slate-900 shadow-sm ring-1 ring-slate-200'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {tab.label}
                <span
                  className={`rounded-full px-1.5 py-0 text-[10px] tabular-nums ${
                    active ? 'bg-blue-100 text-blue-700' : 'bg-slate-200 text-slate-600'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            )
          })}
        </div>
        <label
          className="ml-auto flex items-center gap-1.5 text-[11px] text-slate-600"
          title="决策保存后自动跳到下一个未决策的台词"
        >
          <input
            type="checkbox"
            checked={autoAdvance}
            onChange={onToggleAutoAdvance}
            className="h-3 w-3 cursor-pointer accent-blue-600"
            data-testid="toggle-auto-advance"
          />
          保存后自动跳下一个
        </label>
      </div>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto"
        data-testid="transcript-track"
      >
        {segments.length === 0 ? (
          <div className="flex h-full items-center justify-center px-4 py-8 text-center text-xs text-slate-400">
            {totalSegments === 0 ? '暂无台词数据' : '当前筛选下没有台词，切换 Tab 查看其它类别'}
          </div>
        ) : (
          segments.map(segment => {
            const active = activeSegment?.segment_id === segment.segment_id
            const left = (segment.start / timelineDuration) * 100
            const width = Math.max(0.4, ((segment.end - segment.start) / timelineDuration) * 100)
            const currentDecision = decisionLabel(segment)
            return (
              <div
                key={segment.segment_id}
                className={`relative border-b border-slate-200 ${
                  active ? 'bg-blue-50 ring-1 ring-inset ring-blue-200' : 'bg-white hover:bg-slate-50'
                }`}
              >
                <button
                  ref={el => {
                    rowRefs.current[segment.segment_id] = el
                  }}
                  type="button"
                  onPointerDown={() => onSelect(segment)}
                  onClick={() => onSelect(segment)}
                  className="grid w-full grid-cols-[76px_minmax(120px,180px)_minmax(0,1fr)_132px] items-center gap-3 px-4 py-2 text-left text-xs transition"
                  data-testid={`transcript-row-${segment.segment_id}`}
                  title={
                    segment.risk_flags.length > 0
                      ? `风险等级：${riskLevelLabel(segment.risk_level)}；风险点：${riskFlagsLabel(segment.risk_flags)}`
                      : undefined
                  }
                >
                  <span className="font-mono tabular-nums text-slate-500">
                    {formatTimeSec(segment.start)}
                  </span>
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: speakerColor(segment.speaker_label) }}
                    />
                    <span className="truncate font-semibold text-slate-800">
                      {displayLabel(data, segment.speaker_label)}
                    </span>
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-slate-800">{segment.text}</span>
                    <span className="relative mt-1 block h-1 overflow-hidden rounded-full bg-slate-200">
                      <span
                        className="absolute inset-y-0 rounded-full bg-slate-400"
                        style={{ left: `${left}%`, width: `${width}%` }}
                      />
                      {active && (
                        <span
                          className="absolute top-1/2 h-2 w-0.5 -translate-y-1/2 bg-blue-600"
                          style={{ left: `${(playheadSec / timelineDuration) * 100}%` }}
                        />
                      )}
                    </span>
                  </span>
                  <span className="flex items-center justify-end gap-1">
                    {currentDecision ? (
                      <span className="flex items-center gap-1">
                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700">
                          {currentDecision}
                        </span>
                      </span>
                    ) : segment.risk_flags.length > 0 ? (
                      <RiskLevelBadge level={segment.risk_level} />
                    ) : (
                      <span className="text-[11px] text-slate-400">未决策</span>
                    )}
                  </span>
                </button>
                {currentDecision && (
                  <button
                    type="button"
                    onClick={event => {
                      event.stopPropagation()
                      onUndoDecision(segment)
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 flex h-6 w-6 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-rose-200 hover:text-rose-600"
                    title="撤销此决策"
                    data-testid={`undo-decision-${segment.segment_id}`}
                  >
                    <Undo2 size={12} />
                  </button>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function DecisionPanel({
  data,
  activeSegment,
  previousSegment,
  nextSegment,
  speakers,
  speakerChoices,
  saving,
  renamingSpeaker,
  renameDraft,
  riskDetailsOpen,
  onToggleRiskDetails,
  loopActiveSegment,
  onToggleLoop,
  onAssign,
  onKeep,
  onUndoDecision,
  onStartRename,
  onChangeRename,
  onCommitRename,
  onCancelRename,
  globalMatches,
  onBindGlobalCandidate,
  onRefreshGlobalMatches,
  bindingPersonaId,
  globalMatchesLoading,
}: {
  data?: SpeakerReviewResponse
  activeSegment: SpeakerReviewSegment | null
  previousSegment: SpeakerReviewSegment | null
  nextSegment: SpeakerReviewSegment | null
  speakers: SpeakerReviewSpeaker[]
  speakerChoices: SpeakerReviewSpeaker[]
  saving: boolean
  renamingSpeaker: string | null
  renameDraft: string
  riskDetailsOpen: boolean
  onToggleRiskDetails: () => void
  loopActiveSegment: boolean
  onToggleLoop: () => void
  onAssign: (speakerLabel: string) => void
  onKeep: () => void
  onUndoDecision: () => void
  onStartRename: (speakerLabel: string) => void
  onChangeRename: (value: string) => void
  onCommitRename: () => void
  onCancelRename: () => void
  globalMatches: SuggestFromGlobalMatch[]
  onBindGlobalCandidate: (
    candidate: SuggestFromGlobalCandidate,
    speakerLabel: string,
  ) => Promise<void>
  onRefreshGlobalMatches: () => void
  bindingPersonaId: string | null
  globalMatchesLoading: boolean
}) {
  if (!activeSegment) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-500">
        播放视频或选择一条台词开始核对
      </div>
    )
  }
  const isLowRisk = activeSegment.risk_level !== 'high' && activeSegment.risk_level !== 'medium' && (activeSegment.risk_flags?.length ?? 0) === 0
  const decisionText = decisionLabel(activeSegment)

  return (
    <>
      <div className="shrink-0 border-b border-slate-200 p-4">
        <div className="flex items-center gap-2">
          <span
            className="h-3 w-3 rounded-full"
            style={{ backgroundColor: speakerColor(activeSegment.speaker_label) }}
          />
          {renamingSpeaker === activeSegment.speaker_label ? (
            <input
              autoFocus
              value={renameDraft}
              onChange={event => onChangeRename(event.currentTarget.value)}
              onKeyDown={event => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  onCommitRename()
                } else if (event.key === 'Escape') {
                  event.preventDefault()
                  onCancelRename()
                }
              }}
              onBlur={onCommitRename}
              placeholder={activeSegment.speaker_label}
              className="min-w-0 flex-1 rounded-md border border-blue-300 bg-white px-2 py-1 text-sm font-semibold text-slate-950 outline-none ring-2 ring-blue-100"
              data-testid="rename-active-speaker-input"
            />
          ) : (
            <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-950">
              {displayLabel(data, activeSegment.speaker_label)}
            </h3>
          )}
          {renamingSpeaker !== activeSegment.speaker_label && (
            <button
              type="button"
              onClick={() => onStartRename(activeSegment.speaker_label)}
              disabled={saving}
              className="flex h-7 items-center gap-1 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              data-testid="rename-active-speaker"
              title="修改当前说话人昵称"
            >
              <Pencil size={12} />
              改昵称
            </button>
          )}
          <RiskLevelBadge level={activeSegment.risk_level} />
        </div>
        <div className="mt-2 flex items-center gap-2 font-mono text-xs text-slate-500">
          <span>
            {formatTimeSec(activeSegment.start)} - {formatTimeSec(activeSegment.end)}
          </span>
          <button
            type="button"
            onClick={onToggleLoop}
            className={`ml-auto inline-flex h-6 items-center gap-1 rounded-md border px-2 font-sans text-[11px] font-medium transition ${
              loopActiveSegment
                ? 'border-blue-300 bg-blue-50 text-blue-700'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
            title="按 L 切换：循环播放当前句"
            data-testid="toggle-loop-active"
            aria-pressed={loopActiveSegment}
          >
            <Repeat size={12} />
            {loopActiveSegment ? '循环中' : '循环 (L)'}
          </button>
        </div>
        <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-800">
          {activeSegment.text}
        </p>
        {isLowRisk ? (
          <button
            type="button"
            onClick={onToggleRiskDetails}
            className="mt-3 flex w-full items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-500 hover:bg-slate-50"
            data-testid="toggle-risk-details"
            aria-expanded={riskDetailsOpen}
          >
            <span className="flex items-center gap-1.5">
              <ShieldCheck size={12} className="text-emerald-600" />
              低风险，无明显异常
            </span>
            {riskDetailsOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        ) : null}
        {(!isLowRisk || riskDetailsOpen) && <ActiveRiskSummary segment={activeSegment} />}
        {decisionText && (
          <div
            className="mt-2 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-emerald-700"
            data-testid="active-decision-status"
          >
            <ShieldCheck size={13} />
            <span className="min-w-0 flex-1 truncate">{decisionText}</span>
            <button
              type="button"
              onClick={onUndoDecision}
              disabled={saving}
              className="flex h-6 items-center gap-1 rounded border border-emerald-200 bg-white px-1.5 text-[11px] text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
              data-testid="undo-active-decision"
              title="撤销该决策"
            >
              <Undo2 size={11} />
              撤销
            </button>
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <ContextBlock
          data={data}
          previousSegment={previousSegment}
          currentSegment={activeSegment}
          nextSegment={nextSegment}
        />

        <CharacterLibraryMatchCard
          activeSpeakerLabel={activeSegment.speaker_label}
          matches={globalMatches}
          onBind={onBindGlobalCandidate}
          onRefresh={onRefreshGlobalMatches}
          bindingPersonaId={bindingPersonaId}
          loading={globalMatchesLoading}
        />

        <section className="mt-5">
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-xs font-semibold text-slate-900">快速改说话人</h4>
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
          </div>
          <div className="space-y-2">
            {speakerChoices.map((speaker, index) => {
              const active = speaker.speaker_label === activeSegment.speaker_label
              return (
                <button
                  key={speaker.speaker_label}
                  type="button"
                  onClick={() => onAssign(speaker.speaker_label)}
                  disabled={saving}
                  className={`flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm transition ${
                    active
                      ? 'border-blue-200 bg-blue-50 text-blue-800'
                      : 'border-slate-200 bg-white text-slate-800 hover:bg-slate-50'
                  } disabled:opacity-50`}
                  data-testid={`speaker-choice-${speaker.speaker_label}`}
                >
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-slate-900 text-xs font-semibold text-white">
                    {index + 1}
                  </span>
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: speakerColor(speaker.speaker_label) }}
                  />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {displayLabel(data, speaker.speaker_label)}
                  </span>
                  <span className="text-xs text-slate-500">{speaker.segment_count} 句</span>
                </button>
              )
            })}
          </div>
        </section>

        <section className="mt-5 space-y-2">
          <h4 className="text-xs font-semibold text-slate-900">当前句动作</h4>
          <button
            type="button"
            onClick={onKeep}
            disabled={saving}
            className="flex w-full items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
            data-testid="action-keep-current"
          >
            <Check size={14} />
            确认当前识别正确
          </button>
          <button
            type="button"
            onClick={() => previousSegment && onAssign(previousSegment.speaker_label)}
            disabled={saving || !previousSegment}
            className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-40"
            data-testid="action-assign-previous"
          >
            <ChevronLeft size={14} />
            归到上一句说话人
          </button>
          <button
            type="button"
            onClick={() => nextSegment && onAssign(nextSegment.speaker_label)}
            disabled={saving || !nextSegment}
            className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 hover:bg-slate-50 disabled:opacity-40"
            data-testid="action-assign-next"
          >
            <ChevronRight size={14} />
            归到下一句说话人
          </button>
        </section>

        <section className="mt-5">
          <h4 className="mb-2 flex items-center gap-1 text-xs font-semibold text-slate-900">
            <Users size={13} /> 全部说话人
          </h4>
          <div className="grid grid-cols-2 gap-2">
            {speakers.map(speaker => (
              <button
                key={speaker.speaker_label}
                type="button"
                onClick={() => onAssign(speaker.speaker_label)}
                disabled={saving}
                className="min-w-0 rounded-md border border-slate-200 px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <span className="flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: speakerColor(speaker.speaker_label) }}
                  />
                  <span className="truncate">{displayLabel(data, speaker.speaker_label)}</span>
                </span>
              </button>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}

function ContextBlock({
  data,
  previousSegment,
  currentSegment,
  nextSegment,
}: {
  data?: SpeakerReviewResponse
  previousSegment: SpeakerReviewSegment | null
  currentSegment: SpeakerReviewSegment
  nextSegment: SpeakerReviewSegment | null
}) {
  const rows = [
    { label: '上一句', segment: previousSegment },
    { label: '当前', segment: currentSegment },
    { label: '下一句', segment: nextSegment },
  ]
  return (
    <section>
      <h4 className="mb-2 text-xs font-semibold text-slate-900">上下文</h4>
      <div className="space-y-2">
        {rows.map(row => (
          <div
            key={row.label}
            className={`rounded-md border p-2 ${
              row.label === '当前' ? 'border-blue-200 bg-blue-50' : 'border-slate-200 bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-2 text-xs">
              <span className="w-10 shrink-0 text-slate-500">{row.label}</span>
              {row.segment ? (
                <>
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: speakerColor(row.segment.speaker_label) }}
                  />
                  <span className="min-w-0 truncate font-semibold text-slate-800">
                    {displayLabel(data, row.segment.speaker_label)}
                  </span>
                  {row.segment.risk_flags.length > 0 && (
                    <AlertTriangle
                      className="h-3 w-3 shrink-0 text-amber-600"
                      aria-label={`风险点：${riskFlagsLabel(row.segment.risk_flags)}`}
                    />
                  )}
                </>
              ) : (
                <span className="text-slate-400">无</span>
              )}
            </div>
            {row.segment && (
              <>
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-700">{row.segment.text}</p>
                {row.segment.risk_flags.length > 0 && (
                  <div className="mt-1 line-clamp-1 text-[11px] leading-4 text-amber-700">
                    风险点：{riskFlagsLabel(row.segment.risk_flags)}
                  </div>
                )}
              </>
            )}
          </div>
        ))}
      </div>
      {currentSegment.recommended_action && (
        <div
          className="mt-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs leading-5 text-amber-800"
          data-testid="system-recommendation"
        >
          <Wand2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          系统建议：{actionLabel(currentSegment.recommended_action)}
        </div>
      )}
    </section>
  )
}

function CharacterLibraryMatchCard({
  activeSpeakerLabel,
  matches,
  onBind,
  onRefresh,
  bindingPersonaId,
  loading,
}: {
  activeSpeakerLabel: string
  matches: SuggestFromGlobalMatch[]
  onBind: (candidate: SuggestFromGlobalCandidate, speakerLabel: string) => Promise<void>
  onRefresh: () => void
  bindingPersonaId: string | null
  loading: boolean
}) {
  const activeMatch = matches.find(m => m.speaker_label === activeSpeakerLabel)
  const candidates = activeMatch?.candidates ?? []
  const [boundState, setBoundState] = useState<{ speakerLabel: string; personaId: string | null }>({
    speakerLabel: activeSpeakerLabel,
    personaId: null,
  })
  const boundPersonaId =
    boundState.speakerLabel === activeSpeakerLabel ? boundState.personaId : null

  async function handleBind(candidate: SuggestFromGlobalCandidate, speakerLabel: string) {
    await onBind(candidate, speakerLabel)
    setBoundState({ speakerLabel, personaId: candidate.persona_id })
  }

  return (
    <section className="mt-5" data-testid="character-library-match-card">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <BookUser className="h-3.5 w-3.5 text-indigo-600" />
          <h4 className="text-xs font-semibold text-slate-900">
            {candidates.some(candidate => candidate.work_id) ? '作品角色候选' : '角色库匹配'}
          </h4>
          {loading && <Loader2 className="h-3 w-3 animate-spin text-slate-400" />}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="flex h-6 items-center gap-1 rounded border border-slate-200 px-1.5 text-[11px] text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          data-testid="refresh-character-library"
        >
          <Sparkles className="h-3 w-3" /> 重新匹配
        </button>
      </div>

      {candidates.length === 0 ? (
        <div
          className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-3 text-[11px] leading-5 text-slate-500"
          data-testid="character-library-empty"
        >
          暂无匹配到的角色库候选，你可以先点击上方「保存到角色库」沉淀当前任务里的人物。
        </div>
      ) : (
        <>
          <ul className="space-y-1.5" data-testid="character-library-candidate-list">
            {candidates.map(candidate => {
              const binding = bindingPersonaId === candidate.persona_id
              const bound = boundPersonaId === candidate.persona_id
              return (
                <li
                  key={candidate.persona_id}
                  className={`flex items-center gap-2 rounded-md border p-2 ${bound ? 'border-emerald-200 bg-emerald-50' : 'border-slate-200 bg-white'}`}
                  data-testid={`character-library-candidate-${candidate.persona_id}`}
                >
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm"
                    style={{
                      backgroundColor: candidate.color ? `${candidate.color}22` : '#eef2ff',
                      color: candidate.color ?? '#4f46e5',
                    }}
                  >
                    {candidate.avatar_emoji || '🎭'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-xs font-semibold text-slate-900">
                        {candidate.name || '(未命名角色)'}
                      </span>
                      {candidate.role && (
                        <span className="shrink-0 rounded bg-slate-100 px-1 text-[10px] text-slate-600">
                          {candidate.role}
                        </span>
                      )}
                      {bound ? (
                        <span className="ml-auto shrink-0 text-[10px] text-emerald-600 font-medium">已绑定</span>
                      ) : (
                        <span className="ml-auto shrink-0 text-[10px] text-indigo-600">
                          {Math.round((candidate.score ?? 0) * 100)}%
                        </span>
                      )}
                    </div>
                    {candidate.reason && !bound && (
                      <div className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">
                        {candidate.reason}
                      </div>
                    )}
                  </div>
                  {!bound && (
                    <button
                      type="button"
                      onClick={() => handleBind(candidate, activeSpeakerLabel)}
                      disabled={binding || boundPersonaId !== null}
                      className="flex h-7 shrink-0 items-center gap-1 rounded-md bg-indigo-600 px-2 text-[11px] font-semibold text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                      data-testid={`bind-character-library-${candidate.persona_id}`}
                    >
                      {binding ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                      绑定
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
          <div className="mt-2 flex justify-end">
            <a
              href="/character-library"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-indigo-500 hover:underline"
              data-testid="character-library-search-more"
            >
              搜索更多角色 →
            </a>
          </div>
        </>
      )}
    </section>
  )
}

export function SpeakerAvatar({ speakerLabel }: { speakerLabel: string }) {
  return (
    <span
      className="inline-flex h-5 w-5 items-center justify-center rounded-full text-white"
      style={{ backgroundColor: speakerColor(speakerLabel) }}
    >
      <UserRound className="h-3 w-3" />
    </span>
  )
}
