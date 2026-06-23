import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Download, FlaskConical, Loader2 } from 'lucide-react'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../../components/layout/PageContainer'
import { StatusBadge } from '../../components/shared/StatusBadge'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'
import { labApi, type LabRunDetail } from '../../api/lab'

const CARD = 'rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]'
const TABLE_WRAPPER = 'overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]'
const SECONDARY_BUTTON =
  'inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50'
const TH = 'px-4 py-3 text-xs font-semibold uppercase tracking-wide text-[#9ca3af] whitespace-nowrap'
const RATE_METRICS = ['cer_micro', 'cer_macro', 'cer', 'der', 'jer', 'wer']

type T = ReturnType<typeof useI18n>['t']

function mapStatusForBadge(status?: string): string {
  const key = (status ?? 'pending').toLowerCase()
  if (key === 'finished' || key === 'succeeded') return 'completed'
  if (key === 'queued') return 'pending'
  return key
}

function fmtMetric(key: string | undefined, value: unknown): string {
  if (typeof value !== 'number') return '—'
  if (key && RATE_METRICS.includes(key)) return `${(value * 100).toFixed(2)}%`
  if (key === 'rtf') return value.toFixed(2)
  return value.toFixed(3)
}

function fmtDuration(sec: unknown): string {
  if (typeof sec !== 'number' || !sec) return '—'
  if (sec < 60) return `${Math.round(sec)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

function aggregateKey(scenario: string, arm?: string): string {
  return !arm || arm === 'default' ? scenario : `${scenario}@${arm}`
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className={cn(CARD, 'p-4')}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{label}</div>
      <div className="mt-1.5 truncate text-sm font-semibold text-[#111827]" title={value}>{value}</div>
    </div>
  )
}

function ResultRow({ r, metricKey, t }: { r: Record<string, unknown>; metricKey?: string; t: T }) {
  const [open, setOpen] = useState(false)
  const status = String(r.status ?? 'pending')
  const err = r.error ? String(r.error) : ''
  return (
    <>
      <tr className="border-b border-[#f9fafb] last:border-0 transition-colors hover:bg-[#fafafa]">
        <td className="px-4 py-3 font-mono text-xs text-[#4b5563]">{String(r.sample_id ?? '—')}</td>
        <td className="px-4 py-3 text-[#4b5563]">{String(r.scenario ?? '—')}</td>
        <td className="px-4 py-3">
          <StatusBadge status={mapStatusForBadge(status)} size="sm" />
          {err ? (
            <button type="button" onClick={() => setOpen(o => !o)} className="ml-2 text-xs text-rose-600 underline">
              {open ? t.lab.detail.hideError : t.lab.detail.showError}
            </button>
          ) : null}
        </td>
        <td className="px-4 py-3 font-mono">{fmtMetric(metricKey, r.primary_metric)}</td>
        <td className="px-4 py-3 text-xs text-[#4b5563]">{fmtDuration(r.duration_sec)}</td>
        <td className="px-4 py-3 text-center text-xs text-[#9ca3af]">{r.cached ? '✓' : ''}</td>
      </tr>
      {err && open ? (
        <tr className="bg-rose-50/40">
          <td colSpan={6} className="px-4 pb-3">
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-[#1f2937] p-3 font-mono text-xs leading-relaxed text-rose-200">
              {err}
            </pre>
          </td>
        </tr>
      ) : null}
    </>
  )
}

export function RunDetailPage() {
  const { t } = useI18n()
  const { runId = '' } = useParams()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['lab', 'run', runId],
    queryFn: () => labApi.runDetail(runId),
    retry: false,
    enabled: Boolean(runId),
  })
  const download = useMutation({
    mutationFn: async () => {
      const md = await labApi.reportMarkdown(runId)
      const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${runId}.md`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    },
  })

  const run = (data ?? {}) as LabRunDetail
  const aggregates = (run.aggregates ?? {}) as Record<string, Record<string, unknown>>
  const results = (run.results ?? []) as Array<Record<string, unknown>>
  const samples = run.sample_count ?? run.num_samples
  const started = run.started_at ?? run.created_at
  const elapsed = run.elapsed_sec ?? run.duration_sec

  const metricKeyFor = (scenario: string, arm?: string): string | undefined => {
    const agg = aggregates[aggregateKey(scenario, arm)] ?? aggregates[scenario]
    return agg?.primary_metric as string | undefined
  }

  return (
    <PageContainer className={cn(APP_CONTENT_MAX_WIDTH, 'space-y-5')}>
      <Link to="/lab?tab=leaderboard" className={SECONDARY_BUTTON}>
        <ArrowLeft className="h-3.5 w-3.5" />
        {t.lab.detail.back}
      </Link>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-[#9ca3af]">{t.lab.loading}</div>
      ) : isError || !run.run_id ? (
        <div className="py-16 text-center text-sm">
          <p className="text-rose-600">{t.lab.detail.notFound}</p>
          <button type="button" onClick={() => refetch()} className={cn(SECONDARY_BUTTON, 'mt-3')}>
            {t.lab.retry}
          </button>
        </div>
      ) : (
        <>
          <header className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-[#eef1fd] p-2.5 text-[#3b5bdb]">
                <FlaskConical className="h-5 w-5" />
              </div>
              <div>
                <h1 className="font-mono text-xl font-semibold text-[#111827]">{String(run.run_id)}</h1>
                <p className="mt-1 text-sm text-[#6b7280]">
                  {t.lab.detail.suite}: <span className="text-[#111827]">{run.suite ?? '—'}</span>
                  {' · '}
                  {t.lab.detail.dataset}: <span className="text-[#111827]">{run.dataset ?? '—'}</span>
                </p>
              </div>
            </div>
            <button
              type="button"
              disabled={download.isPending}
              onClick={() => download.mutate()}
              className={SECONDARY_BUTTON}
            >
              {download.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
              {t.lab.detail.downloadReport}
            </button>
          </header>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MetaCard label={t.lab.detail.samples} value={samples != null ? String(samples) : '—'} />
            <MetaCard label={t.lab.detail.scenarios} value={(run.scenarios ?? []).join(', ') || '—'} />
            <MetaCard label={t.lab.detail.started} value={started ? String(started) : '—'} />
            <MetaCard label={t.lab.detail.elapsed} value={fmtDuration(elapsed)} />
          </div>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-[#374151]">{t.lab.detail.aggregates}</h2>
            <div className={TABLE_WRAPPER}>
              <table className="w-full min-w-[720px] text-sm">
                <thead className="border-b border-[#f3f4f6] text-left">
                  <tr>
                    {[t.lab.detail.colScenario, t.lab.detail.colMetric, 'mean', 'micro', 'std',
                      t.lab.detail.colScored, t.lab.detail.colFailed, t.lab.detail.colSkipped].map(h => (
                      <th key={h} className={TH}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(aggregates).length === 0 ? (
                    <tr><td colSpan={8} className="px-4 py-8 text-center text-[#9ca3af]">—</td></tr>
                  ) : Object.entries(aggregates).map(([key, agg]) => {
                    const metric = agg.primary_metric as string | undefined
                    const higher = agg.higher_is_better
                    const arrow = higher === false ? '↓' : higher ? '↑' : ''
                    const micro = (agg.corpus as Record<string, unknown> | undefined)?.[`${metric}_micro`]
                    return (
                      <tr key={key} className="border-b border-[#f9fafb] last:border-0">
                        <td className="px-4 py-3 font-medium text-[#111827]">{key}</td>
                        <td className="px-4 py-3 font-mono text-xs text-[#4b5563]">{metric ?? '—'} {arrow}</td>
                        <td className="px-4 py-3 font-mono text-[#111827]">{fmtMetric(metric, agg.mean)}</td>
                        <td className="px-4 py-3 font-mono text-[#4b5563]">{fmtMetric(metric, micro)}</td>
                        <td className="px-4 py-3 font-mono text-xs text-[#9ca3af]">{fmtMetric(metric, agg.std)}</td>
                        <td className="px-4 py-3 text-emerald-700">{String(agg.scored ?? 0)}</td>
                        <td className="px-4 py-3 text-rose-600">{String(agg.failed ?? 0)}</td>
                        <td className="px-4 py-3 text-[#9ca3af]">{String(agg.skipped ?? 0)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-[#374151]">{t.lab.detail.samplesTitle}</h2>
            <div className={TABLE_WRAPPER}>
              <table className="w-full min-w-[760px] text-sm">
                <thead className="border-b border-[#f3f4f6] text-left">
                  <tr>
                    {[t.lab.detail.colSample, t.lab.detail.colScenario, t.lab.detail.colStatus,
                      t.lab.detail.colMetric, t.lab.detail.colDuration, t.lab.detail.colCached].map(h => (
                      <th key={h} className={TH}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {results.length === 0 ? (
                    <tr><td colSpan={6} className="px-4 py-8 text-center text-[#9ca3af]">{t.lab.detail.noSamples}</td></tr>
                  ) : results.map((r, i) => (
                    <ResultRow key={i} r={r} metricKey={metricKeyFor(String(r.scenario ?? ''), r.arm as string | undefined)} t={t} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </PageContainer>
  )
}

export default RunDetailPage
