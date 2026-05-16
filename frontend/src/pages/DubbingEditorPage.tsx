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
  Download,
  ExternalLink,
  Headphones,
  History,
  Keyboard,
  Loader2,
  Maximize2,
  Mic2,
  Minimize2,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
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
  Gauge,
  Wand2,
  VolumeX,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { dubbingEditorApi } from '../api/dubbing-editor'
import { tasksApi } from '../api/tasks'
import { useI18n } from '../i18n/useI18n'
import type { LocaleMessages } from '../i18n/messages'
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

function loadMediaElement(element: HTMLMediaElement) {
  if (typeof navigator !== 'undefined' && navigator.userAgent.includes('jsdom')) return
  try {
    element.load()
  } catch {
    /* Some test/browser environments do not implement media loading. */
  }
}

// ---------------------------------------------------------------------------
// Benchmark Badge (compact status pill used in the status bar)
// ---------------------------------------------------------------------------

function BenchmarkBadge({ status, score }: { status: string; score: number }) {
  const { t } = useI18n()
  const config: Record<string, { label: string; cls: string }> = {
    approved: { label: t.dubbingEditor.benchmark.approved, cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    deliverable_candidate: {
      label: t.dubbingEditor.benchmark.deliverable,
      cls: 'bg-blue-50 text-blue-700 border-blue-200',
    },
    review_required: {
      label: t.dubbingEditor.benchmark.reviewRequired,
      cls: 'bg-amber-50 text-amber-700 border-amber-200',
    },
    blocked: { label: t.dubbingEditor.benchmark.blocked, cls: 'bg-rose-50 text-rose-700 border-rose-200' },
    unknown: { label: t.dubbingEditor.benchmark.unknown, cls: 'bg-slate-50 text-slate-500 border-slate-200' },
  }
  const cfg = config[status] ?? config['unknown']
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${cfg.cls}`}
    >
      <span>{cfg.label}</span>
      <span className="tabular-nums font-semibold">{formatScore(score)}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// P2: Progress Bar
// ---------------------------------------------------------------------------

function ProgressBar({ approved, total }: { approved: number; total: number }) {
  const { t } = useI18n()
  const pct = total > 0 ? (approved / total) * 100 : 0
  const colorCls = pct >= 80 ? 'bg-emerald-500' : pct >= 40 ? 'bg-blue-500' : 'bg-amber-500'
  return (
    <div
      className="flex items-center gap-2"
      data-testid="progress-bar"
      title={t.dubbingEditor.approvedTooltip(approved, total)}
    >
      <div className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorCls}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] tabular-nums text-slate-500">
        {approved}/{total}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Top Bar — two-row layout
//   Row 1 (h-14): identity ← + title    │ mode toggle · Export
//   Row 2 (h-9):  status (benchmark · progress · severity)    │ tools
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
    <div data-testid="severity-chart" className="flex items-center gap-2" title={`P0 ${p0} · P1 ${p1} · P2 ${p2}`}>
      <div className="flex h-1.5 w-20 overflow-hidden rounded-full bg-slate-100">
        {p0 > 0 && <div className="h-full bg-rose-500 transition-all" style={{ width: pct(p0) }} />}
        {p1 > 0 && <div className="h-full bg-amber-400 transition-all" style={{ width: pct(p1) }} />}
        {p2 > 0 && <div className="h-full bg-slate-300 transition-all" style={{ width: pct(p2) }} />}
      </div>
      <div className="flex items-center gap-2 text-[11px] tabular-nums">
        {p0 > 0 && <span className="font-medium text-rose-600">{p0} P0</span>}
        {p1 > 0 && <span className="font-medium text-amber-600">{p1} P1</span>}
        {p2 > 0 && <span className="text-slate-500">{p2} P2</span>}
      </div>
    </div>
  )
}

const TOPBAR_ICON_BTN =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent'

const DUBBING_LAYOUT_STORAGE_KEY = 'translip:dubbing-editor-layout'
const LEFT_PANEL_MIN = 260
const LEFT_PANEL_MAX = 420
const LEFT_PANEL_DEFAULT = 300
const RIGHT_PANEL_MIN = 320
const RIGHT_PANEL_MAX = 520
const RIGHT_PANEL_DEFAULT = 360
const PANEL_RESIZE_STEP = 24

type WorkbenchLayoutPreset = 'review' | 'focus' | 'timeline' | 'voice' | 'preview'
type StoredWorkbenchLayoutPreset = WorkbenchLayoutPreset | 'custom'

interface DubbingWorkbenchLayout {
  leftWidth: number
  rightWidth: number
  leftOpen: boolean
  rightOpen: boolean
  preset: StoredWorkbenchLayoutPreset
}

interface PanelResizeState {
  side: 'left' | 'right'
  startX: number
  startWidth: number
}

const DEFAULT_WORKBENCH_LAYOUT: DubbingWorkbenchLayout = {
  leftWidth: LEFT_PANEL_DEFAULT,
  rightWidth: RIGHT_PANEL_DEFAULT,
  leftOpen: false,
  rightOpen: true,
  preset: 'focus',
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function sanitizePanelWidth(value: unknown, fallback: number, min: number, max: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? clampNumber(Math.round(value), min, max)
    : fallback
}

function isStoredPreset(value: unknown): value is StoredWorkbenchLayoutPreset {
  return value === 'review' || value === 'focus' || value === 'timeline' || value === 'voice' || value === 'preview' || value === 'custom'
}

function readInitialWorkbenchLayout(): DubbingWorkbenchLayout {
  if (typeof window === 'undefined') return DEFAULT_WORKBENCH_LAYOUT
  try {
    const raw = window.localStorage.getItem(DUBBING_LAYOUT_STORAGE_KEY)
    if (!raw) return DEFAULT_WORKBENCH_LAYOUT
    const parsed = JSON.parse(raw) as Partial<DubbingWorkbenchLayout>
    return {
      leftWidth: sanitizePanelWidth(parsed.leftWidth, LEFT_PANEL_DEFAULT, LEFT_PANEL_MIN, LEFT_PANEL_MAX),
      rightWidth: sanitizePanelWidth(parsed.rightWidth, RIGHT_PANEL_DEFAULT, RIGHT_PANEL_MIN, RIGHT_PANEL_MAX),
      leftOpen: typeof parsed.leftOpen === 'boolean' ? parsed.leftOpen : true,
      rightOpen: typeof parsed.rightOpen === 'boolean' ? parsed.rightOpen : true,
      preset: isStoredPreset(parsed.preset) ? parsed.preset : 'custom',
    }
  } catch {
    return DEFAULT_WORKBENCH_LAYOUT
  }
}

function layoutForPreset(preset: WorkbenchLayoutPreset): Pick<DubbingWorkbenchLayout, 'leftOpen' | 'rightOpen' | 'preset'> {
  if (preset === 'focus') return { leftOpen: false, rightOpen: true, preset }
  if (preset === 'timeline') return { leftOpen: false, rightOpen: false, preset }
  if (preset === 'voice') return { leftOpen: false, rightOpen: true, preset }
  return { leftOpen: true, rightOpen: true, preset }
}

function PanelResizeHandle({
  side,
  label,
  value,
  min,
  max,
  onMouseDown,
  onKeyboardResize,
}: {
  side: 'left' | 'right'
  label: string
  value: number
  min: number
  max: number
  onMouseDown: (event: React.MouseEvent<HTMLDivElement>) => void
  onKeyboardResize: (side: 'left' | 'right', delta: number) => void
}) {
  const testId = side === 'left' ? 'resize-issue-queue-panel' : 'resize-inspector-panel'

  return (
    <div
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      tabIndex={0}
      title={label}
      data-testid={testId}
      onMouseDown={onMouseDown}
      onKeyDown={event => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
        event.preventDefault()
        const direction = event.key === 'ArrowRight' ? 1 : -1
        const delta = side === 'left' ? direction * PANEL_RESIZE_STEP : -direction * PANEL_RESIZE_STEP
        onKeyboardResize(side, delta)
      }}
      className="group flex w-2 shrink-0 cursor-col-resize items-center justify-center bg-slate-50 transition-colors hover:bg-blue-50 focus:bg-blue-50 focus:outline-none"
    >
      <span className="h-14 w-1 rounded-full bg-slate-300 transition-colors group-hover:bg-blue-500 group-focus:bg-blue-500" />
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
  layoutPreset,
  onLayoutPresetChange,
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
  layoutPreset: WorkbenchLayoutPreset | 'custom'
  onLayoutPresetChange: (preset: WorkbenchLayoutPreset) => void
}) {
  const { t } = useI18n()
  const { summary, quality_benchmark } = project
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [showMore, setShowMore] = useState(false)
  const moreMenuRef = useRef<HTMLDivElement>(null)
  const shortcutsRef = useRef<HTMLDivElement>(null)

  // Close popovers on outside click
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(e.target as Node)) {
        setShowMore(false)
      }
      if (shortcutsRef.current && !shortcutsRef.current.contains(e.target as Node)) {
        setShowShortcuts(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

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

  // Task name — shown in the identity block next to the back link.
  const taskQuery = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => tasksApi.get(taskId),
    enabled: !!taskId,
    staleTime: 1000 * 60,
  })
  const taskName = taskQuery.data?.name

  return (
    <div className="shrink-0 border-b border-slate-200 bg-white">
      {/* Single-row top bar: identity · status · tools · mode/export */}
      <div className="flex h-12 items-center gap-2 px-3">
        {/* Identity block */}
        <div className="flex min-w-0 shrink items-center gap-1.5">
          <Link
            to={`/tasks/${taskId}`}
            className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
            title={t.dubbingEditor.backToTask}
          >
            <ArrowLeft size={14} />
          </Link>
          <span
            className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900"
            title={taskName ?? taskId}
          >
            {taskName ?? taskId}
          </span>
        </div>

        <span className="h-4 w-px shrink-0 bg-slate-200" aria-hidden="true" />

        {/* Status cluster — compact */}
        <div className="flex shrink-0 items-center gap-2">
          <BenchmarkBadge
            status={quality_benchmark?.status ?? 'unknown'}
            score={summary?.quality_score ?? 0}
          />
          <ProgressBar
            approved={summary?.approved_count ?? 0}
            total={summary?.unit_count ?? 0}
          />
          <IssueSeverityChart project={project} />
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Workbench layout presets */}
        <div
          className="hidden shrink-0 items-center gap-0.5 rounded-lg border border-slate-200 bg-slate-50 p-0.5 xl:flex"
          role="tablist"
          aria-label={t.dubbingEditor.layoutPresetGroupLabel}
        >
          {(['review', 'focus', 'timeline', 'voice', 'preview'] as WorkbenchLayoutPreset[]).map(preset => {
            const active = layoutPreset === preset
            return (
              <button
                key={preset}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`layout-preset-${preset}`}
                onClick={() => onLayoutPresetChange(preset)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  active
                    ? 'bg-slate-900 text-white shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {t.dubbingEditor.layoutPresets[preset]}
              </button>
            )
          })}
        </div>

        {/* Tools — icon-only DAW-style toolbar */}
        <div className="flex shrink-0 items-center gap-0.5">
          {/* Undo / Redo group */}
          <button
            type="button"
            data-testid="undo-btn"
            onClick={onUndo}
            disabled={!canUndo}
            className={TOPBAR_ICON_BTN}
            title={t.dubbingEditor.undoTooltip}
          >
            <Undo2 size={14} />
          </button>
          <button
            type="button"
            data-testid="redo-btn"
            onClick={onRedo}
            disabled={!canRedo}
            className={TOPBAR_ICON_BTN}
            title={t.dubbingEditor.redoTooltip}
          >
            <Redo2 size={14} />
          </button>

          <span className="mx-1 h-4 w-px bg-slate-200" aria-hidden="true" />

          {/* Render-range as primary action (only enabled when a unit is picked) */}
          <button
            type="button"
            onClick={onRenderRange}
            disabled={!selectedUnit}
            className={TOPBAR_ICON_BTN}
            title={`${t.dubbingEditor.renderRange} — ${t.dubbingEditor.renderRangeTooltip}`}
            aria-label={t.dubbingEditor.renderRange}
          >
            <Sliders size={14} />
          </button>

          {/* Refresh as icon-only */}
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            className={TOPBAR_ICON_BTN}
            title={t.dubbingEditor.refreshTooltip}
            aria-label={t.dubbingEditor.refresh}
          >
            <RefreshCw size={14} className={isRefreshing ? 'animate-spin' : ''} />
          </button>

          {/* Keyboard shortcuts popover */}
          <div className="relative" ref={shortcutsRef}>
            <button
              type="button"
              data-testid="keyboard-shortcuts-btn"
              onClick={() => setShowShortcuts(v => !v)}
              className={TOPBAR_ICON_BTN}
              title={t.dubbingEditor.shortcutsTooltip}
              aria-haspopup="true"
              aria-expanded={showShortcuts}
            >
              <Keyboard size={14} />
            </button>
            {showShortcuts && (
              <div
                data-testid="shortcuts-popover"
                className="absolute right-0 top-9 z-50 w-60 rounded-xl border border-slate-200 bg-white p-3 shadow-lg"
              >
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
                  {t.dubbingEditor.shortcutsTitle}
                </div>
                {[
                  ['↓ / J', t.dubbingEditor.shortcutDescriptions.nextIssue],
                  ['↑ / K', t.dubbingEditor.shortcutDescriptions.prevIssue],
                  ['Space', t.dubbingEditor.shortcutDescriptions.togglePlay],
                  ['A', t.dubbingEditor.shortcutDescriptions.approve],
                  ['F', t.dubbingEditor.shortcutDescriptions.needsReview],
                  ['R', t.dubbingEditor.shortcutDescriptions.renderRange],
                  ['Ctrl+Z', t.dubbingEditor.shortcutDescriptions.undo],
                  ['Ctrl+Y', t.dubbingEditor.shortcutDescriptions.redo],
                  ['Esc', t.dubbingEditor.shortcutDescriptions.cancelSelection],
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

          {/* "More" menu — collects SRT export + help/manual */}
          <div className="relative" ref={moreMenuRef}>
            <button
              type="button"
              onClick={() => setShowMore(v => !v)}
              className={TOPBAR_ICON_BTN}
              title={t.dubbingEditor.moreTooltip}
              aria-haspopup="true"
              aria-expanded={showMore}
            >
              <MoreHorizontal size={14} />
            </button>
            {showMore && (
              <div className="absolute right-0 top-9 z-50 w-52 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                <button
                  type="button"
                  data-testid="srt-export-btn"
                  onClick={() => { setShowMore(false); handleSRTExport() }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50"
                  title={t.dubbingEditor.srtExportTooltip}
                >
                  <Download size={13} className="text-slate-400" />
                  {t.dubbingEditor.srtExport}
                </button>
                <a
                  href="/manual.html"
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="help-manual-btn"
                  onClick={() => setShowMore(false)}
                  className="flex items-center gap-2 px-3 py-2 text-xs text-slate-700 hover:bg-slate-50"
                >
                  <BookOpen size={13} className="text-slate-400" />
                  {t.dubbingEditor.helpManual}
                </a>
              </div>
            )}
          </div>

          <span className="mx-1 h-4 w-px bg-slate-200" aria-hidden="true" />

          {/* Mode toggle: Edit ↔ Preview */}
          <div
            className="inline-flex items-center gap-0.5 rounded-lg border border-slate-200 bg-slate-50 p-0.5"
            role="tablist"
            aria-label={t.dubbingEditor.modeGroupLabel}
          >
            <button
              type="button"
              data-testid="mode-edit-btn"
              onClick={() => mode !== 'edit' && onModeToggle()}
              role="tab"
              aria-selected={mode === 'edit'}
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                mode === 'edit'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <PenLine size={11} />
              {t.dubbingEditor.modeEdit}
            </button>
            <button
              type="button"
              data-testid="mode-preview-btn"
              onClick={() => mode !== 'preview' && onModeToggle()}
              role="tab"
              aria-selected={mode === 'preview'}
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                mode === 'preview'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              <Video size={11} />
              {t.dubbingEditor.modePreview}
            </button>
          </div>

          <a
            href={`/api/tasks/${taskId}/artifacts/${project.artifact_paths?.final_dub ?? ''}`}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg bg-blue-600 px-3 text-xs font-medium text-white shadow-[0_6px_14px_-8px_rgba(37,99,235,0.6)] transition-colors hover:bg-blue-700"
          >
            <Download size={13} />
            {t.dubbingEditor.export}
          </a>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Issue Queue
// ---------------------------------------------------------------------------

const ISSUE_TYPE_LABEL_KEYS: Record<string, keyof LocaleMessages['dubbingEditor']['issueTypes']> = {
  voice_gender_mismatch: 'voice_gender_mismatch',
  silent_with_subtitle: 'silent_with_subtitle',
  speaker_similarity_failed: 'speaker_similarity_failed',
  wrong_character: 'wrong_character',
  duration_overrun: 'duration_overrun',
  overlap_conflict: 'overlap_conflict',
  translation_untrusted: 'translation_untrusted',
  pronunciation_issue: 'pronunciation_issue',
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
  const { t } = useI18n()
  const resolved = issue.status === 'resolved' || issue.status === 'ignored'
  const typeKey = ISSUE_TYPE_LABEL_KEYS[issue.type]
  const typeLabel = typeKey ? t.dubbingEditor.issueTypes[typeKey] : issue.type
  return (
    <button
      type="button"
      data-testid={`issue-item-${issue.issue_id}`}
      onClick={onClick}
      className={`w-full rounded-none border-b border-slate-100 px-3 py-2 text-left transition-colors ${
        isSelected
          ? 'bg-blue-50'
          : resolved
            ? 'bg-slate-50/50 opacity-60'
            : 'hover:bg-slate-50'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={issue.severity} />
          <span className={`line-clamp-1 text-xs font-medium ${resolved ? 'text-slate-400 line-through' : 'text-slate-900'}`}>
            {issue.title}
          </span>
        </div>
        <span className="text-[10px] tabular-nums text-slate-400 shrink-0">{formatTimeSec(issue.time_sec)}</span>
      </div>
      <div className="mt-0.5 line-clamp-1 text-[10px] text-slate-400">
        {typeLabel} · {issue.description}
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
  const { t } = useI18n()
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
    <div className="flex h-full flex-col bg-white">
      {/* Summary + quick-stats inline row */}
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-1.5">
        <span className="truncate text-[10px] text-slate-400">
          {t.dubbingEditor.issueQueue.summary(filteredIssues.length, summary?.approved_count ?? 0)}
        </span>
        <div className="flex shrink-0 items-center gap-2 text-[10px] tabular-nums">
          <button
            type="button"
            onClick={() => setFilter(filter === 'P0' ? 'open' : 'P0')}
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${filter === 'P0' ? 'bg-rose-50 text-rose-600' : 'text-slate-500 hover:bg-slate-100'}`}
            title={`P0 ${p0Count}`}
          >
            <span className="font-bold">{p0Count}</span>
            <span className="text-slate-400">P0</span>
          </button>
          <button
            type="button"
            onClick={() => setCharFilter(charFilter === 'all' ? '' : 'all')}
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 transition-colors ${charFilter !== 'all' ? 'bg-blue-50 text-blue-600' : 'text-slate-500 hover:bg-slate-100'}`}
            title={`${t.dubbingEditor.issueQueue.character} ${charReview}`}
          >
            <span className="font-bold">{charReview}</span>
            <span className="text-slate-400">{t.dubbingEditor.issueQueue.character}</span>
          </button>
          <span className="inline-flex items-center gap-1 text-slate-500">
            <span className="font-bold">{candidateCount}</span>
            <span className="text-slate-400">{t.dubbingEditor.issueQueue.candidate}</span>
          </span>
        </div>
      </div>

      {/* Filters + P2 bulk approve */}
      <div className="border-b border-slate-100 px-3 py-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1">
            {(['all', 'open', 'P0', 'P1', 'P2', 'resolved'] as IssueFilter[]).map(f => {
              const label =
                f === 'all'
                  ? t.dubbingEditor.issueQueue.filters.all
                  : f === 'open'
                    ? t.dubbingEditor.issueQueue.filters.open
                    : f === 'resolved'
                      ? t.dubbingEditor.issueQueue.filters.resolved
                      : f
              return (
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
                  {label}
                </button>
              )
            })}
          </div>
          {bulkApprovableP2Units.length > 0 && (
            <button
              type="button"
              data-testid="bulk-approve-btn"
              onClick={() => onBulkApprove(bulkApprovableP2Units)}
              className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 hover:bg-emerald-50 hover:text-emerald-800"
              title={t.dubbingEditor.issueQueue.bulkApproveP2(bulkApprovableP2Units.length)}
              aria-label={t.dubbingEditor.issueQueue.bulkApproveP2(bulkApprovableP2Units.length)}
            >
              <CheckCheck size={11} />
              <span className="tabular-nums">{bulkApprovableP2Units.length}</span>
            </button>
          )}
        </div>
      </div>

      {/* Issues list */}
      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="issue-list">
        {filteredIssues.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            {filter === 'open' ? t.dubbingEditor.issueQueue.noOpen : t.dubbingEditor.issueQueue.noMatches}
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

function IssueQueueRail({
  project,
  onExpand,
}: {
  project: DubbingEditorProject
  onExpand: () => void
}) {
  const { t } = useI18n()
  const openIssues = project.issues.filter(issue => issue.status === 'open')
  const p0 = openIssues.filter(issue => issue.severity === 'P0').length
  const p1 = openIssues.filter(issue => issue.severity === 'P1').length
  const p2 = openIssues.filter(issue => issue.severity === 'P2').length

  return (
    <div
      className="flex h-full w-12 shrink-0 flex-col items-center border-r border-slate-200 bg-slate-50/80 py-2"
      data-testid="issue-queue-rail"
    >
      <button
        type="button"
        onClick={onExpand}
        data-testid="toggle-issue-queue-panel"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600"
        title={t.dubbingEditor.panels.expandIssueQueue}
        aria-label={t.dubbingEditor.panels.expandIssueQueue}
      >
        <PanelLeftOpen size={14} />
      </button>
      <div className="mt-2 flex flex-1 flex-col items-center gap-1.5">
        {[
          ['P0', p0, 'border-rose-200 bg-rose-50 text-rose-700'],
          ['P1', p1, 'border-amber-200 bg-amber-50 text-amber-700'],
          ['P2', p2, 'border-slate-200 bg-white text-slate-500'],
        ].map(([label, count, cls]) => (
          <button
            key={label}
            type="button"
            onClick={onExpand}
            className={`flex h-8 w-8 flex-col items-center justify-center rounded-lg border text-[9px] font-bold leading-none ${cls}`}
            title={`${label} ${count}`}
          >
            <span>{label}</span>
            <span className="mt-0.5 text-[10px] tabular-nums">{count}</span>
          </button>
        ))}
      </div>
      <div className="mb-1 text-[10px] font-semibold text-slate-400 [writing-mode:vertical-rl]">
        {openIssues.length} open
      </div>
    </div>
  )
}

function InspectorRail({
  selectedUnit,
  onExpand,
}: {
  selectedUnit: DubbingEditorUnit | null
  onExpand: () => void
}) {
  const { t } = useI18n()

  return (
    <div
      className="flex h-full w-12 shrink-0 flex-col items-center border-l border-slate-200 bg-slate-50/80 py-2"
      data-testid="inspector-panel-rail"
    >
      <button
        type="button"
        onClick={onExpand}
        data-testid="toggle-inspector-panel"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600"
        title={t.dubbingEditor.panels.expandInspector}
        aria-label={t.dubbingEditor.panels.expandInspector}
      >
        <PanelRightOpen size={14} />
      </button>
      <div className="mt-3 flex flex-1 items-center justify-center">
        <div className="text-[10px] font-semibold text-slate-400 [writing-mode:vertical-rl]">
          {selectedUnit ? selectedUnit.unit_id : t.dubbingEditor.inspector.title}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Character Cast Section
// ---------------------------------------------------------------------------

function CharacterStatusBadge({ status }: { status: string }) {
  const { t } = useI18n()
  if (status === 'passed')
    return (
      <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
        {t.dubbingEditor.characterStatus.passed}
      </span>
    )
  if (status === 'blocked')
    return (
      <span className="rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[10px] font-medium text-rose-700">
        {t.dubbingEditor.characterStatus.blocked}
      </span>
    )
  return (
    <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
      {t.dubbingEditor.characterStatus.review}
    </span>
  )
}

function CharacterCastSection({ characters }: { characters: DubbingEditorCharacter[] }) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="shrink-0 border-t-2 border-slate-100 bg-slate-50/60">
      <button
        type="button"
        onClick={() => setExpanded(e => !e)}
        className="flex w-full items-center justify-between px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:bg-slate-100/60"
      >
        <div className="flex items-center gap-1.5">
          <User size={11} />
          {t.dubbingEditor.characterCast}
          <span className="rounded-full bg-slate-200 px-1.5 py-px text-[9px] tabular-nums text-slate-600">
            {characters.length}
          </span>
        </div>
        {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      </button>
      {expanded && (
        <div className="max-h-48 overflow-y-auto bg-white">
          {characters.map(char => (
            <div key={char.character_id} className="flex items-center justify-between px-3 py-1.5 hover:bg-slate-50">
              <div className="min-w-0">
                <div className="truncate text-xs font-medium text-slate-800">{char.display_name}</div>
                <div className="truncate text-[10px] text-slate-400">
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
  const { t } = useI18n()
  if (pending || !peaks || peaks.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded bg-slate-900/80 text-[10px] text-slate-500"
        style={{ height }}
      >
        {pending ? t.dubbingEditor.waveform.generating : t.dubbingEditor.waveform.loading}
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
  { bg: 'bg-slate-50',   border: 'border-slate-300',   text: 'text-slate-700',   dot: '#2563eb' },
  { bg: 'bg-stone-50',   border: 'border-stone-300',   text: 'text-stone-700',   dot: '#b45309' },
  { bg: 'bg-sky-50',     border: 'border-sky-200',     text: 'text-slate-700',   dot: '#0284c7' },
  { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-slate-700',   dot: '#059669' },
  { bg: 'bg-violet-50',  border: 'border-violet-200',  text: 'text-slate-700',   dot: '#7c3aed' },
  { bg: 'bg-zinc-50',    border: 'border-zinc-300',    text: 'text-zinc-700',    dot: '#52525b' },
  { bg: 'bg-indigo-50',  border: 'border-indigo-200',  text: 'text-slate-700',   dot: '#4f46e5' },
  { bg: 'bg-cyan-50',    border: 'border-cyan-200',    text: 'text-slate-700',   dot: '#0891b2' },
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

// ---------------------------------------------------------------------------
// Playback rate (preview-time speed) — shared across clip preview, edit
// monitor, and legacy video player. Value is normalised to one of
// PLAYBACK_RATE_LEVELS so the UI segmented control always has an exact match.
// ---------------------------------------------------------------------------
const PLAYBACK_RATE_LEVELS = [0.75, 1, 1.25, 1.5, 2] as const
type PlaybackRate = (typeof PLAYBACK_RATE_LEVELS)[number]
const PLAYBACK_RATE_STORAGE_KEY = 'dubbingEditor.playbackRate'
const PLAYBACK_RATE_EVENT = 'dubbingEditor:playbackRateChange'
const DEFAULT_PLAYBACK_RATE: PlaybackRate = 1

function clampPlaybackRate(value: number): PlaybackRate {
  let nearest: PlaybackRate = DEFAULT_PLAYBACK_RATE
  let bestDelta = Number.POSITIVE_INFINITY
  for (const level of PLAYBACK_RATE_LEVELS) {
    const delta = Math.abs(level - value)
    if (delta < bestDelta) {
      bestDelta = delta
      nearest = level
    }
  }
  return nearest
}

function readPlaybackRate(): PlaybackRate {
  if (typeof window === 'undefined') return DEFAULT_PLAYBACK_RATE
  try {
    const raw = window.localStorage.getItem(PLAYBACK_RATE_STORAGE_KEY)
    if (!raw) return DEFAULT_PLAYBACK_RATE
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) return DEFAULT_PLAYBACK_RATE
    return clampPlaybackRate(parsed)
  } catch {
    return DEFAULT_PLAYBACK_RATE
  }
}

function writePlaybackRate(rate: PlaybackRate) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(PLAYBACK_RATE_STORAGE_KEY, String(rate))
  } catch {
    /* ignore quota / privacy errors */
  }
}

function usePlaybackRate(): [PlaybackRate, (rate: PlaybackRate) => void] {
  const [rate, setRateState] = useState<PlaybackRate>(() => readPlaybackRate())

  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<PlaybackRate>).detail
      if (typeof detail === 'number') setRateState(clampPlaybackRate(detail))
    }
    window.addEventListener(PLAYBACK_RATE_EVENT, handler as EventListener)
    return () => window.removeEventListener(PLAYBACK_RATE_EVENT, handler as EventListener)
  }, [])

  const setRate = useCallback((next: PlaybackRate) => {
    const safe = clampPlaybackRate(next)
    setRateState(safe)
    writePlaybackRate(safe)
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent<PlaybackRate>(PLAYBACK_RATE_EVENT, { detail: safe }))
    }
  }, [])

  return [rate, setRate]
}

function applyPlaybackRate(el: HTMLMediaElement | null, rate: PlaybackRate) {
  if (!el) return
  try {
    el.playbackRate = rate
    // Keep pitch stable when slowed/sped (Safari uses preservesPitch, others webkit/moz).
    type PitchPreservingMedia = HTMLMediaElement & {
      preservesPitch?: boolean
      mozPreservesPitch?: boolean
      webkitPreservesPitch?: boolean
    }
    const pp = el as PitchPreservingMedia
    pp.preservesPitch = true
    pp.mozPreservesPitch = true
    pp.webkitPreservesPitch = true
  } catch {
    /* not all browsers expose playbackRate setter */
  }
}

type TimelineTextMode = 'source' | 'target' | 'bilingual'
const TIMELINE_TEXT_MODE_STORAGE_KEY = 'dubbingEditor.timelineTextMode'
const TIMELINE_TEXT_MODES: readonly TimelineTextMode[] = ['source', 'target', 'bilingual'] as const

function readTimelineTextMode(): TimelineTextMode {
  if (typeof window === 'undefined') return 'target'
  try {
    const raw = window.localStorage.getItem(TIMELINE_TEXT_MODE_STORAGE_KEY)
    if (raw === 'source' || raw === 'target' || raw === 'bilingual') return raw
  } catch {
    /* localStorage may be unavailable (private mode / tests) */
  }
  return 'target'
}

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
  const { t } = useI18n()
  const [zoomIdx, setZoomIdx] = useState(2) // 40px/s default
  const pixelsPerSec = ZOOM_LEVELS[zoomIdx]
  const scrollRef = useRef<HTMLDivElement>(null)
  const [textMode, setTextMode] = useState<TimelineTextMode>(() => readTimelineTextMode())
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(TIMELINE_TEXT_MODE_STORAGE_KEY, textMode)
    } catch {
      /* ignore quota / privacy errors */
    }
  }, [textMode])
  const isBilingual = textMode === 'bilingual'
  const laneHeight = isBilingual ? 40 : 28

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
      const nextLeft = Math.max(0, left - 100)
      if (typeof el.scrollTo === 'function') {
        el.scrollTo({ left: nextLeft, behavior: 'smooth' })
      } else {
        el.scrollLeft = nextLeft
      }
    }
  }, [selectedUnit, totalWidth, totalDuration])

  // Playhead position in px
  const playheadLeft = (playheadSec / totalDuration) * totalWidth

  // Auto-scroll to follow playhead when in darkMode (preview) — keep playhead centred
  useEffect(() => {
    if (!darkMode || !scrollRef.current) return
    const el = scrollRef.current
    const trackLabelWidth = 96
    const targetScrollLeft = playheadLeft + trackLabelWidth - el.clientWidth / 2
    const nextLeft = Math.max(0, targetScrollLeft)
    if (typeof el.scrollTo === 'function') {
      el.scrollTo({ left: nextLeft, behavior: 'smooth' })
    } else {
      el.scrollLeft = nextLeft
    }
  }, [darkMode, playheadLeft])

  // Click on scrollable container to seek
  const handleTimelineClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!scrollRef.current) return
      const rect = scrollRef.current.getBoundingClientRect()
      // Account for track label width (96px = w-24)
      const trackLabelWidth = 96
      const clickX = e.clientX - rect.left + scrollRef.current.scrollLeft - trackLabelWidth
      if (clickX < 0) return
      const sec = (clickX / totalWidth) * totalDuration
      onSeek(Math.max(0, Math.min(sec, totalDuration)))
    },
    [totalWidth, totalDuration, onSeek],
  )

  // Render the per-unit label according to the active text mode.
  // Bilingual stacks source above target in two lines; very narrow cards
  // gracefully degrade to a single-line target (full text still visible via title tooltip).
  const renderUnitLabel = useCallback(
    (unit: DubbingEditorUnit, width: number) => {
      if (pixelsPerSec < 40 || width <= 20) return null
      const source = unit.source_text || ''
      const target = unit.target_text || ''
      if (textMode === 'source') {
        return <span className="truncate text-[9px] leading-tight font-medium">{source || target}</span>
      }
      if (textMode === 'target') {
        return <span className="truncate text-[9px] leading-tight font-medium">{target || source}</span>
      }
      // bilingual
      if (width < 56 || !source || !target) {
        return <span className="truncate text-[9px] leading-tight font-medium">{target || source}</span>
      }
      return (
        <span className="flex min-w-0 flex-1 flex-col justify-center leading-tight">
          <span className={`truncate text-[8.5px] ${darkMode ? 'text-slate-400/90' : 'text-slate-500'}`}>{source}</span>
          <span className="truncate text-[9px] font-medium">{target}</span>
        </span>
      )
    },
    [pixelsPerSec, textMode, darkMode],
  )

  return (
    <div className={`flex h-full flex-col ${darkMode ? 'bg-slate-900' : 'bg-white'}`}>
      {/* Header: duration + zoom controls */}
      <div
        data-testid="timeline-header"
        className={`flex shrink-0 items-center justify-between border-b px-3 py-1 ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}
      >
        <span className={`text-[10px] ${darkMode ? 'text-slate-500' : 'text-slate-500'}`}>
          {t.dubbingEditor.timeline.summary(formatTimeSec(totalDuration), units.length)}
        </span>
        <div className="flex items-center gap-3">
          <div
            role="radiogroup"
            aria-label={t.dubbingEditor.timeline.textMode.ariaLabel}
            data-testid="timeline-text-mode"
            className={`inline-flex items-center rounded-md border p-0.5 ${
              darkMode ? 'border-slate-700 bg-slate-800/60' : 'border-slate-200 bg-slate-50'
            }`}
          >
            {TIMELINE_TEXT_MODES.map(mode => {
              const active = textMode === mode
              const label = t.dubbingEditor.timeline.textMode[mode]
              return (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  data-testid={`timeline-text-mode-${mode}`}
                  onClick={e => { e.stopPropagation(); setTextMode(mode) }}
                  className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                    active
                      ? darkMode
                        ? 'bg-slate-700 text-slate-100 shadow-sm'
                        : 'bg-white text-slate-800 shadow-sm'
                      : darkMode
                        ? 'text-slate-400 hover:text-slate-200'
                        : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <div data-testid="zoom-controls" className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoomIdx(i => Math.max(0, i - 1))}
            disabled={zoomIdx === 0}
            className={`rounded p-0.5 disabled:opacity-30 ${darkMode ? 'text-slate-500 hover:bg-slate-700 hover:text-slate-300' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}
            title={t.dubbingEditor.timeline.zoomOut}
          >
            <ZoomOut size={12} />
          </button>
          <span className={`w-14 text-center text-[10px] ${darkMode ? 'text-slate-500' : 'text-slate-500'}`}>{pixelsPerSec}px/s</span>
          <button
            type="button"
            onClick={() => setZoomIdx(i => Math.min(ZOOM_LEVELS.length - 1, i + 1))}
            disabled={zoomIdx === ZOOM_LEVELS.length - 1}
            className={`rounded p-0.5 disabled:opacity-30 ${darkMode ? 'text-slate-500 hover:bg-slate-700 hover:text-slate-300' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-700'}`}
            title={t.dubbingEditor.timeline.zoomIn}
          >
            <ZoomIn size={12} />
          </button>
        </div>
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
              style={{ left: `${playheadLeft + 96}px` }}
            />
          )}

          {/* Original Dialogue track */}
          <div className={`flex shrink-0 items-center gap-0 border-b ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}>
            <span className={`w-24 shrink-0 px-2 text-[10px] font-medium ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>{t.dubbingEditor.timeline.labels.original}</span>
            <div className="h-8 flex-1 overflow-hidden">
              <WaveformBar
                peaks={originalWaveformQuery.data?.peaks ?? []}
                pending={originalWaveformQuery.data?.available === false && originalWaveformQuery.data?.pending}
                color={darkMode ? '#475569' : '#cbd5e1'}
                height={32}
              />
            </div>
          </div>

          {/* Background track */}
          <div className={`flex shrink-0 items-center border-b ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}>
            <span className={`w-24 shrink-0 px-2 text-[10px] font-medium ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>{t.dubbingEditor.timeline.labels.background}</span>
            <div className="h-7 flex-1 overflow-hidden">
              <WaveformBar
                peaks={backgroundWaveformQuery.data?.peaks ?? []}
                pending={backgroundWaveformQuery.data?.available === false && backgroundWaveformQuery.data?.pending}
                color={darkMode ? '#1e293b' : '#334155'}
                height={28}
              />
            </div>
          </div>

          {/* Speaker Lanes — one row per character */}
          <div className={`flex flex-1 flex-col overflow-y-auto border-t ${darkMode ? 'border-slate-700' : 'border-slate-200'}`}>
            {project.characters.length === 0 ? (
              // Fallback: no characters, show flat unit lane
              <div className="flex shrink-0 items-center" style={{ height: `${laneHeight}px` }}>
                <span className={`w-24 shrink-0 px-2 text-[10px] font-medium ${darkMode ? 'text-slate-500' : 'text-slate-400'}`}>{t.dubbingEditor.timeline.labels.units}</span>
                <div className={`relative flex-1 h-full overflow-hidden border-l ${darkMode ? 'bg-slate-800/50 border-slate-700' : 'bg-slate-50/50 border-slate-100'}`}>
                  {units.map(unit => {
                    const left = (unit.start / totalDuration) * totalWidth
                    const width = ((unit.end - unit.start) / totalDuration) * totalWidth
                    const isSelected = selectedUnit?.unit_id === unit.unit_id
                    const fitStrategy = unit.current_clip?.fit_strategy
                    const hasFitWarning = fitStrategy === 'stretch' || fitStrategy === 'pad' || fitStrategy === 'overflow_unfitted'
                    return (
                      <button
                        key={unit.unit_id}
                        type="button"
                        onClick={e => { e.stopPropagation(); onSelectUnit(unit) }}
                        style={{ left: `${left}px`, width: `${Math.max(2, width)}px` }}
                        title={`${unit.source_text}\n→ ${unit.target_text}\n[${formatTimeSec(unit.start)} – ${formatTimeSec(unit.end)}]`}
                        className={`absolute inset-y-0.5 cursor-pointer rounded border text-[9px] font-medium flex items-center overflow-hidden px-1 transition-opacity ${
                          isSelected
                            ? 'bg-blue-100 border-blue-400 ring-1 ring-blue-400 text-blue-700'
                            : hasFitWarning
                              ? 'bg-rose-50 border-rose-300 text-rose-700 opacity-90 hover:opacity-100'
                              : 'bg-slate-100 border-slate-300 text-slate-600 opacity-80 hover:opacity-100'
                        }`}
                      >
                        {renderUnitLabel(unit, width)}
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
                    style={{ height: `${laneHeight}px` }}
                  >
                    {/* Lane label */}
                    <div className="w-24 shrink-0 flex items-center gap-1.5 px-2">
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
                        const fitStrategy = unit.current_clip?.fit_strategy
                        const hasFitWarning = fitStrategy === 'stretch' || fitStrategy === 'pad' || fitStrategy === 'overflow_unfitted'
                        const isSelected = selectedUnit?.unit_id === unit.unit_id
                        return (
                          <button
                            key={unit.unit_id}
                            type="button"
                            onClick={e => { e.stopPropagation(); onSelectUnit(unit) }}
                            style={{ left: `${left}px`, width: `${Math.max(2, width)}px` }}
                            title={`${unit.source_text}\n→ ${unit.target_text}\n[${formatTimeSec(unit.start)} – ${formatTimeSec(unit.end)}]`}
                            className={`absolute inset-y-0.5 cursor-pointer rounded border transition-colors flex items-center overflow-hidden px-1 ${
                              isSelected
                                ? 'bg-blue-50 border-blue-500 ring-1 ring-offset-0 ring-blue-500 text-blue-800 shadow-sm'
                                : hasFitWarning
                                  ? 'bg-rose-50 border-rose-300 text-rose-700 hover:bg-rose-100'
                                  : hasIssue
                                    ? 'bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100'
                                    : `${color.bg} ${color.border} ${color.text} hover:bg-white`
                            }`}
                          >
                            {renderUnitLabel(unit, width)}
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
// Unit status badge
// ---------------------------------------------------------------------------

function UnitStatusBadge({ status }: { status: string }) {
  const { t } = useI18n()
  const config: Record<string, { label: string; cls: string }> = {
    approved: {
      label: t.dubbingEditor.unitStatus.approved,
      cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    },
    locked: { label: t.dubbingEditor.unitStatus.locked, cls: 'bg-blue-50 text-blue-700 border border-blue-200' },
    needs_review: { label: t.dubbingEditor.unitStatus.needs_review, cls: 'bg-amber-50 text-amber-700 border border-amber-200' },
    ignored: { label: t.dubbingEditor.unitStatus.ignored, cls: 'bg-slate-50 text-slate-400 border border-slate-200' },
    unreviewed: { label: t.dubbingEditor.unitStatus.unreviewed, cls: 'bg-slate-50 text-slate-500 border border-slate-200' },
  }
  const cfg = config[status] ?? config['unreviewed']
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${cfg.cls}`}>{cfg.label}</span>
}

// ---------------------------------------------------------------------------
// Segment Inspector (Phase 2: quality scores, voice mismatch, candidate tournament, back-translation)
// ---------------------------------------------------------------------------

function InspectorSection({
  title,
  icon,
  action,
  children,
  className = '',
  collapsible = false,
  defaultCollapsed = false,
  collapsedKey,
  summary,
  testId,
  headerTestId,
}: {
  title: string
  icon?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
  collapsible?: boolean
  defaultCollapsed?: boolean
  collapsedKey?: string | number
  summary?: React.ReactNode
  testId?: string
  headerTestId?: string
}) {
  if (!collapsible) {
    return (
      <section className={`border-b border-slate-100 px-3 py-3 ${className}`}>
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
            {icon}
            <span className="truncate">{title}</span>
          </div>
          {action}
        </div>
        {children}
      </section>
    )
  }

  return (
    <CollapsibleInspectorSection
      key={`${collapsedKey ?? ''}::${defaultCollapsed ? '1' : '0'}`}
      title={title}
      icon={icon}
      action={action}
      className={className}
      defaultCollapsed={defaultCollapsed}
      summary={summary}
      testId={testId}
      headerTestId={headerTestId}
    >
      {children}
    </CollapsibleInspectorSection>
  )
}

function CollapsibleInspectorSection({
  title,
  icon,
  action,
  children,
  className = '',
  defaultCollapsed = false,
  summary,
  testId,
  headerTestId,
}: {
  title: string
  icon?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
  defaultCollapsed?: boolean
  summary?: React.ReactNode
  testId?: string
  headerTestId?: string
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  return (
    <section
      className={`border-b border-slate-100 px-3 py-3 ${className}`}
      data-testid={testId}
      data-collapsed={collapsed ? 'true' : 'false'}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <button
          type="button"
          data-testid={headerTestId}
          onClick={() => setCollapsed(prev => !prev)}
          aria-expanded={!collapsed}
          className="flex min-w-0 flex-1 items-center gap-1.5 rounded text-left text-[10px] font-semibold uppercase tracking-widest text-slate-400 transition-colors hover:text-slate-600 focus:outline-none focus:ring-1 focus:ring-slate-300"
        >
          {collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
          {icon}
          <span className="truncate">{title}</span>
        </button>
        {action}
      </div>
      {collapsed ? (summary ?? null) : children}
    </section>
  )
}

function InspectorMetaRow({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: React.ReactNode
  tone?: 'default' | 'success' | 'warning'
}) {
  const valueCls =
    tone === 'success'
      ? 'text-emerald-600'
      : tone === 'warning'
        ? 'text-amber-600'
        : 'text-slate-700'
  return (
    <div className="flex items-center justify-between gap-3 text-[11px]">
      <span className="shrink-0 text-slate-400">{label}</span>
      <span className={`min-w-0 truncate text-right font-medium ${valueCls}`}>{value}</span>
    </div>
  )
}

function formatClipStatus(status: string | null | undefined, locale: 'zh-CN' | 'en-US'): string {
  if (!status) return locale === 'zh-CN' ? '未知' : 'Unknown'
  const copy: Record<string, { zh: string; en: string }> = {
    placed: { zh: '已放置', en: 'Placed' },
    mixed: { zh: '已混入', en: 'Mixed' },
    pending: { zh: '待处理', en: 'Pending' },
    failed: { zh: '失败', en: 'Failed' },
  }
  const item = copy[status]
  return item ? (locale === 'zh-CN' ? item.zh : item.en) : status
}

function formatFitStrategy(strategy: string | null | undefined, locale: 'zh-CN' | 'en-US'): string {
  if (!strategy) return locale === 'zh-CN' ? '默认' : 'Default'
  const copy: Record<string, { zh: string; en: string }> = {
    pad: { zh: '补静音', en: 'Pad' },
    compress: { zh: '压缩贴合', en: 'Compress' },
    stretch: { zh: '拉伸贴合', en: 'Stretch' },
    trim: { zh: '裁剪', en: 'Trim' },
  }
  const item = copy[strategy]
  return item ? (locale === 'zh-CN' ? item.zh : item.en) : strategy
}

function qualityTone(value: number): { bar: string; dot: string; text: string } {
  if (value >= 0.85) return { bar: 'bg-emerald-500', dot: 'bg-emerald-500', text: 'text-emerald-700' }
  if (value >= 0.72) return { bar: 'bg-amber-400', dot: 'bg-amber-400', text: 'text-amber-700' }
  return { bar: 'bg-rose-500', dot: 'bg-rose-500', text: 'text-rose-700' }
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const bounded = Math.max(0, Math.min(1, value))
  const pct = Math.round(bounded * 100)
  const tone = qualityTone(bounded)
  return (
    <div className="grid grid-cols-[76px_minmax(0,1fr)_34px] items-center gap-2">
      <span className="min-w-0 truncate text-[11px] text-slate-500">{label}</span>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${tone.bar} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-right text-[10px] font-semibold tabular-nums ${tone.text}`}>{pct}%</span>
    </div>
  )
}

type QualityVerdict = 'pass' | 'review' | 'fail'

function computeQualityVerdict(
  speakerSimilarity: number,
  durationRatio: number,
  intelligibility: number,
): { verdict: QualityVerdict; weakest: number } {
  const boundedDuration = Math.min(1, durationRatio)
  const values = [speakerSimilarity, boundedDuration, intelligibility]
  const weakest = values.reduce((min, v) => (v < min ? v : min), values[0])
  const isGood = values.every(v => v >= 0.85)
  const isRisky = weakest < 0.72
  const verdict: QualityVerdict = isGood ? 'pass' : isRisky ? 'fail' : 'review'
  return { verdict, weakest }
}

function QualitySummary({
  speakerSimilarity,
  durationRatio,
  intelligibility,
}: {
  speakerSimilarity: number
  durationRatio: number
  intelligibility: number
}) {
  const { locale } = useI18n()
  const { verdict, weakest } = computeQualityVerdict(
    speakerSimilarity,
    durationRatio,
    intelligibility,
  )
  const isGood = verdict === 'pass'
  const isRisky = verdict === 'fail'
  const label =
    locale === 'zh-CN'
      ? isGood
        ? '可通过'
        : isRisky
          ? '建议重合成'
          : '建议复听'
      : isGood
        ? 'Ready'
        : isRisky
          ? 'Resynthesis advised'
          : 'Review advised'
  const description =
    locale === 'zh-CN'
      ? isGood
        ? '三项指标稳定，重点确认语义即可。'
        : isRisky
          ? '存在明显短板，先复听并考虑重新合成。'
          : '指标接近阈值，复听后再做审核决策。'
      : isGood
        ? 'All metrics are stable. Focus on meaning.'
        : isRisky
          ? 'One metric is weak. Listen again and consider resynthesis.'
          : 'Metrics are near the threshold. Review before deciding.'
  const badgeCls = isGood
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : isRisky
      ? 'border-rose-200 bg-rose-50 text-rose-700'
      : 'border-amber-200 bg-amber-50 text-amber-700'

  return (
    <div className="mb-2.5 flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2">
      <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${qualityTone(weakest).dot}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold text-slate-800">{label}</span>
          <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold ${badgeCls}`}>
            {Math.round(weakest * 100)}%
          </span>
        </div>
        <p className="mt-0.5 text-[10px] leading-4 text-slate-500">{description}</p>
      </div>
    </div>
  )
}

function ClipPreviewPlayer({
  src,
  fileName,
  initialDurationSec,
}: {
  src: string
  fileName?: string
  initialDurationSec?: number | null
}) {
  const { t, locale } = useI18n()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [currentSec, setCurrentSec] = useState(0)
  const [durationSec, setDurationSec] = useState(initialDurationSec ?? 0)
  const [playbackRate, setPlaybackRate] = usePlaybackRate()

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      loadMediaElement(audioRef.current)
    }
  }, [src])

  // Keep the audio element's playbackRate in sync with the global preference.
  useEffect(() => {
    applyPlaybackRate(audioRef.current, playbackRate)
  }, [playbackRate, src])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const updateDuration = () => {
      if (Number.isFinite(audio.duration) && audio.duration > 0) {
        setDurationSec(audio.duration)
      }
    }
    const updateTime = () => setCurrentSec(audio.currentTime || 0)
    const handlePlay = () => setIsPlaying(true)
    const handlePause = () => setIsPlaying(false)
    const handleEnded = () => {
      setIsPlaying(false)
      setCurrentSec(audio.duration || 0)
    }

    audio.addEventListener('loadedmetadata', updateDuration)
    audio.addEventListener('durationchange', updateDuration)
    audio.addEventListener('timeupdate', updateTime)
    audio.addEventListener('play', handlePlay)
    audio.addEventListener('pause', handlePause)
    audio.addEventListener('ended', handleEnded)
    return () => {
      audio.removeEventListener('loadedmetadata', updateDuration)
      audio.removeEventListener('durationchange', updateDuration)
      audio.removeEventListener('timeupdate', updateTime)
      audio.removeEventListener('play', handlePlay)
      audio.removeEventListener('pause', handlePause)
      audio.removeEventListener('ended', handleEnded)
    }
  }, [])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused || !isPlaying) {
      audio.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false))
    } else {
      audio.pause()
      setIsPlaying(false)
    }
  }, [isPlaying])

  const toggleMute = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.muted = !audio.muted
    setIsMuted(audio.muted)
  }, [])

  const seekPreview = useCallback((nextValue: number) => {
    const audio = audioRef.current
    const nextSec = Math.max(0, Math.min(durationSec || nextValue, nextValue))
    if (audio) audio.currentTime = nextSec
    setCurrentSec(nextSec)
  }, [durationSec])

  const handleProgressInput = useCallback(
    (event: React.FormEvent<HTMLInputElement>) => {
      seekPreview(Number(event.currentTarget.value))
    },
    [seekPreview],
  )

  const progressPct = durationSec > 0 ? Math.min(100, (currentSec / durationSec) * 100) : 0
  const playerLabel = locale === 'zh-CN' ? '播放片段音频' : 'Play clip audio'
  const muteLabel = isMuted
    ? t.dubbingEditor.preview.unmute
    : t.dubbingEditor.preview.mute

  return (
    <div
      data-testid="clip-preview-player"
      className="rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,.7)]"
    >
      <audio
        ref={audioRef}
        data-testid="clip-preview-audio"
        preload="metadata"
        src={src}
        className="hidden"
      >
        <track kind="captions" />
      </audio>
      <div className="flex items-center gap-2">
        <button
          type="button"
          data-testid="clip-preview-play"
          onClick={togglePlay}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white shadow-sm transition-colors hover:bg-slate-700"
          title={playerLabel}
          aria-label={playerLabel}
        >
          {isPlaying ? <Pause size={14} /> : <Play size={14} className="ml-0.5" />}
        </button>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span
              data-testid="clip-preview-timecode"
              className="font-mono text-[10px] font-medium tabular-nums text-slate-600"
            >
              {formatTimeSec(currentSec)}
              <span className="mx-1 text-slate-300">/</span>
              {formatTimeSec(durationSec)}
            </span>
            {fileName && (
              <span className="min-w-0 truncate text-[10px] text-slate-400" title={fileName}>
                {fileName}
              </span>
            )}
          </div>
          <div className="relative h-4">
            <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 overflow-hidden rounded-full bg-slate-200">
              <div className="h-full rounded-full bg-blue-500" style={{ width: `${progressPct}%` }} />
            </div>
            <input
              type="range"
              min={0}
              max={durationSec || 0}
              step={0.01}
              value={Math.min(currentSec, durationSec || currentSec)}
              onInput={handleProgressInput}
              onChange={handleProgressInput}
              className="absolute inset-0 h-4 w-full cursor-pointer opacity-0"
              aria-label={t.dubbingEditor.preview.seek}
              title={t.dubbingEditor.preview.seek}
            />
          </div>
        </div>

        <button
          type="button"
          onClick={toggleMute}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white hover:text-slate-700"
          title={muteLabel}
          aria-label={muteLabel}
        >
          {isMuted ? <VolumeX size={14} /> : <Volume2 size={14} />}
        </button>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-white hover:text-slate-700"
          title={fileName ?? src}
          aria-label={locale === 'zh-CN' ? '打开音频文件' : 'Open audio file'}
        >
          <ExternalLink size={13} />
        </a>
      </div>
      <div
        data-testid="clip-preview-rate"
        role="radiogroup"
        aria-label={t.dubbingEditor.preview.playbackRateLabel}
        className="mt-1.5 flex items-center justify-end gap-1"
      >
        <span className="mr-1 text-[10px] font-medium uppercase tracking-widest text-slate-400">
          {t.dubbingEditor.preview.playbackRateLabel}
        </span>
        {PLAYBACK_RATE_LEVELS.map(level => {
          const active = playbackRate === level
          return (
            <button
              key={level}
              type="button"
              role="radio"
              aria-checked={active}
              data-testid={`clip-preview-rate-${level}`}
              onClick={() => setPlaybackRate(level)}
              className={`h-5 rounded-md px-1.5 font-mono text-[10px] tabular-nums transition-colors ${
                active
                  ? 'bg-slate-900 text-white shadow-sm'
                  : 'text-slate-500 hover:bg-white hover:text-slate-700'
              }`}
              title={`${level}×`}
            >
              {level}×
            </button>
          )
        })}
      </div>
    </div>
  )
}

interface FitDescriptor {
  tone: 'success' | 'amber' | 'rose' | 'slate'
  label: string
  hint: string
  showRate: boolean
  showDeltaPercent: boolean
}

function describeFitStrategy(
  strategy: string,
  generatedSec: number | null,
  fittedSec: number | null,
  t: ReturnType<typeof useI18n>['t'],
): FitDescriptor {
  const inspector = t.dubbingEditor.inspector
  const known = strategy && (
    strategy === 'direct'
    || strategy === 'compress'
    || strategy === 'stretch'
    || strategy === 'pad'
    || strategy === 'overflow_unfitted'
    || strategy === 'underflow_unfitted'
  )
  const finalStrategy = known ? strategy : (
    generatedSec && fittedSec && Math.abs(generatedSec - fittedSec) > 0.05
      ? (generatedSec < fittedSec ? 'stretch' : 'compress')
      : 'direct'
  )
  switch (finalStrategy) {
    case 'compress':
      return {
        tone: 'amber',
        label: inspector.fitCompressLabel,
        hint: inspector.fitCompressHint,
        showRate: true,
        showDeltaPercent: true,
      }
    case 'stretch':
      return {
        tone: 'rose',
        label: inspector.fitStretchLabel,
        hint: inspector.fitStretchHint,
        showRate: true,
        showDeltaPercent: true,
      }
    case 'pad':
      return {
        tone: 'rose',
        label: inspector.fitPadLabel,
        hint: inspector.fitPadHint,
        showRate: false,
        showDeltaPercent: false,
      }
    case 'overflow_unfitted':
      return {
        tone: 'rose',
        label: inspector.fitOverflowLabel,
        hint: inspector.fitOverflowHint,
        showRate: true,
        showDeltaPercent: true,
      }
    case 'underflow_unfitted':
      return {
        tone: 'slate',
        label: inspector.fitUnderflowLabel,
        hint: inspector.fitUnderflowHint,
        showRate: false,
        showDeltaPercent: false,
      }
    default:
      return {
        tone: 'success',
        label: inspector.fitDirect,
        hint: inspector.fitDirectHint,
        showRate: false,
        showDeltaPercent: false,
      }
  }
}

const FIT_TONE_STYLES: Record<FitDescriptor['tone'], { dot: string; chip: string; bar: string }> = {
  success: {
    dot: 'bg-emerald-500',
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    bar: 'bg-emerald-400',
  },
  amber: {
    dot: 'bg-amber-500',
    chip: 'bg-amber-50 text-amber-700 border-amber-200',
    bar: 'bg-amber-400',
  },
  rose: {
    dot: 'bg-rose-500',
    chip: 'bg-rose-50 text-rose-700 border-rose-200',
    bar: 'bg-rose-400',
  },
  slate: {
    dot: 'bg-slate-400',
    chip: 'bg-slate-50 text-slate-600 border-slate-200',
    bar: 'bg-slate-300',
  },
}

interface ClipFitMeterProps {
  fitStrategy: string
  generatedDuration: number | null
  fittedDuration: number | null
  sourceDuration: number | null
  onSuggestSpeed?: (speed: number) => void
}

// Snap an arbitrary ratio to the inspector's 5-step synth-speed segmented
// (0.85 / 0.95 / 1 / 1.1 / 1.2). We deliberately *cap* outside ±20% — TTS
// timbre falls apart past that range and the user is better off splitting
// the segment than asking the engine to do the impossible.
const SYNTH_SPEED_LEVELS = [0.85, 0.95, 1, 1.1, 1.2] as const

function snapSynthSpeed(ratio: number): number {
  const clamped = Math.max(SYNTH_SPEED_LEVELS[0], Math.min(SYNTH_SPEED_LEVELS[SYNTH_SPEED_LEVELS.length - 1], ratio))
  let best: number = SYNTH_SPEED_LEVELS[2]
  let bestDelta = Number.POSITIVE_INFINITY
  for (const level of SYNTH_SPEED_LEVELS) {
    const d = Math.abs(level - clamped)
    if (d < bestDelta) {
      bestDelta = d
      best = level
    }
  }
  return best
}

function ClipFitMeter({
  fitStrategy,
  generatedDuration,
  fittedDuration,
  sourceDuration,
  onSuggestSpeed,
}: ClipFitMeterProps) {
  const { t } = useI18n()
  const inspector = t.dubbingEditor.inspector

  const generated = generatedDuration && generatedDuration > 0 ? generatedDuration : null
  const fitted = fittedDuration && fittedDuration > 0 ? fittedDuration : null
  const slot = sourceDuration && sourceDuration > 0 ? sourceDuration : null

  if (!fitted && !generated) return null

  const descriptor = describeFitStrategy(fitStrategy, generated, fitted, t)
  const tone = FIT_TONE_STYLES[descriptor.tone]

  // playback rate = how fast vs. natural read; rate < 1 means slowed down.
  const rate = generated && fitted ? generated / fitted : null
  // delta = how much fitted differs from natural (positive = longer/slower).
  const deltaPercent = generated && fitted ? Math.round(((fitted / generated) - 1) * 100) : null

  const maxDuration = Math.max(generated ?? 0, fitted ?? 0, slot ?? 0, 0.001)
  const widthPct = (v: number | null) => (v ? Math.max(2, Math.min(100, (v / maxDuration) * 100)) : 0)

  const rateText = rate ? `${rate.toFixed(2)}×` : null
  const deltaText = (() => {
    if (deltaPercent == null) return null
    if (deltaPercent > 0) return inspector.fitSlowerPercent.replace('{value}', String(deltaPercent))
    if (deltaPercent < 0) return inspector.fitFasterPercent.replace('{value}', String(-deltaPercent))
    return null
  })()

  const chipText = (() => {
    if (descriptor.showRate && rateText && deltaText) return `${rateText} · ${deltaText}`
    if (descriptor.showRate && rateText) return rateText
    if (descriptor.showDeltaPercent && deltaText) return deltaText
    return descriptor.label
  })()

  return (
    <div data-testid="clip-fit-meter" className="mt-2.5 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
          <Gauge size={11} />
          {inspector.fitTitle}
        </div>
        <div
          data-testid="clip-fit-meter-chip"
          className={`flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${tone.chip}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
          <span>{descriptor.label}</span>
          {(descriptor.showRate || descriptor.showDeltaPercent) && chipText !== descriptor.label && (
            <span className="font-mono text-[10px] tabular-nums">· {chipText}</span>
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        {generated != null && (
          <div data-testid="clip-fit-meter-natural" className="flex items-center gap-2 text-[11px] text-slate-500">
            <span className="w-14 shrink-0">{inspector.fitNatural}</span>
            <div className="relative h-1.5 flex-1 rounded-full bg-slate-100">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-slate-400"
                style={{ width: `${widthPct(generated)}%` }}
              />
            </div>
            <span className="w-12 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-600">
              {generated.toFixed(2)}s
            </span>
          </div>
        )}
        {fitted != null && (
          <div data-testid="clip-fit-meter-fitted" className="flex items-center gap-2 text-[11px] text-slate-500">
            <span className="w-14 shrink-0">{inspector.fitFitted}</span>
            <div className="relative h-1.5 flex-1 rounded-full bg-slate-100">
              <div
                className={`absolute inset-y-0 left-0 rounded-full ${tone.bar}`}
                style={{ width: `${widthPct(fitted)}%` }}
              />
            </div>
            <span className="w-12 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-700">
              {fitted.toFixed(2)}s
            </span>
          </div>
        )}
        {slot != null && (
          <div data-testid="clip-fit-meter-slot" className="flex items-center gap-2 text-[11px] text-slate-400">
            <span className="w-14 shrink-0">{inspector.fitSlot}</span>
            <div className="relative h-1 flex-1 rounded-full bg-slate-100">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-slate-300"
                style={{ width: `${widthPct(slot)}%` }}
              />
            </div>
            <span className="w-12 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-500">
              {slot.toFixed(2)}s
            </span>
          </div>
        )}
      </div>

      <p className="mt-2 text-[11px] leading-4 text-slate-500">{descriptor.hint}</p>
      {/*
        Suggest button: when the meter shows a non-trivial mismatch between
        natural speech and source-slot duration, offer a one-click "fix" that
        snaps the right speed onto the synth-speed segmented and triggers a
        resynth. We compute the suggestion from generated/source rather than
        generated/fitted because the user's *intent* is to make the natural
        read fit the slot, eliminating the post-hoc stretch entirely.
      */}
      {onSuggestSpeed && generated != null && slot != null && Math.abs(generated / slot - 1) >= 0.05 && (() => {
        const suggested = snapSynthSpeed(generated / slot)
        if (suggested === 1) return null
        return (
          <button
            type="button"
            data-testid="clip-fit-meter-suggest"
            onClick={() => onSuggestSpeed(suggested)}
            className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-700 ring-1 ring-inset ring-slate-200 transition-all hover:bg-slate-100 hover:ring-slate-300"
            title={inspector.fitSuggestHint.replace('{value}', `${suggested}×`)}
          >
            <Wand2 size={11} className="text-slate-500" strokeWidth={2.25} />
            <span>{inspector.fitSuggestApply.replace('{value}', `${suggested}×`)}</span>
          </button>
        )
      })()}
    </div>
  )
}

// LiveFitPredictor — drawn under the target_text textarea while the user is
// typing, so they can tell *before* spending GPU on a re-synth whether the
// new wording is going to overflow the slot. The estimate uses the most
// recently synthesised clip as a per-voice/per-segment calibration anchor:
// chars-per-second for *this* unit ≈ chars(target_text) / generated_duration.
// That is far more accurate than a global voice average because it
// implicitly accounts for the speaker's pace, the speed_hint, and the
// language-specific token density. When no baseline exists yet (the unit
// has never been synthesised) we degrade to a hint instead of fabricating
// a number.
type LiveFitTone = 'safe' | 'borderline' | 'over' | 'under' | 'unknown'

function liveFitTone(predicted: number | null, slot: number | null): LiveFitTone {
  if (predicted === null || slot === null || slot <= 0) return 'unknown'
  const ratio = predicted / slot
  if (ratio <= 1.05 && ratio >= 0.7) return 'safe'
  if (ratio < 0.7) return 'under'
  if (ratio <= 1.2) return 'borderline'
  return 'over'
}

function LiveFitPredictor({
  draftText,
  baselineText,
  baselineDuration,
  slotDuration,
}: {
  draftText: string
  baselineText: string
  baselineDuration: number | null
  slotDuration: number | null
}) {
  const { t } = useI18n()

  const baselineChars = baselineText.trim().length
  const draftChars = draftText.trim().length

  const predicted =
    baselineDuration !== null && baselineChars > 0
      ? (baselineDuration / baselineChars) * draftChars
      : null

  const tone = liveFitTone(predicted, slotDuration)

  if (predicted === null || slotDuration === null) {
    return (
      <div
        data-testid="live-fit-predictor"
        data-tone="unknown"
        className="mt-1.5 rounded-md border border-dashed border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-500"
      >
        {t.dubbingEditor.inspector.liveFitNoBaseline}
      </div>
    )
  }

  const delta = predicted - slotDuration
  const palette: Record<LiveFitTone, { wrap: string; chip: string; chipText: string }> = {
    safe: {
      wrap: 'border-emerald-200 bg-emerald-50',
      chip: 'bg-emerald-100',
      chipText: 'text-emerald-700',
    },
    borderline: {
      wrap: 'border-amber-200 bg-amber-50',
      chip: 'bg-amber-100',
      chipText: 'text-amber-700',
    },
    over: {
      wrap: 'border-rose-200 bg-rose-50',
      chip: 'bg-rose-100',
      chipText: 'text-rose-700',
    },
    under: {
      wrap: 'border-sky-200 bg-sky-50',
      chip: 'bg-sky-100',
      chipText: 'text-sky-700',
    },
    unknown: {
      wrap: 'border-slate-200 bg-slate-50',
      chip: 'bg-slate-100',
      chipText: 'text-slate-600',
    },
  }
  const colors = palette[tone]

  const summaryLabel = (() => {
    if (tone === 'over') return t.dubbingEditor.inspector.liveFitOver.replace('{value}', delta.toFixed(2))
    if (tone === 'borderline') return t.dubbingEditor.inspector.liveFitBorderline
    if (tone === 'under') return t.dubbingEditor.inspector.liveFitUnder.replace('{value}', (-delta).toFixed(2))
    return t.dubbingEditor.inspector.liveFitSafe
  })()

  return (
    <div
      data-testid="live-fit-predictor"
      data-tone={tone}
      data-predicted={predicted.toFixed(3)}
      data-slot={slotDuration.toFixed(3)}
      className={`mt-1.5 flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-[11px] ${colors.wrap}`}
    >
      <span className="font-medium text-slate-700">
        {t.dubbingEditor.inspector.liveFitEstimated.replace('{value}', predicted.toFixed(2))}
        <span className="ml-1.5 text-slate-400">
          {t.dubbingEditor.inspector.liveFitSlot.replace('{value}', slotDuration.toFixed(2))}
        </span>
      </span>
      <span
        data-testid="live-fit-predictor-chip"
        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${colors.chip} ${colors.chipText}`}
      >
        {summaryLabel}
      </span>
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
  synthesizedAt,
  synthError,
}: {
  unit: DubbingEditorUnit
  project: DubbingEditorProject
  taskId: string
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, targetText: string) => Promise<void>
  onResynthesize: (unitId: string, targetText?: string, options?: { speed?: number }) => void
  isSynthesizing: boolean
  synthesizedAt: string | null
  synthError: string | null
}) {
  const { t, locale } = useI18n()
  const [editingText, setEditingText] = useState(unit.target_text)
  const [isDirty, setIsDirty] = useState(false)
  const [showBacktranslate, setShowBacktranslate] = useState(false)
  const [copiedSource, setCopiedSource] = useState(false)
  const [synthSpeed, setSynthSpeed] = useState<number>(1)

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

  // Wrapper used by every "重新合成" button inside this inspector. If the
  // user has unsaved edits in the target_text textarea we must persist them
  // *first* (so the backend's materialized view picks them up) before kicking
  // off TTS, otherwise the freshly generated wav will be based on the stale
  // target_text. We swallow save failures here to keep the synth call best
  // effort -- the operations mutation surfaces its own toast/error UI -- and
  // additionally pass ``editingText`` inline so the backend gets a second
  // chance to persist the draft on its end (defence in depth: avoids any
  // race where the save mutation hasn't fully committed yet).
  const handleResynthClick = useCallback(async () => {
    const draft = editingText
    if (isDirty) {
      try {
        await onSaveText(unit.unit_id, draft)
        setIsDirty(false)
      } catch {
        // fall through: backend will receive the previous target_text via
        // materialized state, but inline ``draft`` below still wins.
      }
    }
    onResynthesize(
      unit.unit_id,
      isDirty ? draft : undefined,
      synthSpeed !== 1 ? { speed: synthSpeed } : undefined,
    )
  }, [isDirty, editingText, unit.unit_id, onSaveText, onResynthesize, synthSpeed])

  // Listen for the global "Y" hotkey dispatched from DubbingEditorPage. We
  // do this with a CustomEvent rather than props so the hotkey owner up the
  // tree doesn't need a ref into the inspector and so the keystroke remains
  // a no-op when no inspector is mounted.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ unitId?: string }>).detail
      if (!detail || detail.unitId !== unit.unit_id) return
      if (isSynthesizing) return // hard guard: ignore extra Y while one is in flight
      void handleResynthClick()
    }
    window.addEventListener('dubbingEditor:resynthesizeCurrent', handler as EventListener)
    return () => window.removeEventListener('dubbingEditor:resynthesizeCurrent', handler as EventListener)
  }, [unit.unit_id, handleResynthClick, isSynthesizing])

  const clipFileName = clip.audio_artifact_path?.split('/').pop()
  const clipPreviewSrc = clip.audio_artifact_path
    ? `/api/tasks/${taskId}/artifacts/${clip.audio_artifact_path}?t=${encodeURIComponent(synthesizedAt ?? unit.unit_id)}`
    : null
  const speakerSimilarity = qualitySegment?.speaker_similarity ?? 0.75
  const durationRatio = qualitySegment?.duration_ratio ?? 1
  const intelligibility = qualitySegment?.intelligibility ?? 0.8
  const qualityVerdict = computeQualityVerdict(speakerSimilarity, durationRatio, intelligibility).verdict

  const sourceText = unit.source_text?.trim() ?? ''
  const handleCopySource = useCallback(async () => {
    if (!sourceText) return
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(sourceText)
      }
      setCopiedSource(true)
      window.setTimeout(() => setCopiedSource(false), 1500)
    } catch {
      /* clipboard unavailable; silently ignore */
    }
  }, [sourceText])

  return (
    <div className="space-y-0">
      {/* Segment header */}
      <div className="border-b border-slate-100 bg-white px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-900">{unit.unit_id}</div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-400">
              <span className="truncate">{char?.display_name ?? unit.character_id}</span>
              <span className="font-mono tabular-nums">
                {formatTimeSec(unit.start)} – {formatTimeSec(unit.end)}
              </span>
            </div>
          </div>
          <UnitStatusBadge status={unit.status} />
        </div>
      </div>

      {/* Read-only source text — gives reviewers an always-on reference for the original line. */}
      {sourceText && (
        <InspectorSection
          title={t.dubbingEditor.inspector.sourceText}
          icon={<BookOpen size={11} />}
          action={
            <button
              type="button"
              onClick={handleCopySource}
              aria-label={t.dubbingEditor.inspector.sourceTextCopy}
              title={t.dubbingEditor.inspector.sourceTextCopy}
              data-testid="inspector-source-text-copy"
              className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold transition-colors ${
                copiedSource
                  ? 'text-emerald-600 hover:bg-emerald-50'
                  : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700'
              }`}
            >
              {copiedSource ? t.dubbingEditor.inspector.sourceTextCopied : t.dubbingEditor.inspector.sourceTextCopy}
            </button>
          }
        >
          <div
            data-testid="inspector-source-text"
            className="max-h-32 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-5 text-slate-700"
          >
            {sourceText}
          </div>
        </InspectorSection>
      )}

      {/* Editable target text */}
      <InspectorSection
        title={t.dubbingEditor.inspector.dubText}
        icon={<PenLine size={11} />}
        action={
          isDirty ? (
            <button
              type="button"
              onClick={() => {
                onSaveText(unit.unit_id, editingText)
                setIsDirty(false)
              }}
              className="rounded-md px-1.5 py-0.5 text-[10px] font-semibold text-blue-600 transition-colors hover:bg-blue-50 hover:text-blue-700"
            >
              {t.dubbingEditor.inspector.saveText}
            </button>
          ) : null
        }
      >
        <textarea
          value={editingText}
          onChange={e => {
            setEditingText(e.target.value)
            setIsDirty(e.target.value !== unit.target_text)
          }}
          rows={3}
          className="min-h-[74px] w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm leading-5 text-slate-800 shadow-[inset_0_1px_0_rgba(15,23,42,.03)] transition-colors focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
        />
        <LiveFitPredictor
          draftText={editingText}
          baselineText={unit.target_text}
          baselineDuration={clip.generated_duration ?? null}
          slotDuration={unit.duration ?? null}
        />
      </InspectorSection>

      {/* Clip info */}
      <InspectorSection title={t.dubbingEditor.inspector.clip} icon={<AudioLines size={11} />}>
        {(() => {
          const clipStatusLabel = formatClipStatus(clip.mix_status, locale)
          const isStatusOk = clip.mix_status === 'placed' || clip.mix_status === 'mixed'
          const fitStrategyLabel = clip.fit_strategy ? formatFitStrategy(clip.fit_strategy, locale) : null
          const isOverflowUnfitted = clip.fit_strategy === 'overflow_unfitted'
          const metaWarn = !isStatusOk || isOverflowUnfitted
          const metaSummaryParts: string[] = [clipStatusLabel]
          if (clip.duration) metaSummaryParts.push(`${clip.duration.toFixed(2)}s`)
          if (fitStrategyLabel) metaSummaryParts.push(fitStrategyLabel)
          if (clipFileName) metaSummaryParts.push(clipFileName)
          const metaSummary = metaSummaryParts.join(' · ')
          return (
            <InlineCollapsible
              key={unit.unit_id}
              testId="clip-meta"
              defaultCollapsed={!metaWarn}
              collapsedSummary={metaSummary}
              expandedTitle={t.dubbingEditor.inspector.clipMetaTitle}
              toggleAriaLabel={{
                expand: t.dubbingEditor.inspector.clipMetaToggleExpand,
                collapse: t.dubbingEditor.inspector.clipMetaToggleCollapse,
              }}
              warn={metaWarn}
            >
              <div className="space-y-1.5 rounded-lg bg-slate-50 px-2.5 py-2">
                <InspectorMetaRow
                  label={t.dubbingEditor.inspector.clipStatus}
                  value={clipStatusLabel}
                  tone={isStatusOk ? 'success' : 'warning'}
                />
                {clip.duration && (
                  <InspectorMetaRow
                    label={t.dubbingEditor.inspector.clipDuration}
                    value={`${clip.duration.toFixed(2)}s`}
                  />
                )}
                {fitStrategyLabel && (
                  <InspectorMetaRow
                    label={t.dubbingEditor.inspector.clipFitStrategy}
                    value={fitStrategyLabel}
                  />
                )}
                {clip.audio_artifact_path && (
                  <InspectorMetaRow
                    label={locale === 'zh-CN' ? '文件' : 'File'}
                    value={
                      <a
                        data-testid="clip-audio-link"
                        href={clipPreviewSrc ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="truncate text-blue-600 hover:text-blue-700"
                      >
                        {clipFileName}
                      </a>
                    }
                  />
                )}
              </div>
            </InlineCollapsible>
          )
        })()}

        <ClipFitMeter
          fitStrategy={clip.fit_strategy}
          generatedDuration={clip.generated_duration ?? null}
          fittedDuration={clip.duration ?? null}
          sourceDuration={clip.source_duration ?? unit.duration ?? null}
          onSuggestSpeed={speed => {
            // Adopt the suggestion *and* immediately re-synthesise so the
            // user gets one-click "fix the stretch". We bypass
            // handleResynthClick's draft-save dance because suggestions are
            // about the audio, not the text — but we still preserve any
            // dirty edit by passing it inline.
            setSynthSpeed(speed)
            const draft = isDirty ? editingText : undefined
            onResynthesize(unit.unit_id, draft, { speed })
          }}
        />

        {/* Per-unit clip preview player — listen to *this* segment after re-synthesis */}
        <div data-testid="clip-preview-card" className="mt-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
            <Headphones size={11} />
            {t.dubbingEditor.inspector.clipPreviewTitle}
          </div>
          {clipPreviewSrc ? (
            <>
              <ClipPreviewPlayer
                key={clipPreviewSrc}
                src={clipPreviewSrc}
                fileName={clipFileName}
                initialDurationSec={clip.duration}
              />
              <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-slate-400">
                <span className="min-w-0">{t.dubbingEditor.inspector.clipPreviewHint}</span>
              </div>
              {synthesizedAt && (
                <div className="mt-0.5 text-[10px] text-emerald-600">
                  {t.dubbingEditor.inspector.clipPreviewSynthesizedAt(
                    new Date(synthesizedAt).toLocaleTimeString(),
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[11px] text-slate-400">
              {t.dubbingEditor.inspector.clipPreviewMissing}
            </div>
          )}
        </div>
      </InspectorSection>

      {/* Phase 2: Per-unit quality score breakdown */}
      {(qualitySegment || clip.duration) && (() => {
        const summaryNode = (
          <QualitySummary
            speakerSimilarity={speakerSimilarity}
            durationRatio={durationRatio}
            intelligibility={intelligibility}
          />
        )
        return (
          <InspectorSection
            testId="quality-scores"
            title={t.dubbingEditor.inspector.qualityScores}
            icon={<Sliders size={11} />}
            collapsible
            defaultCollapsed={qualityVerdict === 'pass'}
            collapsedKey={`${unit.unit_id}:${qualityVerdict}`}
            summary={summaryNode}
          >
            {summaryNode}
            <div className="space-y-1.5">
              <ScoreBar label={t.dubbingEditor.inspector.speakerSimilarity} value={speakerSimilarity} />
              <ScoreBar label={t.dubbingEditor.inspector.durationRatio} value={Math.min(1, durationRatio)} />
              <ScoreBar label={t.dubbingEditor.inspector.intelligibility} value={intelligibility} />
            </div>
          </InspectorSection>
        )
      })()}

      {/* Phase 2: Voice mismatch quick-fix */}
      {hasMismatch && (
        <div
          data-testid="voice-mismatch-card"
          className="mx-3 my-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2"
        >
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold text-amber-700">
            <AlertTriangle size={11} />
            {t.dubbingEditor.inspector.voiceMismatchTitle}
          </div>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={handleResynthClick}
              disabled={isSynthesizing}
              className="flex-1 rounded-md bg-amber-100 px-2 py-1.5 text-[10px] font-semibold text-amber-800 transition-colors hover:bg-amber-200 disabled:opacity-50"
            >
              {t.dubbingEditor.inspector.voiceMismatchResynth}
            </button>
            <button
              type="button"
              onClick={() => onApprove(unit.unit_id)}
              className="flex-1 rounded-md bg-white px-2 py-1.5 text-[10px] font-semibold text-slate-700 transition-colors hover:bg-slate-100"
            >
              {t.dubbingEditor.inspector.voiceMismatchExempt}
            </button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div data-testid="clip-primary-actions" className="border-b border-slate-100 bg-white px-3 py-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
            {locale === 'zh-CN' ? '审核与修复' : 'Review actions'}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <button
            type="button"
            onClick={() => onApprove(unit.unit_id)}
            disabled={unit.status === 'approved'}
            className="group inline-flex h-8 items-center justify-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 text-xs font-medium text-emerald-700 transition-all hover:border-emerald-300 hover:bg-emerald-100 hover:text-emerald-800 active:scale-[0.98] disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
          >
            <Check size={12} className="shrink-0" strokeWidth={2.5} />
            <span className="truncate">{t.dubbingEditor.inspector.approve}</span>
            <kbd className="ml-0.5 hidden h-3.5 min-w-3.5 items-center justify-center rounded border border-emerald-200 bg-white px-1 font-mono text-[9px] font-medium text-emerald-600 group-disabled:border-slate-200 group-disabled:text-slate-400 sm:inline-flex">A</kbd>
          </button>
          <button
            type="button"
            onClick={() => onNeedsReview(unit.unit_id)}
            disabled={unit.status === 'needs_review'}
            className="group inline-flex h-8 items-center justify-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2 text-xs font-medium text-amber-700 transition-all hover:border-amber-300 hover:bg-amber-100 hover:text-amber-800 active:scale-[0.98] disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-400"
          >
            <AlertTriangle size={12} className="shrink-0" strokeWidth={2.5} />
            <span className="truncate">{t.dubbingEditor.inspector.needsReview}</span>
            <kbd className="ml-0.5 hidden h-3.5 min-w-3.5 items-center justify-center rounded border border-amber-200 bg-white px-1 font-mono text-[9px] font-medium text-amber-600 group-disabled:border-slate-200 group-disabled:text-slate-400 sm:inline-flex">F</kbd>
          </button>
        </div>

        {/* P1: Re-synthesis button — primary repair action */}
        <div
          data-testid="resynth-speed-control"
          role="radiogroup"
          aria-label={t.dubbingEditor.inspector.synthSpeedLabel}
          className="mt-2 flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1.5"
        >
          <span className="text-[10px] font-medium uppercase tracking-widest text-slate-500">
            {t.dubbingEditor.inspector.synthSpeedLabel}
          </span>
          <div className="flex items-center gap-0.5">
            {[0.85, 0.95, 1, 1.1, 1.2].map(level => {
              const active = synthSpeed === level
              return (
                <button
                  key={level}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  data-testid={`resynth-speed-${level}`}
                  onClick={() => setSynthSpeed(level)}
                  className={`h-5 rounded px-1.5 font-mono text-[10px] tabular-nums transition-colors ${
                    active
                      ? 'bg-slate-900 text-white shadow-sm'
                      : 'text-slate-500 hover:bg-white hover:text-slate-700'
                  }`}
                  title={`${level.toFixed(2)}×`}
                >
                  {level === 1 ? '1×' : `${level}×`}
                </button>
              )
            })}
          </div>
        </div>
        {synthSpeed !== 1 && (
          <p className="mt-1 text-[10px] leading-tight text-slate-500">
            {synthSpeed > 1
              ? t.dubbingEditor.inspector.synthSpeedFasterHint
              : t.dubbingEditor.inspector.synthSpeedSlowerHint}
          </p>
        )}
        <button
          type="button"
          data-testid="resynthesize-btn"
          onClick={handleResynthClick}
          disabled={isSynthesizing}
          className="mt-1.5 inline-flex h-8 w-full items-center justify-center gap-1 rounded-md bg-slate-900 px-2 text-xs font-medium text-white shadow-sm ring-1 ring-inset ring-slate-900/5 transition-all hover:bg-slate-800 active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isSynthesizing ? (
            <Loader2 size={12} className="shrink-0 animate-spin" />
          ) : (
            <RotateCcw size={12} className="shrink-0" strokeWidth={2.5} />
          )}
          <span className="truncate">
            {t.dubbingEditor.inspector.resynthesize}
            {synthSpeed !== 1 ? ` · ${synthSpeed}×` : ''}
          </span>
        </button>
        {synthError && (
          <div
            data-testid="resynth-error-banner"
            role="alert"
            className="mt-1.5 flex items-start gap-1.5 rounded-md bg-rose-50 px-2 py-1.5 text-[11px] leading-tight text-rose-700 ring-1 ring-inset ring-rose-200"
          >
            <AlertTriangle size={11} className="mt-0.5 shrink-0" strokeWidth={2.25} />
            <div className="flex-1">
              <div className="font-medium">{t.dubbingEditor.inspector.resynthFailed}</div>
              <div className="mt-0.5 break-words text-[10px] text-rose-600">{synthError}</div>
            </div>
          </div>
        )}
      </div>

      {/* Phase 2: Back-translation check */}
      <div className="border-t border-slate-100 px-3 py-2">
        <button
          type="button"
          onClick={() => setShowBacktranslate(v => !v)}
          className="flex items-center gap-1.5 text-[10px] font-medium text-slate-500 hover:text-slate-700"
        >
          <AudioLines size={10} />
          {t.dubbingEditor.inspector.backtranslateTitle}
          {showBacktranslate ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        </button>
        {showBacktranslate && (
          <div data-testid="backtranslate-result" className="mt-2 space-y-1.5">
            {backtranslateQuery.isLoading ? (
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <Loader2 size={10} className="animate-spin" />
                {t.dubbingEditor.inspector.backtranslateLoading}
              </div>
            ) : backtranslateQuery.data ? (
              <>
                <div className="text-[10px] text-slate-500">
                  <span className="font-medium text-slate-700">{t.dubbingEditor.inspector.backtranslateHeard}</span>{' '}
                  {backtranslateQuery.data.heard_text}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-slate-500">{t.dubbingEditor.inspector.backtranslateMatch}</span>
                  <ScoreBar label="" value={backtranslateQuery.data.match_score} />
                </div>
                {!backtranslateQuery.data.asr_available && (
                  <div className="text-[9px] text-slate-400">{t.dubbingEditor.inspector.backtranslateAsrUnavailable}</div>
                )}
              </>
            ) : null}
          </div>
        )}
      </div>

      {/* Phase 2: Candidate Tournament */}
      {unit.candidates.length > 0 && (() => {
        const minScore = unit.candidates.reduce<number>((min, c) => {
          if (c.score === null || c.score === undefined) return min
          return c.score < min ? c.score : min
        }, 1)
        const candidateRisky = minScore < 0.6 || qualityVerdict === 'fail'
        const topScore = unit.candidates.reduce<number | null>((max, c) => {
          if (c.score === null || c.score === undefined) return max
          if (max === null || c.score > max) return c.score
          return max
        }, null)
        const topPct = topScore !== null ? `${(topScore * 100).toFixed(0)}` : '—'
        const candidateSummary = `${unit.candidates.length} · top ${topPct}`
        return (
          <InspectorSection
            title={t.dubbingEditor.inspector.candidatesTitle(unit.candidates.length)}
            icon={<Star size={11} />}
            collapsible
            defaultCollapsed={!candidateRisky}
            collapsedKey={`${unit.unit_id}:cand:${candidateRisky ? '1' : '0'}`}
            summary={
              <div className="px-1 text-[10px] text-slate-400">{candidateSummary}</div>
            }
          >
            <div data-testid="candidate-list" className="space-y-1">
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
                      title={t.dubbingEditor.inspector.candidatePlay}
                    >
                      <Play size={10} />
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-2">
              <button
                type="button"
                onClick={handleResynthClick}
                disabled={isSynthesizing}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-slate-200 py-1.5 text-[10px] font-medium text-slate-500 hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
              >
                <RotateCcw size={10} />
                {t.dubbingEditor.inspector.generateMoreCandidates}
              </button>
            </div>
          </InspectorSection>
        )
      })()}

      {/* P2: Operation history accordion */}
      {unitOps.length > 0 && (
        <InspectorSection
          title={t.dubbingEditor.inspector.operationHistory(unitOps.length)}
          icon={<History size={11} />}
          collapsible
          defaultCollapsed
          collapsedKey={`${unit.unit_id}:ops`}
          headerTestId="op-history-btn"
        >
          <div className="space-y-0.5">
            {unitOps.map(op => (
              <div key={op.op_id} className="flex items-center justify-between text-[10px] text-slate-500">
                <span className="font-medium text-slate-700">{op.type}</span>
                <span>{new Date(op.created_at).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </InspectorSection>
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
  const { t } = useI18n()
  const [inputPath, setInputPath] = useState(character.default_voice?.reference_path ?? '')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-96 rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-800">{t.dubbingEditor.voicePicker.title}</div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <X size={14} />
          </button>
        </div>
        <div className="mb-3 text-[11px] text-slate-500">{t.dubbingEditor.voicePicker.characterLabel(character.display_name)}</div>
        <label className="mb-1 block text-[10px] font-medium text-slate-500">{t.dubbingEditor.voicePicker.pathLabel}</label>
        <input
          type="text"
          value={inputPath}
          onChange={e => setInputPath(e.target.value)}
          placeholder={t.dubbingEditor.voicePicker.pathPlaceholder}
          className="mb-3 w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-200"
        />
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-lg border border-slate-200 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            {t.dubbingEditor.voicePicker.cancel}
          </button>
          <button
            type="button"
            onClick={() => { onAssign(inputPath); onClose() }}
            disabled={!inputPath.trim()}
            className="flex-1 rounded-lg bg-blue-600 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {t.dubbingEditor.voicePicker.confirm}
          </button>
        </div>
      </div>
    </div>
  )
}

function InlineCollapsible({
  defaultCollapsed,
  collapsedSummary,
  expandedTitle,
  toggleAriaLabel,
  warn = false,
  testId,
  children,
}: {
  defaultCollapsed: boolean
  collapsedSummary: React.ReactNode
  expandedTitle: React.ReactNode
  toggleAriaLabel: { expand: string; collapse: string }
  warn?: boolean
  testId?: string
  children: React.ReactNode
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  return (
    <div data-testid={testId} data-collapsed={collapsed ? 'true' : 'false'}>
      <button
        type="button"
        onClick={() => setCollapsed(prev => !prev)}
        aria-expanded={!collapsed}
        aria-label={collapsed ? toggleAriaLabel.expand : toggleAriaLabel.collapse}
        className="flex w-full min-w-0 items-center gap-1.5 rounded text-left text-[11px] text-slate-500 transition-colors hover:text-slate-700 focus:outline-none focus:ring-1 focus:ring-slate-300"
      >
        {collapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
        {collapsed ? (
          <span className={`min-w-0 truncate ${warn ? 'text-amber-600' : 'text-slate-500'}`}>
            {collapsedSummary}
          </span>
        ) : (
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
            {expandedTitle}
          </span>
        )}
      </button>
      {!collapsed && <div className="mt-2">{children}</div>}
    </div>
  )
}

function CharacterStatsCollapsible({
  defaultCollapsed,
  compactSummary,
  ratioWarn,
  children,
}: {
  defaultCollapsed: boolean
  compactSummary: string
  ratioWarn: boolean
  children: React.ReactNode
}) {
  const { t } = useI18n()
  return (
    <InlineCollapsible
      testId="character-stats"
      defaultCollapsed={defaultCollapsed}
      collapsedSummary={compactSummary}
      expandedTitle={t.dubbingEditor.inspector.charStatsTitle}
      toggleAriaLabel={{
        expand: t.dubbingEditor.inspector.charStatsToggleExpand,
        collapse: t.dubbingEditor.inspector.charStatsToggleCollapse,
      }}
      warn={ratioWarn}
    >
      {children}
    </InlineCollapsible>
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
  const { t } = useI18n()
  const [showVoicePicker, setShowVoicePicker] = useState(false)

  const failedRatio = character.stats.speaker_failed_ratio
  const failedCount = character.stats.speaker_failed_count
  const segmentCount = character.stats.segment_count
  const hasRisk = failedRatio > 0.15 || character.risk_flags.length > 0

  const pitchValue = `${character.pitch_class}${character.pitch_hz ? ` · ${character.pitch_hz.toFixed(1)}Hz` : ''}`
  const failedRatioPct = (failedRatio * 100).toFixed(0)
  const compactSummary =
    `${pitchValue} · ${segmentCount}${t.dubbingEditor.inspector.charStatsSegSuffix} · ${t.dubbingEditor.inspector.charStatsFailedShort} ${failedCount} (${failedRatioPct}%)`

  return (
    <div className="px-3 py-2">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100">
          <User size={14} className="text-slate-500" />
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-800">{character.display_name}</div>
          <div className="text-[10px] text-slate-400">{character.speaker_ids.join(', ')}</div>
        </div>
      </div>

      <CharacterStatsCollapsible
        key={character.character_id}
        defaultCollapsed={!hasRisk}
        compactSummary={compactSummary}
        ratioWarn={failedRatio > 0.15}
      >
        <div className="space-y-2 text-[11px] text-slate-600">
          <div className="flex justify-between">
            <span className="text-slate-400">{t.dubbingEditor.inspector.pitch}</span>
            <span>{pitchValue}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">{t.dubbingEditor.inspector.voiceLock}</span>
            <span className={character.voice_lock ? 'text-emerald-600' : 'text-slate-500'}>
              {character.voice_lock ? t.dubbingEditor.inspector.voiceLockOn : t.dubbingEditor.inspector.voiceLockOff}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">{t.dubbingEditor.inspector.segments}</span>
            <span>{segmentCount}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">{t.dubbingEditor.inspector.speakerFailed}</span>
            <span
              className={
                failedRatio > 0.15 ? 'font-medium text-amber-600' : 'text-slate-600'
              }
            >
              {failedCount} ({failedRatioPct}%)
            </span>
          </div>
        </div>
      </CharacterStatsCollapsible>

      {/* Phase 2: Voice sample preview + swap */}
      <div className="mt-3 rounded-md border border-slate-100 px-3 py-2">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[10px] font-semibold text-slate-500">{t.dubbingEditor.inspector.voiceReference}</span>
          <button
            type="button"
            data-testid="voice-swap-btn"
            onClick={() => setShowVoicePicker(true)}
            className="flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium text-blue-600 hover:bg-blue-50"
          >
            <Volume2 size={9} />
            {t.dubbingEditor.inspector.voiceSwap}
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
            {t.dubbingEditor.inspector.voiceReferenceMissing}
          </div>
        )}
      </div>

      {character.risk_flags.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-400">{t.dubbingEditor.inspector.riskFlags}</div>
          <div className="flex flex-wrap gap-1">
            {character.risk_flags.map(flag => (
              <span key={flag} className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] text-amber-700">
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}

      {(character.stats.speaker_failed_ratio > 0.15 || character.risk_flags.includes('wrong_character')) && (
        <div data-testid="speaker-attribution-callout" className="mt-3 rounded-md border border-rose-200 bg-rose-50/70 p-2.5">
          <div className="flex items-start gap-1.5">
            <AlertTriangle size={11} className="mt-0.5 shrink-0 text-rose-600" />
            <div className="min-w-0 text-[10.5px] leading-4 text-rose-700">
              <div className="font-semibold">声纹相似度异常</div>
              <div className="mt-0.5 text-rose-600/90">
                可能是上游说话人归属错了。回到说话人核对修正后从 Task B 重跑，效果更彻底。
              </div>
              <Link
                to={`/tasks/${taskId}?speakerReview=1`}
                className="mt-1.5 inline-flex items-center gap-1 rounded bg-white px-1.5 py-0.5 text-[10px] font-medium text-rose-700 ring-1 ring-rose-200 transition-colors hover:bg-rose-100"
              >
                <Mic2 size={10} />
                打开说话人核对
                <ExternalLink size={9} />
              </Link>
            </div>
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
  onTogglePanel,
  onApprove,
  onNeedsReview,
  onSaveText,
  onResynthesize,
  onAssignVoice,
  isSynthesizing,
  synthesizedAt,
  synthError,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  onTogglePanel: () => void
  onApprove: (unitId: string) => void
  onNeedsReview: (unitId: string) => void
  onSaveText: (unitId: string, text: string) => Promise<void>
  onResynthesize: (unitId: string, targetText?: string) => void
  onAssignVoice: (characterId: string, voicePath: string) => void
  isSynthesizing: boolean
  synthesizedAt: string | null
  synthError: string | null
}) {
  const { t } = useI18n()
  if (!selectedUnit) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{t.dubbingEditor.inspector.title}</div>
          <button
            type="button"
            data-testid="toggle-inspector-panel"
            onClick={onTogglePanel}
            className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            title={t.dubbingEditor.panels.collapseInspector}
            aria-label={t.dubbingEditor.panels.collapseInspector}
          >
            <PanelRightClose size={13} />
          </button>
        </div>
        <div className="flex flex-1 items-center justify-center text-sm text-slate-400">
          {t.dubbingEditor.inspector.empty}
        </div>
      </div>
    )
  }

  const char = project.characters.find(c => c.character_id === selectedUnit.character_id)

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{t.dubbingEditor.inspector.title}</div>
          <div className="mt-0.5 truncate text-xs text-slate-600">{selectedUnit.unit_id}</div>
        </div>
        <button
          type="button"
          data-testid="toggle-inspector-panel"
          onClick={onTogglePanel}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          title={t.dubbingEditor.panels.collapseInspector}
          aria-label={t.dubbingEditor.panels.collapseInspector}
        >
          <PanelRightClose size={13} />
        </button>
      </div>

      {/* Segment Inspector */}
      <div>
        <div className="flex items-center gap-1.5 px-3 pt-3 pb-0.5 text-[10px] font-semibold text-slate-500">
          <Settings2 size={11} />
          {t.dubbingEditor.inspector.segment}
        </div>
        <SegmentInspector
          key={`${selectedUnit.unit_id}:${selectedUnit.target_text}`}
          unit={selectedUnit}
          project={project}
          taskId={taskId}
          onApprove={onApprove}
          onNeedsReview={onNeedsReview}
          onSaveText={onSaveText}
          onResynthesize={onResynthesize}
          isSynthesizing={isSynthesizing}
          synthesizedAt={synthesizedAt}
          synthError={synthError}
        />
      </div>

      {/* Character Inspector */}
      {char && (
        <div className="border-t border-slate-100">
          <div className="flex items-center gap-1.5 px-3 pt-3 pb-0.5 text-[10px] font-semibold text-slate-500">
            <User size={11} />
            {t.dubbingEditor.inspector.character}
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
// Edit Video Monitor — video-first workbench surface
// ---------------------------------------------------------------------------

function EditMonitorPane({
  project,
  taskId,
  selectedUnit,
  playheadSec,
  onPlayheadChange,
  renderRangeResult,
  clipAudioRef,
  videoRef,
}: {
  project: DubbingEditorProject
  taskId: string
  selectedUnit: DubbingEditorUnit | null
  playheadSec: number
  onPlayheadChange: (sec: number) => void
  renderRangeResult: { url: string; start_sec: number; end_sec: number } | null
  clipAudioRef: React.RefObject<HTMLAudioElement | null>
  videoRef: React.RefObject<HTMLVideoElement | null>
}) {
  const { t } = useI18n()
  const monitorAudioRef = useRef<HTMLAudioElement>(null)
  const rangeAudioRef = useRef<HTMLAudioElement>(null)
  const progressTrackRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const subtitleRef = useRef<HTMLDivElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioTrack, setAudioTrack] = useState<'original' | 'dub' | 'mix'>('dub')
  const [subtitleMode, setSubtitleMode] = useState<'source' | 'target' | 'bilingual'>('target')
  const [duration, setDuration] = useState(0)
  const [subtitlePos, setSubtitlePos] = useState<{ x: number; y: number } | null>(null)
  const [isDraggingSubtitle, setIsDraggingSubtitle] = useState(false)
  const [playbackRate] = usePlaybackRate()

  // Keep every monitor media element synced with the global preview rate.
  useEffect(() => {
    applyPlaybackRate(videoRef.current, playbackRate)
    applyPlaybackRate(monitorAudioRef.current, playbackRate)
    applyPlaybackRate(rangeAudioRef.current, playbackRate)
    applyPlaybackRate(clipAudioRef.current, playbackRate)
  }, [playbackRate, clipAudioRef, videoRef])

  const videoSrc = `/api/tasks/${taskId}/dubbing-editor/video-preview`
  const activeUnit = selectedUnit ?? project.units.find(u => u.start <= playheadSec && u.end > playheadSec) ?? null
  const clipTrack = audioTrack === 'mix' ? 'preview_mix' : audioTrack
  const monitorAudioPath =
    audioTrack === 'dub'
      ? project.artifact_paths?.dub_voice
      : audioTrack === 'mix'
        ? project.artifact_paths?.preview_mix
        : ''
  const monitorAudioUrl = monitorAudioPath ? `/api/tasks/${taskId}/artifacts/${monitorAudioPath}` : ''
  const usesExternalMonitorAudio = audioTrack !== 'original' && !!monitorAudioUrl

  const clipPreviewQuery = useQuery({
    queryKey: ['clip-preview', taskId, selectedUnit?.unit_id, clipTrack],
    queryFn: () =>
      selectedUnit
        ? dubbingEditorApi.getClipPreview(taskId, Math.max(0, selectedUnit.start - 0.2), selectedUnit.end + 0.2, clipTrack)
        : null,
    enabled: !!selectedUnit && !!taskId,
    staleTime: 1000 * 60,
  })

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const audio = monitorAudioRef.current
    const syncExternalAudio = () => {
      if (!usesExternalMonitorAudio || !audio || video.paused) return
      if (Math.abs(audio.currentTime - video.currentTime) > 0.25) {
        audio.currentTime = video.currentTime
      }
    }
    const onTimeUpdate = () => {
      onPlayheadChange(video.currentTime)
      syncExternalAudio()
    }
    const onDurationChange = () => setDuration(video.duration || 0)
    const onPlay = () => {
      setIsPlaying(true)
      if (!audio) return
      if (!usesExternalMonitorAudio) {
        audio.pause()
        video.muted = false
        return
      }
      video.muted = true
      audio.currentTime = video.currentTime
      audio.play().catch(() => {})
    }
    const onPause = () => {
      setIsPlaying(false)
      audio?.pause()
    }
    const onEnded = () => {
      setIsPlaying(false)
      audio?.pause()
    }
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
  }, [onPlayheadChange, usesExternalMonitorAudio, videoRef])

  useEffect(() => {
    const video = videoRef.current
    const audio = monitorAudioRef.current
    if (!video || !audio) return

    if (!usesExternalMonitorAudio) {
      audio.pause()
      audio.removeAttribute('src')
      video.muted = false
      return
    }

    video.muted = true
    audio.currentTime = video.currentTime
    loadMediaElement(audio)
    if (!video.paused) {
      audio.play().catch(() => {})
    }
  }, [monitorAudioUrl, usesExternalMonitorAudio, videoRef])

  useEffect(() => {
    if (!selectedUnit || !videoRef.current) return
    const video = videoRef.current
    if (Math.abs(video.currentTime - selectedUnit.start) > 0.5) {
      video.currentTime = selectedUnit.start
      onPlayheadChange(selectedUnit.start)
    }
  }, [selectedUnit, onPlayheadChange, videoRef])

  useEffect(() => {
    if (!clipAudioRef.current) return
    const url = clipPreviewQuery.data?.url
    if (url) {
      clipAudioRef.current.src = url
      clipAudioRef.current.dataset.startSec = String(clipPreviewQuery.data?.start_sec ?? selectedUnit?.start ?? 0)
      loadMediaElement(clipAudioRef.current)
    }
  }, [clipAudioRef, clipPreviewQuery.data?.start_sec, clipPreviewQuery.data?.url, selectedUnit?.start])

  useEffect(() => {
    if (renderRangeResult && rangeAudioRef.current) {
      loadMediaElement(rangeAudioRef.current)
    }
  }, [renderRangeResult])

  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    const audio = monitorAudioRef.current

    if (video.paused) {
      if (usesExternalMonitorAudio && audio) {
        video.muted = true
        audio.currentTime = video.currentTime
        audio.play().catch(() => {})
      } else {
        video.muted = false
        audio?.pause()
      }
      video.play().catch(() => {})
    } else {
      video.pause()
      audio?.pause()
    }
  }, [usesExternalMonitorAudio, videoRef])

  const toggleClipPreview = useCallback(() => {
    const audio = clipAudioRef.current
    if (!audio || !clipPreviewQuery.data?.url) return
    const video = videoRef.current
    if (audio.paused) {
      video?.pause()
      if (audio.ended) audio.currentTime = 0
      audio.play().catch(() => {})
    } else {
      audio.pause()
    }
  }, [clipAudioRef, clipPreviewQuery.data?.url, videoRef])

  const projectDuration = project.units.reduce((max, unit) => Math.max(max, unit.end), 0)
  const monitorDuration = Math.max(duration || 0, projectDuration, playheadSec, 1)
  const progressPct = Math.min(100, Math.max(0, (playheadSec / monitorDuration) * 100))
  const seekMonitor = useCallback(
    (sec: number) => {
      const nextSec = clampNumber(sec, 0, monitorDuration)
      const video = videoRef.current
      if (video) {
        video.currentTime = nextSec
      }
      const audio = clipAudioRef.current
      if (audio && !audio.paused) audio.pause()
      const monitorAudio = monitorAudioRef.current
      if (monitorAudio && usesExternalMonitorAudio) {
        monitorAudio.currentTime = nextSec
      }
      onPlayheadChange(nextSec)
    },
    [clipAudioRef, monitorDuration, onPlayheadChange, usesExternalMonitorAudio, videoRef],
  )
  const seekMonitorFromClientX = useCallback(
    (clientX: number) => {
      const rect = progressTrackRef.current?.getBoundingClientRect()
      if (!rect || rect.width <= 0) return
      const pct = clampNumber((clientX - rect.left) / rect.width, 0, 1)
      seekMonitor(pct * monitorDuration)
    },
    [monitorDuration, seekMonitor],
  )
  const handleProgressMouseDown = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault()
      seekMonitorFromClientX(event.clientX)

      const handleMouseMove = (moveEvent: MouseEvent) => {
        seekMonitorFromClientX(moveEvent.clientX)
      }
      const handleMouseUp = () => {
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
      }

      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    },
    [seekMonitorFromClientX],
  )
  const handleProgressInput = useCallback(
    (event: React.FormEvent<HTMLInputElement>) => {
      seekMonitor(Number(event.currentTarget.value))
    },
    [seekMonitor],
  )
  const handleSubtitlePointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const stage = stageRef.current
    const subtitle = subtitleRef.current
    if (!stage || !subtitle) return
    event.preventDefault()
    event.stopPropagation()

    const stageRect = stage.getBoundingClientRect()
    const subRect = subtitle.getBoundingClientRect()
    const offsetX = event.clientX - subRect.left
    const offsetY = event.clientY - subRect.top

    setIsDraggingSubtitle(true)

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const nextLeft = moveEvent.clientX - stageRect.left - offsetX
      const nextTop = moveEvent.clientY - stageRect.top - offsetY
      const maxLeft = Math.max(0, stageRect.width - subRect.width)
      const maxTop = Math.max(0, stageRect.height - subRect.height)
      setSubtitlePos({
        x: clampNumber(nextLeft, 0, maxLeft),
        y: clampNumber(nextTop, 0, maxTop),
      })
    }
    const handlePointerUp = () => {
      setIsDraggingSubtitle(false)
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
      window.removeEventListener('pointercancel', handlePointerUp)
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    window.addEventListener('pointercancel', handlePointerUp)
  }, [])
  const resetSubtitlePosition = useCallback(() => {
    setSubtitlePos(null)
  }, [])
  const sourceText = activeUnit?.source_text || t.dubbingEditor.currentLine.empty
  const targetText = activeUnit?.target_text || ''
  const canPreviewClip = !!selectedUnit && !!clipPreviewQuery.data?.url

  return (
    <div
      data-testid="edit-monitor-pane"
      className="flex h-full flex-col overflow-hidden border-b border-slate-200 bg-[#111827]"
    >
      <audio
        ref={monitorAudioRef}
        data-testid="edit-monitor-audio"
        src={monitorAudioUrl || undefined}
        preload="metadata"
        className="hidden"
      />
      <audio ref={clipAudioRef} preload="none" className="hidden" />

      <div ref={stageRef} className="relative min-h-0 flex-1 overflow-hidden bg-[#111827]">
        <video
          ref={videoRef}
          data-testid="edit-monitor-video"
          src={videoSrc}
          className="h-full w-full object-contain"
          preload="metadata"
          muted={usesExternalMonitorAudio}
          playsInline
        />

        <div className="absolute left-3 top-3 flex flex-wrap items-center gap-2">
          <span className="rounded-md border border-white/10 bg-black/45 px-2 py-1 text-[11px] font-medium text-slate-100 shadow-sm backdrop-blur-sm">
            {activeUnit
              ? `${formatTimeSec(activeUnit.start)} – ${formatTimeSec(activeUnit.end)}`
              : t.dubbingEditor.currentLine.title}
          </span>
          <span className="rounded-md border border-white/10 bg-black/45 px-2 py-1 text-[11px] font-medium text-slate-100 shadow-sm backdrop-blur-sm">
            {audioTrack === 'mix'
              ? t.dubbingEditor.preview.mix
              : audioTrack === 'dub'
                ? t.dubbingEditor.preview.dub
                : t.dubbingEditor.preview.original}
          </span>
        </div>

        <div
          ref={subtitleRef}
          data-testid="edit-monitor-subtitle"
          role="group"
          aria-label={t.dubbingEditor.preview.dragSubtitle}
          title={t.dubbingEditor.preview.dragSubtitle}
          onPointerDown={handleSubtitlePointerDown}
          onDoubleClick={resetSubtitlePosition}
          className={`group absolute w-[min(760px,82%)] select-none text-center ${
            subtitlePos
              ? ''
              : 'bottom-16 left-1/2 -translate-x-1/2'
          } ${isDraggingSubtitle ? 'cursor-grabbing' : 'cursor-grab'}`}
          style={
            subtitlePos
              ? { left: `${subtitlePos.x}px`, top: `${subtitlePos.y}px` }
              : undefined
          }
        >
          {(subtitleMode === 'source' || subtitleMode === 'bilingual') && (
            <div className="inline-block rounded-md bg-black/45 px-2.5 py-0.5 text-sm font-semibold leading-snug text-white shadow-lg shadow-black/20 backdrop-blur-sm">
              {sourceText}
            </div>
          )}
          {(subtitleMode === 'target' || subtitleMode === 'bilingual') && targetText && (
            <div className="mt-1 inline-block rounded-md bg-black/50 px-2.5 py-1 text-[15px] font-semibold leading-snug text-white shadow-lg shadow-black/20 backdrop-blur-sm">
              {targetText}
            </div>
          )}
          {subtitlePos && (
            <button
              type="button"
              onPointerDown={event => event.stopPropagation()}
              onClick={resetSubtitlePosition}
              className="pointer-events-auto absolute -top-2 -right-2 hidden rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-medium text-slate-100 shadow-md ring-1 ring-white/10 transition-colors hover:bg-black/85 group-hover:inline-flex"
              title={t.dubbingEditor.preview.resetSubtitlePosition}
            >
              {t.dubbingEditor.preview.resetSubtitlePosition}
            </button>
          )}
        </div>

        <div className="absolute inset-x-0 bottom-0 flex h-11 items-center gap-2 bg-gradient-to-t from-black/80 via-black/55 to-transparent px-3 text-slate-200">
          <button
            type="button"
            data-testid="edit-monitor-play"
            onClick={togglePlay}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white shadow-lg shadow-black/25 transition-colors hover:bg-blue-500"
            title={isPlaying ? t.dubbingEditor.preview.pause : t.dubbingEditor.preview.play}
          >
            {isPlaying ? <Pause size={15} /> : <Play size={15} className="ml-0.5" />}
          </button>
          <span data-testid="edit-monitor-timecode" className="w-28 shrink-0 font-mono text-[11px] text-slate-100">
            {formatTimeSec(playheadSec)}
            <span className="mx-1 text-slate-500">/</span>
            {formatTimeSec(monitorDuration)}
          </span>
          <div
            ref={progressTrackRef}
            data-testid="edit-monitor-progress-track"
            className="group relative h-7 min-w-20 flex-1"
            onMouseDown={handleProgressMouseDown}
          >
            <div className="pointer-events-none absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 overflow-hidden rounded-full bg-white/20">
              <div className="h-full rounded-full bg-blue-500" style={{ width: `${progressPct}%` }} />
            </div>
            <div
              className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white bg-blue-500 shadow-sm shadow-black/30"
              style={{ left: `${progressPct}%` }}
            />
            <input
              data-testid="edit-monitor-progress"
              type="range"
              min={0}
              max={monitorDuration}
              step={0.01}
              value={Math.min(playheadSec, monitorDuration)}
              onInput={handleProgressInput}
              onChange={handleProgressInput}
              className="absolute inset-0 h-7 w-full cursor-pointer opacity-0"
              aria-label={t.dubbingEditor.preview.seek}
              title={t.dubbingEditor.preview.seek}
            />
          </div>
          <button
            type="button"
            onClick={toggleClipPreview}
            disabled={!canPreviewClip}
            className="flex h-7 shrink-0 items-center gap-1.5 rounded-lg border border-white/10 bg-black/35 px-2 text-[11px] font-medium text-slate-200 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:text-slate-600"
            title={t.dubbingEditor.preview.segmentPreview}
          >
            <AudioLines size={13} />
            <span className="hidden xl:inline">
              {clipPreviewQuery.isLoading ? t.dubbingEditor.currentLine.loading : t.dubbingEditor.preview.segmentPreview}
            </span>
          </button>
          <div className="flex shrink-0 items-center rounded-lg border border-white/10 bg-black/35 p-0.5">
            {(['original', 'dub', 'mix'] as const).map(track => (
              <button
                key={track}
                type="button"
                onClick={() => setAudioTrack(track)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  audioTrack === track
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-slate-100'
                }`}
              >
                {track === 'mix'
                  ? t.dubbingEditor.preview.mix
                  : track === 'dub'
                    ? t.dubbingEditor.preview.dub
                    : t.dubbingEditor.preview.original}
              </button>
            ))}
          </div>
          <div className="flex shrink-0 items-center rounded-lg border border-white/10 bg-black/35 p-0.5">
            {(['source', 'target', 'bilingual'] as const).map(mode => (
              <button
                key={mode}
                type="button"
                onClick={() => setSubtitleMode(mode)}
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  subtitleMode === mode
                    ? 'bg-white text-slate-950 shadow-sm'
                    : 'text-slate-400 hover:text-slate-100'
                }`}
              >
                {mode === 'source'
                  ? t.dubbingEditor.preview.sourceSubtitle
                  : mode === 'target'
                    ? t.dubbingEditor.preview.targetSubtitle
                    : t.dubbingEditor.preview.bilingualSubtitle}
              </button>
            ))}
          </div>
        </div>
      </div>

      {renderRangeResult && (
        <div className="flex h-9 shrink-0 items-center gap-2 border-t border-slate-800 bg-slate-900 px-3">
          <AudioLines size={12} className="text-blue-300" />
          <span className="text-[11px] font-semibold text-blue-100">
            {t.dubbingEditor.currentLine.rangePreview}
          </span>
          <span className="text-[10px] tabular-nums text-blue-200">
            {formatTimeSec(renderRangeResult.start_sec)} – {formatTimeSec(renderRangeResult.end_sec)}
          </span>
          <audio
            ref={rangeAudioRef}
            controls
            src={renderRangeResult.url}
            className="ml-auto h-7 w-[260px]"
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
  const { t } = useI18n()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [audioTrack, setAudioTrack] = useState<'original' | 'dub'>('dub')
  const [duration, setDuration] = useState(0)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [playbackRate] = usePlaybackRate()

  useEffect(() => {
    applyPlaybackRate(videoRef.current, playbackRate)
  }, [playbackRate])

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
              title={isPlaying ? t.dubbingEditor.preview.pause : t.dubbingEditor.preview.play}
            >
              {isPlaying ? <Pause size={16} /> : <Play size={16} />}
            </button>

            {/* Mute */}
            <button
              type="button"
              onClick={toggleMute}
              className="flex h-7 w-7 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              title={isMuted ? t.dubbingEditor.preview.unmute : t.dubbingEditor.preview.mute}
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
                {t.dubbingEditor.preview.original}
              </button>
              <button
                type="button"
                onClick={() => setAudioTrack('dub')}
                className={`rounded px-2 py-0.5 font-medium transition-colors ${
                  audioTrack === 'dub' ? 'bg-blue-500 text-white shadow-sm' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {t.dubbingEditor.preview.dub}
              </button>
            </div>

            {/* Fullscreen */}
            <button
              type="button"
              onClick={toggleFullscreen}
              className="flex h-7 w-7 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              title={t.dubbingEditor.preview.fullscreen}
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
  const { t } = useI18n()
  const { id: taskId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const [selectedUnit, setSelectedUnit] = useState<DubbingEditorUnit | null>(null)
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null)
  const [isSynthesizing, setIsSynthesizing] = useState(false)
  // Concurrency guard: a useRef so re-entrant calls inside the same tick
  // (e.g. user hammers Y, or hotkey + button fire together) see the latched
  // truth without waiting for React's setState commit.
  const synthInFlightRef = useRef(false)
  // Per-unit cache-busting token: latest synthesize-unit response timestamp.
  // When this changes for the selected unit, the inspector's preview <audio>
  // element re-mounts and reloads the freshly synthesized clip.
  const [synthesizedAtByUnit, setSynthesizedAtByUnit] = useState<Record<string, string>>({})
  // Per-unit synthesize error message, cleared on the next successful run for
  // the same unit. Surfaced as a small banner under the resynth button.
  const [synthErrorByUnit, setSynthErrorByUnit] = useState<Record<string, string>>({})
  const [renderRangeResult, setRenderRangeResult] = useState<{
    url: string
    start_sec: number
    end_sec: number
  } | null>(null)

  // Phase 2: undo/redo cursor (number of ops to replay)
  const [opCursor, setOpCursor] = useState<number | null>(null)
  const [playheadSec, setPlayheadSec] = useState(0)
  const [editorMode, setEditorMode] = useState<'edit' | 'preview'>('edit')
  const [workbenchLayout, setWorkbenchLayout] = useState<DubbingWorkbenchLayout>(readInitialWorkbenchLayout)
  const [resizeState, setResizeState] = useState<PanelResizeState | null>(null)

  // P0: refs for primary video playback and selected-clip audio previews
  const clipAudioRef = useRef<HTMLAudioElement | null>(null)
  const editVideoRef = useRef<HTMLVideoElement | null>(null)
  const autoSelectedTaskRef = useRef<string | null>(null)

  useEffect(() => {
    try {
      window.localStorage.setItem(DUBBING_LAYOUT_STORAGE_KEY, JSON.stringify(workbenchLayout))
    } catch {
      /* ignore private mode / quota errors */
    }
  }, [workbenchLayout])

  useEffect(() => {
    if (!resizeState) return

    const previousCursor = document.body.style.cursor
    const previousSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handleMouseMove = (event: MouseEvent) => {
      const rawWidth =
        resizeState.side === 'left'
          ? resizeState.startWidth + event.clientX - resizeState.startX
          : resizeState.startWidth + resizeState.startX - event.clientX
      const min = resizeState.side === 'left' ? LEFT_PANEL_MIN : RIGHT_PANEL_MIN
      const max = resizeState.side === 'left' ? LEFT_PANEL_MAX : RIGHT_PANEL_MAX
      const nextWidth = clampNumber(Math.round(rawWidth), min, max)

      setWorkbenchLayout(prev => ({
        ...prev,
        preset: 'custom',
        ...(resizeState.side === 'left' ? { leftWidth: nextWidth } : { rightWidth: nextWidth }),
      }))
    }

    const handleMouseUp = () => setResizeState(null)

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousSelect
    }
  }, [resizeState])

  const activeLayoutPreset: WorkbenchLayoutPreset | 'custom' =
    editorMode === 'preview' ? 'preview' : workbenchLayout.preset === 'preview' ? 'review' : workbenchLayout.preset

  const beginPanelResize = useCallback(
    (side: 'left' | 'right', event: React.MouseEvent<HTMLDivElement>) => {
      event.preventDefault()
      setResizeState({
        side,
        startX: event.clientX,
        startWidth: side === 'left' ? workbenchLayout.leftWidth : workbenchLayout.rightWidth,
      })
    },
    [workbenchLayout.leftWidth, workbenchLayout.rightWidth],
  )

  const handleKeyboardResize = useCallback((side: 'left' | 'right', delta: number) => {
    setWorkbenchLayout(prev => {
      if (side === 'left') {
        return {
          ...prev,
          preset: 'custom',
          leftWidth: clampNumber(prev.leftWidth + delta, LEFT_PANEL_MIN, LEFT_PANEL_MAX),
        }
      }
      return {
        ...prev,
        preset: 'custom',
        rightWidth: clampNumber(prev.rightWidth + delta, RIGHT_PANEL_MIN, RIGHT_PANEL_MAX),
      }
    })
  }, [])

  const setIssueQueueOpen = useCallback((leftOpen: boolean) => {
    setWorkbenchLayout(prev => ({ ...prev, leftOpen, preset: 'custom' }))
  }, [])

  const setInspectorOpen = useCallback((rightOpen: boolean) => {
    setWorkbenchLayout(prev => ({ ...prev, rightOpen, preset: 'custom' }))
  }, [])

  const handleLayoutPresetChange = useCallback((preset: WorkbenchLayoutPreset) => {
    if (preset === 'preview') {
      setEditorMode('preview')
      return
    }
    setEditorMode('edit')
    setWorkbenchLayout(prev => ({ ...prev, ...layoutForPreset(preset) }))
  }, [])

  // Phase 2: animate playhead from audio current time
  useEffect(() => {
    let rafId: number
    const tick = () => {
      const audio = clipAudioRef.current
      if (audio && !audio.paused) {
        const startSec = Number(audio.dataset.startSec ?? 0)
        setPlayheadSec(startSec + audio.currentTime)
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

  useEffect(() => {
    const project = projectQuery.data
    if (!project || !taskId || autoSelectedTaskRef.current === taskId) return

    const severityRank: Record<DubbingEditorIssue['severity'], number> = { P0: 0, P1: 1, P2: 2 }
    const firstOpenIssue = [...project.issues]
      .filter(issue => issue.status === 'open')
      .sort((a, b) => severityRank[a.severity] - severityRank[b.severity] || a.time_sec - b.time_sec)[0]

    if (firstOpenIssue) {
      const unit = project.units.find(u => u.unit_id === firstOpenIssue.unit_id)
      setSelectedIssueId(firstOpenIssue.issue_id)
      if (unit) setSelectedUnit(unit)
    } else if (project.units.length > 0) {
      setSelectedUnit(project.units[0])
    }

    autoSelectedTaskRef.current = taskId
  }, [projectQuery.data, taskId])

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

  // Triage flow helper: after approving / flagging the current unit, jump to
  // the next *open* issue so power users can rip through a batch with A/A/A
  // or F/F/F instead of arrow-down clicks. We compute the next issue at call
  // time (rather than caching) so the list reflects the freshly-mutated
  // status.
  const advanceToNextOpenIssue = useCallback(
    (afterIssueId: string | null) => {
      const issues = projectQuery.data?.issues ?? []
      const open = issues.filter(i => i.status === 'open')
      if (open.length === 0) {
        setSelectedIssueId(null)
        setSelectedUnit(null)
        return
      }
      const idx = afterIssueId ? open.findIndex(i => i.issue_id === afterIssueId) : -1
      // If the just-resolved issue is still in the list (server hasn't yet
      // re-fetched), step past it; otherwise idx is -1 and (idx+1) % len = 0
      // selects the first remaining open issue.
      const next = open[(idx + 1) % open.length]
      setSelectedIssueId(next.issue_id)
      const unit = projectQuery.data?.units.find(u => u.unit_id === next.unit_id)
      if (unit) setSelectedUnit(unit)
    },
    [projectQuery.data],
  )

  const handleSaveText = useCallback(
    async (unitId: string, targetText: string) => {
      await operationsMutation.mutateAsync([
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
    async (unitId: string, targetText?: string, options?: { speed?: number }) => {
      if (!taskId) return
      // Hard de-dup: a synth is already running, drop this click silently.
      // We don't queue because if the user is impatient the right thing is
      // to wait for the latest *intentional* request; queueing would
      // multiply backend load and could play stale audio.
      if (synthInFlightRef.current) return
      synthInFlightRef.current = true
      setIsSynthesizing(true)
      // Optimistically clear any previous error for this unit; on failure
      // we'll repopulate with the new message.
      setSynthErrorByUnit(prev => {
        if (!(unitId in prev)) return prev
        const next = { ...prev }
        delete next[unitId]
        return next
      })
      try {
        const result = await dubbingEditorApi.synthesizeUnit(taskId, unitId, targetText, options)
        // Always bump the token so the audio element re-mounts even if the
        // backend doesn't yet supply a synthesized_at timestamp.
        const token = result.synthesized_at ?? new Date().toISOString()
        setSynthesizedAtByUnit(prev => ({ ...prev, [unitId]: token }))
        queryClient.invalidateQueries({ queryKey: ['dubbing-editor', taskId] })
      } catch (err) {
        // Fall back to a generic message if the API client doesn't expose
        // structured error info; the banner is mostly there to confirm the
        // synth *didn't* succeed (so the user doesn't think their click
        // was lost).
        type AxiosLike = { response?: { data?: { detail?: string; message?: string } }; message?: string }
        const e = err as AxiosLike
        const detail = e.response?.data?.detail ?? e.response?.data?.message ?? e.message ?? 'unknown error'
        setSynthErrorByUnit(prev => ({ ...prev, [unitId]: detail }))
      } finally {
        synthInFlightRef.current = false
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
        const video = editorMode === 'edit' ? editVideoRef.current : null
        if (video) {
          if (video.paused) video.play().catch(() => {})
          else video.pause()
          return
        }
        const audio = clipAudioRef.current
        if (audio) {
          if (audio.paused) audio.play().catch(() => {})
          else audio.pause()
        }
      } else if (e.key === 'a' || e.key === 'A') {
        // Approve current unit and auto-advance to the next open issue.
        // Power-user triage: A / A / A / A churns through a queue.
        if (selectedUnit) {
          const currentIssue = selectedIssueId
          handleApprove(selectedUnit.unit_id)
          advanceToNextOpenIssue(currentIssue)
        }
      } else if (e.key === 'f' || e.key === 'F') {
        // Flag for review and advance — symmetric to A but for the
        // "needs human ear" bucket.
        if (selectedUnit) {
          const currentIssue = selectedIssueId
          handleNeedsReview(selectedUnit.unit_id)
          advanceToNextOpenIssue(currentIssue)
        }
      } else if (e.key === 'y' || e.key === 'Y') {
        // Resynthesize current unit at whatever speed is currently selected
        // in the inspector. We don't own that state up here; the inspector
        // listens for a custom event so the keystroke can hand off to it.
        if (selectedUnit) {
          window.dispatchEvent(
            new CustomEvent('dubbingEditor:resynthesizeCurrent', {
              detail: { unitId: selectedUnit.unit_id },
            }),
          )
        }
      } else if (e.key === '[') {
        e.preventDefault()
        const current = readPlaybackRate()
        const idx = PLAYBACK_RATE_LEVELS.indexOf(current)
        const next = PLAYBACK_RATE_LEVELS[Math.max(0, idx - 1)]
        writePlaybackRate(next)
        window.dispatchEvent(new CustomEvent<PlaybackRate>(PLAYBACK_RATE_EVENT, { detail: next }))
      } else if (e.key === ']') {
        e.preventDefault()
        const current = readPlaybackRate()
        const idx = PLAYBACK_RATE_LEVELS.indexOf(current)
        const next = PLAYBACK_RATE_LEVELS[Math.min(PLAYBACK_RATE_LEVELS.length - 1, idx + 1)]
        writePlaybackRate(next)
        window.dispatchEvent(new CustomEvent<PlaybackRate>(PLAYBACK_RATE_EVENT, { detail: next }))
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
    advanceToNextOpenIssue,
    editorMode,
  ])

  if (!taskId) return null

  if (projectQuery.isLoading && !projectQuery.data) {
    return (
      <div className="flex h-full items-center justify-center bg-[#F5F7FB]">
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          {t.dubbingEditor.loading}
        </div>
      </div>
    )
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <div className="flex h-full items-center justify-center bg-[#F5F7FB]">
        <div className="text-center">
          <div className="text-sm text-slate-500">{t.dubbingEditor.loadFailed}</div>
          <button
            type="button"
            onClick={handleRefresh}
            className="mt-3 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            {t.dubbingEditor.reload}
          </button>
        </div>
      </div>
    )
  }

  const project = projectQuery.data

  return (
    <div data-testid="dubbing-editor" className="flex h-full flex-col overflow-hidden bg-[#F5F7FB]">
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
        layoutPreset={activeLayoutPreset}
        onLayoutPresetChange={handleLayoutPresetChange}
      />

      {/* Undo mode indicator */}
      {opCursor !== null && (
        <div className="shrink-0 bg-amber-50 px-4 py-1 text-[10px] font-medium text-amber-700 border-b border-amber-200">
          {t.dubbingEditor.undoModeBanner(opCursor, effectiveTotalOps)}
        </div>
      )}

      {editorMode === 'edit' ? (
        /* ── Edit Mode: 3-column layout (collapsible left rail · timeline-first center · inspector) ── */
        <div className="flex min-h-0 flex-1 overflow-hidden bg-white" data-testid="dubbing-editor-workbench">
          {/* Left: Issue Queue (collapsible) */}
          {workbenchLayout.leftOpen ? (
            <>
            <div
              className="flex shrink-0 flex-col overflow-hidden border-r border-slate-200 bg-white"
              data-testid="issue-queue-panel"
              style={{ width: `${workbenchLayout.leftWidth}px` }}
            >
              <div className="flex h-9 shrink-0 items-center justify-between border-b border-slate-100 pl-3 pr-1">
                <div className="flex items-center gap-1.5">
                  <AlertTriangle size={12} className="text-slate-400" />
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    {t.dubbingEditor.issueQueue.title}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIssueQueueOpen(false)}
                  data-testid="toggle-issue-queue-panel"
                  className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
                  title={t.dubbingEditor.panels.collapseIssueQueue}
                  aria-label={t.dubbingEditor.panels.collapseIssueQueue}
                >
                  <PanelLeftClose size={13} />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-hidden">
                <IssueQueue
                  project={project}
                  selectedIssueId={selectedIssueId}
                  onSelectIssue={handleSelectIssue}
                  onBulkApprove={handleBulkApprove}
                />
              </div>
            </div>
            <PanelResizeHandle
              side="left"
              label={t.dubbingEditor.panels.resizeIssueQueue}
              value={workbenchLayout.leftWidth}
              min={LEFT_PANEL_MIN}
              max={LEFT_PANEL_MAX}
              onMouseDown={event => beginPanelResize('left', event)}
              onKeyboardResize={handleKeyboardResize}
            />
            </>
          ) : (
            <IssueQueueRail project={project} onExpand={() => setIssueQueueOpen(true)} />
          )}

          {/* Center: Current line strip + Timeline */}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-[#FAFBFD]">
            {/* Video monitor — primary editing context */}
            <div className="h-[min(42vh,420px)] min-h-[280px] shrink-0 overflow-hidden border-b border-slate-200 bg-slate-950">
              <EditMonitorPane
                project={project}
                taskId={taskId}
                selectedUnit={selectedUnit}
                playheadSec={playheadSec}
                onPlayheadChange={setPlayheadSec}
                renderRangeResult={renderRangeResult}
                clipAudioRef={clipAudioRef}
                videoRef={editVideoRef}
              />
            </div>

            {/* Timeline — fills remaining */}
            <div className="min-h-0 flex-1 overflow-hidden bg-white">
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
          {workbenchLayout.rightOpen ? (
            <>
            <PanelResizeHandle
              side="right"
              label={t.dubbingEditor.panels.resizeInspector}
              value={workbenchLayout.rightWidth}
              min={RIGHT_PANEL_MIN}
              max={RIGHT_PANEL_MAX}
              onMouseDown={event => beginPanelResize('right', event)}
              onKeyboardResize={handleKeyboardResize}
            />
            <div
              className="flex shrink-0 flex-col overflow-hidden border-l border-slate-200 bg-white"
              data-testid="inspector-panel-shell"
              style={{ width: `${workbenchLayout.rightWidth}px` }}
            >
              <InspectorPanel
                project={project}
                taskId={taskId}
                selectedUnit={selectedUnit}
                onTogglePanel={() => setInspectorOpen(false)}
                onApprove={handleApprove}
                onNeedsReview={handleNeedsReview}
                onSaveText={handleSaveText}
                onResynthesize={handleResynthesize}
                onAssignVoice={handleAssignVoice}
                isSynthesizing={isSynthesizing}
                synthesizedAt={
                  selectedUnit ? synthesizedAtByUnit[selectedUnit.unit_id] ?? null : null
                }
                synthError={
                  selectedUnit ? synthErrorByUnit[selectedUnit.unit_id] ?? null : null
                }
              />
            </div>
            </>
          ) : (
            <InspectorRail selectedUnit={selectedUnit} onExpand={() => setInspectorOpen(true)} />
          )}
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
