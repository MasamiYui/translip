import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Gauge, Info, Play, RefreshCw, Sparkles, Trash2, X } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import {
  ISSUE_TAGS,
  evaluationApi,
  taskArtifactUrl,
  taskInputFileUrl,
  type Analysis,
  type DubQaGate,
  type DubQaReport,
  type DubQaSegment,
  type IssueTag,
  type SegmentDirective,
  type SegmentSeverity,
} from '../api/evaluation'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { RemediationPanel } from '../components/evaluation/RemediationPanel'
import { SegmentTimingBar } from '../components/evaluation/SegmentTimingBar'
import { WaveformCompare } from '../components/evaluation/WaveformCompare'
import { useI18n } from '../i18n/useI18n'
import { cn } from '../lib/utils'

const SEVERITY_STYLE: Record<SegmentSeverity, string> = {
  P0: 'bg-red-100 text-red-700',
  P1: 'bg-amber-100 text-amber-700',
  P2: 'bg-blue-100 text-blue-700',
  ok: 'bg-emerald-50 text-emerald-600',
}

type Filter = 'all' | 'problems' | IssueTag

function formatTime(sec: number | null | undefined): string {
  if (typeof sec !== 'number') return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${s.toFixed(1).padStart(4, '0')}`
}

function normalizeToken(token: string): string {
  return token.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
}

export function EvaluationDetailPage() {
  const { taskId = '' } = useParams<{ taskId: string }>()
  const { t } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [withJudge, setWithJudge] = useState(false)
  const [filter, setFilter] = useState<Filter>('problems')
  const [selected, setSelected] = useState<DubQaSegment | null>(null)
  // An explicit segment-id focus (set from the remediation panel "locate" links)
  // overrides the chip filter until cleared.
  const [focus, setFocus] = useState<{ ids: string[]; label: string } | null>(null)

  const taskQuery = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => tasksApi.get(taskId),
    enabled: !!taskId,
  })

  const analysesQuery = useQuery({
    queryKey: ['analyses', taskId],
    queryFn: () => evaluationApi.list(taskId),
    enabled: !!taskId,
    refetchInterval: query => {
      const rows = (query.state.data as Analysis[] | undefined) ?? []
      return rows.some(r => r.status === 'pending' || r.status === 'running') ? 2000 : false
    },
  })

  // The report view tracks the latest dub-qa; auto-fix rows live in the same
  // table but must not hijack the report (they have no dub-qa report shape).
  const latest = analysesQuery.data?.find(a => a.analysis_type === 'dub-qa')

  const reportQuery = useQuery({
    queryKey: ['analysis-report', taskId, latest?.id],
    queryFn: () => evaluationApi.getReport(taskId, latest!.id),
    enabled: !!latest && latest.status === 'succeeded',
  })

  const createMutation = useMutation({
    mutationFn: () => evaluationApi.create(taskId, { run_translation_judge: withJudge }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['analyses', taskId] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (analysisId: string) => evaluationApi.remove(taskId, analysisId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['analyses', taskId] })
      setSelected(null)
    },
  })

  const report: DubQaReport | undefined = reportQuery.data
  const running = !!latest && (latest.status === 'pending' || latest.status === 'running')

  const filteredSegments = useMemo(() => {
    const segments = report?.segments ?? []
    if (focus) {
      const ids = new Set(focus.ids)
      return segments.filter(s => ids.has(s.segment_id))
    }
    if (filter === 'all') return segments
    if (filter === 'problems') return segments.filter(s => s.issue_tags.length > 0)
    return segments.filter(s => s.issue_tags.includes(filter))
  }, [report, filter, focus])

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} px-6 py-6`}>
      {/* Header */}
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate('/evaluation')}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#6b7280] hover:bg-[#f3f4f6]"
            aria-label={t.evaluation.backToList}
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#3b5bdb]/10 text-[#3b5bdb]">
            <Gauge size={18} />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[#111827]">
              {taskQuery.data?.name ?? taskId}
            </h1>
            <p className="text-xs text-[#9ca3af]">{t.evaluation.subtitle}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-[#6b7280]" title={t.evaluation.judgeHint}>
            <input
              type="checkbox"
              checked={withJudge}
              onChange={e => setWithJudge(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-[#d1d5db]"
            />
            {t.evaluation.withJudge}
          </label>
          <button
            type="button"
            disabled={createMutation.isPending || running}
            onClick={() => createMutation.mutate()}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              createMutation.isPending || running
                ? 'cursor-not-allowed bg-[#e5e7eb] text-[#9ca3af]'
                : 'bg-[#3b5bdb] text-white hover:bg-[#324bc0]',
            )}
          >
            <RefreshCw size={14} className={running ? 'animate-spin' : undefined} />
            {report ? t.evaluation.rerun : t.evaluation.runAnalysis}
          </button>
        </div>
      </div>

      {/* Status line */}
      {running && (
        <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50 px-4 py-2.5 text-sm text-[#3b5bdb]">
          {t.evaluation.running}
        </div>
      )}
      {latest?.status === 'failed' && (
        <div className="mb-4 rounded-lg border border-red-100 bg-red-50 px-4 py-2.5 text-sm text-red-600">
          {t.evaluation.failedHint}: {latest.error_message}
        </div>
      )}

      {!latest && !running && (
        <div className="rounded-xl border border-dashed border-[#e5e7eb] bg-white p-10 text-center text-sm text-[#9ca3af]">
          {t.evaluation.noReport}
        </div>
      )}

      {report && (
        <>
          <Scorecard report={report} latest={latest} onDelete={id => deleteMutation.mutate(id)} />

          {/* Next optimizations: prioritized fixes + export for the AI loop */}
          <div className="mt-5">
            <RemediationPanel
              taskId={taskId}
              report={report}
              onFocusSegments={(ids, label) => {
                setFocus({ ids, label })
                document.getElementById('eval-segment-table')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}
              onApplied={() => {
                setFocus(null)
                queryClient.invalidateQueries({ queryKey: ['analyses', taskId] })
              }}
            />
          </div>

          {/* Original-vs-dub waveform comparison */}
          <div className="mt-5">
            <WaveformCompare
              taskId={taskId}
              report={report}
              segments={report.segments}
              selectedId={selected?.segment_id ?? null}
              onSelectSegment={setSelected}
            />
          </div>

          {/* Issue filter chips */}
          <div id="eval-segment-table" className="mb-3 mt-5 flex flex-wrap items-center gap-2">
            <FilterChip active={!focus && filter === 'problems'} onClick={() => { setFocus(null); setFilter('problems') }}>
              {t.evaluation.problemsOnly} ({report.qa_summary.problem_segment_count})
            </FilterChip>
            <FilterChip active={!focus && filter === 'all'} onClick={() => { setFocus(null); setFilter('all') }}>
              {t.evaluation.filterAll} ({report.qa_summary.segment_count})
            </FilterChip>
            <span className="mx-1 h-4 w-px bg-[#e5e7eb]" />
            {ISSUE_TAGS.map(tag => {
              const count = report.qa_summary.issue_counts[tag] ?? 0
              return (
                <FilterChip
                  key={tag}
                  active={!focus && filter === tag}
                  disabled={count === 0}
                  onClick={() => { setFocus(null); setFilter(tag) }}
                >
                  {t.evaluation.issues[tag]} ({count})
                </FilterChip>
              )
            })}
          </div>

          {/* Focus banner: explicit segment-id selection from the remediation panel */}
          {focus && (
            <div className="mb-3 flex items-center justify-between rounded-lg border border-[#3b5bdb]/20 bg-[#3b5bdb]/5 px-3 py-2 text-xs text-[#3b5bdb]">
              <span>
                {focus.label} · {focus.ids.length}
              </span>
              <button
                type="button"
                onClick={() => setFocus(null)}
                aria-label="clear focus"
                className="flex items-center justify-center rounded-md p-1 font-medium hover:bg-[#3b5bdb]/10"
              >
                <X size={12} />
              </button>
            </div>
          )}

          {/* Segment table */}
          <div className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#f3f4f6] text-left text-xs text-[#9ca3af]">
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.colTime}</th>
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.colSeverity}</th>
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.colSpeaker}</th>
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.colSource}</th>
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.colTarget}</th>
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.timing.col}</th>
                  <th className="px-3 py-2.5 font-medium">{t.evaluation.colIssues}</th>
                </tr>
              </thead>
              <tbody>
                {filteredSegments.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-[#9ca3af]">
                      {t.evaluation.emptyRows}
                    </td>
                  </tr>
                ) : (
                  filteredSegments.map(seg => (
                    <tr
                      key={seg.segment_id}
                      onClick={() => setSelected(seg)}
                      className="cursor-pointer border-b border-[#f9fafb] align-top transition-colors hover:bg-[#f9fafb]"
                    >
                      <td className="whitespace-nowrap px-3 py-2.5 text-xs text-[#6b7280]">
                        {formatTime(seg.start)}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className={cn('rounded px-1.5 py-0.5 text-[11px] font-semibold', SEVERITY_STYLE[seg.severity])}>
                          {seg.severity}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-xs text-[#6b7280]">
                        {seg.speaker_id ?? '—'}
                      </td>
                      <td className="max-w-[18rem] px-3 py-2.5 text-[#374151]">
                        <div className="line-clamp-2">{seg.source_text || '—'}</div>
                      </td>
                      <td className="max-w-[18rem] px-3 py-2.5 text-[#374151]">
                        <div className="line-clamp-2">{seg.target_text || '—'}</div>
                      </td>
                      <td className="px-3 py-2.5">
                        <SegmentTimingBar segment={seg} variant="compact" />
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex flex-wrap gap-1">
                          {seg.issue_tags.map(tag => (
                            <IssueBadge key={tag} tag={tag} label={t.evaluation.issues[tag]} />
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {selected && (
        <SegmentDrawer
          taskId={taskId}
          segment={selected}
          directive={report?.remediation?.segment_directives?.[selected.segment_id] ?? null}
          onClose={() => setSelected(null)}
        />
      )}
    </PageContainer>
  )
}

function Scorecard({
  report,
  latest,
  onDelete,
}: {
  report: DubQaReport
  latest?: Analysis
  onDelete: (analysisId: string) => void
}) {
  const { t } = useI18n()
  const summary = report.qa_summary
  const score = report.scorecard.score
  const judgeStatus = summary.judge_status as keyof typeof t.evaluation.judgeStatusMap
  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
      {/* Meta row: verdict on the left, timestamp + actions on the right */}
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#9ca3af]">{t.evaluation.status}</span>
          <VerdictBadge verdict={report.scorecard.status} />
        </div>
        {latest && (
          <div className="flex items-center gap-2 text-xs text-[#9ca3af]">
            <span>
              {t.evaluation.createdAt} {new Date(latest.created_at).toLocaleString()}
            </span>
            <button
              type="button"
              onClick={() => onDelete(latest.id)}
              className="flex items-center justify-center rounded-md p-1.5 text-[#9ca3af] hover:bg-red-50 hover:text-red-500"
              title={t.evaluation.deleteAnalysis}
            >
              <Trash2 size={14} />
            </button>
          </div>
        )}
      </div>

      {/* Metric strip: evenly distributed cards, content centered in each */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCell label={t.evaluation.score}>
          <span className="text-3xl font-bold text-[#111827]">{score}</span>
        </MetricCell>
        <MetricCell label={t.evaluation.dubCoverage}>
          <span className={summary.coverage.undubbed_count > 0 ? 'text-red-600' : 'text-[#111827]'}>
            {summary.coverage.dubbed_count}/{summary.coverage.translated_count}
            {summary.coverage.coverage_ratio != null
              ? ` (${Math.round(summary.coverage.coverage_ratio * 100)}%)`
              : ''}
          </span>
        </MetricCell>
        <MetricCell label={t.evaluation.problems}>
          <span className={summary.problem_segment_count > 0 ? 'text-amber-600' : 'text-[#111827]'}>
            {summary.problem_segment_count}
          </span>
        </MetricCell>
        <MetricCell label={t.evaluation.judgeStatusLabel}>
          <span className="text-[#111827]">
            {t.evaluation.judgeStatusMap[judgeStatus] ?? judgeStatus}
          </span>
        </MetricCell>
      </div>

      {/* Gates */}
      {report.scorecard.gates.length > 0 && (
        <div className="mt-4 border-t border-[#f3f4f6] pt-4">
          <div className="mb-2 text-xs font-medium text-[#9ca3af]">{t.evaluation.gatesTitle}</div>
          <div className="flex flex-wrap gap-2">
            {report.scorecard.gates.map(gate => (
              <GateChip key={gate.id} gate={gate} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function MetricCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-h-[5.5rem] flex-col items-center justify-center gap-1 rounded-xl bg-[#f9fafb] px-3 py-4 text-center transition-colors hover:bg-[#f3f4f6]">
      <div className="text-xl font-bold leading-tight text-[#111827]">{children}</div>
      <div className="text-xs font-medium text-[#9ca3af]">{label}</div>
    </div>
  )
}

function FilterChip({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'rounded-full px-3 py-1 text-xs font-medium transition-colors',
        disabled && 'cursor-not-allowed opacity-40',
        active
          ? 'bg-[#3b5bdb] text-white'
          : 'bg-[#f3f4f6] text-[#6b7280] hover:bg-[#e5e7eb]',
      )}
    >
      {children}
    </button>
  )
}

/** Renders the dub-QA verdict (blocked / review_required / deliverable_candidate) — NOT a pipeline task status. */
function VerdictBadge({ verdict }: { verdict: string }) {
  const { t } = useI18n()
  const key = verdict as keyof typeof t.evaluation.verdictMap
  const style =
    verdict === 'deliverable_candidate'
      ? { badge: 'bg-emerald-50 text-emerald-700', dot: 'bg-emerald-500' }
      : verdict === 'blocked'
        ? { badge: 'bg-red-50 text-red-600', dot: 'bg-red-500' }
        : { badge: 'bg-amber-50 text-amber-700', dot: 'bg-amber-500' }
  const label = t.evaluation.verdictMap[key] ?? verdict
  const tip = t.evaluation.verdictTipMap[key]
  return (
    <span className="group/verdict relative inline-flex">
      <span
        tabIndex={tip ? 0 : undefined}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium outline-none',
          style.badge,
        )}
      >
        <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', style.dot)} />
        {label}
        {tip && <Info size={12} className="opacity-60" />}
      </span>
      {tip && (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-0 top-full z-30 mt-1.5 hidden w-72 rounded-lg bg-slate-900 px-3 py-2 text-[11px] leading-relaxed text-slate-100 shadow-lg group-hover/verdict:block group-focus-within/verdict:block"
        >
          {tip}
        </span>
      )}
    </span>
  )
}

/** A single delivery-gate chip — localized by stable gate id, with a status + threshold tooltip. */
function GateChip({ gate }: { gate: DubQaGate }) {
  const { t } = useI18n()
  const id = gate.id as keyof typeof t.evaluation.gateInfo.labels
  const label = t.evaluation.gateInfo.labels[id] ?? gate.label
  const statusLabel =
    t.evaluation.gateInfo.statusMap[gate.status as keyof typeof t.evaluation.gateInfo.statusMap] ??
    gate.status
  const desc = t.evaluation.gateInfo.desc[id] ?? gate.threshold
  const style =
    gate.status === 'passed'
      ? 'bg-emerald-50 text-emerald-600'
      : gate.status === 'failed'
        ? 'bg-red-50 text-red-600'
        : 'bg-amber-50 text-amber-700'
  return (
    <span className="group/gate relative inline-flex">
      <span
        tabIndex={0}
        className={cn('rounded-full px-2.5 py-1 text-[11px] font-medium outline-none', style)}
      >
        {label}
      </span>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-30 mt-1.5 hidden w-64 rounded-lg bg-slate-900 px-3 py-2 text-[11px] leading-relaxed text-slate-100 shadow-lg group-hover/gate:block group-focus-within/gate:block"
      >
        <span className="font-semibold">{statusLabel}</span> · {desc}
      </span>
    </span>
  )
}

function IssueBadge({ tag, label }: { tag: IssueTag; label: string }) {
  const isP0 = tag === 'undubbed'
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-[10px] font-medium',
        isP0 ? 'bg-red-100 text-red-700' : 'bg-amber-50 text-amber-700',
      )}
    >
      {label}
    </span>
  )
}

function SegmentDrawer({
  taskId,
  segment,
  directive,
  onClose,
}: {
  taskId: string
  segment: DubQaSegment
  directive: SegmentDirective | null
  onClose: () => void
}) {
  const { t } = useI18n()
  const navigate = useNavigate()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="close"
        className="absolute inset-0 bg-black/20"
        onClick={onClose}
      />
      <div className="relative z-10 flex h-full w-full max-w-md flex-col overflow-y-auto bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-[#f3f4f6] px-5 py-4">
          <div>
            <div className="text-sm font-semibold text-[#111827]">{t.evaluation.drawerTitle}</div>
            <div className="text-xs text-[#9ca3af]">
              {formatTime(segment.start)} – {formatTime(segment.end)} · {segment.speaker_id ?? '—'}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#6b7280] hover:bg-[#f3f4f6]"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-5 px-5 py-4">
          {/* Issue tags */}
          {segment.issue_tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {segment.issue_tags.map(tag => (
                <IssueBadge key={tag} tag={tag} label={t.evaluation.issues[tag]} />
              ))}
            </div>
          )}

          {/* Diagnosis & recommended fix */}
          {directive && (
            <DiagnosisCard taskId={taskId} segment={segment} directive={directive} onNavigate={navigate} />
          )}

          {/* A/B audio */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-[#e5e7eb] p-3">
              <div className="mb-2 text-xs font-medium text-[#6b7280]">{t.evaluation.original}</div>
              <OriginalSegmentPlayer
                src={taskInputFileUrl(taskId)}
                start={segment.start ?? 0}
                end={segment.end ?? 0}
                playLabel={t.evaluation.playSegment}
              />
            </div>
            <div className="rounded-lg border border-[#e5e7eb] p-3">
              <div className="mb-2 text-xs font-medium text-[#6b7280]">{t.evaluation.dubbed}</div>
              {segment.dub_audio_path ? (
                <audio controls className="w-full" src={taskArtifactUrl(taskId, segment.dub_audio_path)} />
              ) : (
                <div className="text-xs text-[#9ca3af]">{t.evaluation.noAudio}</div>
              )}
            </div>
          </div>

          {/* Timing: original window vs dub footprint */}
          <Field label={t.evaluation.timing.col}>
            <SegmentTimingBar segment={segment} variant="full" />
          </Field>

          {/* Texts */}
          <Field label={t.evaluation.sourceText}>
            <p className="text-sm text-[#374151]">{segment.source_text || '—'}</p>
          </Field>
          <Field label={t.evaluation.targetText}>
            <DropoutText target={segment.target_text} backread={segment.backread_text} />
            {segment.dropout_total_tokens > 0 && segment.dropout_ratio >= 0.34 && (
              <p className="mt-1 text-[11px] text-red-500">{t.evaluation.dropoutHint}</p>
            )}
          </Field>
          {segment.backread_text && (
            <Field label={t.evaluation.backread}>
              <p className="text-sm text-[#9ca3af]">{segment.backread_text}</p>
            </Field>
          )}

          {/* Judge */}
          {typeof segment.judge_score === 'number' && (
            <Field label={`${t.evaluation.judgeReason} · ${t.evaluation.judgeScore} ${segment.judge_score}`}>
              <p className="text-sm text-[#374151]">{segment.judge_reason || '—'}</p>
            </Field>
          )}

          {/* Metrics */}
          <Field label={t.evaluation.metrics}>
            <dl className="grid grid-cols-2 gap-y-1.5 text-xs">
              <Metric label={t.evaluation.speakerSim} value={segment.speaker_similarity} status={segment.speaker_status} />
              <Metric label={t.evaluation.textSim} value={segment.text_similarity} status={segment.intelligibility_status} />
              <Metric label={t.evaluation.durationRatio} value={segment.duration_ratio} status={segment.duration_status} />
              <Metric label={t.evaluation.coverage} value={segment.subtitle_coverage_ratio} />
            </dl>
          </Field>
        </div>
      </div>
    </div>
  )
}

/** Root-cause + recommended-fix card shown at the top of the segment drawer. */
function DiagnosisCard({
  taskId,
  segment,
  directive,
  onNavigate,
}: {
  taskId: string
  segment: DubQaSegment
  directive: SegmentDirective
  onNavigate: (path: string) => void
}) {
  const { t } = useI18n()
  const tr = t.evaluation.remediation
  const ev = directive.evidence
  const causeText = (defect: IssueTag): string => {
    switch (defect) {
      case 'undubbed':
        return tr.cause.undubbed()
      case 'pacing':
        return tr.cause.pacing(ev.duration_ratio ?? 1)
      case 'dropout':
        return tr.cause.dropout(ev.dropout_ratio ?? 0)
      case 'low_intelligibility':
        return tr.cause.low_intelligibility(ev.text_similarity ?? 0)
      case 'timbre_mismatch':
        return tr.cause.timbre_mismatch(ev.speaker_similarity ?? 0)
      case 'bad_translation':
        return tr.cause.bad_translation(ev.judge_score ?? 0)
      case 'inaudible':
        return tr.cause.inaudible(ev.subtitle_coverage_ratio ?? 0)
      default:
        return ''
    }
  }
  return (
    <div className="rounded-lg border border-[#3b5bdb]/20 bg-[#3b5bdb]/[0.03] p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-[#3b5bdb]">
        <Sparkles size={13} /> {tr.drawerTitle}
      </div>
      <ul className="mb-2.5 space-y-1">
        {segment.issue_tags.map(tag => (
          <li key={tag} className="flex gap-1.5 text-xs text-[#4b5563]">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#9ca3af]" />
            <span>{causeText(tag)}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center justify-between gap-2 rounded-md bg-white px-2.5 py-2 ring-1 ring-[#e5e7eb]">
        <div className="min-w-0">
          <div className="text-[11px] text-[#9ca3af]">{tr.recommend}</div>
          <div className="text-sm font-medium text-[#111827]">{tr.actionLabel[directive.primary_action]}</div>
          <div className="text-[11px] text-[#9ca3af]">{tr.actionHint[directive.primary_action]}</div>
        </div>
        <button
          type="button"
          onClick={() => onNavigate(`/tasks/${encodeURIComponent(taskId)}/dubbing-editor`)}
          className="flex shrink-0 items-center gap-1 rounded-md bg-[#3b5bdb] px-2.5 py-1.5 text-xs font-medium text-white hover:bg-[#324bc0]"
        >
          {tr.goEditor} <ExternalLink size={12} />
        </button>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-[#9ca3af]">{label}</div>
      {children}
    </div>
  )
}

function Metric({
  label,
  value,
  status,
}: {
  label: string
  value: number | null | undefined
  status?: string | null
}) {
  const color =
    status === 'failed' ? 'text-red-600' : status === 'review' ? 'text-amber-600' : 'text-[#374151]'
  return (
    <>
      <dt className="text-[#9ca3af]">{label}</dt>
      <dd className={cn('text-right font-medium', color)}>
        {typeof value === 'number' ? value.toFixed(2) : '—'}
      </dd>
    </>
  )
}

/** Highlights target words that don't appear in the read-back (likely dropped by TTS). */
function DropoutText({ target, backread }: { target: string; backread: string }) {
  const backreadSet = useMemo(() => {
    return new Set(backread.toLowerCase().split(/\s+/).map(normalizeToken).filter(Boolean))
  }, [backread])
  const words = target.split(/(\s+)/)
  if (!backread) {
    return <p className="text-sm text-[#374151]">{target || '—'}</p>
  }
  return (
    <p className="text-sm text-[#374151]">
      {words.map((word, idx) => {
        const norm = normalizeToken(word)
        const dropped = norm.length > 0 && !backreadSet.has(norm)
        return (
          <span key={idx} className={dropped ? 'rounded bg-red-100 text-red-700' : undefined}>
            {word}
          </span>
        )
      })}
    </p>
  )
}

function OriginalSegmentPlayer({
  src,
  start,
  end,
  playLabel,
}: {
  src: string
  start: number
  end: number
  playLabel: string
}) {
  const ref = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onTimeUpdate = () => {
      if (end > start && el.currentTime >= end) {
        el.pause()
      }
    }
    el.addEventListener('timeupdate', onTimeUpdate)
    return () => el.removeEventListener('timeupdate', onTimeUpdate)
  }, [start, end])

  const playSegment = () => {
    const el = ref.current
    if (!el) return
    el.currentTime = start
    void el.play()
  }

  return (
    <div className="space-y-2">
      <video ref={ref} src={src} controls className="w-full rounded bg-black" preload="metadata" />
      <button
        type="button"
        onClick={playSegment}
        className="flex w-full items-center justify-center gap-1.5 rounded-md bg-[#f3f4f6] px-2 py-1.5 text-xs font-medium text-[#374151] hover:bg-[#e5e7eb]"
      >
        <Play size={12} /> {playLabel}
      </button>
    </div>
  )
}
