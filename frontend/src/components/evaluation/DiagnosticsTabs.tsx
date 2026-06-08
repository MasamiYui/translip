import { useMemo, useState } from 'react'
import { Activity, AudioWaveform, Music2, Radar, ScatterChart, Video } from 'lucide-react'
import type { DubQaReport, DubQaSegment } from '../../api/evaluation'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'
import { EvaluationVideoPanel } from './EvaluationVideoPanel'
import { WaveformCompare } from './WaveformCompare'
import { SpeakerRadar } from './SpeakerRadar'
import { EmbeddingScatter } from './EmbeddingScatter'
import { PitchContourCompare } from './PitchContourCompare'
import { MelSpectrogramCompare } from './MelSpectrogramCompare'

type TabKey = 'video' | 'waveform' | 'speakerRadar' | 'embedding' | 'pitch' | 'mel'

interface Props {
  taskId: string
  report: DubQaReport
  segments: DubQaSegment[]
  selectedId: string | null
  onSelectSegment: (segment: DubQaSegment) => void
}

interface TabDef {
  key: TabKey
  label: string
  icon: typeof Video
  badge?: string
  available: boolean
}

const STORAGE_KEY = 'evaluation-diagnostics-tab'

function readPreferredTab(): TabKey | null {
  if (typeof window === 'undefined') return null
  const v = window.localStorage.getItem(STORAGE_KEY)
  return v && ['video', 'waveform', 'speakerRadar', 'embedding', 'pitch', 'mel'].includes(v)
    ? (v as TabKey)
    : null
}

/**
 * Compact tabbed diagnostics panel for the evaluation detail page.
 *
 * Why a tabbed card?
 *   The page used to stack 5–6 large visualizations vertically (video,
 *   waveform, radar, embedding scatter, pitch, mel-spectrogram) which made
 *   the first viewport feel endless. Reviewers actually need at most one
 *   visualization at a time when triaging a problem segment, so we put them
 *   all behind tabs and only render the active tab's heavy chart.
 *
 * Behaviour:
 *   - Tabs whose data is unavailable in the current report are hidden,
 *     keeping the strip lean per task.
 *   - The chosen tab is persisted to localStorage so reviewers don't have
 *     to reselect their preferred view across navigations.
 *   - Each tab gets a small badge (counts / status) so the value of
 *     switching is visible up-front.
 */
export function DiagnosticsTabs({
  taskId,
  report,
  segments,
  selectedId,
  onSelectSegment,
}: Props) {
  const { t } = useI18n()
  const tx = t.evaluation.diagnostics

  const problemCount = useMemo(
    () => segments.filter(s => s.issue_tags.length > 0).length,
    [segments],
  )
  const speakerCount = useMemo(() => {
    const ids = new Set<string>()
    for (const s of segments) {
      if (s.speaker_id) ids.add(s.speaker_id)
    }
    return ids.size
  }, [segments])
  const hasEmbedding =
    report.embedding_meta?.status === 'ok' &&
    segments.some(s => Array.isArray(s.speaker_embedding) && s.speaker_embedding.length > 0)
  const hasPitch =
    report.pitch_meta?.status === 'ok' && segments.some(s => s.pitch_contour)
  const hasMel =
    report.mel_meta?.status === 'ok' && segments.some(s => s.mel_spectrogram)

  const tabs: TabDef[] = useMemo(
    () => [
      {
        key: 'video',
        label: tx.tabs.video,
        icon: Video,
        badge: problemCount > 0 ? String(problemCount) : undefined,
        available: true,
      },
      {
        key: 'waveform',
        label: tx.tabs.waveform,
        icon: AudioWaveform,
        available: true,
      },
      {
        key: 'speakerRadar',
        label: tx.tabs.speakerRadar,
        icon: Radar,
        badge: speakerCount > 0 ? String(speakerCount) : undefined,
        available: speakerCount > 0,
      },
      {
        key: 'embedding',
        label: tx.tabs.embedding,
        icon: ScatterChart,
        available: hasEmbedding,
      },
      {
        key: 'pitch',
        label: tx.tabs.pitch,
        icon: Activity,
        available: hasPitch,
      },
      {
        key: 'mel',
        label: tx.tabs.mel,
        icon: Music2,
        available: hasMel,
      },
    ],
    [tx, problemCount, speakerCount, hasEmbedding, hasPitch, hasMel],
  )

  const visibleTabs = tabs.filter(t => t.available)

  const [active, setActive] = useState<TabKey>(() => {
    const stored = readPreferredTab()
    if (stored && tabs.find(t => t.key === stored && t.available)) return stored
    return 'video'
  })

  // If the active tab stops being available (data changed), fall back to the
  // first visible one. Adjusted during render rather than in an effect so it
  // resolves before paint; the guard makes it converge in one extra render.
  if (visibleTabs.length > 0 && !visibleTabs.find(t => t.key === active)) {
    setActive(visibleTabs[0].key)
  }

  const onSelectTab = (key: TabKey) => {
    setActive(key)
    try {
      window.localStorage.setItem(STORAGE_KEY, key)
    } catch {
      /* ignore quota / private mode */
    }
  }

  if (visibleTabs.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-5 py-6 text-center text-xs text-[#9ca3af]">
        {tx.emptyHint}
      </section>
    )
  }

  return (
    <section className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white">
      <header className="flex items-center justify-between gap-3 border-b border-[#f3f4f6] px-3 py-2">
        <div className="hidden px-2 sm:block">
          <h2 className="text-sm font-semibold text-[#111827]">{tx.title}</h2>
          <p className="text-[11px] text-[#9ca3af]">{tx.subtitle}</p>
        </div>
        <nav
          role="tablist"
          aria-label={tx.title}
          className="flex flex-1 flex-wrap justify-end gap-1"
        >
          {visibleTabs.map(tab => {
            const Icon = tab.icon
            const isActive = tab.key === active
            return (
              <button
                key={tab.key}
                role="tab"
                aria-selected={isActive}
                type="button"
                onClick={() => onSelectTab(tab.key)}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                  isActive
                    ? 'bg-[#3b5bdb] text-white shadow-sm'
                    : 'text-[#6b7280] hover:bg-[#f3f4f6]',
                )}
              >
                <Icon size={13} />
                <span>{tab.label}</span>
                {tab.badge && (
                  <span
                    className={cn(
                      'rounded px-1 text-[10px] font-semibold tabular-nums',
                      isActive ? 'bg-white/20 text-white' : 'bg-[#f3f4f6] text-[#6b7280]',
                    )}
                  >
                    {tab.badge}
                  </span>
                )}
              </button>
            )
          })}
        </nav>
      </header>

      <div className="px-4 py-4">
        {active === 'video' && (
          <EvaluationVideoPanel
            taskId={taskId}
            report={report}
            segments={segments}
            selectedId={selectedId}
            onSelectSegment={onSelectSegment}
            embedded
          />
        )}
        {active === 'waveform' && (
          <WaveformCompare
            taskId={taskId}
            report={report}
            segments={segments}
            selectedId={selectedId}
            onSelectSegment={onSelectSegment}
            embedded
          />
        )}
        {active === 'speakerRadar' && <SpeakerRadar segments={segments} embedded />}
        {active === 'embedding' && hasEmbedding && (
          <EmbeddingScatter
            report={report}
            selectedId={selectedId}
            onSelectSegment={onSelectSegment}
            embedded
          />
        )}
        {active === 'pitch' && hasPitch && (
          <PitchContourCompare
            report={report}
            selectedId={selectedId}
            onSelectSegment={onSelectSegment}
            embedded
          />
        )}
        {active === 'mel' && hasMel && (
          <MelSpectrogramCompare
            report={report}
            selectedId={selectedId}
            onSelectSegment={onSelectSegment}
            embedded
          />
        )}
      </div>
    </section>
  )
}
