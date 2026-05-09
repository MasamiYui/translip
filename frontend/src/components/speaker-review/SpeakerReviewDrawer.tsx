import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  BookOpen,
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  GitMerge,
  Keyboard,
  Loader2,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  Sparkles,
  SkipBack,
  SkipForward,
  Trash2,
  Undo2,
  Upload,
  Users,
  UserRound,
  Volume2,
  Wand2,
  X,
} from 'lucide-react'
import { tasksApi, type PersonaBulkTemplate } from '../../api/tasks'
import type {
  PersonaSuggestCandidate,
  SpeakerPersonaBrief,
  SpeakerReviewDecisionPayload,
  SpeakerReviewResponse,
  SpeakerReviewRun,
  SpeakerReviewSegment,
  SpeakerReviewSpeaker,
} from '../../types'
import { useSpeakerReviewStore, type ReviewSelection } from './speakerReviewStore'

type QueueEntry =
  | { kind: 'speaker'; id: string; start: number; end: number; risk: string; speaker: SpeakerReviewSpeaker }
  | { kind: 'run'; id: string; start: number; end: number; risk: string; run: SpeakerReviewRun }
  | { kind: 'segment'; id: string; start: number; end: number; risk: string; segment: SpeakerReviewSegment }

const RISK_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 }

function formatDuration(value?: number | null) {
  if (!value && value !== 0) return '--'
  const total = Math.max(0, Math.round(value))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function fmtTime(value?: number | null) {
  if (value === undefined || value === null) return '0:00.0'
  const minutes = Math.floor(value / 60)
  const seconds = value - minutes * 60
  return `${minutes}:${seconds.toFixed(1).padStart(4, '0')}`
}

function riskColor(risk?: string | null) {
  if (risk === 'high') return 'text-rose-700 bg-rose-50 border-rose-200'
  if (risk === 'medium') return 'text-amber-700 bg-amber-50 border-amber-200'
  return 'text-emerald-700 bg-emerald-50 border-emerald-200'
}

function personaOf(
  data: SpeakerReviewResponse | undefined,
  speakerLabel: string | undefined | null,
): SpeakerPersonaBrief | null {
  if (!data || !speakerLabel) return null
  const map = data.personas?.by_speaker
  if (!map) return null
  return map[speakerLabel] ?? null
}

function displayLabel(
  data: SpeakerReviewResponse | undefined,
  speakerLabel: string | undefined | null,
): string {
  if (!speakerLabel) return '—'
  const p = personaOf(data, speakerLabel)
  if (p?.name) return p.name
  return speakerLabel
}

function personaDotStyle(color?: string | null): React.CSSProperties {
  return {
    backgroundColor: color || '#94a3b8',
  }
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
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [applyResult, setApplyResult] = useState<string | null>(null)
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return 220
    return window.localStorage.getItem('translip:sidebar-collapsed') === '1' ? 56 : 220
  })
  const [headerHeight, setHeaderHeight] = useState<number>(48)
  useEffect(() => {
    const handler = () => {
      setSidebarWidth(
        window.localStorage.getItem('translip:sidebar-collapsed') === '1' ? 56 : 220,
      )
      const headerEl = document.querySelector('header')
      if (headerEl instanceof HTMLElement) {
        setHeaderHeight(headerEl.getBoundingClientRect().height || 48)
      }
    }
    handler()
    window.addEventListener('storage', handler)
    const interval = window.setInterval(handler, 600)
    return () => {
      window.removeEventListener('storage', handler)
      window.clearInterval(interval)
    }
  }, [])

  const {
    selection,
    bulkSelection,
    filters,
    showShortcuts,
    pendingMerge,
    renamingSpeaker,
    renameDraft,
    showPersonaBulk,
    showPersonaSuggest,
    continuousRenaming,
    pendingConflict,
    showApplyPreview,
    applyPreviewData,
    showOnboarding,
    showGlobalPersonas,
    globalMatchToast,
    setSelection,
    toggleBulk,
    clearBulk,
    setFilters,
    setShowShortcuts,
    setPendingMerge,
    startRename,
    cancelRename,
    updateRenameDraft,
    setShowPersonaBulk,
    setShowPersonaSuggest,
    setContinuousRenaming,
    setPendingConflict,
    setShowApplyPreview,
    setApplyPreviewData,
    setShowOnboarding,
    setShowGlobalPersonas,
    setGlobalMatchToast,
    markUndo,
    markRedo,
  } = useSpeakerReviewStore()

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
      setApplyResult(data.archive_path ? `已归档旧产物到 ${data.archive_path}` : '已应用')
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const invalidateReview = () => queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })

  const createPersonaMutation = useMutation({
    mutationFn: (payload: { name: string; bindings?: string[]; force?: boolean; tts_voice_id?: string | null }) =>
      tasksApi.createSpeakerPersona(taskId, payload),
    onSuccess: invalidateReview,
  })
  const updatePersonaMutation = useMutation({
    mutationFn: (payload: {
      id: string
      name?: string
      color?: string | null
      force?: boolean
      tts_voice_id?: string | null
      tts_skip?: boolean
    }) => {
      const { id, ...rest } = payload
      return tasksApi.updateSpeakerPersona(taskId, id, rest)
    },
    onSuccess: invalidateReview,
  })
  const bindPersonaMutation = useMutation({
    mutationFn: ({ id, speaker }: { id: string; speaker: string }) =>
      tasksApi.bindSpeakerPersona(taskId, id, speaker),
    onSuccess: invalidateReview,
  })
  const unbindPersonaMutation = useMutation({
    mutationFn: ({ id, speaker }: { id: string; speaker: string }) =>
      tasksApi.unbindSpeakerPersona(taskId, id, speaker),
    onSuccess: invalidateReview,
  })
  const bulkPersonaMutation = useMutation({
    mutationFn: (template: PersonaBulkTemplate) => tasksApi.bulkCreateSpeakerPersonas(taskId, template),
    onSuccess: invalidateReview,
  })
  const suggestPersonaMutation = useMutation({
    mutationFn: () => tasksApi.suggestSpeakerPersonas(taskId),
  })
  const undoPersonaMutation = useMutation({
    mutationFn: () => tasksApi.undoSpeakerPersonas(taskId),
    onSuccess: () => {
      markUndo()
      invalidateReview()
    },
  })
  const redoPersonaMutation = useMutation({
    mutationFn: () => tasksApi.redoSpeakerPersonas(taskId),
    onSuccess: () => {
      markRedo()
      invalidateReview()
    },
  })
  const applyPreviewMutation = useMutation({
    mutationFn: () => tasksApi.previewSpeakerReviewApply(taskId),
    onSuccess: data => {
      setApplyPreviewData(data)
      setShowApplyPreview(true)
    },
  })

  const globalPersonasQuery = useQuery({
    queryKey: ['global-personas'],
    queryFn: () => tasksApi.listGlobalPersonas(),
    enabled: showGlobalPersonas,
  })
  const exportToGlobalMutation = useMutation({
    mutationFn: () => tasksApi.exportTaskPersonasToGlobal(taskId, { overwrite: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['global-personas'] })
    },
  })
  const importFromGlobalMutation = useMutation({
    mutationFn: (payload: { persona_ids: string[]; bindings_by_id?: Record<string, string[]> }) =>
      tasksApi.importPersonasFromGlobal(taskId, payload),
    onSuccess: () => {
      invalidateReview()
      setGlobalMatchToast(null)
    },
  })
  const suggestFromGlobalMutation = useMutation({
    mutationFn: (payload: { speakers?: Array<{ speaker_label: string; gender?: string | null; role?: string | null }> } = {}) =>
      tasksApi.suggestPersonasFromGlobal(taskId, payload),
    onSuccess: data => {
      const withHits = (data.matches || []).filter(m => (m.candidates || []).length > 0)
      if (withHits.length > 0) {
        setGlobalMatchToast({ matches: withHits, dismissedAt: null })
      }
    },
  })
  const deleteGlobalPersonaMutation = useMutation({
    mutationFn: (id: string) => tasksApi.deleteGlobalPersona(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['global-personas'] })
    },
  })

  const extractConflict = (err: unknown): import('../../types').PersonaNameConflict | null => {
    const anyErr = err as { response?: { status?: number; data?: { detail?: unknown } } }
    if (anyErr?.response?.status !== 409) return null
    const detail = anyErr.response.data?.detail
    if (detail && typeof detail === 'object' && (detail as Record<string, unknown>).code === 'persona_name_conflict') {
      return detail as import('../../types').PersonaNameConflict
    }
    return null
  }

  const findNextUnnamedSpeaker = (currentSpeaker: string | null): string | null => {
    const speakers = reviewQuery.data?.speakers ?? []
    const bySpeaker = reviewQuery.data?.personas?.by_speaker ?? {}
    const labels = speakers.map(s => s.speaker_label).filter((s): s is string => Boolean(s))
    const startIdx = currentSpeaker ? labels.indexOf(currentSpeaker) + 1 : 0
    for (let i = startIdx; i < labels.length; i += 1) {
      if (!bySpeaker[labels[i]]?.persona_id) return labels[i]
    }
    return null
  }

  const commitRename = async () => {
    if (!renamingSpeaker) return
    const speakerToName = renamingSpeaker
    const name = renameDraft.trim()
    if (!name) {
      cancelRename()
      return
    }
    const bundle = reviewQuery.data?.personas
    const existing = bundle?.by_speaker?.[speakerToName]
    try {
      if (existing?.persona_id) {
        await updatePersonaMutation.mutateAsync({ id: existing.persona_id, name })
      } else {
        await createPersonaMutation.mutateAsync({ name, bindings: [speakerToName] })
      }
      cancelRename()
      if (continuousRenaming) {
        const next = findNextUnnamedSpeaker(speakerToName)
        if (next) {
          startRename(next, '')
        } else {
          setContinuousRenaming(false)
        }
      }
    } catch (err) {
      const conflict = extractConflict(err)
      if (conflict) {
        setPendingConflict({
          conflict,
          attempted: existing?.persona_id
            ? { kind: 'rename', name, personaId: existing.persona_id, speaker: speakerToName }
            : { kind: 'create', name, speaker: speakerToName },
        })
      } else {
        cancelRename()
      }
    }
  }

  const resolveConflictWithForce = async () => {
    if (!pendingConflict) return
    const { attempted } = pendingConflict
    try {
      if (attempted.kind === 'rename' && attempted.personaId) {
        await updatePersonaMutation.mutateAsync({
          id: attempted.personaId,
          name: attempted.name,
          force: true,
        })
      } else {
        await createPersonaMutation.mutateAsync({
          name: attempted.name,
          bindings: attempted.speaker ? [attempted.speaker] : [],
          force: true,
        })
      }
    } finally {
      setPendingConflict(null)
      cancelRename()
    }
  }

  const resolveConflictByMerge = async () => {
    if (!pendingConflict) return
    const { conflict, attempted } = pendingConflict
    if (attempted.speaker && conflict.existing_id) {
      try {
        await bindPersonaMutation.mutateAsync({ id: conflict.existing_id, speaker: attempted.speaker })
      } finally {
        setPendingConflict(null)
        cancelRename()
      }
    } else {
      setPendingConflict(null)
    }
  }

  const queue = useMemo(() => buildQueue(reviewQuery.data), [reviewQuery.data])

  const filteredQueue = useMemo(() => {
    let rows = queue.filter(r => filters.risk.includes(r.risk as never))
    if (filters.onlyUndecided) {
      rows = rows.filter(r => !getDecisionFor(r))
    }
    if (filters.sortBy === 'time') {
      rows = [...rows].sort((a, b) => a.start - b.start)
    } else {
      rows = [...rows].sort(
        (a, b) => (RISK_ORDER[a.risk] ?? 9) - (RISK_ORDER[b.risk] ?? 9) || a.start - b.start,
      )
    }
    return rows
  }, [queue, filters])

  const selected = useMemo(() => findSelected(reviewQuery.data, selection), [reviewQuery.data, selection])

  const audioSrc = useMemo(() => {
    if (!selected) return null
    const sel = selected as { audio_url?: string | null; reference_clips?: Array<{ url?: string | null }> }
    return sel.audio_url ?? sel.reference_clips?.[0]?.url ?? null
  }, [selected])

  useEffect(() => {
    if (audioSrc && audioRef.current) {
      audioRef.current.src = audioSrc
      audioRef.current.load()
    }
  }, [audioSrc])

  useEffect(() => {
    if (!isOpen) return
    const handler = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      const mod = event.metaKey || event.ctrlKey
      if (mod && event.shiftKey && (event.key === 'z' || event.key === 'Z')) {
        event.preventDefault()
        redoPersonaMutation.mutate()
        return
      }
      if (mod && (event.key === 'z' || event.key === 'Z')) {
        event.preventDefault()
        undoPersonaMutation.mutate()
        return
      }
      if (mod && event.shiftKey && (event.key === 'p' || event.key === 'P')) {
        event.preventDefault()
        applyPreviewMutation.mutate()
        return
      }
      if (event.key === '?') {
        setShowShortcuts(!showShortcuts)
        return
      }
      if (event.key === 'Escape') {
        if (pendingConflict) {
          setPendingConflict(null)
          return
        }
        if (showApplyPreview) {
          setShowApplyPreview(false)
          return
        }
        if (showOnboarding) {
          setShowOnboarding(false)
          return
        }
        if (continuousRenaming) {
          setContinuousRenaming(false)
          return
        }
        if (pendingMerge) {
          setPendingMerge(null)
          return
        }
        if (renamingSpeaker) {
          cancelRename()
          return
        }
        if (showPersonaBulk) {
          setShowPersonaBulk(false)
          return
        }
        if (showPersonaSuggest) {
          setShowPersonaSuggest(false)
          return
        }
        onClose()
        return
      }
      if (event.key === ' ') {
        event.preventDefault()
        const el = audioRef.current
        if (!el) return
        if (el.paused) {
          el.play().catch(() => undefined)
          setIsPlaying(true)
        } else {
          el.pause()
          setIsPlaying(false)
        }
        return
      }
      if (event.shiftKey && (event.key === 'h' || event.key === 'H')) {
        event.preventDefault()
        setContinuousRenaming(true)
        const next = findNextUnnamedSpeaker(null)
        if (next) {
          startRename(next, '')
        }
        return
      }
      if (event.key === 'h' || event.key === 'H') {
        event.preventDefault()
        const targetSpeaker =
          selection?.kind === 'speaker'
            ? selection.id
            : selection?.kind === 'run'
              ? (reviewQuery.data?.speaker_runs.find(r => r.run_id === selection.id)?.speaker_label ?? null)
              : selection?.kind === 'segment'
                ? (reviewQuery.data?.segments.find(s => s.segment_id === selection.id)?.speaker_label ?? null)
                : null
        if (targetSpeaker) {
          const current = personaOf(reviewQuery.data, targetSpeaker)
          startRename(targetSpeaker, current?.name ?? '')
        }
        return
      }
      if (event.key === 'b' || event.key === 'B') {
        event.preventDefault()
        setShowPersonaBulk(true)
        return
      }
      if (event.key === 'g' || event.key === 'G') {
        event.preventDefault()
        setShowPersonaSuggest(true)
        suggestPersonaMutation.mutate()
        return
      }
      if (event.key === 'j' || event.key === 'ArrowDown') {
        event.preventDefault()
        if (!filteredQueue.length) return
        const idx = filteredQueue.findIndex(entry => entry.id === selection?.id && entry.kind === selection?.kind)
        const next = filteredQueue[Math.min(Math.max(idx + 1, 0), filteredQueue.length - 1)]
        if (next) setSelection({ kind: next.kind, id: next.id })
      } else if (event.key === 'k' || event.key === 'ArrowUp') {
        event.preventDefault()
        if (!filteredQueue.length) return
        const idx = filteredQueue.findIndex(entry => entry.id === selection?.id && entry.kind === selection?.kind)
        const next = filteredQueue[Math.min(Math.max(idx - 1, 0), filteredQueue.length - 1)]
        if (next) setSelection({ kind: next.kind, id: next.id })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [
    isOpen,
    showShortcuts,
    pendingMerge,
    filteredQueue,
    selection,
    onClose,
    setShowShortcuts,
    setPendingMerge,
    setSelection,
    renamingSpeaker,
    cancelRename,
    showPersonaBulk,
    showPersonaSuggest,
    setShowPersonaBulk,
    setShowPersonaSuggest,
    startRename,
    reviewQuery.data,
    suggestPersonaMutation,
    undoPersonaMutation,
    redoPersonaMutation,
    applyPreviewMutation,
    pendingConflict,
    setPendingConflict,
    showApplyPreview,
    setShowApplyPreview,
    showOnboarding,
    setShowOnboarding,
    continuousRenaming,
    setContinuousRenaming,
  ])

  useEffect(() => {
    if (!isOpen) return
    try {
      const key = 'speaker-review-onboarded-v1'
      const done = window.localStorage.getItem(key)
      if (!done) {
        setShowOnboarding(true)
      }
    } catch {
      // localStorage may be unavailable in some environments; ignore
    }
  }, [isOpen, setShowOnboarding])

  const suggestFromGlobalRef = useRef(suggestFromGlobalMutation)
  suggestFromGlobalRef.current = suggestFromGlobalMutation
  const lastSuggestedTaskRef = useRef<string | null>(null)
  useEffect(() => {
    if (!isOpen) return
    const reviewData = reviewQuery.data
    if (!reviewData) return
    if (lastSuggestedTaskRef.current === taskId) return
    const speakers = (reviewData.speakers || [])
      .map(sp => ({ speaker_label: String(sp.speaker_label || ''), gender: null, role: null }))
      .filter(s => s.speaker_label)
    if (speakers.length === 0) return
    lastSuggestedTaskRef.current = taskId
    suggestFromGlobalRef.current.mutate({ speakers })
  }, [isOpen, reviewQuery.data, taskId])

  const dismissOnboarding = () => {
    try {
      window.localStorage.setItem('speaker-review-onboarded-v1', '1')
    } catch {
      // ignore
    }
    setShowOnboarding(false)
  }

  const togglePlay = () => {
    const el = audioRef.current
    if (!el) return
    if (el.paused) {
      el.play().catch(() => undefined)
      setIsPlaying(true)
    } else {
      el.pause()
      setIsPlaying(false)
    }
  }

  const handleDecision = (payload: SpeakerReviewDecisionPayload) => {
    decisionMutation.mutate(payload)
  }

  const confirmMerge = () => {
    if (!pendingMerge) return
    const selectedRun = selected && 'run_id' in selected ? (selected as SpeakerReviewRun) : null
    if (selectedRun) {
      handleDecision({
        item_id: selectedRun.run_id,
        item_type: 'speaker_run',
        decision: 'merge_speaker',
        payload: { target_speaker: pendingMerge.target, source_speaker: pendingMerge.source },
      })
    } else {
      handleDecision({
        item_id: `speaker:${pendingMerge.source}`,
        item_type: 'speaker_profile',
        decision: 'merge_speaker',
        payload: { target_speaker: pendingMerge.target, source_speaker: pendingMerge.source },
      })
    }
    setPendingMerge(null)
  }

  if (!isOpen) return null

  const data = reviewQuery.data

  return (
    <div
      className="fixed inset-y-0 right-0 z-40 flex items-stretch bg-[#F5F7FB]"
      style={{ left: sidebarWidth, top: headerHeight }}
      data-testid="speaker-review-drawer"
    >
      <div className="flex h-full w-full flex-col bg-[#F5F7FB]">
        <Topbar
          data={data}
          onClose={onClose}
          onApply={() => applyMutation.mutate()}
          applying={applyMutation.isPending}
          applyResult={applyResult}
          onRerunFromTaskB={onRerunFromTaskB}
          onToggleShortcuts={() => setShowShortcuts(!showShortcuts)}
          onOpenBulk={() => setShowPersonaBulk(true)}
          onOpenSuggest={() => {
            setShowPersonaSuggest(true)
            suggestPersonaMutation.mutate()
          }}
          onUndo={() => undoPersonaMutation.mutate()}
          undoing={undoPersonaMutation.isPending}
          onRedo={() => redoPersonaMutation.mutate()}
          onApplyPreview={() => applyPreviewMutation.mutate()}
          onOpenGlobalPersonas={() => setShowGlobalPersonas(true)}
        />

        <GlobalAudioPlayer
          audioRef={audioRef}
          src={audioSrc}
          isPlaying={isPlaying}
          onToggle={togglePlay}
          onEnded={() => setIsPlaying(false)}
          label={selected ? describeSelection(selected, data) : '未选中'}
        />

        <div className="grid flex-1 grid-cols-[300px_1fr_380px] gap-3 overflow-hidden bg-[#F5F7FB] p-3">
          <RosterPanel
            data={data}
            onSelect={sel => setSelection(sel)}
            selection={selection}
            onMergeSuggest={(source, target) => setPendingMerge({ source, target })}
            renamingSpeaker={renamingSpeaker}
            renameDraft={renameDraft}
            onStartRename={(speaker, initial) => startRename(speaker, initial)}
            onChangeRename={updateRenameDraft}
            onCommitRename={() => { void commitRename() }}
            onCancelRename={cancelRename}
            onUnbind={(personaId, speaker) => unbindPersonaMutation.mutate({ id: personaId, speaker })}
            onEditVoice={(personaId, currentVoiceId) => {
              const input = window.prompt('设置 TTS 配音 voice_id（留空=使用默认）', currentVoiceId ?? '')
              if (input === null) return
              const next = input.trim() || null
              updatePersonaMutation.mutate({ id: personaId, tts_voice_id: next })
            }}
          />

          <ReviewQueue
            entries={filteredQueue}
            filters={filters}
            setFilters={setFilters}
            onSelect={sel => setSelection(sel)}
            selection={selection}
            bulkSelection={bulkSelection}
            onToggleBulk={toggleBulk}
            onClearBulk={clearBulk}
            onBulkKeep={() => handleBulkKeep(filteredQueue, bulkSelection, handleDecision, clearBulk)}
            data={data}
          />

          <InspectorPanel
            selected={selected}
            onDecision={handleDecision}
            onDeleteDecision={itemId => deleteDecisionMutation.mutate(itemId)}
            loading={decisionMutation.isPending || deleteDecisionMutation.isPending}
            data={data}
            onRename={(speaker, initial) => startRename(speaker, initial)}
            onBindToPersona={(personaId, speaker) =>
              bindPersonaMutation.mutate({ id: personaId, speaker })
            }
          />
        </div>

        {pendingMerge && (
          <MergeConfirmModal
            pending={pendingMerge}
            onCancel={() => setPendingMerge(null)}
            onConfirm={confirmMerge}
          />
        )}

        {showPersonaBulk && (
          <PersonaBulkModal
            onCancel={() => setShowPersonaBulk(false)}
            onPick={template => {
              bulkPersonaMutation.mutate(template, {
                onSuccess: () => setShowPersonaBulk(false),
              })
            }}
            loading={bulkPersonaMutation.isPending}
          />
        )}

        {showPersonaSuggest && (
          <PersonaSuggestModal
            onCancel={() => setShowPersonaSuggest(false)}
            loading={suggestPersonaMutation.isPending}
            suggestions={suggestPersonaMutation.data?.suggestions ?? {}}
            data={data}
            onAccept={(speaker, name) => {
              const bundle = reviewQuery.data?.personas
              const existing = bundle?.by_speaker?.[speaker]
              if (existing?.persona_id) {
                updatePersonaMutation.mutate({ id: existing.persona_id, name })
              } else {
                createPersonaMutation.mutate({ name, bindings: [speaker] })
              }
            }}
          />
        )}

        {showShortcuts && <ShortcutsModal onClose={() => setShowShortcuts(false)} />}

        {pendingConflict && (
          <PersonaConflictModal
            conflict={pendingConflict.conflict}
            onCancel={() => {
              setPendingConflict(null)
              cancelRename()
            }}
            onRenameAnyway={() => { void resolveConflictWithForce() }}
            onMerge={() => { void resolveConflictByMerge() }}
            canMerge={Boolean(pendingConflict.attempted.speaker)}
          />
        )}

        {showApplyPreview && (
          <ApplyDiffPreviewModal
            data={applyPreviewData}
            loading={applyPreviewMutation.isPending}
            onClose={() => setShowApplyPreview(false)}
            onConfirm={() => {
              setShowApplyPreview(false)
              applyMutation.mutate()
            }}
          />
        )}

        {showOnboarding && (
          <OnboardingGuide onDismiss={dismissOnboarding} />
        )}

        {showGlobalPersonas && (
          <GlobalPersonaModal
            onClose={() => setShowGlobalPersonas(false)}
            loading={globalPersonasQuery.isLoading}
            data={globalPersonasQuery.data}
            onExportFromTask={() => exportToGlobalMutation.mutate()}
            exporting={exportToGlobalMutation.isPending}
            exportResult={exportToGlobalMutation.data ?? null}
            onImportIds={ids => {
              if (ids.length === 0) return
              importFromGlobalMutation.mutate({ persona_ids: ids })
            }}
            importing={importFromGlobalMutation.isPending}
            onDeleteGlobal={id => deleteGlobalPersonaMutation.mutate(id)}
          />
        )}

        {globalMatchToast && globalMatchToast.matches.length > 0 && (
          <GlobalMatchToast
            matches={globalMatchToast.matches}
            onDismiss={() => setGlobalMatchToast(null)}
            onImportAll={() => {
              const ids = Array.from(
                new Set(
                  globalMatchToast.matches
                    .flatMap(m => (m.candidates?.[0]?.persona_id ? [m.candidates[0].persona_id] : []))
                    .map(String),
                ),
              )
              const bindings: Record<string, string[]> = {}
              globalMatchToast.matches.forEach(m => {
                const cand = m.candidates?.[0]
                if (!cand?.persona_id) return
                const pid = String(cand.persona_id)
                bindings[pid] = [...(bindings[pid] || []), m.speaker_label]
              })
              if (ids.length === 0) return
              importFromGlobalMutation.mutate({ persona_ids: ids, bindings_by_id: bindings })
            }}
            importing={importFromGlobalMutation.isPending}
          />
        )}

        {continuousRenaming && (
          <div
            className="pointer-events-none fixed left-1/2 top-20 z-50 -translate-x-1/2 rounded-full bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white shadow-lg"
            data-testid="continuous-renaming-banner"
          >
            连续命名模式 · 按 Esc 退出
          </div>
        )}
      </div>
    </div>
  )
}

const TOPBAR_ICON_BTN =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent'

function Topbar({
  data,
  onClose,
  onApply,
  applying,
  applyResult,
  onRerunFromTaskB,
  onToggleShortcuts,
  onOpenBulk,
  onOpenSuggest,
  onUndo,
  undoing,
  onRedo,
  onApplyPreview,
  onOpenGlobalPersonas,
}: {
  data?: SpeakerReviewResponse
  onClose: () => void
  onApply: () => void
  applying: boolean
  applyResult: string | null
  onRerunFromTaskB?: () => void
  onToggleShortcuts: () => void
  onOpenBulk: () => void
  onOpenSuggest: () => void
  onUndo: () => void
  undoing: boolean
  onRedo?: () => void
  onApplyPreview?: () => void
  onOpenGlobalPersonas?: () => void
}) {
  const summary = data?.summary
  return (
    <div
      className="shrink-0 border-b border-slate-200 bg-white"
      data-testid="speaker-review-topbar"
    >
      <div className="flex h-12 items-center gap-2 px-3">
        <div className="flex min-w-0 shrink items-center gap-1.5">
          <button
            type="button"
            onClick={onClose}
            className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
            title="返回任务详情"
            data-testid="close-drawer"
          >
            <ArrowLeft size={14} />
          </button>
          <span className="min-w-0 truncate text-sm font-semibold text-slate-900" title="说话人核对">
            说话人核对
          </span>
        </div>

        <span className="h-4 w-px shrink-0 bg-slate-200" aria-hidden="true" />

        <div className="flex shrink-0 items-center gap-1.5 text-[11px]">
          <StatBadge label="说话人" value={summary?.speaker_count} />
          <StatBadge label="待审" value={summary?.review_segment_count} />
          <StatBadge label="高风险" value={summary?.high_risk_run_count} tone="warn" />
          <StatBadge label="已决策" value={summary?.decision_count} tone="ok" />
          {(summary?.unnamed_speaker_count ?? 0) > 0 && (
            <span
              className="inline-flex h-6 items-center gap-1 rounded-md border border-rose-200 bg-rose-50 px-1.5 text-[11px] leading-none text-rose-700"
              data-testid="unnamed-badge"
            >
              <span>未命名</span>
              <strong className="font-semibold tabular-nums">
                {summary?.unnamed_speaker_count ?? 0}
              </strong>
            </span>
          )}
        </div>

        <div className="flex-1" />

        {applyResult && (
          <span className="truncate text-[11px] text-emerald-700" data-testid="apply-result">
            {applyResult}
          </span>
        )}

        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            className={TOPBAR_ICON_BTN}
            onClick={onOpenSuggest}
            data-testid="persona-suggest-button"
            title="智能建议昵称 (G)"
            aria-label="智能建议"
          >
            <Sparkles size={14} />
          </button>
          <button
            type="button"
            className={TOPBAR_ICON_BTN}
            onClick={onOpenBulk}
            data-testid="persona-bulk-button"
            title="批量命名 (B)"
            aria-label="批量命名"
          >
            <Users size={14} />
          </button>
          <button
            type="button"
            className={TOPBAR_ICON_BTN}
            onClick={onUndo}
            disabled={undoing}
            data-testid="persona-undo-button"
            title="撤销 (Cmd+Z)"
            aria-label="撤销"
          >
            {undoing ? <Loader2 size={13} className="animate-spin" /> : <Undo2 size={14} />}
          </button>
          {onRedo && (
            <button
              type="button"
              className={TOPBAR_ICON_BTN}
              onClick={onRedo}
              data-testid="persona-redo-button"
              title="重做 (Cmd+Shift+Z)"
              aria-label="重做"
            >
              <Undo2 size={14} className="-scale-x-100" />
            </button>
          )}
          {onApplyPreview && (
            <button
              type="button"
              className={TOPBAR_ICON_BTN}
              onClick={onApplyPreview}
              data-testid="persona-apply-preview-button"
              title="应用前预览 (Cmd+Shift+P)"
              aria-label="应用前预览"
            >
              <Sparkles size={14} className="text-indigo-500" />
            </button>
          )}
          {onOpenGlobalPersonas && (
            <button
              type="button"
              className={TOPBAR_ICON_BTN}
              onClick={onOpenGlobalPersonas}
              data-testid="global-personas-button"
              title="角色库 (跨任务复用)"
              aria-label="角色库"
            >
              <BookOpen size={14} className="text-amber-600" />
            </button>
          )}
          <button
            type="button"
            className={TOPBAR_ICON_BTN}
            onClick={onToggleShortcuts}
            data-testid="shortcuts-button"
            title="快捷键帮助"
            aria-label="快捷键"
          >
            <Keyboard size={14} />
          </button>
          {onRerunFromTaskB && (
            <button
              type="button"
              className={TOPBAR_ICON_BTN}
              onClick={onRerunFromTaskB}
              title="从 Task B 重跑"
              aria-label="重跑 Task B"
            >
              <RotateCcw size={14} />
            </button>
          )}

          <span className="mx-1 h-4 w-px bg-slate-200" aria-hidden="true" />

          <button
            type="button"
            className="flex h-8 items-center gap-1 rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            onClick={onApply}
            disabled={applying}
            data-testid="apply-decisions"
            title="应用所有决策"
          >
            {applying ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            应用决策
          </button>
        </div>
      </div>
    </div>
  )
}

function StatBadge({ label, value, tone }: { label: string; value?: number; tone?: 'ok' | 'warn' }) {
  const cls =
    tone === 'warn'
      ? 'border-amber-200 bg-amber-50 text-amber-700'
      : tone === 'ok'
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
        : 'border-slate-200 bg-slate-50 text-slate-600'
  return (
    <span
      className={`inline-flex h-6 items-center gap-1 rounded-md border px-1.5 text-[11px] leading-none ${cls}`}
    >
      <span className="text-slate-500">{label}</span>
      <strong className="font-semibold tabular-nums">{value ?? 0}</strong>
    </span>
  )
}

function GlobalAudioPlayer({
  audioRef,
  src,
  isPlaying,
  onToggle,
  onEnded,
  label,
}: {
  audioRef: React.MutableRefObject<HTMLAudioElement | null>
  src: string | null
  isPlaying: boolean
  onToggle: () => void
  onEnded: () => void
  label: string
}) {
  return (
    <div
      className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-2"
      data-testid="global-audio-player"
    >
      <button
        type="button"
        className="flex h-7 w-7 items-center justify-center rounded-md bg-emerald-600 text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
        onClick={onToggle}
        disabled={!src}
        data-testid="play-toggle"
        title={isPlaying ? '暂停' : '播放'}
      >
        {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
      </button>
      <div className="min-w-0 flex-1 truncate text-xs text-slate-700" data-testid="player-label">
        {label}
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2 text-[11px] text-slate-500">
        <SkipBack className="h-3.5 w-3.5" />
        <span>按 J/K 切换</span>
        <SkipForward className="h-3.5 w-3.5" />
      </div>
      <audio
        ref={audioRef}
        className="hidden"
        onEnded={onEnded}
        onPause={() => undefined}
        data-testid="audio-element"
      />
    </div>
  )
}

function RosterPanel({
  data,
  onSelect,
  selection,
  onMergeSuggest,
  renamingSpeaker,
  renameDraft,
  onStartRename,
  onChangeRename,
  onCommitRename,
  onCancelRename,
  onUnbind,
  onEditVoice,
}: {
  data?: SpeakerReviewResponse
  onSelect: (selection: ReviewSelection) => void
  selection: ReviewSelection | null
  onMergeSuggest: (source: string, target: string) => void
  renamingSpeaker: string | null
  renameDraft: string
  onStartRename: (speaker: string, initial: string) => void
  onChangeRename: (value: string) => void
  onCommitRename: () => void
  onCancelRename: () => void
  onUnbind: (personaId: string, speaker: string) => void
  onEditVoice?: (personaId: string, currentVoiceId: string | null | undefined) => void
}) {
  const speakers = data?.speakers ?? []
  return (
    <aside
      className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
      data-testid="roster-panel"
    >
      <header className="border-b border-slate-200 px-4 py-3 text-xs font-semibold text-slate-800">
        说话人花名册（{speakers.length}）
      </header>
      <div className="flex-1 overflow-y-auto">
        {speakers.map(sp => {
          const active = selection?.kind === 'speaker' && selection.id === sp.speaker_label
          const persona = personaOf(data, sp.speaker_label)
          const isRenaming = renamingSpeaker === sp.speaker_label
          return (
            <div
              key={sp.speaker_label}
              className={`cursor-pointer border-b border-slate-200 px-4 py-3 text-xs transition ${
                active ? 'bg-slate-100' : 'hover:bg-slate-50'
              }`}
              onClick={() => onSelect({ kind: 'speaker', id: sp.speaker_label })}
              data-testid={`roster-item-${sp.speaker_label}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className="relative flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] text-white"
                    style={personaDotStyle(persona?.color)}
                    aria-hidden="true"
                  >
                    {persona?.avatar_emoji ?? <UserRound className="h-3 w-3" />}
                    {!persona?.persona_id && (
                      <span
                        className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-rose-500"
                        style={{ animation: 'speaker-review-pulse 1.2s ease-in-out infinite' }}
                        data-testid={`unnamed-dot-${sp.speaker_label}`}
                      />
                    )}
                  </span>
                  {isRenaming ? (
                    <input
                      autoFocus
                      value={renameDraft}
                      onChange={event => onChangeRename(event.target.value)}
                      onClick={event => event.stopPropagation()}
                      onKeyDown={event => {
                        if (event.key === 'Enter') {
                          event.preventDefault()
                          onCommitRename()
                        } else if (event.key === 'Escape') {
                          event.preventDefault()
                          onCancelRename()
                        }
                      }}
                      onBlur={() => onCommitRename()}
                      placeholder="输入昵称"
                      className="w-28 rounded border border-emerald-400 bg-white px-1.5 py-0.5 text-xs text-slate-900 outline-none"
                      data-testid={`rename-input-${sp.speaker_label}`}
                    />
                  ) : (
                    <span
                      className="min-w-0 truncate font-semibold text-slate-900"
                      data-testid={`speaker-display-${sp.speaker_label}`}
                    >
                      {persona?.name ?? sp.speaker_label}
                    </span>
                  )}
                  {persona?.name && (
                    <span
                      className="rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500"
                      title="原始标签"
                    >
                      {sp.speaker_label}
                    </span>
                  )}
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${riskColor(sp.risk_level)}`}
                  >
                    {sp.risk_level}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1 text-slate-500">
                  <button
                    type="button"
                    className="flex h-6 w-6 items-center justify-center rounded hover:bg-slate-100"
                    onClick={event => {
                      event.stopPropagation()
                      onStartRename(sp.speaker_label, persona?.name ?? '')
                    }}
                    data-testid={`rename-${sp.speaker_label}`}
                    title="重命名 (H)"
                    aria-label="重命名"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                  {persona?.persona_id && onEditVoice && (
                    <button
                      type="button"
                      className="flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-indigo-500"
                      onClick={event => {
                        event.stopPropagation()
                        const fullPersona = data?.personas?.items.find(p => p.id === persona.persona_id)
                        onEditVoice(persona.persona_id!, fullPersona?.tts_voice_id ?? null)
                      }}
                      data-testid={`voice-edit-${sp.speaker_label}`}
                      title="设置 TTS 配音"
                      aria-label="设置 TTS 配音"
                    >
                      <Volume2 className="h-3 w-3" />
                    </button>
                  )}
                  {persona?.persona_id && (
                    <button
                      type="button"
                      className="flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-rose-500"
                      onClick={event => {
                        event.stopPropagation()
                        onUnbind(persona.persona_id!, sp.speaker_label)
                      }}
                      data-testid={`unbind-${sp.speaker_label}`}
                      title="解除绑定"
                      aria-label="解除绑定"
                    >
                      <Ban className="h-3 w-3" />
                    </button>
                  )}
                  <span className="ml-1 text-slate-500">{sp.segment_count} 段</span>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                <span>{formatDuration(sp.total_speech_sec)}</span>
                <span>平均 {sp.avg_duration_sec.toFixed(1)}s</span>
                {sp.risk_flags?.map(flag => (
                  <span
                    key={flag}
                    className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] text-slate-700"
                  >
                    {flag}
                  </span>
                ))}
              </div>
              {!!sp.similar_peers?.length && (
                <div className="mt-2 space-y-1">
                  {sp.similar_peers.map(peer => (
                    <button
                      key={peer.label}
                      type="button"
                      onClick={event => {
                        event.stopPropagation()
                        onMergeSuggest(sp.speaker_label, peer.label)
                      }}
                      className="flex w-full items-center justify-between rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700 hover:bg-amber-100"
                      data-testid={`suggest-merge-${sp.speaker_label}-${peer.label}`}
                    >
                      <span className="flex items-center gap-1">
                        <GitMerge className="h-3 w-3" />合并到 {displayLabel(data, peer.label)}
                      </span>
                      <span>相似度 {(peer.similarity * 100).toFixed(0)}%</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}

function ReviewQueue({
  entries,
  filters,
  setFilters,
  onSelect,
  selection,
  bulkSelection,
  onToggleBulk,
  onClearBulk,
  onBulkKeep,
  data,
}: {
  entries: QueueEntry[]
  filters: { risk: string[]; onlyUndecided: boolean; sortBy: 'time' | 'risk' }
  setFilters: (
    updater: (value: { risk: ('high' | 'medium' | 'low')[]; onlyUndecided: boolean; sortBy: 'time' | 'risk' }) => {
      risk: ('high' | 'medium' | 'low')[]
      onlyUndecided: boolean
      sortBy: 'time' | 'risk'
    },
  ) => void
  onSelect: (selection: ReviewSelection) => void
  selection: ReviewSelection | null
  bulkSelection: Set<string>
  onToggleBulk: (id: string) => void
  onClearBulk: () => void
  onBulkKeep: () => void
  data?: SpeakerReviewResponse
}) {
  return (
    <section
      className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
      data-testid="review-queue"
    >
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3">
        <span className="text-xs font-semibold text-slate-900">待审队列（{entries.length}）</span>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-slate-500">
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={filters.onlyUndecided}
              onChange={event =>
                setFilters(current => ({ ...current, onlyUndecided: event.target.checked }))
              }
              data-testid="filter-undecided"
            />
            仅未决
          </label>
          <select
            value={filters.sortBy}
            onChange={event =>
              setFilters(current => ({
                ...current,
                sortBy: event.target.value as 'time' | 'risk',
              }))
            }
            className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]"
            data-testid="sort-by"
          >
            <option value="risk">按风险</option>
            <option value="time">按时间</option>
          </select>
          {bulkSelection.size > 0 && (
            <div className="flex items-center gap-1">
              <button
                type="button"
                className="rounded-md bg-emerald-600 px-2 py-1 text-[11px] text-white"
                onClick={onBulkKeep}
                data-testid="bulk-keep"
              >
                批量保留 ({bulkSelection.size})
              </button>
              <button
                type="button"
                className="rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-700"
                onClick={onClearBulk}
              >
                清空
              </button>
            </div>
          )}
        </div>
      </header>
      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">
            没有需要处理的条目，好棒！
          </div>
        ) : (
          entries.map(entry => {
            const active = selection?.kind === entry.kind && selection.id === entry.id
            const isBulk = bulkSelection.has(entry.id)
            const decision = getDecisionFor(entry)
            return (
              <div
                key={`${entry.kind}:${entry.id}`}
                className={`flex cursor-pointer items-start gap-3 border-b border-slate-200 px-4 py-3 text-xs transition ${
                  active ? 'bg-slate-100' : 'hover:bg-slate-50'
                }`}
                onClick={() => onSelect({ kind: entry.kind, id: entry.id })}
                data-testid={`queue-item-${entry.id}`}
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={isBulk}
                  onClick={event => event.stopPropagation()}
                  onChange={() => onToggleBulk(entry.id)}
                  data-testid={`queue-check-${entry.id}`}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[10px] ${riskColor(entry.risk)}`}
                    >
                      {entry.risk}
                    </span>
                    <span className="font-semibold text-slate-900">
                      {displayLabel(
                        data,
                        entry.kind === 'speaker'
                          ? entry.speaker.speaker_label
                          : entry.kind === 'run'
                            ? entry.run.speaker_label
                            : entry.segment.speaker_label,
                      )}
                    </span>
                    <span className="text-slate-500">
                      {fmtTime(entry.start)} – {fmtTime(entry.end)}
                    </span>
                    {decision && (
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700">
                        ✓ {decision.decision}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 line-clamp-2 text-slate-700">
                    {entry.kind === 'speaker'
                      ? `${entry.speaker.segment_count} 段，平均 ${entry.speaker.avg_duration_sec.toFixed(1)}s`
                      : entry.kind === 'run'
                        ? entry.run.text
                        : entry.segment.text}
                  </p>
                </div>
              </div>
            )
          })
        )}
      </div>
    </section>
  )
}

function InspectorPanel({
  selected,
  onDecision,
  onDeleteDecision,
  loading,
  data,
  onRename,
  onBindToPersona,
}: {
  selected: SpeakerReviewSpeaker | SpeakerReviewRun | SpeakerReviewSegment | null
  onDecision: (payload: SpeakerReviewDecisionPayload) => void
  onDeleteDecision: (itemId: string) => void
  loading: boolean
  data?: SpeakerReviewResponse
  onRename: (speaker: string, initial: string) => void
  onBindToPersona: (personaId: string, speaker: string) => void
}) {
  if (!selected) {
    return (
      <aside
        className="flex h-full items-center justify-center rounded-lg border border-slate-200 bg-white text-xs text-slate-500 shadow-sm"
        data-testid="inspector-panel"
      >
        选择一条记录开始核对
      </aside>
    )
  }

  const isSpeaker = 'speaker_label' in selected && !('start' in selected)
  const isSegment = 'segment_id' in selected
  const speakers = data?.speakers ?? []
  const personas = data?.personas?.items ?? []
  const currentSpeakerLabel = isSpeaker
    ? (selected as SpeakerReviewSpeaker).speaker_label
    : (selected as SpeakerReviewRun | SpeakerReviewSegment).speaker_label
  const currentPersona = personaOf(data, currentSpeakerLabel)
  const itemId = isSpeaker
    ? `speaker:${(selected as SpeakerReviewSpeaker).speaker_label}`
    : isSegment
      ? (selected as SpeakerReviewSegment).segment_id
      : (selected as SpeakerReviewRun).run_id
  const itemType = isSpeaker ? 'speaker_profile' : isSegment ? 'segment' : 'speaker_run'
  const decoratedSelected = selected as {
    decision?: { decision?: string } | null
    recommended_action?: string | null
    risk_flags?: string[] | null
  }
  const current = decoratedSelected.decision ?? null

  return (
    <aside
      className="flex h-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
      data-testid="inspector-panel"
    >
      <header className="border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-900">
            {describeSelection(selected, data)}
          </h3>
          {current && (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700">
              已决策
            </span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
          <span className="text-slate-500">昵称：</span>
          <span className="flex items-center gap-1 font-medium text-slate-800">
            <span
              className="flex h-3 w-3 rounded-full"
              style={personaDotStyle(currentPersona?.color)}
              aria-hidden="true"
            />
            {currentPersona?.name ?? '未命名'}
          </span>
          <button
            type="button"
            onClick={() => onRename(currentSpeakerLabel, currentPersona?.name ?? '')}
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-slate-700 hover:bg-slate-100"
            data-testid="inspector-rename"
          >
            <Pencil className="h-3 w-3" />重命名
          </button>
        </div>
        {decoratedSelected.recommended_action && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-amber-700">
            <Wand2 className="h-3 w-3" /> 建议：{decoratedSelected.recommended_action}
          </p>
        )}
      </header>
      <div className="flex-1 overflow-y-auto p-4 text-xs text-slate-700">
        {!isSpeaker && (
          <div className="mb-3 rounded-md border border-slate-200 bg-slate-50 p-3">
            <p className="font-semibold text-slate-900">内容</p>
            <p className="mt-1 text-slate-700">
              {(selected as SpeakerReviewRun | SpeakerReviewSegment).text}
            </p>
            <p className="mt-2 text-[11px] text-slate-500">
              上：{displayLabel(data, (selected as SpeakerReviewRun).previous_speaker_label) ?? '—'} ／ 下：
              {displayLabel(data, (selected as SpeakerReviewRun).next_speaker_label) ?? '—'}
            </p>
          </div>
        )}

        {(decoratedSelected.risk_flags?.length ?? 0) > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {decoratedSelected.risk_flags!.map((flag: string) => (
              <span
                key={flag}
                className="flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700"
              >
                <AlertTriangle className="h-3 w-3" />
                {flag}
              </span>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <h4 className="text-[11px] font-semibold uppercase text-slate-500">决策动作</h4>
          {isSpeaker ? (
            <>
              <ActionButton
                icon={<Ban className="h-3.5 w-3.5" />}
                label="标记为不可克隆"
                onClick={() =>
                  onDecision({
                    item_id: itemId,
                    item_type: itemType,
                    decision: 'mark_non_cloneable',
                  })
                }
                loading={loading}
                testId="action-mark-non-cloneable"
              />
              <ActionButton
                icon={<Check className="h-3.5 w-3.5" />}
                label="保持独立角色"
                onClick={() =>
                  onDecision({
                    item_id: itemId,
                    item_type: itemType,
                    decision: 'keep_independent',
                  })
                }
                loading={loading}
                testId="action-keep-independent"
              />
              <h5 className="mt-3 text-[11px] font-semibold uppercase text-slate-500">合并到</h5>
              <div className="grid grid-cols-2 gap-2">
                {speakers
                  .filter(sp => sp.speaker_label !== (selected as SpeakerReviewSpeaker).speaker_label)
                  .map(sp => (
                    <button
                      key={sp.speaker_label}
                      type="button"
                      onClick={() =>
                        onDecision({
                          item_id: itemId,
                          item_type: itemType,
                          decision: 'merge_speaker',
                          payload: {
                            target_speaker: sp.speaker_label,
                            source_speaker: (selected as SpeakerReviewSpeaker).speaker_label,
                          },
                        })
                      }
                      className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-800 hover:bg-slate-100"
                      data-testid={`action-merge-${sp.speaker_label}`}
                    >
                      {displayLabel(data, sp.speaker_label)}
                    </button>
                  ))}
              </div>
              {personas.length > 0 && (
                <>
                  <h5 className="mt-3 text-[11px] font-semibold uppercase text-slate-500">
                    绑定到现有昵称
                  </h5>
                  <div className="flex flex-wrap gap-1.5" data-testid="bind-persona-list">
                    {personas
                      .filter(p => p.id !== currentPersona?.persona_id)
                      .map(p => (
                        <button
                          key={p.id}
                          type="button"
                          onClick={() =>
                            onBindToPersona(p.id, (selected as SpeakerReviewSpeaker).speaker_label)
                          }
                          className="flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-800 hover:bg-slate-50"
                          data-testid={`bind-persona-${p.id}`}
                        >
                          <span
                            className="h-2.5 w-2.5 rounded-full"
                            style={personaDotStyle(p.color)}
                            aria-hidden="true"
                          />
                          {p.name}
                        </button>
                      ))}
                  </div>
                </>
              )}
            </>
          ) : (
            <>
              <ActionButton
                icon={<ChevronUp className="h-3.5 w-3.5" />}
                label="归到上一位说话人"
                onClick={() =>
                  onDecision({
                    item_id: itemId,
                    item_type: itemType,
                    decision: 'relabel_to_previous_speaker',
                  })
                }
                loading={loading}
                testId="action-relabel-prev"
              />
              <ActionButton
                icon={<ChevronDown className="h-3.5 w-3.5" />}
                label="归到下一位说话人"
                onClick={() =>
                  onDecision({
                    item_id: itemId,
                    item_type: itemType,
                    decision: 'relabel_to_next_speaker',
                  })
                }
                loading={loading}
                testId="action-relabel-next"
              />
              <ActionButton
                icon={<GitMerge className="h-3.5 w-3.5" />}
                label="并入相邻说话人"
                onClick={() =>
                  onDecision({
                    item_id: itemId,
                    item_type: itemType,
                    decision: 'merge_to_surrounding_speaker',
                  })
                }
                loading={loading}
                testId="action-merge-surrounding"
              />
              <ActionButton
                icon={<Check className="h-3.5 w-3.5" />}
                label="保留原判"
                onClick={() =>
                  onDecision({
                    item_id: itemId,
                    item_type: itemType,
                    decision: 'keep_independent',
                  })
                }
                loading={loading}
                testId="action-keep"
              />
            </>
          )}
        </div>

        {current && (
          <button
            type="button"
            className="mt-4 flex w-full items-center justify-center gap-1 rounded-md border border-red-500/30 px-3 py-2 text-[11px] text-red-300 hover:bg-red-500/10"
            onClick={() => onDeleteDecision(itemId)}
            data-testid="delete-decision"
          >
            <Trash2 className="h-3.5 w-3.5" />撤销当前决策
          </button>
        )}
      </div>
    </aside>
  )
}

function ActionButton({
  icon,
  label,
  onClick,
  loading,
  testId,
}: {
  icon: ReactNode
  label: string
  onClick: () => void
  loading: boolean
  testId: string
}) {
  return (
    <button
      type="button"
      className="flex w-full items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] text-slate-800 hover:bg-slate-100 disabled:opacity-50"
      onClick={onClick}
      disabled={loading}
      data-testid={testId}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

function MergeConfirmModal({
  pending,
  onCancel,
  onConfirm,
}: {
  pending: { source: string; target: string }
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      data-testid="merge-confirm-modal"
    >
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-2xl">
        <h4 className="text-base font-semibold text-slate-900">确认合并？</h4>
        <p className="mt-2 text-sm text-slate-700">
          将 <span className="font-mono text-amber-700">{pending.source}</span> 全部归到{' '}
          <span className="font-mono text-emerald-700">{pending.target}</span>。此动作可随时通过“撤销当前决策”回退。
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
            onClick={onCancel}
            data-testid="merge-cancel"
          >
            取消
          </button>
          <button
            type="button"
            className="rounded-md bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500"
            onClick={onConfirm}
            data-testid="merge-confirm"
          >
            确认合并
          </button>
        </div>
      </div>
    </div>
  )
}

function PersonaConflictModal({
  conflict,
  onCancel,
  onRenameAnyway,
  onMerge,
  canMerge,
}: {
  conflict: import('../../types').PersonaNameConflict
  onCancel: () => void
  onRenameAnyway: () => void
  onMerge: () => void
  canMerge: boolean
}) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={onCancel}
      data-testid="persona-conflict-modal"
    >
      <div
        className="w-[440px] rounded-xl bg-white p-5 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-100 text-amber-600">!</div>
          <div className="text-sm font-semibold text-slate-800">昵称已存在</div>
        </div>
        <div className="mb-4 text-sm text-slate-600">
          已有一个叫 <span className="font-medium text-slate-900">{conflict.existing_name}</span> 的说话人（ID: <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{conflict.existing_id}</code>）。
        </div>
        <div className="mb-4 text-xs text-slate-500">
          你可以把这个说话人合并到已有昵称下，或者强制使用同名（通常不推荐）。
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
            data-testid="persona-conflict-cancel"
          >
            取消
          </button>
          {canMerge && (
            <button
              type="button"
              onClick={onMerge}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700"
              data-testid="persona-conflict-merge"
            >
              合并到已有
            </button>
          )}
          <button
            type="button"
            onClick={onRenameAnyway}
            className="rounded-lg bg-amber-600 px-3 py-1.5 text-sm text-white hover:bg-amber-700"
            data-testid="persona-conflict-force"
          >
            仍然使用同名
          </button>
        </div>
      </div>
    </div>
  )
}

function ApplyDiffPreviewModal({
  data,
  loading,
  onClose,
  onConfirm,
}: {
  data: import('../../types').PersonaApplyPreviewResponse | null
  loading: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={onClose}
      data-testid="apply-diff-preview-modal"
    >
      <div
        className="flex max-h-[80vh] w-[720px] flex-col rounded-xl bg-white p-5 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-3 text-sm font-semibold text-slate-800">应用前预览</div>
        {loading && <div className="text-sm text-slate-500">加载中…</div>}
        {!loading && !data && (
          <div className="text-sm text-slate-500">暂无数据</div>
        )}
        {!loading && data && (
          <>
            <div className="mb-3 grid grid-cols-3 gap-3 text-xs">
              <div className="rounded-lg bg-slate-50 p-3">
                <div className="text-slate-500">总段数</div>
                <div className="mt-0.5 text-lg font-semibold text-slate-800">{data.summary.total_segments}</div>
              </div>
              <div className="rounded-lg bg-amber-50 p-3">
                <div className="text-amber-700">将发生改变</div>
                <div className="mt-0.5 text-lg font-semibold text-amber-800">{data.summary.changed_segments}</div>
              </div>
              <div className="rounded-lg bg-rose-50 p-3">
                <div className="text-rose-700">仍未命名</div>
                <div className="mt-0.5 text-lg font-semibold text-rose-800">{data.summary.unassigned_segments}</div>
              </div>
            </div>
            {Object.keys(data.summary.personas_used).length > 0 && (
              <div className="mb-3 rounded-lg border border-slate-200 p-3">
                <div className="mb-2 text-xs text-slate-500">每位说话人的段数</div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(data.summary.personas_used).map(([name, count]) => (
                    <span
                      key={name}
                      className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700"
                    >
                      {name} · {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
            <div className="flex-1 overflow-auto rounded-lg border border-slate-200">
              <table className="w-full text-xs">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-2 py-1.5 text-left font-medium text-slate-500">时间</th>
                    <th className="px-2 py-1.5 text-left font-medium text-slate-500">原说话人</th>
                    <th className="px-2 py-1.5 text-left font-medium text-slate-500">→</th>
                    <th className="px-2 py-1.5 text-left font-medium text-slate-500">新说话人</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sample_changes.map((row, idx) => (
                    <tr key={`${row.segment_id}-${idx}`} className="border-t border-slate-100">
                      <td className="px-2 py-1 text-slate-500">
                        {row.start?.toFixed?.(1) ?? '-'}s
                      </td>
                      <td className="px-2 py-1 text-slate-700">
                        {row.original_persona ?? row.original_speaker ?? '-'}
                      </td>
                      <td className="px-2 py-1 text-slate-400">→</td>
                      <td className="px-2 py-1 font-medium text-slate-800">
                        {row.new_persona ?? row.new_speaker ?? '-'}
                      </td>
                    </tr>
                  ))}
                  {data.sample_changes.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-2 py-3 text-center text-slate-400">
                        无变化段落
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
            data-testid="apply-preview-cancel"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white hover:bg-indigo-700"
            data-testid="apply-preview-confirm"
          >
            确认应用
          </button>
        </div>
      </div>
    </div>
  )
}

function OnboardingGuide({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={onDismiss}
      data-testid="onboarding-guide"
    >
      <div
        className="w-[480px] rounded-xl bg-white p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="mb-2 text-lg font-semibold text-slate-800">欢迎使用说话人核对</div>
        <div className="mb-4 text-sm text-slate-600">三步搞定：</div>
        <ol className="mb-4 space-y-2 text-sm text-slate-700">
          <li>
            <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-xs text-indigo-700">1</span>
            按 <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">H</kbd> 给当前说话人起昵称；按 <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">Shift+H</kbd> 进入连续命名模式
          </li>
          <li>
            <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-xs text-indigo-700">2</span>
            按 <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">G</kbd> 让系统智能推荐昵称；按 <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">B</kbd> 批量模板
          </li>
          <li>
            <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-100 text-xs text-indigo-700">3</span>
            按 <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">⌘+Shift+P</kbd> 应用前预览；按 <kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">⌘+Z</kbd> 撤销，<kbd className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">⌘+Shift+Z</kbd> 重做
          </li>
        </ol>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm text-white hover:bg-indigo-700"
            data-testid="onboarding-dismiss"
          >
            开始使用
          </button>
        </div>
      </div>
    </div>
  )
}

function ShortcutsModal({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={onClose}
      data-testid="shortcuts-modal"
    >
      <div
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <h4 className="text-base font-semibold text-slate-900">快捷键</h4>
        <ul className="mt-3 space-y-2 text-sm text-slate-700">
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">空格</kbd> 播放/暂停当前片段</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">J / ↓</kbd> 下一条</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">K / ↑</kbd> 上一条</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">H</kbd> 重命名当前说话人昵称</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">B</kbd> 打开批量命名</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">G</kbd> 智能建议昵称</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">Cmd/Ctrl + Z</kbd> 撤销上一次昵称改动</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">?</kbd> 显示/关闭本面板</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">Esc</kbd> 关闭抽屉或取消对话框</li>
        </ul>
      </div>
    </div>
  )
}

function PersonaBulkModal({
  onCancel,
  onPick,
  loading,
}: {
  onCancel: () => void
  onPick: (template: PersonaBulkTemplate) => void
  loading: boolean
}) {
  const options: Array<{ template: PersonaBulkTemplate; title: string; desc: string }> = [
    { template: 'role_abc', title: '角色 A / B / C', desc: '按字母顺序依次命名，适合剧情拆解' },
    { template: 'protagonist', title: '主持人 / 嘉宾 …', desc: '时长最多者为主持人，其余为嘉宾' },
    { template: 'by_index', title: '说话人 1 / 2 / 3', desc: '按说话人序号直接编号' },
  ]
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={onCancel}
      data-testid="persona-bulk-modal"
    >
      <div
        className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-6 shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <h4 className="text-base font-semibold text-slate-900">批量命名模板</h4>
        <p className="mt-1 text-[12px] text-slate-500">
          一键为所有未命名说话人创建昵称（已存在的不会被覆盖）
        </p>
        <div className="mt-4 space-y-2">
          {options.map(opt => (
            <button
              key={opt.template}
              type="button"
              onClick={() => onPick(opt.template)}
              disabled={loading}
              className="flex w-full items-start gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs text-slate-800 hover:bg-slate-100 disabled:opacity-50"
              data-testid={`bulk-template-${opt.template}`}
            >
              <div className="flex-1">
                <div className="font-semibold text-slate-900">{opt.title}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">{opt.desc}</div>
              </div>
              {loading && <Loader2 className="h-3 w-3 animate-spin text-slate-400" />}
            </button>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
            data-testid="bulk-cancel"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}

function PersonaSuggestModal({
  onCancel,
  onAccept,
  loading,
  suggestions,
  data,
}: {
  onCancel: () => void
  onAccept: (speaker: string, name: string) => void
  loading: boolean
  suggestions: Record<string, PersonaSuggestCandidate[]>
  data?: SpeakerReviewResponse
}) {
  const entries = Object.entries(suggestions)
  return (
    <div
      className="fixed inset-0 z-60 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm"
      onClick={onCancel}
      data-testid="persona-suggest-modal"
    >
      <div
        className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-6 shadow-2xl"
        onClick={event => event.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-emerald-600" />
          <h4 className="text-base font-semibold text-slate-900">智能建议昵称</h4>
          {loading && <Loader2 className="h-3 w-3 animate-spin text-slate-400" />}
        </div>
        <p className="mt-1 text-[12px] text-slate-500">
          基于台词中的自称与称呼（"我是..."、"XX，你..."）生成候选，采纳即可一键命名。
        </p>
        <div className="mt-4 max-h-[50vh] space-y-3 overflow-y-auto">
          {entries.length === 0 ? (
            <div className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-xs text-slate-500">
              {loading ? '分析中…' : '暂无候选，请尝试批量命名或手动重命名'}
            </div>
          ) : (
            entries.map(([speaker, candidates]) => (
              <div
                key={speaker}
                className="rounded-md border border-slate-200 p-3"
                data-testid={`suggest-row-${speaker}`}
              >
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-3 w-3 rounded-full"
                      style={personaDotStyle(personaOf(data, speaker)?.color)}
                      aria-hidden="true"
                    />
                    <span className="font-semibold text-slate-900">{speaker}</span>
                    {personaOf(data, speaker)?.name && (
                      <span className="text-[11px] text-slate-500">
                        当前：{personaOf(data, speaker)?.name}
                      </span>
                    )}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {candidates.length === 0 ? (
                    <span className="text-[11px] text-slate-400">无候选</span>
                  ) : (
                    candidates.map(cand => (
                      <button
                        key={`${speaker}:${cand.name}`}
                        type="button"
                        onClick={() => onAccept(speaker, cand.name)}
                        className="flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700 hover:bg-emerald-100"
                        data-testid={`suggest-accept-${speaker}-${cand.name}`}
                      >
                        <Check className="h-3 w-3" />
                        {cand.name}
                        <span className="text-[10px] text-emerald-600">
                          {(cand.confidence * 100).toFixed(0)}%
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </div>
            ))
          )}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
            data-testid="suggest-cancel"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}

function buildQueue(data?: SpeakerReviewResponse): QueueEntry[] {
  if (!data) return []
  const runs: QueueEntry[] = (data.speaker_runs ?? []).map(run => ({
    kind: 'run',
    id: run.run_id,
    start: run.start,
    end: run.end,
    risk: run.risk_level ?? 'low',
    run,
  }))
  const segs: QueueEntry[] = (data.segments ?? []).map(segment => ({
    kind: 'segment',
    id: segment.segment_id,
    start: segment.start,
    end: segment.end,
    risk: segment.risk_level ?? 'low',
    segment,
  }))
  return [...runs, ...segs]
}

function findSelected(data?: SpeakerReviewResponse, selection?: ReviewSelection | null) {
  if (!data || !selection) return null
  if (selection.kind === 'speaker') {
    return data.speakers.find(sp => sp.speaker_label === selection.id) ?? null
  }
  if (selection.kind === 'run') {
    return data.speaker_runs.find(r => r.run_id === selection.id) ?? null
  }
  return data.segments.find(s => s.segment_id === selection.id) ?? null
}

function describeSelection(
  selected: SpeakerReviewSpeaker | SpeakerReviewRun | SpeakerReviewSegment,
  data?: SpeakerReviewResponse,
) {
  if ('run_id' in selected) {
    return `Run ${selected.run_id} · ${displayLabel(data, selected.speaker_label)} · ${fmtTime(
      selected.start,
    )} → ${fmtTime(selected.end)}`
  }
  if ('segment_id' in selected) {
    return `Segment ${selected.segment_id} · ${displayLabel(data, selected.speaker_label)} · ${fmtTime(
      selected.start,
    )} → ${fmtTime(selected.end)}`
  }
  return `Speaker ${displayLabel(data, selected.speaker_label)} · ${selected.segment_count} 段`
}

function getDecisionFor(entry: QueueEntry | SpeakerReviewSpeaker | SpeakerReviewRun | SpeakerReviewSegment) {
  const target =
    'kind' in entry
      ? entry.kind === 'speaker'
        ? entry.speaker
        : entry.kind === 'run'
          ? entry.run
          : entry.segment
      : entry
  return (target as { decision?: { decision?: string } | null } | undefined)?.decision ?? null
}

function handleBulkKeep(
  entries: QueueEntry[],
  bulk: Set<string>,
  onDecision: (payload: SpeakerReviewDecisionPayload) => void,
  clearBulk: () => void,
) {
  entries
    .filter(entry => bulk.has(entry.id))
    .forEach(entry => {
      const itemType = entry.kind === 'speaker' ? 'speaker_profile' : entry.kind === 'run' ? 'speaker_run' : 'segment'
      const itemId = entry.kind === 'speaker' ? `speaker:${entry.id}` : entry.id
      onDecision({
        item_id: itemId,
        item_type: itemType,
        decision: 'keep_independent',
      })
    })
  clearBulk()
}

function GlobalPersonaModal({
  onClose,
  loading,
  data,
  onExportFromTask,
  exporting,
  exportResult,
  onImportIds,
  importing,
  onDeleteGlobal,
}: {
  onClose: () => void
  loading: boolean
  data?: import('../../types').GlobalPersonasListResponse
  onExportFromTask: () => void
  exporting: boolean
  exportResult: import('../../types').GlobalExportFromTaskResponse | null
  onImportIds: (ids: string[]) => void
  importing: boolean
  onDeleteGlobal: (id: string) => void
}) {
  const [tab, setTab] = useState<'browse' | 'export'>('browse')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const personas = data?.personas ?? []
  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      data-testid="global-persona-modal"
    >
      <div className="flex max-h-[85vh] w-[640px] flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <BookOpen size={15} className="text-amber-600" />
            角色库（跨任务共享）
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
            aria-label="关闭"
          >
            <X size={14} />
          </button>
        </div>
        <div className="flex gap-1 border-b border-slate-200 px-4 pt-2 text-xs">
          <button
            type="button"
            onClick={() => setTab('browse')}
            className={`rounded-t-md px-3 py-1.5 ${tab === 'browse' ? 'bg-white text-slate-900 font-semibold border border-b-transparent border-slate-200' : 'text-slate-500 hover:text-slate-700'}`}
            data-testid="global-persona-tab-browse"
          >
            浏览与导入 ({personas.length})
          </button>
          <button
            type="button"
            onClick={() => setTab('export')}
            className={`rounded-t-md px-3 py-1.5 ${tab === 'export' ? 'bg-white text-slate-900 font-semibold border border-b-transparent border-slate-200' : 'text-slate-500 hover:text-slate-700'}`}
            data-testid="global-persona-tab-export"
          >
            导出当前任务
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 text-xs text-slate-700">
          {tab === 'browse' && (
            <>
              {loading ? (
                <div className="flex items-center gap-2 text-slate-500">
                  <Loader2 size={13} className="animate-spin" /> 正在加载角色库...
                </div>
              ) : personas.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-slate-500">
                  暂无共享角色。你可以在「导出当前任务」Tab 把当前任务的人设推送到角色库。
                </div>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {personas.map(p => (
                    <li
                      key={p.id}
                      className="flex items-center gap-3 py-2"
                      data-testid={`global-persona-row-${p.name}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(p.id)}
                        onChange={() => toggle(p.id)}
                        className="h-4 w-4"
                        data-testid={`global-persona-check-${p.name}`}
                      />
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          {p.avatar_emoji && <span>{p.avatar_emoji}</span>}
                          <span className="font-semibold">{p.name}</span>
                          {p.role && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">{p.role}</span>}
                          {p.gender && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600">{p.gender}</span>}
                        </div>
                        {p.tts_voice_id && (
                          <div className="mt-0.5 text-[10px] text-slate-500">
                            <Volume2 size={9} className="inline" /> {p.tts_voice_id}
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => onDeleteGlobal(p.id)}
                        className="rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-500"
                        title="从角色库删除"
                      >
                        <Trash2 size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {tab === 'export' && (
            <div className="space-y-3">
              <p className="text-slate-600">
                把当前任务的人设一键推送到角色库，下次在其他任务中即可直接复用（按名称去重，冲突时会覆盖）。
              </p>
              <button
                type="button"
                onClick={onExportFromTask}
                disabled={exporting}
                className="inline-flex items-center gap-1 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-500 disabled:opacity-50"
                data-testid="global-persona-export-button"
              >
                {exporting ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                导出到角色库
              </button>
              {exportResult && (
                <div
                  className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-800"
                  data-testid="global-persona-export-result"
                >
                  已导出 {exportResult.exported.length} 个 · 跳过 {exportResult.skipped.length} 个 · 当前角色库共 {exportResult.total} 个
                </div>
              )}
            </div>
          )}
        </div>

        {tab === 'browse' && personas.length > 0 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-5 py-3">
            <span className="text-[11px] text-slate-500">已选 {selected.size} 个</span>
            <button
              type="button"
              onClick={() => onImportIds(Array.from(selected))}
              disabled={selected.size === 0 || importing}
              className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
              data-testid="global-persona-import-button"
            >
              {importing ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />}
              导入到当前任务
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function GlobalMatchToast({
  matches,
  onDismiss,
  onImportAll,
  importing,
}: {
  matches: import('../../types').SuggestFromGlobalMatch[]
  onDismiss: () => void
  onImportAll: () => void
  importing: boolean
}) {
  const total = matches.length
  return (
    <div
      className="fixed bottom-5 right-5 z-50 w-80 rounded-xl border border-amber-200 bg-white p-3 shadow-xl"
      data-testid="global-match-toast"
    >
      <div className="flex items-start gap-2">
        <BookOpen size={14} className="mt-0.5 text-amber-600" />
        <div className="flex-1">
          <div className="text-xs font-semibold text-slate-800">角色库匹配</div>
          <div className="mt-1 text-[11px] text-slate-600">
            检测到 <strong className="text-amber-700">{total}</strong> 个说话人可能匹配到角色库中的已有角色，是否一键导入？
          </div>
          <ul className="mt-1 max-h-20 space-y-0.5 overflow-y-auto text-[10px] text-slate-500">
            {matches.slice(0, 5).map(m => (
              <li key={m.speaker_label}>
                · <span className="font-mono">{m.speaker_label}</span> → {m.candidates[0]?.name} ({m.candidates[0]?.reason})
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={onImportAll}
              disabled={importing}
              className="rounded-md bg-amber-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-amber-500 disabled:opacity-50"
              data-testid="global-match-import-all"
            >
              {importing ? '导入中…' : '一键导入'}
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-200"
              data-testid="global-match-dismiss"
            >
              忽略
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
