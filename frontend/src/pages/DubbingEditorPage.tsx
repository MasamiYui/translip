import { useState, useRef, useCallback, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  AudioLines,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  Filter,
  Headphones,
  Loader2,
  Mic2,
  Play,
  RefreshCw,
  Settings2,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Star,
  User,
  Volume2,
  Wand2,
  X,
  Zap,
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
// Top Bar
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

  return (
    <div className="flex h-[52px] items-center justify-between border-b border-slate-200 bg-white px-4">
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
      </div>

      <div className="flex items-center gap-2">
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
  selectedUnit,
  onSelectIssue,
}: {
  project: DubbingEditorProject
  selectedIssueId: string | null
  selectedUnit: DubbingEditorUnit | null
  onSelectIssue: (issue: DubbingEditorIssue) => void
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

      {/* Filters */}
      <div className="flex gap-1 border-b border-slate-100 px-3 py-2">
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

      {/* Issues list */}
      <div className="min-h-0 flex-1 overflow-y-auto">
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

function WaveformBar({ peaks, color = '#64748b', height = 60 }: { peaks: number[]; color?: string; height?: number }) {
  if (!peaks || peaks.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded bg-slate-900/80 text-[10px] text-slate-500"
        style={{ height }}
      >
        loading…
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
// Timeline Pane
// ---------------------------------------------------------------------------

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
  const dubWaveformQuery = useQuery({
    queryKey: ['waveform', taskId, 'dub'],
    queryFn: () => dubbingEditorApi.getWaveform(taskId, 'dub'),
    staleTime: 1000 * 60 * 5,
  })

  const originalWaveformQuery = useQuery({
    queryKey: ['waveform', taskId, 'original'],
    queryFn: () => dubbingEditorApi.getWaveform(taskId, 'original'),
    staleTime: 1000 * 60 * 5,
  })

  const { units } = project
  const totalDuration = units.reduce((m, u) => Math.max(m, u.end), 0) || 1

  // Visible units (first 60 for performance)
  const visibleUnits = units.slice(0, 60)

  return (
    <div className="flex h-full flex-col bg-slate-950">
      {/* Original Dialogue track */}
      <div className="border-b border-slate-800">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <span className="w-28 shrink-0 text-[10px] font-medium text-slate-400">Original Dialogue</span>
          <div className="h-10 min-w-0 flex-1 overflow-hidden rounded-sm">
            <WaveformBar
              peaks={originalWaveformQuery.data?.peaks ?? []}
              color="#475569"
              height={40}
            />
          </div>
        </div>
      </div>

      {/* Generated Dub track */}
      <div className="border-b border-slate-800">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <span className="w-28 shrink-0 text-[10px] font-medium text-slate-400">Generated Dub</span>
          <div className="relative h-10 min-w-0 flex-1 overflow-hidden rounded-sm bg-slate-900">
            <WaveformBar
              peaks={dubWaveformQuery.data?.peaks ?? []}
              color="#22c55e"
              height={40}
            />
            {/* Segment clips overlay */}
            {visibleUnits.map(unit => {
              const left = (unit.start / totalDuration) * 100
              const width = ((unit.end - unit.start) / totalDuration) * 100
              const hasIssue = unit.issue_ids.length > 0
              const isSelected = selectedUnit?.unit_id === unit.unit_id
              return (
                <button
                  key={unit.unit_id}
                  type="button"
                  onClick={() => onSelectUnit(unit)}
                  style={{ left: `${left}%`, width: `${Math.max(0.3, width)}%` }}
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
      </div>

      {/* Subtitles / Dialogue Units */}
      <div className="flex items-center gap-2 px-3 py-1.5">
        <span className="w-28 shrink-0 text-[10px] font-medium text-slate-400">Subtitles / Dialogue Units</span>
        <div className="relative h-8 min-w-0 flex-1 overflow-hidden rounded-sm bg-slate-900/50">
          {visibleUnits.map(unit => {
            const left = (unit.start / totalDuration) * 100
            const width = ((unit.end - unit.start) / totalDuration) * 100
            return (
              <button
                key={unit.unit_id}
                type="button"
                onClick={() => onSelectUnit(unit)}
                style={{ left: `${left}%`, width: `${Math.max(0.3, width)}%` }}
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
  )
}

// ---------------------------------------------------------------------------
// Current Line / Video Preview Pane
// ---------------------------------------------------------------------------

function CurrentLinePane({
  project,
  taskId,
  selectedUnit,
  renderRangeResult,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  renderRangeResult: { url: string; start_sec: number; end_sec: number } | null
}) {
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    if (renderRangeResult && audioRef.current) {
      audioRef.current.load()
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
      <div className="border-b border-slate-100 px-5 py-3">
        <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">Current Line</div>
        <div className="mt-1 text-xs text-slate-500">
          {selectedUnit.unit_id} · {formatTimeSec(selectedUnit.start)} – {formatTimeSec(selectedUnit.end)}
        </div>
      </div>

      {/* 2-column body: text left, audio right */}
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
          {/* Status badges */}
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

        {/* Right: playback / render result */}
        <div className="flex w-64 shrink-0 flex-col gap-2 px-4 py-3">
          {/* Range render audio player */}
          {renderRangeResult ? (
            <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2.5">
              <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold text-blue-700">
                <AudioLines size={10} />
                局部预览
              </div>
              <div className="mb-1.5 text-[10px] text-blue-500">
                {formatTimeSec(renderRangeResult.start_sec)} – {formatTimeSec(renderRangeResult.end_sec)}
              </div>
              <audio
                ref={audioRef}
                controls
                src={renderRangeResult.url}
                className="h-8 w-full"
              />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-slate-200 px-3 py-4 text-center">
              <AudioLines size={18} className="mb-1.5 text-slate-300" />
              <div className="text-[10px] text-slate-400">点击顶栏 Render Range</div>
              <div className="text-[10px] text-slate-400">生成局部预览</div>
            </div>
          )}

          {/* Ref audio link */}
          {selectedUnit.current_clip?.audio_artifact_path && (
            <div className="rounded-md border border-slate-100 px-3 py-2">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">配音片段</div>
              <a
                href={`/api/tasks/${taskId}/artifacts/${selectedUnit.current_clip.audio_artifact_path}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 text-[11px] text-blue-600 hover:text-blue-800"
              >
                <AudioLines size={10} />
                {selectedUnit.current_clip.audio_artifact_path.split('/').pop()}
              </a>
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
// Segment Inspector
// ---------------------------------------------------------------------------

function SegmentInspector({
  unit,
  project,
  taskId,
  onApprove,
  onNeedsReview,
  onSaveText,
}: {
  unit: DubbingEditorUnit
  project: DubbingEditorProject
  taskId: string
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, targetText: string) => void
}) {
  const [editingText, setEditingText] = useState(unit.target_text)
  const [isDirty, setIsDirty] = useState(false)

  useEffect(() => {
    setEditingText(unit.target_text)
    setIsDirty(false)
  }, [unit.unit_id, unit.target_text])

  const char = project.characters.find(c => c.character_id === unit.character_id)
  const clip = unit.current_clip

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
            <span
              className={`font-medium ${clip.mix_status === 'placed' ? 'text-emerald-600' : 'text-amber-600'}`}
            >
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
          </button>
          <button
            type="button"
            onClick={() => onNeedsReview(unit.unit_id)}
            disabled={unit.status === 'needs_review'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 py-2 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
          >
            <AlertTriangle size={12} />
            仍需复核
          </button>
        </div>
      </div>
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
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, text: string) => void
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
  const [renderRangeResult, setRenderRangeResult] = useState<{
    url: string
    start_sec: number
    end_sec: number
  } | null>(null)

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
      setRenderRangeResult({
        url: result.url,
        start_sec: result.start_sec,
        end_sec: result.end_sec,
      })
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
      // Optimistic update
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
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50">
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
            selectedUnit={selectedUnit}
            onSelectIssue={handleSelectIssue}
          />
        </div>

        {/* Center: Video Preview + Timeline */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {/* Current line (video preview area) */}
          <div className="border-b border-slate-200 bg-white" style={{ height: '240px', minHeight: '200px' }}>
            <CurrentLinePane
              project={project}
              taskId={taskId}
              selectedUnit={selectedUnit}
              renderRangeResult={renderRangeResult}
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
          />
        </div>
      </div>
    </div>
  )
}
