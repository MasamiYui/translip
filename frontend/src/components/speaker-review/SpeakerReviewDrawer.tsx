import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  Check,
  ChevronDown,
  ChevronUp,
  GitMerge,
  Keyboard,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward,
  Trash2,
  UserRound,
  Wand2,
} from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import type {
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
    setSelection,
    toggleBulk,
    clearBulk,
    setFilters,
    setShowShortcuts,
    setPendingMerge,
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
      if (event.key === '?') {
        setShowShortcuts(!showShortcuts)
        return
      }
      if (event.key === 'Escape') {
        if (pendingMerge) {
          setPendingMerge(null)
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
  }, [isOpen, showShortcuts, pendingMerge, filteredQueue, selection, onClose, setShowShortcuts, setPendingMerge, setSelection])

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
        />

        <GlobalAudioPlayer
          audioRef={audioRef}
          src={audioSrc}
          isPlaying={isPlaying}
          onToggle={togglePlay}
          onEnded={() => setIsPlaying(false)}
          label={selected ? describeSelection(selected) : '未选中'}
        />

        <div className="grid flex-1 grid-cols-[300px_1fr_380px] gap-3 overflow-hidden bg-[#F5F7FB] p-3">
          <RosterPanel
            data={data}
            onSelect={sel => setSelection(sel)}
            selection={selection}
            onMergeSuggest={(source, target) => setPendingMerge({ source, target })}
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
          />

          <InspectorPanel
            selected={selected}
            onDecision={handleDecision}
            onDeleteDecision={itemId => deleteDecisionMutation.mutate(itemId)}
            loading={decisionMutation.isPending || deleteDecisionMutation.isPending}
            data={data}
          />
        </div>

        {pendingMerge && (
          <MergeConfirmModal
            pending={pendingMerge}
            onCancel={() => setPendingMerge(null)}
            onConfirm={confirmMerge}
          />
        )}

        {showShortcuts && <ShortcutsModal onClose={() => setShowShortcuts(false)} />}
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
}: {
  data?: SpeakerReviewResponse
  onClose: () => void
  onApply: () => void
  applying: boolean
  applyResult: string | null
  onRerunFromTaskB?: () => void
  onToggleShortcuts: () => void
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
}: {
  data?: SpeakerReviewResponse
  onSelect: (selection: ReviewSelection) => void
  selection: ReviewSelection | null
  onMergeSuggest: (source: string, target: string) => void
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
          return (
            <div
              key={sp.speaker_label}
              className={`cursor-pointer border-b border-slate-200 px-4 py-3 text-xs transition ${
                active ? 'bg-slate-100' : 'hover:bg-slate-50'
              }`}
              onClick={() => onSelect({ kind: 'speaker', id: sp.speaker_label })}
              data-testid={`roster-item-${sp.speaker_label}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <UserRound className="h-4 w-4 text-slate-500" />
                  <span className="font-semibold text-slate-900">{sp.speaker_label}</span>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${riskColor(sp.risk_level)}`}
                  >
                    {sp.risk_level}
                  </span>
                </div>
                <span className="text-slate-500">{sp.segment_count} 段</span>
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
                        <GitMerge className="h-3 w-3" />合并到 {peer.label}
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
                      {entry.kind === 'speaker'
                        ? entry.speaker.speaker_label
                        : entry.kind === 'run'
                          ? entry.run.speaker_label
                          : entry.segment.speaker_label}
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
}: {
  selected: SpeakerReviewSpeaker | SpeakerReviewRun | SpeakerReviewSegment | null
  onDecision: (payload: SpeakerReviewDecisionPayload) => void
  onDeleteDecision: (itemId: string) => void
  loading: boolean
  data?: SpeakerReviewResponse
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
            {describeSelection(selected)}
          </h3>
          {current && (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700">
              已决策
            </span>
          )}
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
              上：{(selected as SpeakerReviewRun).previous_speaker_label ?? '—'} ／ 下：
              {(selected as SpeakerReviewRun).next_speaker_label ?? '—'}
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
                      {sp.speaker_label}
                    </button>
                  ))}
              </div>
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
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">?</kbd> 显示/关闭本面板</li>
          <li><kbd className="rounded bg-slate-100 px-2 py-0.5">Esc</kbd> 关闭抽屉或取消对话框</li>
        </ul>
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

function describeSelection(selected: SpeakerReviewSpeaker | SpeakerReviewRun | SpeakerReviewSegment) {
  if ('run_id' in selected) {
    return `Run ${selected.run_id} · ${selected.speaker_label} · ${fmtTime(selected.start)} → ${fmtTime(
      selected.end,
    )}`
  }
  if ('segment_id' in selected) {
    return `Segment ${selected.segment_id} · ${selected.speaker_label} · ${fmtTime(selected.start)} → ${fmtTime(
      selected.end,
    )}`
  }
  return `Speaker ${selected.speaker_label} · ${selected.segment_count} 段`
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
