import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  AudioLines,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Download,
  History,
  HelpCircle,
  Keyboard,
  Loader2,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  PenLine,
  RefreshCw,
  RotateCcw,
  Settings2,
  Sliders,
  Star,
  Undo2,
  Redo2,
  User,
  Video,
  Volume2,
  VolumeX,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { dubbingEditorApi } from '../api/dubbing-editor'
import type {
  BacktranslateResult,
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
// Top Bar (Phase 2: undo/redo, SRT export, severity chart)
// ---------------------------------------------------------------------------

/** Severity distribution mini-chart */
function IssueSeverityChart({ project }: { project: DubbingEditorProject }) {
  const openIssues = project.issues.filter(i => i.status === 'open')
  const p0 = openIssues.filter(i => i.severity === 'P0').length
  const p1 = openIssues.filter(i => i.severity === 'P1').length
  const p2 = openIssues.filter(i => i.severity === 'P2').length
  const total = p0 + p1 + p2
  if (total === 0) return null

  const pct = (n: number) => `${((n / total) * 100).toFixed(0)}%`

  return (
    <div data-testid="severity-chart" className="flex items-center gap-2">
      <div className="h-2 w-20 overflow-hidden rounded-full flex">
        {p0 > 0 && <div className="bg-rose-500 h-full transition-all" style={{ width: pct(p0) }} title={`P0: ${p0}`} />}
        {p1 > 0 && <div className="bg-amber-400 h-full transition-all" style={{ width: pct(p1) }} title={`P1: ${p1}`} />}
        {p2 > 0 && <div className="bg-slate-300 h-full transition-all" style={{ width: pct(p2) }} title={`P2: ${p2}`} />}
      </div>
      <div className="flex items-center gap-1 text-[10px] text-slate-500">
        {p0 > 0 && <span className="text-rose-600 font-medium">{p0}P0</span>}
        {p1 > 0 && <span className="text-amber-600 font-medium">{p1}P1</span>}
        {p2 > 0 && <span className="text-slate-500">{p2}P2</span>}
      </div>
    </div>
  )
}

function EditorTopBar({
  project,
  taskId,
  onRefresh,
  onRenderRange,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
  isRefreshing,
  selectedUnit,
  mode,
  onModeToggle,
}: {
  project: DubbingEditorProject
  taskId: string
  onRefresh: () => void
  onRenderRange: () => void
  onUndo: () => void
  onRedo: () => void
  canUndo: boolean
  canRedo: boolean
  isRefreshing: boolean
  selectedUnit: DubbingEditorUnit | null
  mode: 'edit' | 'preview'
  onModeToggle: () => void
}) {
  const { summary, quality_benchmark } = project
  const [showShortcuts, setShowShortcuts] = useState(false)

  /** Generate and download SRT from all units */
  const handleSRTExport = useCallback(() => {
    const units = project.units
    let srt = ''
    units.forEach((unit, idx) => {
      const toTimecode = (sec: number) => {
        const h = Math.floor(sec / 3600)
        const m = Math.floor((sec % 3600) / 60)
        const s = Math.floor(sec % 60)
        const ms = Math.round((sec % 1) * 1000)
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`
      }
      srt += `${idx + 1}\n`
      srt += `${toTimecode(unit.start)} --> ${toTimecode(unit.end)}\n`
      srt += `${unit.target_text}\n\n`
    })
    const blob = new Blob([srt], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${taskId}_dubbed.srt`
    a.click()
    URL.revokeObjectURL(url)
  }, [project.units, taskId])

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
          <div className="ml-2 h-7 border-l border-slate-200" />
          <IssueSeverityChart project={project} />
        </div>

        <div className="flex items-center gap-2">
          {/* Phase 2: Undo/Redo */}
          <button
            type="button"
            data-testid="undo-btn"
            onClick={onUndo}
            disabled={!canUndo}
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30"
            title="撤销 (Ctrl+Z)"
          >
            <Undo2 size={13} />
          </button>
          <button
            type="button"
            data-testid="redo-btn"
            onClick={onRedo}
            disabled={!canRedo}
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30"
            title="重做 (Ctrl+Y)"
          >
            <Redo2 size={13} />
          </button>

          <div className="h-7 border-l border-slate-200" />

          {/* Phase 2: SRT Export */}
          <button
            type="button"
            data-testid="srt-export-btn"
            onClick={handleSRTExport}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            title="导出SRT字幕"
          >
            <Download size={12} />
            SRT
          </button>

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
                  ['Ctrl+Z', '撤销'],
                  ['Ctrl+Y', '重做'],
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
            href="/manual.html"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="help-manual-btn"
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            title="使用手册 / 帮助文档"
          >
            <BookOpen size={13} />
          </a>

          {/* Mode toggle: Edit ↔ Preview */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            <button
              type="button"
              data-testid="mode-edit-btn"
              onClick={() => mode !== 'edit' && onModeToggle()}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                mode === 'edit'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <PenLine size={11} />
              编辑
            </button>
            <button
              type="button"
              data-testid="mode-preview-btn"
              onClick={() => mode !== 'preview' && onModeToggle()}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                mode === 'preview'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Video size={11} />
              预览
            </button>
          </div>

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
      data-testid={`issue-item-${issue.issue_id}`}
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
// Character color palette — deterministic hash → 8 color slots
// ---------------------------------------------------------------------------

const CHAR_COLOR_SLOTS = [
  { bg: 'bg-blue-100',   border: 'border-blue-400',   text: 'text-blue-700',   dot: '#3b82f6' },
  { bg: 'bg-amber-100',  border: 'border-amber-400',  text: 'text-amber-700',  dot: '#f59e0b' },
  { bg: 'bg-violet-100', border: 'border-violet-400', text: 'text-violet-700', dot: '#8b5cf6' },
  { bg: 'bg-rose-100',   border: 'border-rose-400',   text: 'text-rose-700',   dot: '#f43f5e' },
  { bg: 'bg-teal-100',   border: 'border-teal-400',   text: 'text-teal-700',   dot: '#14b8a6' },
  { bg: 'bg-orange-100', border: 'border-orange-400', text: 'text-orange-700', dot: '#ea580c' },
  { bg: 'bg-pink-100',   border: 'border-pink-400',   text: 'text-pink-700',   dot: '#ec4899' },
  { bg: 'bg-lime-100',   border: 'border-lime-400',   text: 'text-lime-700',   dot: '#84cc16' },
]

function charColorSlot(characterId: string) {
  let hash = 0
  for (let i = 0; i < characterId.length; i++) {
    hash = (hash * 31 + characterId.charCodeAt(i)) >>> 0
  }
  return CHAR_COLOR_SLOTS[hash % CHAR_COLOR_SLOTS.length]
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
  playheadSec,
  onSeek,
  darkMode = false,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  onSelectUnit: (unit: DubbingEditorUnit) => void
  playheadSec: number
  onSeek: (sec: number) => void
  darkMode?: boolean
}) {
  const [zoomIdx, setZoomIdx] = useState(2) // 40px/s default
  const pixelsPerSec = ZOOM_LEVELS[zoomIdx]
  const scrollRef = useRef<HTMLDivElement>(null)

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

  // Playhead position in px
  const playheadLeft = (playheadSec / totalDuration) * totalWidth

  // Auto-scroll to follow playhead when in darkMode (preview) — keep playhead centred
  useEffect(() => {
    if (!darkMode || !scrollRef.current) return
    const el = scrollRef.current
    const trackLabelWidth = 112
    const targetScrollLeft = playheadLeft + trackLabelWidth - el.clientWidth / 2
    el.scrollTo({ left: Math.max(0, targetScrollLeft), behavior: 'smooth' })
  }, [darkMode, playheadLeft])

  // Click on scrollable container to seek
  const handleTimelineClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!scrollRef.current) return
      const rect = scrollRef.current.getBoundingClientRect()
      // Account for track label width (112px = w-28)
      const trackLabelWidth = 112
      const clickX = e.clientX - rect.left + scrollRef.current.scrollLeft - trackLabelWidth
      if (clickX < 0) return
      const sec = (clickX / totalWidth) * totalDuration
      onSeek(Math.max(0, Math.min(sec, totalDuration)))
    },
    [totalWidth, totalDuration, onSeek],
  )

  return (
    <div className={`flex h-full flex-col ${darkMode ? 'bg-slate-900' : 'bg-white'}`}>
      {/* Header: duration + zoom controls */}
      <div
        data-testid="timeline-header"
        className={`flex shrink-0 items-center justify-between border-b px-3 py-1 ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}
      >
        <span className={`text-[10px] ${darkMode ? 'text-slate-500' : 'text-slate-500'}`}>
          {formatTimeSec(totalDuration)} · {units.length} segments
        </span>
        <div data-testid="zoom-controls" className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoomIdx(i => Math.max(0, i - 1))}
            disabled={zoomIdx === 0}
            className={`rounded p-0.5 disabled:opacity-30 ${darkMode ? 'text-slate-500 hover:bg-slate-700 hover:text-slate-300' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}
            title="Zoom out"
          >
            <ZoomOut size={12} />
          </button>
          <span className={`w-14 text-center text-[10px] ${darkMode ? 'text-slate-500' : 'text-slate-500'}`}>{pixelsPerSec}px/s</span>
          <button
            type="button"
            onClick={() => setZoomIdx(i => Math.min(ZOOM_LEVELS.length - 1, i + 1))}
            disabled={zoomIdx === ZOOM_LEVELS.length - 1}
            className={`rounded p-0.5 disabled:opacity-30 ${darkMode ? 'text-slate-500 hover:bg-slate-700 hover:text-slate-300' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}
            title="Zoom in"
          >
            <ZoomIn size={12} />
          </button>
        </div>
      </div>

      {/* Scrollable track area */}
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-x-auto overflow-y-hidden cursor-crosshair"
        onClick={handleTimelineClick}
      >
        <div style={{ width: `${totalWidth}px`, minWidth: '100%' }} className="relative flex h-full flex-col">
          {/* Playhead */}
          {playheadSec > 0 && (
            <div
              data-testid="playhead"
              className={`pointer-events-none absolute inset-y-0 z-20 w-px ${darkMode ? 'bg-blue-400' : 'bg-blue-400'}`}
              style={{ left: `${playheadLeft + 112}px` }}
            />
          )}

          {/* Original Dialogue track */}
          <div className={`flex shrink-0 items-center gap-0 border-b ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}>
            <span className={`w-28 shrink-0 px-3 text-[10px] font-medium ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>Original</span>
            <div className="h-10 flex-1 overflow-hidden">
              <WaveformBar
                peaks={originalWaveformQuery.data?.peaks ?? []}
                pending={originalWaveformQuery.data?.available === false && originalWaveformQuery.data?.pending}
                color={darkMode ? '#475569' : '#cbd5e1'}
                height={40}
              />
            </div>
          </div>

          {/* Background track */}
          <div className={`flex shrink-0 items-center border-b ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}>
            <span className={`w-28 shrink-0 px-3 text-[10px] font-medium ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>Background</span>
            <div className="h-8 flex-1 overflow-hidden">
              <WaveformBar
                peaks={backgroundWaveformQuery.data?.peaks ?? []}
                pending={backgroundWaveformQuery.data?.available === false && backgroundWaveformQuery.data?.pending}
                color={darkMode ? '#1e293b' : '#334155'}
                height={32}
              />
            </div>
          </div>

          {/* Speaker Lanes — one row per character */}
          <div className={`flex flex-1 flex-col overflow-y-auto border-t ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}>
            {project.characters.length === 0 ? (
              // Fallback: no characters, show flat unit lane
              <div className="flex shrink-0 items-center" style={{ height: '36px' }}>
                <span className={`w-28 shrink-0 px-3 text-[10px] font-medium ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>Units</span>
                <div className={`relative flex-1 h-full overflow-hidden border-l ${darkMode ? 'bg-slate-800/50 border-slate-700' : 'bg-slate-50/50 border-slate-100'}`}>
                  {units.map(unit => {
                    const left = (unit.start / totalDuration) * totalWidth
                    const width = ((unit.end - unit.start) / totalDuration) * totalWidth
                    const isSelected = selectedUnit?.unit_id === unit.unit_id
                    const showText = pixelsPerSec >= 40 && width > 20
                    return (
                      <button
                        key={unit.unit_id}
                        type="button"
                        onClick={e => { e.stopPropagation(); onSelectUnit(unit) }}
                        style={{ left: `${left}px`, width: `${Math.max(2, width)}px` }}
                        title={`${unit.source_text}\n→ ${unit.target_text}\n[${formatTimeSec(unit.start)} – ${formatTimeSec(unit.end)}]`}
                        className={`absolute inset-y-1 cursor-pointer rounded border text-[9px] font-medium flex items-center overflow-hidden px-1 transition-opacity ${
                          isSelected
                            ? 'bg-blue-100 border-blue-400 ring-1 ring-blue-400 text-blue-700'
                            : 'bg-slate-100 border-slate-300 text-slate-600 opacity-80 hover:opacity-100'
                        }`}
                      >
                        {showText && <span className="truncate">{unit.target_text || unit.source_text}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            ) : (
              project.characters.map(char => {
                const color = charColorSlot(char.character_id)
                const charUnits = units.filter(u => u.character_id === char.character_id)
                return (
                  <div
                    key={char.character_id}
                    className={`flex shrink-0 items-center border-b last:border-b-0 ${darkMode ? 'border-slate-700/60' : 'border-slate-100'}`}
                    style={{ height: '36px' }}
                  >
                    {/* Lane label */}
                    <div className="w-28 shrink-0 flex items-center gap-1.5 px-2">
                      <span
                        className="inline-block h-2 w-2 rounded-full shrink-0"
                        style={{ backgroundColor: color.dot }}
                      />
                      <span className={`truncate text-[10px] font-medium ${darkMode ? 'text-slate-400' : 'text-slate-600'}`}>{char.display_name}</span>
                    </div>
                    {/* Lane track */}
                    <div className={`relative flex-1 h-full overflow-hidden border-l ${darkMode ? 'bg-slate-800/40 border-slate-700' : 'bg-slate-50/30 border-slate-100'}`}>
                      {charUnits.map(unit => {
                        const left = (unit.start / totalDuration) * totalWidth
                        const width = ((unit.end - unit.start) / totalDuration) * totalWidth
                        const hasIssue = unit.issue_ids.length > 0
                        const isSelected = selectedUnit?.unit_id === unit.unit_id
                        const showText = pixelsPerSec >= 40 && width > 20
                        return (
                          <button
                            key={unit.unit_id}
                            type="button"
                            onClick={e => { e.stopPropagation(); onSelectUnit(unit) }}
                            style={{ left: `${left}px`, width: `${Math.max(2, width)}px` }}
                            title={`${unit.source_text}\n→ ${unit.target_text}\n[${formatTimeSec(unit.start)} – ${formatTimeSec(unit.end)}]`}
                            className={`absolute inset-y-1 cursor-pointer rounded border transition-opacity flex items-center overflow-hidden px-1 ${
                              isSelected
                                ? `${color.bg} ${color.border} ring-1 ring-offset-0 ring-blue-400 ${color.text}`
                                : hasIssue
                                  ? 'bg-amber-100 border-amber-400 text-amber-700 hover:bg-amber-200'
                                  : `${color.bg} ${color.border} ${color.text} opacity-80 hover:opacity-100`
                            }`}
                          >
                            {showText && (
                              <span className="truncate text-[9px] leading-tight font-medium">
                                {unit.target_text || unit.source_text}
                              </span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })
            )}
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
        <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto border-r border-slate-100 px-5 py-4">
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
// Segment Inspector (Phase 2: quality scores, voice mismatch, candidate tournament, back-translation)
// ---------------------------------------------------------------------------

/** Mini metric score bar */
function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-rose-500'
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 text-[10px] text-slate-500">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-7 text-right text-[10px] font-medium text-slate-700">{pct}%</span>
    </div>
  )
}

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
  const [showBacktranslate, setShowBacktranslate] = useState(false)

  useEffect(() => {
    setEditingText(unit.target_text)
    setIsDirty(false)
    setShowBacktranslate(false)
  }, [unit.unit_id, unit.target_text])

  const char = project.characters.find(c => c.character_id === unit.character_id)
  const clip = unit.current_clip

  // Phase 2: per-unit quality scores from benchmark
  const benchmark = project.quality_benchmark
  const qualitySegment = useMemo(() => {
    const segs = (benchmark as Record<string, unknown>)?.segments as Array<{
      unit_id: string
      speaker_similarity?: number
      duration_ratio?: number
      intelligibility?: number
    }> | undefined
    return segs?.find(s => s.unit_id === unit.unit_id)
  }, [benchmark, unit.unit_id])

  // Phase 2: back-translation
  const backtranslateQuery = useQuery<BacktranslateResult>({
    queryKey: ['backtranslate', taskId, unit.unit_id],
    queryFn: () => dubbingEditorApi.getBacktranslation(taskId, unit.unit_id),
    enabled: showBacktranslate && !!taskId,
    staleTime: 1000 * 60 * 5,
  })

  // Phase 2: voice mismatch detection
  const hasMismatch = useMemo(
    () => char?.risk_flags.some(f => f.includes('mismatch') || f.includes('gender')) ?? false,
    [char],
  )

  // Filter operations for this unit
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

      {/* Phase 2: Per-unit quality score breakdown */}
      {(qualitySegment || clip.duration) && (
        <div
          data-testid="quality-scores"
          className="border-t border-slate-100 px-5 py-3"
        >
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">质量评分</div>
          <div className="space-y-1.5">
            <ScoreBar label="声纹相似度" value={qualitySegment?.speaker_similarity ?? 0.75} />
            <ScoreBar label="时长比例" value={Math.min(1, qualitySegment?.duration_ratio ?? 1)} />
            <ScoreBar label="可懂度" value={qualitySegment?.intelligibility ?? 0.8} />
          </div>
        </div>
      )}

      {/* Phase 2: Voice mismatch quick-fix */}
      {hasMismatch && (
        <div
          data-testid="voice-mismatch-card"
          className="border-t border-slate-100 mx-5 my-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5"
        >
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold text-amber-700">
            <AlertTriangle size={11} />
            音色不匹配
          </div>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={() => onResynthesize(unit.unit_id)}
              disabled={isSynthesizing}
              className="flex-1 rounded bg-amber-100 px-2 py-1 text-[10px] font-medium text-amber-800 hover:bg-amber-200 disabled:opacity-50"
            >
              参考重合成
            </button>
            <button
              type="button"
              onClick={() => onApprove(unit.unit_id)}
              className="flex-1 rounded bg-slate-100 px-2 py-1 text-[10px] font-medium text-slate-700 hover:bg-slate-200"
            >
              标记豁免
            </button>
          </div>
        </div>
      )}

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

      {/* Phase 2: Back-translation check */}
      <div className="border-t border-slate-100 px-5 py-2">
        <button
          type="button"
          onClick={() => setShowBacktranslate(v => !v)}
          className="flex items-center gap-1.5 text-[10px] font-medium text-slate-500 hover:text-slate-700"
        >
          <AudioLines size={10} />
          ASR 回译校验
          {showBacktranslate ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        </button>
        {showBacktranslate && (
          <div data-testid="backtranslate-result" className="mt-2 space-y-1.5">
            {backtranslateQuery.isLoading ? (
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <Loader2 size={10} className="animate-spin" />
                识别中…
              </div>
            ) : backtranslateQuery.data ? (
              <>
                <div className="text-[10px] text-slate-500">
                  <span className="font-medium text-slate-700">听到：</span>{' '}
                  {backtranslateQuery.data.heard_text}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-500">匹配度</span>
                  <ScoreBar label="" value={backtranslateQuery.data.match_score} />
                </div>
                {!backtranslateQuery.data.asr_available && (
                  <div className="text-[9px] text-slate-400">（ASR未安装，显示期望文本）</div>
                )}
              </>
            ) : null}
          </div>
        )}
      </div>

      {/* Phase 2: Candidate Tournament */}
      {unit.candidates.length > 0 && (
        <div className="border-t border-slate-100">
          <div className="flex items-center justify-between px-5 py-2">
            <div className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-500">
              <Star size={10} />
              候选版本 ({unit.candidates.length})
            </div>
          </div>
          <div data-testid="candidate-list" className="space-y-1 px-5 pb-3">
            {unit.candidates.map((cand, idx) => (
              <div
                key={cand.candidate_id}
                className="flex items-center gap-2 rounded-md border border-slate-100 px-2 py-1.5"
              >
                <span className="w-5 text-center text-[10px] font-bold text-slate-400">#{idx + 1}</span>
                {cand.score !== null && (
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                      cand.score >= 0.8
                        ? 'bg-emerald-50 text-emerald-700'
                        : cand.score >= 0.6
                          ? 'bg-amber-50 text-amber-700'
                          : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {(cand.score * 100).toFixed(0)}
                  </span>
                )}
                {cand.duration && (
                  <span className="text-[10px] text-slate-400">{cand.duration.toFixed(1)}s</span>
                )}
                {cand.audio_path && (
                  <button
                    type="button"
                    onClick={() => {
                      const audio = new Audio(`/api/tasks/${taskId}/artifacts/${cand.audio_path}`)
                      audio.play().catch(() => {})
                    }}
                    className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    title="播放此候选"
                  >
                    <Play size={10} />
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="px-5 pb-3">
            <button
              type="button"
              onClick={() => onResynthesize(unit.unit_id)}
              disabled={isSynthesizing}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-slate-200 py-1.5 text-[10px] font-medium text-slate-500 hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
            >
              <RotateCcw size={10} />
              生成更多候选
            </button>
          </div>
        </div>
      )}

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
// Character Inspector (Phase 2: voice sample preview + swap modal)
// ---------------------------------------------------------------------------

function VoicePickerModal({
  character,
  onClose,
  onAssign,
}: {
  character: DubbingEditorCharacter
  onClose: () => void
  onAssign: (voicePath: string) => void
}) {
  const [inputPath, setInputPath] = useState(character.default_voice?.reference_path ?? '')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-96 rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-800">更换声音参考</div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={14} />
          </button>
        </div>
        <div className="mb-3 text-[11px] text-slate-500">角色: {character.display_name}</div>
        <label className="mb-1 block text-[10px] font-medium text-slate-500">声音参考路径</label>
        <input
          type="text"
          value={inputPath}
          onChange={e => setInputPath(e.target.value)}
          placeholder="e.g. voices/speaker_a.wav"
          className="mb-3 w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-200"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg border border-slate-200 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => { onAssign(inputPath); onClose() }}
            disabled={!inputPath.trim()}
            className="flex-1 rounded-lg bg-blue-600 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            确认更换
          </button>
        </div>
      </div>
    </div>
  )
}

function CharacterInspector({
  character,
  taskId,
  onAssignVoice,
}: {
  character: DubbingEditorCharacter
  taskId: string
  onAssignVoice: (characterId: string, voicePath: string) => void
}) {
  const [showVoicePicker, setShowVoicePicker] = useState(false)

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

      {/* Phase 2: Voice sample preview + swap */}
      <div className="mt-3 rounded-md border border-slate-100 px-3 py-2">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[10px] font-semibold text-slate-500">声音参考</span>
          <button
            type="button"
            data-testid="voice-swap-btn"
            onClick={() => setShowVoicePicker(true)}
            className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium text-blue-600 hover:bg-blue-50"
          >
            <Volume2 size={9} />
            更换
          </button>
        </div>
        {character.default_voice?.reference_path ? (
          <audio
            data-testid="voice-preview-player"
            controls
            src={`/api/tasks/${taskId}/artifacts/${character.default_voice.reference_path}`}
            className="h-7 w-full"
          />
        ) : (
          <div
            data-testid="voice-preview-player"
            className="h-7 rounded bg-slate-50 text-center text-[10px] leading-7 text-slate-400"
          >
            未设置参考音频
          </div>
        )}
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

      {showVoicePicker && (
        <VoicePickerModal
          character={character}
          onClose={() => setShowVoicePicker(false)}
          onAssign={(voicePath) => onAssignVoice(character.character_id, voicePath)}
        />
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
  onAssignVoice,
  isSynthesizing,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, text: string) => void
  onResynthesize: (unitId: string) => void
  onAssignVoice: (characterId: string, voicePath: string) => void
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

      {/* Character Inspector */}
      {char && (
        <div className="border-t border-slate-100">
          <div className="flex items-center gap-1.5 px-5 pt-4 pb-1 text-[10px] font-semibold text-slate-500">
            <User size={11} />
            Character
          </div>
          <CharacterInspector
            character={char}
            taskId={taskId}
            onAssignVoice={onAssignVoice}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Preview Pane — full-width video player + synced timeline
// ---------------------------------------------------------------------------

function PreviewPane({
  project,
  taskId,
  playheadSec,
  onPlayheadChange,
  onSelectUnit,
  selectedUnit,
}: {
  project: DubbingEditorProject
  taskId: string
  playheadSec: number
  onPlayheadChange: (sec: number) => void
  onSelectUnit: (unit: DubbingEditorUnit) => void
  selectedUnit: DubbingEditorUnit | null
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [audioTrack, setAudioTrack] = useState<'original' | 'dub'>('dub')
  const [duration, setDuration] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)

  // Video URL from project — served by backend streaming endpoint
  const videoSrc = `/api/tasks/${taskId}/dubbing-editor/video-preview`

  // Sync video currentTime → playhead
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const onTimeUpdate = () => onPlayheadChange(video.currentTime)
    const onDurationChange = () => setDuration(video.duration || 0)
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    const onEnded = () => setIsPlaying(false)
    video.addEventListener('timeupdate', onTimeUpdate)
    video.addEventListener('durationchange', onDurationChange)
    video.addEventListener('loadedmetadata', onDurationChange)
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)
    video.addEventListener('ended', onEnded)
    return () => {
      video.removeEventListener('timeupdate', onTimeUpdate)
      video.removeEventListener('durationchange', onDurationChange)
      video.removeEventListener('loadedmetadata', onDurationChange)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
      video.removeEventListener('ended', onEnded)
    }
  }, [onPlayheadChange])

  // Seek video when unit clicked in speaker lane
  useEffect(() => {
    if (!selectedUnit || !videoRef.current) return
    const video = videoRef.current
    if (Math.abs(video.currentTime - selectedUnit.start) > 0.5) {
      video.currentTime = selectedUnit.start
    }
  }, [selectedUnit])

  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) video.play()
    else video.pause()
  }, [])

  const toggleMute = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    video.muted = !video.muted
    setIsMuted(video.muted)
  }, [])

  const toggleFullscreen = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (!document.fullscreenElement) {
      video.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }, [])

  // Click on progress bar to seek
  const progressBarRef = useRef<HTMLDivElement>(null)
  const handleProgressClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const el = progressBarRef.current
      const video = videoRef.current
      if (!el || !video || !duration) return
      const rect = el.getBoundingClientRect()
      const ratio = (e.clientX - rect.left) / rect.width
      video.currentTime = Math.max(0, Math.min(duration, ratio * duration))
    },
    [duration],
  )

  const progressPct = duration > 0 ? (playheadSec / duration) * 100 : 0

  // Current unit under playhead
  const activeUnit = project.units.find(u => u.start <= playheadSec && u.end > playheadSec) ?? null

  return (
    <div className="flex h-full w-full flex-col bg-white">
      {/* Video area */}
      <div className="relative min-h-0 flex-1 flex items-center justify-center bg-gray-100">
        <video
          ref={videoRef}
          src={videoSrc}
          className="max-h-full max-w-full rounded shadow-sm"
          preload="metadata"
          playsInline
        />

        {/* Subtitle overlay */}
        {activeUnit && (
          <div className="pointer-events-none absolute bottom-8 left-1/2 -translate-x-1/2 text-center">
            <div className="inline-block max-w-2xl rounded-md bg-black/60 px-4 py-1.5 text-sm font-medium leading-snug text-white backdrop-blur-sm">
              {audioTrack === 'dub' ? activeUnit.target_text : activeUnit.source_text}
            </div>
          </div>
        )}

        {/* Center play overlay (shows when paused) */}
        {!isPlaying && (
          <button
            type="button"
            onClick={togglePlay}
            className="absolute inset-0 flex items-center justify-center group"
          >
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-black/10 backdrop-blur-sm transition-all group-hover:bg-black/20">
              <Play size={28} className="text-slate-700 ml-1" />
            </div>
          </button>
        )}
      </div>

      {/* Control bar */}
      <div className="shrink-0 border-t border-slate-200 bg-white px-4 pt-2 pb-3">
        {/* Progress bar */}
        <div
          ref={progressBarRef}
          onClick={handleProgressClick}
          className="relative mb-2 h-1.5 w-full cursor-pointer rounded-full bg-slate-200 group"
        >
          <div
            className="h-full rounded-full bg-blue-500 transition-none"
            style={{ width: `${progressPct}%` }}
          />
          {/* Unit markers on progress bar */}
          {project.units.map(unit => {
            if (!duration) return null
            const left = (unit.start / duration) * 100
            const hasIssue = unit.issue_ids.length > 0
            return (
              <div
                key={unit.unit_id}
                className={`absolute top-1/2 h-2.5 w-0.5 -translate-y-1/2 rounded-full ${
                  hasIssue ? 'bg-amber-400' : 'bg-slate-300'
                }`}
                style={{ left: `${left}%` }}
              />
            )
          })}
          {/* Playhead thumb */}
          <div
            className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white border border-slate-300 shadow opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ left: `${progressPct}%` }}
          />
        </div>

        {/* Controls row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {/* Play/Pause */}
            <button
              type="button"
              onClick={togglePlay}
              className="flex h-8 w-8 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100 transition-colors"
              title={isPlaying ? '暂停 (Space)' : '播放 (Space)'}
            >
              {isPlaying ? <Pause size={16} /> : <Play size={16} />}
            </button>

            {/* Mute */}
            <button
              type="button"
              onClick={toggleMute}
              className="flex h-7 w-7 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              title={isMuted ? '取消静音' : '静音'}
            >
              {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>

            {/* Timecode */}
            <span className="font-mono text-xs text-slate-500">
              {formatTimeSec(playheadSec)}
              <span className="mx-1 text-slate-300">/</span>
              {formatTimeSec(duration)}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Audio track toggle */}
            <div className="flex items-center rounded-md border border-slate-200 bg-slate-50 p-0.5 text-[11px]">
              <button
                type="button"
                onClick={() => setAudioTrack('original')}
                className={`rounded px-2 py-0.5 font-medium transition-colors ${
                  audioTrack === 'original' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                原声
              </button>
              <button
                type="button"
                onClick={() => setAudioTrack('dub')}
                className={`rounded px-2 py-0.5 font-medium transition-colors ${
                  audioTrack === 'dub' ? 'bg-blue-500 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                配音
              </button>
            </div>

            {/* Fullscreen */}
            <button
              type="button"
              onClick={toggleFullscreen}
              className="flex h-7 w-7 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              title="全屏"
            >
              {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            </button>
          </div>
        </div>
      </div>

      {/* Speaker lanes timeline (reuse full TimelinePane in preview mode) */}
      <div className="shrink-0 border-t border-slate-200" style={{ height: '220px' }}>
        <TimelinePane
          project={project}
          taskId={taskId}
          selectedUnit={selectedUnit}
          onSelectUnit={onSelectUnit}
          playheadSec={playheadSec}
          onSeek={sec => {
            onPlayheadChange(sec)
            if (videoRef.current) videoRef.current.currentTime = sec
          }}
        />
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

  // Phase 2: undo/redo cursor (number of ops to replay)
  const [opCursor, setOpCursor] = useState<number | null>(null)
  const [playheadSec, setPlayheadSec] = useState(0)
  const [editorMode, setEditorMode] = useState<'edit' | 'preview'>('edit')

  // P0: ref for Space-key audio playback (clips)
  const clipAudioRef = useRef<HTMLAudioElement | null>(null)

  // Phase 2: animate playhead from audio current time
  useEffect(() => {
    let rafId: number
    const tick = () => {
      const audio = clipAudioRef.current
      if (audio && !audio.paused) {
        setPlayheadSec(audio.currentTime)
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [])

  const projectQuery = useQuery({
    queryKey: ['dubbing-editor', taskId, opCursor],
    queryFn: () =>
      opCursor !== null
        ? dubbingEditorApi.replayTo(taskId!, opCursor)
        : dubbingEditorApi.getProject(taskId!),
    enabled: !!taskId,
    staleTime: 1000 * 30,
  })

  // Track total ops count for redo
  const totalOpsRef = useRef(0)
  useEffect(() => {
    const ops = projectQuery.data?.operations?.length ?? 0
    if (opCursor === null) {
      totalOpsRef.current = ops
    }
  }, [projectQuery.data, opCursor])

  const operationsMutation = useMutation({
    mutationFn: (ops: Array<{ type: string; target_id: string; payload: Record<string, unknown> }>) =>
      dubbingEditorApi.saveOperations(taskId!, ops),
    onSuccess: () => {
      setOpCursor(null) // exit undo mode after new op
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

  // Phase 2: assign voice
  const handleAssignVoice = useCallback(
    async (characterId: string, voicePath: string) => {
      if (!taskId) return
      await dubbingEditorApi.assignCharacterVoice(taskId, characterId, voicePath)
      queryClient.invalidateQueries({ queryKey: ['dubbing-editor', taskId] })
    },
    [taskId, queryClient],
  )

  // Phase 2: undo/redo
  const currentOps = projectQuery.data?.operations?.length ?? 0
  const effectiveTotalOps = opCursor !== null ? totalOpsRef.current : currentOps
  const effectiveCursor = opCursor !== null ? opCursor : currentOps

  const handleUndo = useCallback(() => {
    const cur = opCursor !== null ? opCursor : currentOps
    if (cur <= 0) return
    setOpCursor(cur - 1)
  }, [opCursor, currentOps])

  const handleRedo = useCallback(() => {
    const cur = opCursor !== null ? opCursor : currentOps
    if (cur >= effectiveTotalOps) return
    const next = cur + 1
    setOpCursor(next >= effectiveTotalOps ? null : next)
  }, [opCursor, currentOps, effectiveTotalOps])

  const canUndo = effectiveCursor > 0
  const canRedo = opCursor !== null && opCursor < effectiveTotalOps

  const handleRenderRange = useCallback(() => {
    if (!selectedUnit) return
    const pad = 1.0
    renderRangeMutation.mutate({
      start: Math.max(0, selectedUnit.start - pad),
      end: selectedUnit.end + pad,
    })
  }, [selectedUnit, renderRangeMutation])

  const handleRefresh = useCallback(() => {
    setOpCursor(null)
    queryClient.invalidateQueries({ queryKey: ['dubbing-editor', taskId] })
  }, [queryClient, taskId])

  // Global keyboard shortcuts
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

      // Phase 2: Ctrl+Z / Ctrl+Y undo/redo
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        handleUndo()
        return
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) {
        e.preventDefault()
        handleRedo()
        return
      }

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
    handleUndo,
    handleRedo,
  ])

  if (!taskId) return null

  if (projectQuery.isLoading && !projectQuery.data) {
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
        onUndo={handleUndo}
        onRedo={handleRedo}
        canUndo={canUndo}
        canRedo={canRedo}
        isRefreshing={projectQuery.isFetching}
        selectedUnit={selectedUnit}
        mode={editorMode}
        onModeToggle={() => setEditorMode(m => m === 'edit' ? 'preview' : 'edit')}
      />

      {/* Undo mode indicator */}
      {opCursor !== null && (
        <div className="shrink-0 bg-amber-50 px-4 py-1 text-[10px] font-medium text-amber-700 border-b border-amber-200">
          查看历史版本 · 操作 {opCursor} / {effectiveTotalOps} — 点击重做恢复最新版本
        </div>
      )}

      {editorMode === 'edit' ? (
        /* ── Edit Mode: 3-column layout ── */
        <div className="flex min-h-0 flex-1 overflow-hidden p-3 gap-3 bg-slate-50">
          {/* Left: Issue Queue */}
          <div className="flex w-[340px] shrink-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <IssueQueue
              project={project}
              selectedIssueId={selectedIssueId}
              onSelectIssue={handleSelectIssue}
              onBulkApprove={handleBulkApprove}
            />
          </div>

          {/* Center: Clip Preview + Timeline */}
          <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-hidden">
            {/* Current line */}
            <div className="flex shrink-0 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden" style={{ height: '360px', minHeight: '360px' }}>
              <CurrentLinePane
                project={project}
                taskId={taskId}
                selectedUnit={selectedUnit}
                renderRangeResult={renderRangeResult}
                clipAudioRef={clipAudioRef}
              />
            </div>

            {/* Timeline */}
            <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <TimelinePane
                project={project}
                taskId={taskId}
                selectedUnit={selectedUnit}
                onSelectUnit={handleSelectUnit}
                playheadSec={playheadSec}
                onSeek={setPlayheadSec}
              />
            </div>
          </div>

          {/* Right: Inspector */}
          <div className="flex w-96 shrink-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <InspectorPanel
              project={project}
              taskId={taskId}
              selectedUnit={selectedUnit}
              onApprove={handleApprove}
              onNeedsReview={handleNeedsReview}
              onSaveText={handleSaveText}
              onResynthesize={handleResynthesize}
              onAssignVoice={handleAssignVoice}
              isSynthesizing={isSynthesizing}
            />
          </div>
        </div>
      ) : (
        /* ── Preview Mode: full-width video + synced timeline ── */
        <div className="min-h-0 flex-1 overflow-hidden">
          <PreviewPane
            project={project}
            taskId={taskId!}
            playheadSec={playheadSec}
            onPlayheadChange={setPlayheadSec}
            onSelectUnit={handleSelectUnit}
            selectedUnit={selectedUnit}
          />
        </div>
      )}
    </div>
  )
}
