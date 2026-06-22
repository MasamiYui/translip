import { useMemo, useState, useSyncExternalStore } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Database,
  ExternalLink,
  FlaskConical,
  Loader2,
  Minus,
  PlayCircle,
  Sparkles,
  Trophy,
} from 'lucide-react'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../../components/layout/PageContainer'
import { StatusBadge } from '../../components/shared/StatusBadge'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'
import {
  labApi,
  type LabCompareResult,
  type LabDataset,
  type LabRunSummary,
  type LabSource,
} from '../../api/lab'

type TabKey = 'datasets' | 'experiments' | 'leaderboard' | 'regression'

const TABS: TabKey[] = ['datasets', 'experiments', 'leaderboard', 'regression']

const LOWER_IS_BETTER = new Set(['cer_micro', 'cer_macro', 'cer', 'der', 'jer', 'mcd', 'wer', 'rtf'])

const PRIMARY_BUTTON =
  'inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-50'

const SECONDARY_BUTTON =
  'inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50'

const CARD =
  'rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]'

const TABLE_WRAPPER =
  'overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]'

function mapStatusForBadge(status?: string): string {
  const key = (status ?? 'pending').toLowerCase()
  if (key === 'finished') return 'completed'
  if (key === 'queued') return 'pending'
  return key
}

function useLabSource(): LabSource {
  return useSyncExternalStore(labApi.subscribeSource, labApi.source, labApi.source)
}

function SourceBadge() {
  const { t } = useI18n()
  const source = useLabSource()
  if (source === 'live') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        {t.lab.sourceBadge.live}
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700"
      title={t.lab.sourceBadge.mockHint}
    >
      <Sparkles className="h-3 w-3" />
      {t.lab.sourceBadge.mock}
    </span>
  )
}

function LoadingState({ label }: { label: string }) {
  return <div className="py-16 text-center text-sm text-[#9ca3af]">{label}</div>
}

function ErrorState({ message, onRetry, retryLabel }: { message: string; onRetry?: () => void; retryLabel: string }) {
  return (
    <div className="py-16 text-center text-sm">
      <p className="text-rose-600">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className={cn(SECONDARY_BUTTON, 'mt-3')}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  )
}

function EmptyHint({ label }: { label: string }) {
  return <div className="py-16 text-center text-sm text-[#9ca3af]">{label}</div>
}

function ScenarioTag({ name }: { name: string }) {
  const { t } = useI18n()
  const map: Record<string, { label: string; cls: string }> = {
    asr: { label: t.lab.experiments.tagAsr, cls: 'bg-[#eef1fd] text-[#3b5bdb]' },
    diarization: { label: t.lab.experiments.tagDiar, cls: 'bg-violet-50 text-violet-700' },
    separation: { label: t.lab.experiments.tagSep, cls: 'bg-teal-50 text-teal-700' },
    ocr_detect: { label: t.lab.experiments.tagOcr, cls: 'bg-emerald-50 text-emerald-700' },
    subtitle_erase: { label: t.lab.experiments.tagErase, cls: 'bg-pink-50 text-pink-700' },
    e2e_dub: { label: t.lab.experiments.tagDub, cls: 'bg-amber-50 text-amber-700' },
  }
  const m = map[name] ?? { label: name, cls: 'bg-[#f3f4f6] text-[#6b7280]' }
  return (
    <span className={cn('inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold', m.cls)}>
      {m.label}
    </span>
  )
}

function StatCard({ icon: Icon, label, value, hint }: { icon: typeof Database; label: string; value: string; hint?: string }) {
  return (
    <div className={cn(CARD, 'p-4')}>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold text-[#111827]">{value}</div>
      {hint ? <div className="mt-1 text-xs text-[#9ca3af]">{hint}</div> : null}
    </div>
  )
}

function pickPrimaryMetric(run: LabRunSummary): { scenario: string; key: string; value: number } | null {
  const aggregates = run.aggregates ?? {}
  for (const [scenario, metrics] of Object.entries(aggregates)) {
    for (const k of ['cer_micro', 'cer', 'der', 'mcd', 'si_sdr', 'f1', 'psnr']) {
      const v = metrics[k]
      if (typeof v === 'number') return { scenario, key: k, value: v }
    }
  }
  return null
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function formatMetricValue(key: string, value: number): string {
  if (['cer_micro', 'cer_macro', 'cer', 'der', 'jer', 'wer'].includes(key)) return formatPercent(value)
  if (key === 'rtf') return value.toFixed(2)
  return value.toFixed(3)
}

function formatDuration(sec?: number): string {
  if (!sec) return '—'
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
}

function OverviewCards({ datasets, suites, runs }: { datasets: LabDataset[] | undefined; suites: string[] | undefined; runs: LabRunSummary[] | undefined }) {
  const { t } = useI18n()
  const dsCount = datasets?.length ?? 0
  const suitesCount = suites?.length ?? 0
  const runsCount = runs?.length ?? 0
  const bestCer = useMemo(() => {
    if (!runs) return '—'
    let best: number | null = null
    for (const r of runs) {
      const v = r.aggregates?.asr?.cer_micro
      if (typeof v === 'number' && (best === null || v < best)) best = v
    }
    return best === null ? '—' : formatPercent(best)
  }, [runs])

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard icon={Database} label={t.lab.overview.datasets} value={String(dsCount)} />
      <StatCard icon={FlaskConical} label={t.lab.overview.suites} value={String(suitesCount)} />
      <StatCard icon={PlayCircle} label={t.lab.overview.runs} value={String(runsCount)} />
      <StatCard icon={Trophy} label={t.lab.overview.bestPrimary} value={bestCer} hint="wenetspeech-drama / asr" />
    </div>
  )
}

function DatasetsTab() {
  const { t } = useI18n()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['lab', 'datasets'],
    queryFn: labApi.datasets,
    staleTime: 30_000,
    retry: false,
  })

  const datasets = (data ?? []) as LabDataset[]

  return (
    <div className="space-y-3">
      <p className="text-xs text-[#6b7280]">{t.lab.datasets.hint}</p>
      <div className={TABLE_WRAPPER}>
        {isLoading ? (
          <LoadingState label={t.lab.loading} />
        ) : isError ? (
          <ErrorState message={t.lab.notReachable} onRetry={() => refetch()} retryLabel={t.lab.retry} />
        ) : datasets.length === 0 ? (
          <EmptyHint label={t.lab.datasets.empty} />
        ) : (
          <table className="w-full min-w-[680px] text-sm">
            <thead className="border-b border-[#f3f4f6] text-left">
              <tr>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.datasets.columns.name}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.datasets.columns.license}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.datasets.columns.provides}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.datasets.columns.status}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.datasets.columns.samples}</th>
                <th className="hidden px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap md:table-cell">{t.lab.datasets.columns.layout}</th>
              </tr>
            </thead>
            <tbody>
              {datasets.map(ds => {
                const ready = Boolean(ds.subset_exists ?? ds.exists)
                const samples = typeof ds.samples === 'number' ? ds.samples : null
                const duration = typeof ds.total_duration_min === 'number' ? ds.total_duration_min : null
                return (
                  <tr key={ds.name} className="border-b border-[#f9fafb] last:border-0 transition-colors hover:bg-[#fafafa]">
                    <td className="px-4 py-3.5">
                      <div className="font-medium text-[#111827]">{ds.name}</div>
                      {ds.subset ? <div className="text-xs text-[#9ca3af]">subset: {String(ds.subset)}</div> : null}
                    </td>
                    <td className="px-4 py-3.5 text-[#4b5563]">{ds.license ?? '—'}</td>
                    <td className="px-4 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {(ds.provides ?? []).map(p => (
                          <span key={p} className="rounded bg-[#f3f4f6] px-1.5 py-0.5 text-xs text-[#4b5563]">{p}</span>
                        ))}
                        {(ds.provides ?? []).length === 0 ? '—' : null}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      {ready ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                          <CheckCircle2 className="h-3 w-3" />
                          {t.lab.datasets.ready}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[#f3f4f6] px-2 py-0.5 text-xs font-medium text-[#6b7280]">
                          {t.lab.datasets.missing}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-xs text-[#4b5563]">
                      {samples !== null ? (
                        <div>
                          <div className="font-medium text-[#111827]">{samples}</div>
                          {duration !== null ? <div className="text-[#9ca3af]">{duration.toFixed(1)} {t.lab.overview.minutes}</div> : null}
                        </div>
                      ) : '—'}
                    </td>
                    <td className="hidden px-4 py-3.5 font-mono text-xs text-[#9ca3af] md:table-cell">
                      {ds.expected_layout ?? ds.subset_root ?? ds.root ?? '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function ExperimentsTab() {
  const { t } = useI18n()
  const suitesQuery = useQuery({
    queryKey: ['lab', 'suites'],
    queryFn: labApi.suites,
    staleTime: 60_000,
    retry: false,
  })
  const triggerMutation = useMutation({
    mutationFn: (suite: string) => labApi.triggerRun({ suite, limit: 3 }),
  })

  if (suitesQuery.isLoading) return <div className={cn(TABLE_WRAPPER)}><LoadingState label={t.lab.loading} /></div>
  if (suitesQuery.isError)
    return <div className={cn(TABLE_WRAPPER)}><ErrorState message={t.lab.notReachable} onRetry={() => suitesQuery.refetch()} retryLabel={t.lab.retry} /></div>

  const suites = suitesQuery.data ?? []
  if (!suites.length) {
    return <div className={cn(TABLE_WRAPPER)}><EmptyHint label={t.lab.experiments.empty} /></div>
  }

  function inferTags(suite: string): string[] {
    const tags: string[] = []
    if (suite.includes('asr')) tags.push('asr')
    if (suite.includes('diar')) tags.push('diarization')
    if (suite.includes('separation') || suite.includes('mix')) tags.push('separation')
    if (suite.includes('ocr')) tags.push('ocr_detect')
    if (suite.includes('erase')) tags.push('subtitle_erase')
    if (suite.includes('dub')) tags.push('e2e_dub')
    return tags
  }

  function inferDataset(suite: string): string {
    if (suite.includes('wenetspeech')) return 'wenetspeech-drama'
    if (suite.includes('aishell4')) return 'aishell4'
    if (suite.includes('alimeeting')) return 'alimeeting'
    if (suite.includes('synthetic-mix')) return 'synthetic-mix'
    if (suite.includes('synthetic')) return 'synthetic-subtitle'
    return 'folder'
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-[#6b7280]">{t.lab.experiments.hint}</p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {suites.map(suite => {
          const started = triggerMutation.isSuccess && triggerMutation.variables === suite
          const tags = inferTags(suite)
          const dataset = inferDataset(suite)
          return (
            <div key={suite} className={cn(CARD, 'p-4 transition-shadow hover:shadow-[0_4px_12px_rgba(0,0,0,.08)]')}>
              <div className="min-w-0">
                <p className="truncate font-medium text-[#111827]">{suite}</p>
                <div className="mt-1 flex items-center gap-1.5 text-xs text-[#6b7280]">
                  <Database className="h-3 w-3" />
                  {dataset}
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {tags.map(s => <ScenarioTag key={s} name={s} />)}
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <p className="text-xs text-[#9ca3af]">{t.lab.experiments.smokeRun}</p>
                <button
                  type="button"
                  disabled={triggerMutation.isPending}
                  onClick={() => triggerMutation.mutate(suite)}
                  className={cn(
                    started
                      ? 'inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-[0_1px_3px_rgba(16,185,129,.35)] transition-all hover:bg-emerald-700'
                      : 'inline-flex items-center gap-1.5 rounded-lg bg-[#3b5bdb] px-3 py-1.5 text-xs font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]',
                    triggerMutation.isPending && 'opacity-50',
                  )}
                >
                  {started ? <CheckCircle2 className="h-3.5 w-3.5" /> : <PlayCircle className="h-3.5 w-3.5" />}
                  {started ? t.lab.experiments.running : t.lab.experiments.run}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LeaderboardTab() {
  const { t } = useI18n()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['lab', 'runs'],
    queryFn: labApi.runs,
    staleTime: 15_000,
    retry: false,
  })

  const runs = useMemo(() => data ?? [], [data])
  const ranked = useMemo(() => {
    return [...runs].sort((a, b) => {
      const pa = pickPrimaryMetric(a)
      const pb = pickPrimaryMetric(b)
      if (!pa) return 1
      if (!pb) return -1
      const lower = LOWER_IS_BETTER.has(pa.key)
      return lower ? pa.value - pb.value : pb.value - pa.value
    })
  }, [runs])
  const bestRunId = ranked.find(r => r.status === 'finished' && pickPrimaryMetric(r))?.run_id

  return (
    <div className="space-y-3">
      <p className="text-xs text-[#6b7280]">{t.lab.leaderboard.hint}</p>
      <div className={TABLE_WRAPPER}>
        {isLoading ? (
          <LoadingState label={t.lab.loading} />
        ) : isError ? (
          <ErrorState message={t.lab.notReachable} onRetry={() => refetch()} retryLabel={t.lab.retry} />
        ) : ranked.length === 0 ? (
          <EmptyHint label={t.lab.leaderboard.empty} />
        ) : (
          <table className="w-full min-w-[920px] text-sm">
            <thead className="border-b border-[#f3f4f6] text-left">
              <tr>
                <th className="px-4 py-3 w-10 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.leaderboard.columns.rank}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.leaderboard.columns.runId}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.leaderboard.columns.suite}</th>
                <th className="hidden px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap md:table-cell">{t.lab.leaderboard.columns.arm}</th>
                <th className="hidden px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap lg:table-cell">{t.lab.leaderboard.columns.scenarios}</th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.leaderboard.columns.status}</th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.leaderboard.columns.primaryMetric}</th>
                <th className="hidden px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap md:table-cell">{t.lab.leaderboard.columns.rtf}</th>
                <th className="hidden px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap lg:table-cell">{t.lab.leaderboard.columns.createdAt}</th>
                <th className="hidden px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap md:table-cell">{t.lab.leaderboard.columns.duration}</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((run, idx) => {
                const primary = pickPrimaryMetric(run)
                const rtf = run.aggregates?.asr?.rtf
                const isBest = run.run_id === bestRunId
                const isRunning = run.status === 'running'
                return (
                  <tr
                    key={run.run_id}
                    className={cn(
                      'border-b border-[#f9fafb] last:border-0 transition-colors hover:bg-[#fafafa]',
                      isRunning && 'border-l-2 border-l-[#3b5bdb]',
                    )}
                  >
                    <td className="px-4 py-3.5 text-center text-xs font-semibold text-[#9ca3af]">
                      {isBest ? <Trophy className="mx-auto h-4 w-4 text-amber-500" /> : idx + 1}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-xs text-[#4b5563]">{run.run_id}</td>
                    <td className="px-4 py-3.5 text-[#4b5563]">{run.suite ?? '—'}</td>
                    <td className="hidden px-4 py-3.5 text-xs text-[#4b5563] md:table-cell">
                      {String((run as Record<string, unknown>).arm_label ?? '—')}
                    </td>
                    <td className="hidden px-4 py-3.5 lg:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {(run.scenarios ?? []).map(s => <ScenarioTag key={s} name={s} />)}
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <StatusBadge status={mapStatusForBadge(run.status)} size="sm" />
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      {primary ? (
                        <span className={cn(
                          'inline-flex items-baseline gap-1 font-mono text-sm',
                          isBest ? 'font-semibold text-amber-700' : 'text-[#111827]',
                        )}>
                          {formatMetricValue(primary.key, primary.value)}
                          <span className="text-[10px] text-[#9ca3af]">{primary.key}</span>
                        </span>
                      ) : '—'}
                    </td>
                    <td className="hidden px-4 py-3.5 text-right font-mono text-xs text-[#4b5563] md:table-cell">
                      {typeof rtf === 'number' ? rtf.toFixed(2) : '—'}
                    </td>
                    <td className="hidden px-4 py-3.5 text-xs text-[#9ca3af] lg:table-cell">{String(run.created_at ?? '—')}</td>
                    <td className="hidden px-4 py-3.5 text-right text-xs text-[#4b5563] md:table-cell">{formatDuration(run.duration_sec)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function DeltaCell({ value, lower, t }: { value: number; lower: boolean; t: ReturnType<typeof useI18n>['t'] }) {
  if (Math.abs(value) < 1e-6) {
    return (
      <span className="inline-flex items-center gap-1 text-[#9ca3af]">
        <Minus className="h-3.5 w-3.5" />
        {t.lab.regression.noChange}
      </span>
    )
  }
  const improved = lower ? value < 0 : value > 0
  const Icon = improved ? ArrowDownRight : ArrowUpRight
  const cls = improved ? 'text-emerald-600' : 'text-rose-600'
  return (
    <span className={cn('inline-flex items-center gap-1 font-semibold', cls)}>
      <Icon className="h-3.5 w-3.5" />
      {value > 0 ? '+' : ''}{value.toFixed(4)}
      <span className="text-xs font-normal text-[#9ca3af]">({improved ? t.lab.regression.improved : t.lab.regression.regressed})</span>
    </span>
  )
}

function RegressionTab() {
  const { t } = useI18n()
  const runsQuery = useQuery({
    queryKey: ['lab', 'runs'],
    queryFn: labApi.runs,
    staleTime: 15_000,
    retry: false,
  })
  const [baselineRaw, setBaseline] = useState('')
  const [candidateRaw, setCandidate] = useState('')
  const compareMutation = useMutation<LabCompareResult, Error, { baseline: string; candidate: string }>({
    mutationFn: ({ baseline: b, candidate: c }) => labApi.compare(b, c),
  })

  const finishedRuns = useMemo(
    () => (runsQuery.data ?? []).filter(r => r.status === 'finished'),
    [runsQuery.data],
  )
  const baseline = baselineRaw || finishedRuns[0]?.run_id || ''
  const candidate = candidateRaw || finishedRuns[1]?.run_id || ''

  if (runsQuery.isLoading) return <div className={cn(TABLE_WRAPPER)}><LoadingState label={t.lab.loading} /></div>
  if (runsQuery.isError) return <div className={cn(TABLE_WRAPPER)}><ErrorState message={t.lab.notReachable} onRetry={() => runsQuery.refetch()} retryLabel={t.lab.retry} /></div>

  const runs = runsQuery.data ?? []
  const canCompare = Boolean(baseline && candidate && baseline !== candidate)
  const result = compareMutation.data

  return (
    <div className="space-y-4">
      <p className="text-xs text-[#6b7280]">{t.lab.regression.hint}</p>
      <div className={cn(CARD, 'p-4')}>
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              { label: t.lab.regression.baseline, value: baseline, setter: setBaseline },
              { label: t.lab.regression.candidate, value: candidate, setter: setCandidate },
            ] as const
          ).map(({ label, value, setter }) => (
            <label key={label} className="flex flex-col gap-1 text-sm">
              <span className="text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{label}</span>
              <select
                value={value}
                onChange={e => setter(e.target.value)}
                className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#111827] transition-colors hover:border-[#d1d5db] focus:border-[#3b5bdb] focus:outline-none focus:ring-1 focus:ring-[#3b5bdb]"
              >
                <option value="">{t.lab.regression.pickRun}</option>
                {runs.map(r => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.run_id} {r.suite ? `· ${r.suite}` : ''} {(r as Record<string, unknown>).arm_label ? `· ${String((r as Record<string, unknown>).arm_label)}` : ''}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <div className="mt-4">
          <button
            type="button"
            disabled={!canCompare || compareMutation.isPending}
            onClick={() => canCompare && compareMutation.mutate({ baseline, candidate })}
            className={PRIMARY_BUTTON}
          >
            {compareMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trophy className="h-3.5 w-3.5" />}
            {t.lab.regression.compare}
          </button>
        </div>
      </div>

      {result ? (
        <div className={cn(CARD, 'space-y-3 p-4')}>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm">
              <span className="text-[#6b7280]">{t.lab.regression.winner}: </span>
              {result.winner ? (
                <span className="font-mono font-semibold text-[#111827]">{result.winner}</span>
              ) : (
                <span className="text-[#4b5563]">{t.lab.regression.winnerTie}</span>
              )}
            </div>
            <span className="text-xs text-[#9ca3af]">baseline ↔ candidate</span>
          </div>
          <div className="overflow-x-auto rounded-lg border border-[#e5e7eb]">
            <table className="w-full min-w-[680px] text-sm">
              <thead className="border-b border-[#f3f4f6] text-left">
                <tr>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.leaderboard.columns.scenarios}</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.regression.primaryMetric}</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">baseline</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">candidate</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.regression.delta}</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap">{t.lab.regression.relativeDelta}</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.per_scenario ?? {}).map(([scenario, m]) => {
                  const metric = String(m.primary_metric ?? 'cer_micro')
                  const lower = LOWER_IS_BETTER.has(metric)
                  const baseV = Number(m.baseline_value ?? 0)
                  const candV = Number(m.candidate_value ?? 0)
                  const delta = Number(m.delta ?? candV - baseV)
                  const relPct = Number(m.relative_delta_pct ?? 0)
                  return (
                    <tr key={scenario} className="border-b border-[#f9fafb] last:border-0">
                      <td className="px-4 py-3.5"><ScenarioTag name={scenario} /></td>
                      <td className="px-4 py-3.5 text-xs">
                        <div className="font-mono text-[#111827]">{metric}</div>
                        <div className="text-[#9ca3af]">{lower ? t.lab.regression.lowerIsBetter : t.lab.regression.higherIsBetter}</div>
                      </td>
                      <td className="px-4 py-3.5 text-right font-mono text-sm text-[#4b5563]">{formatMetricValue(metric, baseV)}</td>
                      <td className="px-4 py-3.5 text-right font-mono text-sm text-[#4b5563]">{formatMetricValue(metric, candV)}</td>
                      <td className="px-4 py-3.5 text-right text-sm"><DeltaCell value={delta} lower={lower} t={t} /></td>
                      <td className="px-4 py-3.5 text-right font-mono text-sm text-[#4b5563]">
                        {relPct > 0 ? '+' : ''}{relPct.toFixed(2)}%
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p className="text-xs text-[#9ca3af]">{t.lab.regression.empty}</p>
      )}
    </div>
  )
}

export function LabPage() {
  const { t } = useI18n()
  const [searchParams, setSearchParams] = useSearchParams()
  const initialTab = (searchParams.get('tab') as TabKey) || 'datasets'
  const [tab, setTab] = useState<TabKey>(TABS.includes(initialTab) ? initialTab : 'datasets')

  const datasetsQ = useQuery({ queryKey: ['lab', 'datasets'], queryFn: labApi.datasets, retry: false })
  const suitesQ = useQuery({ queryKey: ['lab', 'suites'], queryFn: labApi.suites, retry: false })
  const runsQ = useQuery({ queryKey: ['lab', 'runs'], queryFn: labApi.runs, retry: false })

  const setTabAndUrl = (next: TabKey) => {
    setTab(next)
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    setSearchParams(params, { replace: true })
  }

  const labUrl = useMemo(() => labApi.baseUrl(), [])
  const tabLabels: Record<TabKey, string> = {
    datasets: t.lab.tabs.datasets,
    experiments: t.lab.tabs.experiments,
    leaderboard: t.lab.tabs.leaderboard,
    regression: t.lab.tabs.regression,
  }

  return (
    <PageContainer className={cn(APP_CONTENT_MAX_WIDTH, 'space-y-5')}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-[#eef1fd] p-2.5 text-[#3b5bdb]">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold text-[#111827]">{t.lab.title}</h1>
              <SourceBadge />
            </div>
            <p className="mt-1 max-w-2xl text-sm text-[#6b7280]">{t.lab.subtitle}</p>
          </div>
        </div>
        <a
          href={labUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={SECONDARY_BUTTON}
        >
          {t.lab.advancedDashboard}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </header>

      <OverviewCards datasets={datasetsQ.data} suites={suitesQ.data} runs={runsQ.data} />

      <div className="flex flex-wrap gap-1.5">
        {TABS.map(key => (
          <button
            key={key}
            type="button"
            onClick={() => setTabAndUrl(key)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
              tab === key
                ? 'bg-[#3b5bdb] text-white shadow-sm'
                : 'bg-white border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f9fafb] hover:text-[#374151]',
            )}
          >
            {tabLabels[key]}
          </button>
        ))}
      </div>

      <section>
        {tab === 'datasets' && <DatasetsTab />}
        {tab === 'experiments' && <ExperimentsTab />}
        {tab === 'leaderboard' && <LeaderboardTab />}
        {tab === 'regression' && <RegressionTab />}
      </section>
    </PageContainer>
  )
}

export default LabPage
