import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  AudioLines,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Download,
  History,
  Keyboard,
  Loader2,
  RefreshCw,
  RotateCcw,
  Settings2,
  Sliders,
  Star,
  User,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { dubbingEditorApi } from '../api/dubbing-editor'
import type {
  DubbingEditorCharacter,
  DubbingEditorIssue,
  DubbingEditorProject,
  DubbingEditorUnit,
} from '../api/dubbing-editor'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimeSec(sec: number): string {
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  const ms = Math.round((sec % 1) * 1000)
  const ms3 = String(ms).padStart(3, '0').slice(0, 2)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms3}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms3}`
}

function formatScore(score: number): string {
  return score.toFixed(1)
}

// ---------------------------------------------------------------------------
// Benchmark Badge
// ---------------------------------------------------------------------------

function BenchmarkBadge({ status, score }: { status: string; score: number }) {
  const config: Record<string, { label: string; cls: string }> = {
    approved: { label: 'Approved', cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
    deliverable_candidate: {
      label: 'Deliverable',
      cls: 'bg-blue-50 text-blue-700 border border-blue-200',
    },
    review_required: {
      label: 'Review Required',
      cls: 'bg-amber-50 text-amber-700 border border-amber-200',
    },
    blocked: { label: 'Blocked', cls: 'bg-rose-50 text-rose-700 border border-rose-200' },
    unknown: { label: 'Unknown', cls: 'bg-slate-50 text-slate-500 border border-slate-200' },
  }
  const cfg = config[status] ?? config['unknown']
  return (
    <div className="flex items-center gap-2">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Benchmark</div>
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cfg.cls}`}>{cfg.label}</span>
      <span className="text-sm font-semibold text-slate-700">{formatScore(score)}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// P2: Progress Bar
// ---------------------------------------------------------------------------

function ProgressBar({ approved, total }: { approved: number; total: number }) {
  const pct = total > 0 ? (approved / total) * 100 : 0
  const colorCls = pct >= 80 ? 'bg-emerald-500' : pct >= 40 ? 'bg-blue-500' : 'bg-amber-500'
  return (
    <div className="flex items-center gap-2" data-testid="progress-bar">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorCls}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] text-slate-400">
        {approved}/{total}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Top Bar (P2: progress bar + P0: keyboard shortcut hint)
// ---------------------------------------------------------------------------

function EditorTopBar({
  project,
  taskId,
  onRefresh,
  onRenderRange,
  isRefreshing,
  selectedUnit,
}: {
  project: DubbingEditorProject
  taskId: string
  onRefresh: () => void
  onRenderRange: () => void
  isRefreshing: boolean
  selectedUnit: DubbingEditorUnit | null
}) {
  const { summary, quality_benchmark } = project
  const [showShortcuts, setShowShortcuts] = useState(false)

  return (
    <div className="shrink-0 border-b border-slate-200 bg-white">
      <div className="flex h-[52px] items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <Link
            to={`/tasks/${taskId}`}
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          >
            <ArrowLeft size={15} />
          </Link>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
              Dubbing Workbench
            </div>
            <div className="text-sm font-semibold leading-none text-slate-900">专业配音编辑台</div>
          </div>
          <div className="ml-2 h-7 border-l border-slate-200" />
          <BenchmarkBadge status={quality_benchmark?.status ?? 'unknown'} score={summary?.quality_score ?? 0} />
          <div className="ml-2 h-7 border-l border-slate-200" />
          <ProgressBar approved={summary?.approved_count ?? 0} total={summary?.unit_count ?? 0} />
        </div>

        <div className="flex items-center gap-2">
          {/* P0: Keyboard shortcuts popover */}
          <div className="relative">
            <button
              type="button"
              data-testid="keyboard-shortcuts-btn"
              onClick={() => setShowShortcuts(v => !v)}
              className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              title="键盘快捷键"
            >
              <Keyboard size={13} />
            </button>
            {showShortcuts && (
              <div
                data-testid="shortcuts-popover"
                className="absolute right-0 top-8 z-50 w-56 rounded-lg border border-slate-200 bg-white p-3 shadow-lg"
              >
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  键盘快捷键
                </div>
                {[
                  ['↓ / J', '下一条问题'],
                  ['↑ / K', '上一条问题'],
                  ['Space', '播放/暂停配音片段'],
                  ['A', '批准当前片段'],
                  ['F', '标记需复核'],
                  ['R', 'Render Range'],
                  ['Esc', '取消选择'],
                ].map(([key, desc]) => (
                  <div key={key} className="flex items-center justify-between py-0.5 text-[11px]">
                    <kbd className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-700">
                      {key}
                    </kbd>
                    <span className="text-slate-500">{desc}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw size={12} className={isRefreshing ? 'animate-spin' : ''} />
            刷新
          </button>
          <button
            type="button"
            onClick={onRenderRange}
            disabled={!selectedUnit}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <Sliders size={12} />
            Render Range
          </button>
          <a
            href={`/api/tasks/${taskId}/artifacts/${project.artifact_paths?.final_dub ?? ''}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
          >
            <Download size={12} />
            Export
          </a>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Issue Queue
// ---------------------------------------------------------------------------

const ISSUE_TYPE_LABELS: Record<string, string> = {
  voice_gender_mismatch: '音色冲突',
  silent_with_subtitle: '字幕无声',
  speaker_similarity_failed: '声纹失败',
  wrong_character: '人物错误',
  duration_overrun: '时长超出',
  overlap_conflict: '时间重叠',
  translation_untrusted: '文本可信度低',
  pronunciation_issue: '发音问题',
}

function SeverityBadge({ severity }: { severity: string }) {
  const cls =
    severity === 'P0'
      ? 'bg-rose-50 text-rose-700 border border-rose-200'
      : severity === 'P1'
        ? 'bg-amber-50 text-amber-700 border border-amber-200'
        : 'bg-slate-50 text-slate-500 border border-slate-200'
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${cls}`}>{severity}</span>
}

function IssueCard({
  issue,
  isSelected,
  onClick,
}: {
  issue: DubbingEditorIssue
  isSelected: boolean
  onClick: () => void
}) {
  const resolved = issue.status === 'resolved' || issue.status === 'ignored'
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-none border-b border-slate-100 px-4 py-3 text-left transition-colors ${
        isSelected
          ? 'bg-blue-50'
          : resolved
            ? 'bg-slate-50/50 opacity-60'
            : 'hover:bg-slate-50'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <SeverityBadge severity={issue.severity} />
        <span className="text-[10px] text-slate-400">{formatTimeSec(issue.time_sec)}</span>
      </div>
      <div className="mt-1.5 text-xs font-medium text-slate-900">
        {resolved ? <s className="text-slate-400">{issue.title}</s> : issue.title}
      </div>
      <div className="mt-0.5 text-[10px] text-slate-400">
        {ISSUE_TYPE_LABELS[issue.type] ?? issue.type} · {issue.description}
      </div>
    </button>
  )
}

type IssueFilter = 'all' | 'P0' | 'P1' | 'P2' | 'open' | 'resolved'

function IssueQueue({
  project,
  selectedIssueId,
  onSelectIssue,
  onBulkApprove,
}: {
  project: DubbingEditorProject
  selectedIssueId: string | null
  onSelectIssue: (issue: DubbingEditorIssue) => void
  onBulkApprove: (unitIds: string[]) => void
}) {
  const [filter, setFilter] = useState<IssueFilter>('open')
  const [charFilter, setCharFilter] = useState<string>('all')

  const { issues, summary, characters } = project

  const filteredIssues = issues.filter(issue => {
    if (filter === 'P0' || filter === 'P1' || filter === 'P2') {
      if (issue.severity !== filter) return false
    } else if (filter === 'open') {
      if (issue.status !== 'open') return false
    } else if (filter === 'resolved') {
      if (issue.status === 'open') return false
    }
    if (charFilter !== 'all' && issue.character_id !== charFilter) return false
    return true
  })

  const p0Count = issues.filter(i => i.severity === 'P0' && i.status === 'open').length
  const charReview = summary?.char_review_count ?? 0
  const candidateCount = summary?.candidate_count ?? 0

  // P2: units that only have P2 issues open (safe to bulk-approve)
  const bulkApprovableP2Units = useMemo(() => {
    const unitSeverities: Record<string, Set<string>> = {}
    for (const issue of issues) {
      if (issue.status !== 'open') continue
      const s = unitSeverities[issue.unit_id] ?? new Set<string>()
      s.add(issue.severity)
      unitSeverities[issue.unit_id] = s
    }
    return Object.entries(unitSeverities)
      .filter(([, severities]) => !severities.has('P0') && !severities.has('P1') && severities.has('P2'))
      .map(([uid]) => uid)
  }, [issues])

  return (
    <div className="flex h-full flex-col border-r border-slate-200 bg-white">
      {/* Header */}
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={13} className="text-slate-400" />
            <span className="text-xs font-semibold text-slate-700">Issue Queue</span>
          </div>
          <span className="text-xs text-slate-400">
            {filteredIssues.length} open · {summary?.approved_count ?? 0} approved
          </span>
        </div>

        {/* Stats row */}
        <div className="mt-2.5 grid grid-cols-3 gap-2">
          <div
            className={`cursor-pointer rounded-md border py-2 text-center transition-colors ${filter === 'P0' ? 'border-rose-300 bg-rose-50' : 'border-slate-200 hover:border-slate-300'}`}
            onClick={() => setFilter(filter === 'P0' ? 'open' : 'P0')}
          >
            <div className="text-sm font-bold text-rose-600">{p0Count}</div>
            <div className="text-[10px] text-slate-400">P0</div>
          </div>
          <div
            className={`cursor-pointer rounded-md border py-2 text-center transition-colors ${charFilter !== 'all' ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:border-slate-300'}`}
            onClick={() => setCharFilter(charFilter === 'all' ? '' : 'all')}
          >
            <div className="text-sm font-bold text-slate-700">{charReview}</div>
            <div className="text-[10px] text-slate-400">角色</div>
          </div>
          <div className="rounded-md border border-slate-200 py-2 text-center">
            <div className="text-sm font-bold text-slate-700">{candidateCount}</div>
            <div className="text-[10px] text-slate-400">候选</div>
          </div>
        </div>
      </div>

      {/* Filters + P2 bulk approve */}
      <div className="border-b border-slate-100 px-3 py-2">
        <div className="flex flex-wrap gap-1">
          {(['all', 'open', 'P0', 'P1', 'P2', 'resolved'] as IssueFilter[]).map(f => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
                filter === f
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
        {bulkApprovableP2Units.length > 0 && (
          <button
            type="button"
            data-testid="bulk-approve-btn"
            onClick={() => onBulkApprove(bulkApprovableP2Units)}
            className="mt-1.5 flex items-center gap-1 text-[10px] font-medium text-emerald-600 hover:text-emerald-800"
          >
            <CheckCheck size={11} />
            批量批准 {bulkApprovableP2Units.length} 条仅P2问题
          </button>
        )}
      </div>

      {/* Issues list */}
      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="issue-list">
        {filteredIssues.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            {filter === 'open' ? '暂无未处理问题' : '无匹配问题'}
          </div>
        ) : (
          filteredIssues.map(issue => (
            <IssueCard
              key={issue.issue_id}
              issue={issue}
              isSelected={issue.issue_id === selectedIssueId}
              onClick={() => onSelectIssue(issue)}
            />
          ))
        )}
      </div>

      {/* Character Cast */}
      <CharacterCastSection characters={characters} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Character Cast Section
// ---------------------------------------------------------------------------

function CharacterStatusBadge({ status }: { status: string }) {
  if (status === 'passed')
    return (
      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
        passed
      </span>
    )
  if (status === 'blocked')
    return (
      <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-medium text-rose-700">
        blocked
      </span>
    )
  return (
    <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
      review
    </span>
  )
}

function CharacterCastSection({ characters }: { characters: DubbingEditorCharacter[] }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="border-t border-slate-200">
      <button
        type="button"
        onClick={() => setExpanded(e => !e)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-semibold text-slate-500 hover:bg-slate-50"
      >
        <div className="flex items-center gap-1.5">
          <User size={11} />
          Character Cast
        </div>
        {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      </button>
      {expanded && (
        <div className="max-h-48 overflow-y-auto">
          {characters.map(char => (
            <div key={char.character_id} className="flex items-center justify-between px-4 py-2 hover:bg-slate-50">
              <div>
                <div className="text-xs font-medium text-slate-800">{char.display_name}</div>
                <div className="text-[10px] text-slate-400">
                  {char.speaker_ids[0]} · {char.pitch_class}
                  {char.pitch_hz && ` · ${char.pitch_hz.toFixed(0)}Hz`}
                </div>
                {char.risk_flags.length > 0 && (
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {char.risk_flags.slice(0, 2).map(flag => (
                      <span key={flag} className="rounded bg-amber-50 px-1 py-0.5 text-[9px] text-amber-700">
                        {flag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <CharacterStatusBadge status={char.review_status} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Waveform renderer (SVG-based)
// ---------------------------------------------------------------------------

function WaveformBar({
  peaks,
  color = '#64748b',
  height = 60,
  pending = false,
}: {
  peaks: number[]
  color?: string
  height?: number
  pending?: boolean
}) {
  if (pending || !peaks || peaks.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded bg-slate-900/80 text-[10px] text-slate-500"
        style={{ height }}
      >
        {pending ? '生成中…' : 'loading…'}
      </div>
    )
  }

  const width = 400
  const barWidth = width / peaks.length
  const centerY = height / 2

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-full w-full">
      {peaks.map((p, i) => {
        const barH = Math.max(1, p * (height * 0.9))
        return (
          <rect
            key={i}
            x={i * barWidth}
            y={centerY - barH / 2}
            width={Math.max(1, barWidth - 0.5)}
            height={barH}
            fill={color}
            opacity={0.8}
          />
        )
      })}
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Timeline Pane (P0: scrollable/zoomable, P1: background track, no unit limit)
// ---------------------------------------------------------------------------

const ZOOM_LEVELS = [10, 20, 40, 80, 160, 320] // pixels per second

function TimelinePane({
  project,
  taskId,
  selectedUnit,
  onSelectUnit,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  onSelectUnit: (unit: DubbingEditorUnit) => void
}) {
  const [zoomIdx, setZoomIdx] = useState(2) // 40px/s default
  const pixelsPerSec = ZOOM_LEVELS[zoomIdx]
  const scrollRef = useRef<HTMLDivElement>(null)

  const dubWaveformQuery = useQuery({
    queryKey: ['waveform', taskId, 'dub'],
    queryFn: () => dubbingEditorApi.getWaveform(taskId, 'dub'),
    staleTime: 1000 * 60 * 5,
    refetchInterval: (query: { state: { data?: { available?: boolean; pending?: boolean } } }) =>
      query.state.data?.available === false && query.state.data?.pending ? 2000 : false,
  })

  const originalWaveformQuery = useQuery({
    queryKey: ['waveform', taskId, 'original'],
    queryFn: () => dubbingEditorApi.getWaveform(taskId, 'original'),
    staleTime: 1000 * 60 * 5,
    refetchInterval: (query: { state: { data?: { available?: boolean; pending?: boolean } } }) =>
      query.state.data?.available === false && query.state.data?.pending ? 2000 : false,
  })

  const backgroundWaveformQuery = useQuery({
    queryKey: ['waveform', taskId, 'background'],
    queryFn: () => dubbingEditorApi.getWaveform(taskId, 'background'),
    staleTime: 1000 * 60 * 5,
    refetchInterval: (query: { state: { data?: { available?: boolean; pending?: boolean } } }) =>
      query.state.data?.available === false && query.state.data?.pending ? 2000 : false,
  })

  const { units } = project
  const totalDuration = units.reduce((m, u) => Math.max(m, u.end), 0) || 1
  const totalWidth = Math.max(totalDuration * pixelsPerSec, 800)

  // Auto-scroll selected unit into view
  useEffect(() => {
    if (!selectedUnit || !scrollRef.current) return
    const left = (selectedUnit.start / totalDuration) * totalWidth
    const el = scrollRef.current
    if (left < el.scrollLeft || left > el.scrollLeft + el.clientWidth - 100) {
      el.scrollTo({ left: Math.max(0, left - 100), behavior: 'smooth' })
    }
  }, [selectedUnit, totalWidth, totalDuration])

  return (
    <div className="flex h-full flex-col bg-slate-950">
      {/* Header: duration + zoom controls */}
      <div
        data-testid="timeline-header"
        className="flex shrink-0 items-center justify-between border-b border-slate-800 px-3 py-1"
      >
        <span className="text-[10px] text-slate-500">
          {formatTimeSec(totalDuration)} · {units.length} segments
        </span>
        <div data-testid="zoom-controls" className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoomIdx(i => Math.max(0, i - 1))}
            disabled={zoomIdx === 0}
            className="rounded p-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:opacity-30"
            title="Zoom out"
          >
            <ZoomOut size={12} />
          </button>
          <span className="w-14 text-center text-[10px] text-slate-500">{pixelsPerSec}px/s</span>
          <button
            type="button"
            onClick={() => setZoomIdx(i => Math.min(ZOOM_LEVELS.length - 1, i + 1))}
            disabled={zoomIdx === ZOOM_LEVELS.length - 1}
            className="rounded p-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 disabled:opacity-30"
            title="Zoom in"
          >
            <ZoomIn size={12} />
          </button>
        </div>
      </div>

      {/* Scrollable track area */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden">
        <div style={{ width: `${totalWidth}px`, minWidth: '100%' }} className="flex h-full flex-col">
          {/* Original Dialogue track */}
          <div className="flex shrink-0 items-center gap-0 border-b border-slate-800">
            <span className="w-28 shrink-0 px-3 text-[10px] font-medium text-slate-400">Original</span>
            <div className="h-10 flex-1 overflow-hidden">
              <WaveformBar
                peaks={originalWaveformQuery.data?.peaks ?? []}
                pending={originalWaveformQuery.data?.available === false && originalWaveformQuery.data?.pending}
                color="#475569"
                height={40}
              />
            </div>
          </div>

          {/* Generated Dub track (with all units overlay) */}
          <div className="flex shrink-0 items-center border-b border-slate-800">
            <span className="w-28 shrink-0 px-3 text-[10px] font-medium text-slate-400">Generated Dub</span>
            <div className="relative h-10 flex-1 overflow-hidden bg-slate-900">
              <WaveformBar
                peaks={dubWaveformQuery.data?.peaks ?? []}
                pending={dubWaveformQuery.data?.available === false && dubWaveformQuery.data?.pending}
                color="#22c55e"
                height={40}
              />
              {units.map(unit => {
                const left = (unit.start / totalDuration) * totalWidth
                const width = ((unit.end - unit.start) / totalDuration) * totalWidth
                const hasIssue = unit.issue_ids.length > 0
                const isSelected = selectedUnit?.unit_id === unit.unit_id
                return (
                  <button
                    key={unit.unit_id}
                    type="button"
                    onClick={() => onSelectUnit(unit)}
                    style={{ left: `${left}px`, width: `${Math.max(2, width)}px` }}
                    className={`absolute inset-y-0 cursor-pointer rounded-sm border-t-2 transition-opacity ${
                      isSelected
                        ? 'border-blue-400 bg-blue-500/20'
                        : hasIssue
                          ? 'border-amber-400 bg-amber-500/10 hover:bg-amber-500/20'
                          : 'border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20'
                    }`}
                    title={unit.source_text}
                  />
                )
              })}
            </div>
          </div>

          {/* Background track (P1: new) */}
          <div className="flex shrink-0 items-center border-b border-slate-800">
            <span className="w-28 shrink-0 px-3 text-[10px] font-medium text-slate-400">Background</span>
            <div className="h-8 flex-1 overflow-hidden">
              <WaveformBar
                peaks={backgroundWaveformQuery.data?.peaks ?? []}
                pending={backgroundWaveformQuery.data?.available === false && backgroundWaveformQuery.data?.pending}
                color="#334155"
                height={32}
              />
            </div>
          </div>

          {/* Dialogue Units track */}
          <div className="flex flex-1 items-center">
            <span className="w-28 shrink-0 px-3 text-[10px] font-medium text-slate-400">Subtitles</span>
            <div className="relative h-8 flex-1 overflow-hidden bg-slate-900/50">
              {units.map(unit => {
                const left = (unit.start / totalDuration) * totalWidth
                const width = ((unit.end - unit.start) / totalDuration) * totalWidth
                return (
                  <button
                    key={unit.unit_id}
                    type="button"
                    onClick={() => onSelectUnit(unit)}
                    style={{ left: `${left}px`, width: `${Math.max(2, width)}px` }}
                    className="absolute inset-y-0 flex items-center overflow-hidden rounded-sm bg-blue-600/20 px-0.5 text-[8px] text-blue-300 hover:bg-blue-600/30"
                    title={unit.source_text}
                  >
                    <span className="truncate">{unit.unit_id}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Current Line / Video Preview Pane (P1: A/B comparison, P0: clip audio ref)
// ---------------------------------------------------------------------------

function CurrentLinePane({
  project,
  taskId,
  selectedUnit,
  renderRangeResult,
  clipAudioRef,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  renderRangeResult: { url: string; start_sec: number; end_sec: number } | null
  clipAudioRef: React.RefObject<HTMLAudioElement | null>
}) {
  const rangeAudioRef = useRef<HTMLAudioElement>(null)

  // P1: load clip preview via API for A/B comparison
  const clipPreviewQuery = useQuery({
    queryKey: ['clip-preview', taskId, selectedUnit?.unit_id],
    queryFn: () =>
      selectedUnit
        ? dubbingEditorApi.getClipPreview(taskId, Math.max(0, selectedUnit.start - 0.2), selectedUnit.end + 0.2)
        : null,
    enabled: !!selectedUnit && !!taskId,
    staleTime: 1000 * 60,
  })

  // Sync clip URL into the ref used by keyboard Space shortcut
  useEffect(() => {
    if (!clipAudioRef.current) return
    const url = clipPreviewQuery.data?.url
    if (url) {
      clipAudioRef.current.src = url
      clipAudioRef.current.load()
    }
  }, [clipPreviewQuery.data?.url, clipAudioRef])

  useEffect(() => {
    if (renderRangeResult && rangeAudioRef.current) {
      rangeAudioRef.current.load()
    }
  }, [renderRangeResult])

  if (!selectedUnit) {
    return (
      <div className="flex h-full flex-col">
        <div className="border-b border-slate-100 px-5 py-3">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Current Line</div>
        </div>
        <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
          从左侧问题队列选择一个片段
        </div>
      </div>
    )
  }

  const hasIssue = selectedUnit.issue_ids.length > 0
  const char = project.characters.find(c => c.character_id === selectedUnit.character_id)

  return (
    <div className="flex h-full flex-col">
      {/* Hidden audio element for Space key playback */}
      <audio ref={clipAudioRef} preload="none" className="hidden" />

      <div className="border-b border-slate-100 px-5 py-3">
        <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Current Line</div>
        <div className="mt-1 text-xs text-slate-500">
          {selectedUnit.unit_id} · {formatTimeSec(selectedUnit.start)} – {formatTimeSec(selectedUnit.end)}
        </div>
      </div>

      {/* 2-column body */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left: source / target texts */}
        <div className="flex min-w-0 flex-1 flex-col gap-2 overflow-y-auto border-r border-slate-100 px-5 py-3">
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">源文</div>
            <div className="rounded-md bg-slate-50 px-3 py-2 text-sm leading-relaxed text-slate-800">
              {selectedUnit.source_text}
            </div>
          </div>
          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">配音稿</div>
            <div className="rounded-md bg-slate-50 px-3 py-2 text-sm leading-relaxed text-slate-800">
              {selectedUnit.target_text}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <UnitStatusBadge status={selectedUnit.status} />
            {char && <span className="text-xs text-slate-500">{char.display_name}</span>}
            {hasIssue && (
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                {selectedUnit.issue_ids.length} issues
              </span>
            )}
          </div>
        </div>

        {/* Right: A/B players + render result */}
        <div className="flex w-72 shrink-0 flex-col gap-2 overflow-y-auto px-4 py-3">
          {/* P1: A/B clip comparison */}
          <div className="rounded-md border border-slate-200 px-3 py-2.5">
            <div className="mb-2 text-[10px] font-semibold text-slate-500">A/B 对比</div>
            <div className="mb-1 text-[9px] font-medium uppercase tracking-widest text-slate-400">原声(A)</div>
            {clipPreviewQuery.data?.url ? (
              <audio
                controls
                src={clipPreviewQuery.data.url}
                className="mb-2 h-7 w-full"
              />
            ) : (
              <div className="mb-2 h-7 rounded bg-slate-100 text-center text-[10px] leading-7 text-slate-400">
                {clipPreviewQuery.isLoading ? '加载中…' : '—'}
              </div>
            )}
            <div className="text-[9px] font-medium uppercase tracking-widest text-slate-400">配音(B)</div>
            {selectedUnit.current_clip?.audio_artifact_path ? (
              <audio
                data-testid="clip-audio"
                controls
                src={`/api/tasks/${taskId}/artifacts/${selectedUnit.current_clip.audio_artifact_path}`}
                className="mt-0.5 h-7 w-full"
              />
            ) : (
              <div className="mt-0.5 h-7 rounded bg-slate-100 text-center text-[10px] leading-7 text-slate-400">—</div>
            )}
          </div>

          {/* Range render player */}
          {renderRangeResult && (
            <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2.5">
              <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold text-blue-700">
                <AudioLines size={10} />
                局部预览
              </div>
              <div className="mb-1.5 text-[10px] text-blue-500">
                {formatTimeSec(renderRangeResult.start_sec)} – {formatTimeSec(renderRangeResult.end_sec)}
              </div>
              <audio ref={rangeAudioRef} controls src={renderRangeResult.url} className="h-8 w-full" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Unit status badge
// ---------------------------------------------------------------------------

function UnitStatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; cls: string }> = {
    approved: {
      label: 'approved',
      cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    },
    locked: { label: 'locked', cls: 'bg-blue-50 text-blue-700 border border-blue-200' },
    needs_review: { label: 'needs_review', cls: 'bg-amber-50 text-amber-700 border border-amber-200' },
    ignored: { label: 'ignored', cls: 'bg-slate-50 text-slate-400 border border-slate-200' },
    unreviewed: { label: 'unreviewed', cls: 'bg-slate-50 text-slate-500 border border-slate-200' },
  }
  const cfg = config[status] ?? config['unreviewed']
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${cfg.cls}`}>{cfg.label}</span>
}

// ---------------------------------------------------------------------------
// Segment Inspector (P1: re-synthesis, P2: operation history)
// ---------------------------------------------------------------------------

function SegmentInspector({
  unit,
  project,
  taskId,
  onApprove,
  onNeedsReview,
  onSaveText,
  onResynthesize,
  isSynthesizing,
}: {
  unit: DubbingEditorUnit
  project: DubbingEditorProject
  taskId: string
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, targetText: string) => void
  onResynthesize: (unitId: string) => void
  isSynthesizing: boolean
}) {
  const [editingText, setEditingText] = useState(unit.target_text)
  const [isDirty, setIsDirty] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    setEditingText(unit.target_text)
    setIsDirty(false)
  }, [unit.unit_id, unit.target_text])

  const char = project.characters.find(c => c.character_id === unit.character_id)
  const clip = unit.current_clip

  // P2: filter operations for this unit
  const unitOps = useMemo(
    () => project.operations?.filter(op => op.target_id === unit.unit_id) ?? [],
    [project.operations, unit.unit_id],
  )

  return (
    <div className="space-y-0">
      {/* Segment header */}
      <div className="flex items-center justify-between px-5 py-3">
        <div>
          <div className="text-xs font-semibold text-slate-800">{unit.unit_id}</div>
          <div className="text-[10px] text-slate-400">
            {char?.display_name ?? unit.character_id} · {formatTimeSec(unit.start)} – {formatTimeSec(unit.end)}
          </div>
        </div>
        <UnitStatusBadge status={unit.status} />
      </div>

      {/* Editable target text */}
      <div className="border-t border-slate-100 px-5 py-3">
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">配音稿</div>
        <textarea
          value={editingText}
          onChange={e => {
            setEditingText(e.target.value)
            setIsDirty(e.target.value !== unit.target_text)
          }}
          rows={2}
          className="w-full resize-none rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-200"
        />
        {isDirty && (
          <button
            type="button"
            onClick={() => {
              onSaveText(unit.unit_id, editingText)
              setIsDirty(false)
            }}
            className="mt-1.5 text-xs font-medium text-blue-600 hover:text-blue-800"
          >
            保存文案
          </button>
        )}
      </div>

      {/* Clip info */}
      <div className="border-t border-slate-100 px-5 py-3">
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">Clip</div>
        <div className="space-y-1 text-[10px] text-slate-500">
          <div className="flex justify-between">
            <span>状态</span>
            <span className={`font-medium ${clip.mix_status === 'placed' ? 'text-emerald-600' : 'text-amber-600'}`}>
              {clip.mix_status || 'unknown'}
            </span>
          </div>
          {clip.duration && (
            <div className="flex justify-between">
              <span>时长</span>
              <span className="text-slate-700">{clip.duration.toFixed(2)}s</span>
            </div>
          )}
          {clip.fit_strategy && (
            <div className="flex justify-between">
              <span>Fit 策略</span>
              <span className="text-slate-700">{clip.fit_strategy}</span>
            </div>
          )}
          {clip.audio_artifact_path && (
            <a
              href={`/api/tasks/${taskId}/artifacts/${clip.audio_artifact_path}`}
              target="_blank"
              rel="noopener noreferrer"
              className="block truncate text-blue-500 hover:text-blue-700"
            >
              {clip.audio_artifact_path.split('/').pop()}
            </a>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="border-t border-slate-100 px-5 py-3">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onApprove(unit.unit_id)}
            disabled={unit.status === 'approved'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-emerald-600 py-2 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            <Check size={12} />
            标记已修
            <kbd className="ml-1 rounded bg-emerald-700/60 px-1 text-[9px]">A</kbd>
          </button>
          <button
            type="button"
            onClick={() => onNeedsReview(unit.unit_id)}
            disabled={unit.status === 'needs_review'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 py-2 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
          >
            <AlertTriangle size={12} />
            仍需复核
            <kbd className="ml-1 rounded bg-amber-200/60 px-1 text-[9px]">F</kbd>
          </button>
        </div>

        {/* P1: Re-synthesis button */}
        <button
          type="button"
          data-testid="resynthesize-btn"
          onClick={() => onResynthesize(unit.unit_id)}
          disabled={isSynthesizing}
          className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {isSynthesizing ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <RotateCcw size={12} />
          )}
          重新合成
        </button>
      </div>

      {/* P2: Operation history accordion */}
      {unitOps.length > 0 && (
        <div className="border-t border-slate-100">
          <button
            type="button"
            data-testid="op-history-btn"
            onClick={() => setShowHistory(v => !v)}
            className="flex w-full items-center justify-between px-5 py-2 text-[10px] font-semibold text-slate-500 hover:bg-slate-50"
          >
            <div className="flex items-center gap-1.5">
              <History size={10} />
              操作历史 ({unitOps.length})
            </div>
            {showHistory ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
          {showHistory && (
            <div className="space-y-0.5 px-5 pb-3">
              {unitOps.map(op => (
                <div key={op.op_id} className="flex items-center justify-between text-[10px] text-slate-500">
                  <span className="font-medium text-slate-700">{op.type}</span>
                  <span>{new Date(op.created_at).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Character Inspector
// ---------------------------------------------------------------------------

function CharacterInspector({ character }: { character: DubbingEditorCharacter }) {
  return (
    <div className="px-5 py-3">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100">
          <User size={14} className="text-slate-500" />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-800">{character.display_name}</div>
          <div className="text-[10px] text-slate-400">{character.speaker_ids.join(', ')}</div>
        </div>
      </div>

      <div className="space-y-2 text-[11px] text-slate-600">
        <div className="flex justify-between">
          <span className="text-slate-400">Pitch</span>
          <span>
            {character.pitch_class}
            {character.pitch_hz && ` · ${character.pitch_hz.toFixed(1)}Hz`}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Voice lock</span>
          <span className={character.voice_lock ? 'text-emerald-600' : 'text-slate-500'}>
            {character.voice_lock ? 'Locked' : 'Unlocked'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Segments</span>
          <span>{character.stats.segment_count}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Speaker failed</span>
          <span
            className={
              character.stats.speaker_failed_ratio > 0.15 ? 'font-medium text-amber-600' : 'text-slate-600'
            }
          >
            {character.stats.speaker_failed_count} ({(character.stats.speaker_failed_ratio * 100).toFixed(0)}%)
          </span>
        </div>
      </div>

      {character.risk_flags.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">Risk Flags</div>
          <div className="flex flex-wrap gap-1">
            {character.risk_flags.map(flag => (
              <span key={flag} className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] text-amber-700">
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inspector Panel
// ---------------------------------------------------------------------------

function InspectorPanel({
  project,
  taskId,
  selectedUnit,
  onApprove,
  onNeedsReview,
  onSaveText,
  onResynthesize,
  isSynthesizing,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, text: string) => void
  onResynthesize: (unitId: string) => void
  isSynthesizing: boolean
}) {
  if (!selectedUnit) {
    return (
      <div className="flex h-full flex-col">
        <div className="border-b border-slate-100 px-5 py-3">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Inspector</div>
        </div>
        <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
          选择片段查看详情
        </div>
      </div>
    )
  }

  const char = project.characters.find(c => c.character_id === selectedUnit.character_id)

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-slate-100 px-5 py-3">
        <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Inspector</div>
        <div className="mt-0.5 text-xs text-slate-600">{selectedUnit.unit_id}</div>
      </div>

      {/* Segment Inspector */}
      <div>
        <div className="flex items-center gap-1.5 px-5 pt-4 pb-1 text-[10px] font-semibold text-slate-500">
          <Settings2 size={11} />
          Segment Inspector
        </div>
        <SegmentInspector
          unit={selectedUnit}
          project={project}
          taskId={taskId}
          onApprove={onApprove}
          onNeedsReview={onNeedsReview}
          onSaveText={onSaveText}
          onResynthesize={onResynthesize}
          isSynthesizing={isSynthesizing}
        />
      </div>

      {/* Character Cast */}
      {char && (
        <div className="border-t border-slate-100">
          <div className="flex items-center gap-1.5 px-5 pt-4 pb-1 text-[10px] font-semibold text-slate-500">
            <User size={11} />
            Character Cast
          </div>
          <CharacterInspector character={char} />
        </div>
      )}

      {/* Candidate Tournament */}
      <div className="border-t border-slate-100">
        <div className="flex items-center gap-1.5 px-5 pt-4 pb-1 text-[10px] font-semibold text-slate-500">
          <Star size={11} />
          Candidate Tournament
        </div>
        <div className="px-5 py-3 text-[11px] text-slate-400">
          {selectedUnit.candidates.length > 0
            ? `${selectedUnit.candidates.length} 个候选`
            : '当前片段没有返修候选。'}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export function DubbingEditorPage() {
  const { id: taskId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const [selectedUnit, setSelectedUnit] = useState<DubbingEditorUnit | null>(null)
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null)
  const [isSynthesizing, setIsSynthesizing] = useState(false)
  const [renderRangeResult, setRenderRangeResult] = useState<{
    url: string
    start_sec: number
    end_sec: number
  } | null>(null)

  // P0: ref for Space-key audio playback (clips)
  const clipAudioRef = useRef<HTMLAudioElement | null>(null)

  const projectQuery = useQuery({
    queryKey: ['dubbing-editor', taskId],
    queryFn: () => dubbingEditorApi.getProject(taskId!),
    enabled: !!taskId,
    staleTime: 1000 * 30,
  })

  const operationsMutation = useMutation({
    mutationFn: (ops: Array<{ type: string; target_id: string; payload: Record<string, unknown> }>) =>
      dubbingEditorApi.saveOperations(taskId!, ops),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dubbing-editor', taskId] })
    },
  })

  const renderRangeMutation = useMutation({
    mutationFn: ({ start, end }: { start: number; end: number }) =>
      dubbingEditorApi.renderRange(taskId!, start, end),
    onSuccess: result => {
      setRenderRangeResult({ url: result.url, start_sec: result.start_sec, end_sec: result.end_sec })
    },
  })

  const handleSelectIssue = useCallback(
    (issue: DubbingEditorIssue) => {
      setSelectedIssueId(issue.issue_id)
      const unit = projectQuery.data?.units.find(u => u.unit_id === issue.unit_id)
      if (unit) setSelectedUnit(unit)
    },
    [projectQuery.data],
  )

  const handleSelectUnit = useCallback((unit: DubbingEditorUnit) => {
    setSelectedUnit(unit)
    setSelectedIssueId(null)
  }, [])

  const handleApprove = useCallback(
    (unitId: string) => {
      operationsMutation.mutate([{ type: 'review.set_status', target_id: unitId, payload: { status: 'approved' } }])
      setSelectedUnit(prev => (prev?.unit_id === unitId ? { ...prev, status: 'approved' } : prev))
    },
    [operationsMutation],
  )

  const handleNeedsReview = useCallback(
    (unitId: string) => {
      operationsMutation.mutate([
        { type: 'review.set_status', target_id: unitId, payload: { status: 'needs_review' } },
      ])
      setSelectedUnit(prev => (prev?.unit_id === unitId ? { ...prev, status: 'needs_review' } : prev))
    },
    [operationsMutation],
  )

  const handleSaveText = useCallback(
    (unitId: string, targetText: string) => {
      operationsMutation.mutate([
        { type: 'segment.update_text', target_id: unitId, payload: { target_text: targetText } },
      ])
    },
    [operationsMutation],
  )

  // P2: bulk approve units that only have P2 issues
  const handleBulkApprove = useCallback(
    (unitIds: string[]) => {
      const ops = unitIds.map(uid => ({
        type: 'review.set_status',
        target_id: uid,
        payload: { status: 'approved' },
      }))
      operationsMutation.mutate(ops)
    },
    [operationsMutation],
  )

  // P1: re-synthesis
  const handleResynthesize = useCallback(
    async (unitId: string) => {
      if (!taskId) return
      setIsSynthesizing(true)
      try {
        await dubbingEditorApi.synthesizeUnit(taskId, unitId)
        queryClient.invalidateQueries({ queryKey: ['dubbing-editor', taskId] })
      } finally {
        setIsSynthesizing(false)
      }
    },
    [taskId, queryClient],
  )

  const handleRenderRange = useCallback(() => {
    if (!selectedUnit) return
    const pad = 1.0
    renderRangeMutation.mutate({
      start: Math.max(0, selectedUnit.start - pad),
      end: selectedUnit.end + pad,
    })
  }, [selectedUnit, renderRangeMutation])

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['dubbing-editor', taskId] })
  }, [queryClient, taskId])

  // P0: Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLInputElement ||
        target.isContentEditable
      )
        return

      const units = projectQuery.data?.units
      if (!units) return

      const openIssues = projectQuery.data?.issues.filter(i => i.status === 'open') ?? []

      if (e.key === 'ArrowDown' || e.key === 'j') {
        e.preventDefault()
        if (openIssues.length === 0) return
        const idx = openIssues.findIndex(i => i.issue_id === selectedIssueId)
        const next = openIssues[(idx + 1) % openIssues.length]
        handleSelectIssue(next)
      } else if (e.key === 'ArrowUp' || e.key === 'k') {
        e.preventDefault()
        if (openIssues.length === 0) return
        const idx = openIssues.findIndex(i => i.issue_id === selectedIssueId)
        const prev = openIssues[(idx - 1 + openIssues.length) % openIssues.length]
        handleSelectIssue(prev)
      } else if (e.key === ' ') {
        e.preventDefault()
        const audio = clipAudioRef.current
        if (audio) {
          if (audio.paused) audio.play().catch(() => {})
          else audio.pause()
        }
      } else if (e.key === 'a' || e.key === 'A') {
        if (selectedUnit) handleApprove(selectedUnit.unit_id)
      } else if (e.key === 'f' || e.key === 'F') {
        if (selectedUnit) handleNeedsReview(selectedUnit.unit_id)
      } else if (e.key === 'r' || e.key === 'R') {
        handleRenderRange()
      } else if (e.key === 'Escape') {
        setSelectedUnit(null)
        setSelectedIssueId(null)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [
    projectQuery.data,
    selectedUnit,
    selectedIssueId,
    handleSelectIssue,
    handleApprove,
    handleNeedsReview,
    handleRenderRange,
  ])

  if (!taskId) return null

  if (projectQuery.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          正在加载配音编辑台…
        </div>
      </div>
    )
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <div className="text-center">
          <div className="text-sm text-slate-500">加载失败，请重试</div>
          <button
            type="button"
            onClick={handleRefresh}
            className="mt-3 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            重新加载
          </button>
        </div>
      </div>
    )
  }

  const project = projectQuery.data

  return (
    <div data-testid="dubbing-editor" className="flex h-screen flex-col overflow-hidden bg-slate-50">
      {/* Top bar */}
      <EditorTopBar
        project={project}
        taskId={taskId}
        onRefresh={handleRefresh}
        onRenderRange={handleRenderRange}
        isRefreshing={projectQuery.isFetching}
        selectedUnit={selectedUnit}
      />

      {/* Main area: 3-column layout */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left: Issue Queue */}
        <div className="flex w-80 shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white">
          <IssueQueue
            project={project}
            selectedIssueId={selectedIssueId}
            onSelectIssue={handleSelectIssue}
            onBulkApprove={handleBulkApprove}
          />
        </div>

        {/* Center: Video Preview + Timeline */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Current line */}
          <div className="border-b border-slate-200 bg-white" style={{ height: '240px', minHeight: '200px' }}>
            <CurrentLinePane
              project={project}
              taskId={taskId}
              selectedUnit={selectedUnit}
              renderRangeResult={renderRangeResult}
              clipAudioRef={clipAudioRef}
            />
          </div>

          {/* Timeline */}
          <div className="min-h-0 flex-1 overflow-hidden">
            <TimelinePane
              project={project}
              taskId={taskId}
              selectedUnit={selectedUnit}
              onSelectUnit={handleSelectUnit}
            />
          </div>
        </div>

        {/* Right: Inspector */}
        <div className="flex w-96 shrink-0 flex-col overflow-hidden border-l border-slate-200 bg-white">
          <InspectorPanel
            project={project}
            taskId={taskId}
            selectedUnit={selectedUnit}
            onApprove={handleApprove}
            onNeedsReview={handleNeedsReview}
            onSaveText={handleSaveText}
            onResynthesize={handleResynthesize}
            isSynthesizing={isSynthesizing}
          />
        </div>
      </div>
    </div>
  )
}
