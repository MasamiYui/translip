import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CircleStop, ExternalLink, RefreshCw, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { atomicToolsApi } from '../api/atomic-tools'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { ProgressBar } from '../components/shared/ProgressBar'
import { StatusBadge } from '../components/shared/StatusBadge'
import { useI18n } from '../i18n/useI18n'

export function AtomicJobDetailPage() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { t, formatDuration, formatRelativeTime } = useI18n()

  const { data: job } = useQuery({
    queryKey: ['atomic-tool-job-detail', jobId],
    queryFn: () => atomicToolsApi.getJobDetail(jobId),
    enabled: Boolean(jobId),
    refetchInterval: query => {
      const status = query.state.data?.status
      return status === 'pending' || status === 'running' ? 1000 : false
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => atomicToolsApi.deleteJob(jobId),
    onSuccess: () => navigate('/tools/jobs'),
  })

  const rerunMutation = useMutation({
    mutationFn: () => atomicToolsApi.rerunJob(jobId),
    onSuccess: nextJob => {
      queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] })
      navigate(`/tools/jobs/${nextJob.job_id}`)
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => atomicToolsApi.stopJob(jobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['atomic-tool-job-detail', jobId] })
      queryClient.invalidateQueries({ queryKey: ['atomic-tool-jobs'] })
    },
  })

  if (!job) {
    return (
      <PageContainer className={APP_CONTENT_MAX_WIDTH}>
        <div className="py-16 text-center text-sm text-[#9ca3af]">{t.common.loading}</div>
      </PageContainer>
    )
  }

  const canStop = job.status === 'pending' || job.status === 'running'

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-5`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/tools/jobs" className="mb-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-[#9ca3af] hover:text-[#374151]">
            <ArrowLeft size={13} />
            {t.atomicJobs.backToJobs}
          </Link>
          <h1 className="text-xl font-bold text-[#111827]">{job.tool_name}</h1>
          <p className="mt-1 font-mono text-xs text-[#9ca3af]">{job.job_id}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/tools/${job.tool_id}`}
            className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-xs font-semibold text-[#3b5bdb] transition-all hover:bg-[#f0f3ff]"
          >
            <ExternalLink size={13} />
            {t.atomicJobs.openTool}
          </Link>
          <button
            type="button"
            onClick={() => rerunMutation.mutate()}
            className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-xs font-semibold text-[#374151] transition-all hover:bg-[#f9fafb]"
          >
            <RefreshCw size={13} />
            {t.atomicJobs.rerun}
          </button>
          {canStop ? (
            <button
              type="button"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-white px-3.5 py-2 text-xs font-semibold text-amber-700 transition-all hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <CircleStop size={13} />
              {t.atomicJobs.stop}
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => {
              if (confirm(t.atomicJobs.deleteConfirm)) deleteMutation.mutate()
            }}
            className="inline-flex items-center gap-2 rounded-lg border border-red-100 bg-white px-3.5 py-2 text-xs font-semibold text-red-500 transition-all hover:bg-red-50"
          >
            <Trash2 size={13} />
            {t.atomicJobs.delete}
          </button>
        </div>
      </div>

      <section className="grid gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.status}</div>
          <StatusBadge status={job.status} />
        </div>
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{t.atomicJobs.columns.progress}</div>
          <div className="flex items-center gap-2">
            <ProgressBar value={job.progress_percent} size="sm" className="flex-1" />
            <span className="text-sm font-semibold tabular-nums text-[#374151]">{job.progress_percent.toFixed(0)}%</span>
          </div>
        </div>
        <Metric label={t.atomicJobs.columns.duration} value={formatDuration(job.elapsed_sec ?? undefined)} />
        <Metric label={t.atomicJobs.columns.createdAt} value={formatRelativeTime(job.created_at)} />
      </section>

      <section className="grid gap-5 xl:grid-cols-2">
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-[#374151]">{t.atomicJobs.sections.inputs}</h2>
          <div className="mb-3 space-y-2">
            {job.input_files.map(file => (
              <div key={file.file_id} className="rounded-lg border border-[#f3f4f6] px-3 py-2 text-sm">
                <div className="font-medium text-[#111827]">{file.filename}</div>
                <div className="mt-0.5 text-xs text-[#9ca3af]">{file.content_type}</div>
              </div>
            ))}
          </div>
          <pre className="max-h-[240px] overflow-auto rounded-lg border border-[#f3f4f6] bg-[#f8f9fa] p-3 text-xs leading-5 text-[#374151]">
            {JSON.stringify(job.input_files, null, 2)}
          </pre>
        </div>
        <JsonBlock title={t.atomicJobs.sections.params} value={job.params} />
        <JsonBlock title={t.atomicJobs.sections.result} value={job.result ?? {}} />
        <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-[#374151]">{t.atomicJobs.sections.artifacts}</h2>
          {job.artifacts.length === 0 ? (
            <div className="text-sm text-[#9ca3af]">{t.common.notAvailable}</div>
          ) : (
            <div className="space-y-2">
              {job.artifacts.map(artifact => (
                <a
                  key={artifact.filename}
                  href={artifact.download_url}
                  className="flex items-center justify-between gap-3 rounded-lg border border-[#f3f4f6] px-3 py-2 text-sm hover:bg-[#f9fafb]"
                >
                  <span className="font-medium text-[#111827]">{artifact.filename}</span>
                  <span className="text-xs text-[#9ca3af]">{artifact.content_type}</span>
                </a>
              ))}
            </div>
          )}
        </div>
      </section>
    </PageContainer>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#9ca3af]">{label}</div>
      <div className="text-sm font-semibold text-[#374151]">{value}</div>
    </div>
  )
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-5">
      <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-[#374151]">{title}</h2>
      <pre className="max-h-[360px] overflow-auto rounded-lg border border-[#f3f4f6] bg-[#f8f9fa] p-3 text-xs leading-5 text-[#374151]">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}
