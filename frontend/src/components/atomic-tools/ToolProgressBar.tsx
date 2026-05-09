import type { AtomicJob } from '../../types/atomic-tools'
import { useI18n } from '../../i18n/useI18n'
import type { LocaleMessages } from '../../i18n/messages'

export function ToolProgressBar({ job }: { job: AtomicJob | null }) {
  const { t } = useI18n()

  if (!job) return null

  const tone =
    job.status === 'failed'
      ? 'bg-rose-500'
      : job.status === 'completed'
        ? 'bg-emerald-500'
        : 'bg-blue-500'

  const progressSteps = (
    t.atomicTools as LocaleMessages['atomicTools'] & {
      progressSteps?: Record<string, string>
    }
  ).progressSteps ?? {}
  const rawStep = job.current_step ?? job.status
  const friendlyLabel = friendlyStepLabel(rawStep, progressSteps)

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between text-sm text-slate-600">
        <span className="truncate" title={rawStep ?? undefined}>
          {friendlyLabel}
        </span>
        <span className="shrink-0 tabular-nums font-medium text-slate-700">
          {Math.round(job.progress_percent)}%
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-300 ease-out ${tone} ${
            job.status === 'running' || job.status === 'pending'
              ? 'bg-[length:200%_100%] animate-[progressShimmer_1.8s_linear_infinite]'
              : ''
          }`}
          style={{
            width: `${Math.max(2, Math.min(100, job.progress_percent))}%`,
            backgroundImage:
              job.status === 'running' || job.status === 'pending'
                ? 'linear-gradient(90deg, rgba(255,255,255,0.0) 0%, rgba(255,255,255,0.35) 50%, rgba(255,255,255,0.0) 100%)'
                : undefined,
          }}
        />
      </div>
      {job.error_message && <p className="mt-3 text-sm text-rose-600">{job.error_message}</p>}
    </div>
  )
}

function friendlyStepLabel(
  step: string | null | undefined,
  dictionary: Record<string, string>,
): string {
  if (!step) return ''
  if (dictionary[step]) return dictionary[step]
  if (step.startsWith('auto_detect_')) {
    const nested = dictionary[step] ?? dictionary.auto_detecting
    if (nested) return nested
  }
  if (step.startsWith('erasing_')) {
    return dictionary[step] ?? dictionary.erasing ?? step
  }
  return step
}
