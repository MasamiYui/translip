import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Ban,
  Check,
  GitMerge,
  Loader2,
  Mic2,
  RotateCcw,
  Route,
  SlidersHorizontal,
  UserRound,
  Wand2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import type {
  SpeakerReviewDecisionPayload,
  SpeakerReviewResponse,
  SpeakerReviewRun,
  SpeakerReviewSegment,
  SpeakerReviewSpeaker,
} from '../../types'

type ReviewTab = 'speakers' | 'runs' | 'segments'

const TAB_CONFIG: Array<{ id: ReviewTab; label: string; description: string }> = [
  { id: 'speakers', label: '说话人总览', description: '先处理低样本和不可克隆角色' },
  { id: 'runs', label: '短孤岛', description: '修正夹在上下文中的异常 speaker run' },
  { id: 'segments', label: '片段风险', description: '逐段处理边界和长段异常' },
]

export function SpeakerReviewDrawer({
  taskId,
  isOpen,
  onClose,
  onRerunFromTaskB,
}: {
  taskId: string
  isOpen: boolean
  onClose: () => void
  onRerunFromTaskB?: () => void
}) {
  const [activeTab, setActiveTab] = useState<ReviewTab>('speakers')
  const queryClient = useQueryClient()

  const reviewQuery = useQuery({
    queryKey: ['speaker-review', taskId],
    queryFn: () => tasksApi.getSpeakerReview(taskId),
    enabled: isOpen,
  })

  const decisionMutation = useMutation({
    mutationFn: (payload: SpeakerReviewDecisionPayload) => tasksApi.saveSpeakerReviewDecision(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => tasksApi.applySpeakerReviewDecisions(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['speaker-review', taskId] })
      queryClient.invalidateQueries({ queryKey: ['artifacts', taskId] })
      queryClient.invalidateQueries({ queryKey: ['task', taskId] })
    },
  })

  const review = reviewQuery.data
  const stats = useMemo(() => summarizeReview(review), [review])
  const speakerOptions = useMemo(
    () => review?.speakers.map(speaker => speaker.speaker_label).sort() ?? [],
    [review],
  )

  if (!isOpen) {
    return null
  }

  function saveDecision(payload: SpeakerReviewDecisionPayload) {
    decisionMutation.mutate(payload)
  }

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-30 bg-slate-950/25"
        onClick={onClose}
        aria-label="关闭说话人审查"
      />
      <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-6xl flex-col border-l border-slate-200 bg-white">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              <Mic2 size={13} />
              Step 1 · Speaker Review
            </div>
            <h2 className="mt-2 text-xl font-semibold text-slate-900">说话人核对</h2>
            <div className="mt-1 text-sm text-slate-500">
              确认每一段话是谁说的。归属错误会污染后续音色克隆，审查通过后请从 Task B 重跑。
            </div>
            <FlowProgress />
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-200 p-1.5 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        <div className="border-b border-slate-100 px-6 py-4">
          <div className="grid gap-3 md:grid-cols-5">
            <ReviewStat label="说话人" value={stats.speakers} />
            <ReviewStat label="高风险" value={stats.highRiskSpeakers} />
            <ReviewStat label="短孤岛" value={stats.runs} />
            <ReviewStat label="片段风险" value={stats.segments} />
            <ReviewStat label="决策" value={stats.decisions} />
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-3">
          <div className="flex gap-1 overflow-x-auto">
            {TAB_CONFIG.map(tab => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`min-w-36 rounded-lg px-3 py-2 text-left transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                }`}
              >
                <div className="text-sm font-semibold">{tab.label}</div>
                <div className="mt-0.5 text-xs opacity-75">{tab.description}</div>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {review?.summary.corrected_exists && <StatusPill tone="emerald">已生成修正版</StatusPill>}
            <button
              type="button"
              onClick={() => applyMutation.mutate()}
              disabled={!review || review.status !== 'available' || review.summary.decision_count === 0 || applyMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {applyMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
              应用 speaker 修正
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {reviewQuery.isLoading && (
            <Notice icon={Loader2} tone="slate" spin>
              正在生成说话人诊断...
            </Notice>
          )}

          {reviewQuery.isError && (
            <Notice icon={AlertTriangle} tone="rose">
              说话人审查数据读取失败，请确认 Task A 产物是否完整。
            </Notice>
          )}

          {applyMutation.isSuccess && (
            <div className="mb-4 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3.5">
              <Check size={16} className="mt-0.5 shrink-0 text-emerald-600" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-emerald-800">修正已应用</div>
                <div className="mt-0.5 text-sm text-emerald-700">
                  已输出 <code className="rounded bg-emerald-100 px-1 py-0.5 font-mono text-xs">segments.zh.speaker-corrected.json</code>，
                  建议立即从 Task B 重跑以使变更生效。
                </div>
                {onRerunFromTaskB && (
                  <button
                    type="button"
                    onClick={onRerunFromTaskB}
                    className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
                  >
                    <RotateCcw size={13} />
                    立即从 Task B 重跑
                  </button>
                )}
              </div>
            </div>
          )}

          {applyMutation.isError && (
            <Notice icon={AlertTriangle} tone="rose">
              应用 speaker 决策失败，请先确认已经保存至少一条人工决策。
            </Notice>
          )}

          {review && review.status === 'missing' && (
            <EmptyState
              title="当前还没有可审查的说话人产物"
              description="需要先完成 Task A，生成 segments.zh.json 或 ASR/OCR corrected segments 后，这里才会显示诊断结果。"
            />
          )}

          {review && review.status === 'available' && (
            <>
              {activeTab === 'speakers' && (
                <SpeakerPanel
                  speakers={review.speakers}
                  speakerOptions={speakerOptions}
                  isSaving={decisionMutation.isPending}
                  onSave={saveDecision}
                />
              )}
              {activeTab === 'runs' && (
                <RunPanel
                  runs={review.speaker_runs}
                  speakerOptions={speakerOptions}
                  isSaving={decisionMutation.isPending}
                  onSave={saveDecision}
                />
              )}
              {activeTab === 'segments' && (
                <SegmentPanel
                  segments={review.segments}
                  speakerOptions={speakerOptions}
                  isSaving={decisionMutation.isPending}
                  onSave={saveDecision}
                />
              )}
            </>
          )}
        </div>
      </aside>
    </>
  )
}

function SpeakerPanel({
  speakers,
  speakerOptions,
  isSaving,
  onSave,
}: {
  speakers: SpeakerReviewSpeaker[]
  speakerOptions: string[]
  isSaving: boolean
  onSave: (payload: SpeakerReviewDecisionPayload) => void
}) {
  const [targets, setTargets] = useState<Record<string, string>>({})
  const sorted = useMemo(
    () => [...speakers].sort((a, b) => riskSort(a.risk_level, b.risk_level) || b.segment_count - a.segment_count),
    [speakers],
  )

  if (sorted.length === 0) {
    return <EmptyState title="没有说话人统计" description="当前 segments 文件为空，无法生成 speaker summary。" />
  }

  return (
    <div className="space-y-4">
      {sorted.map(speaker => {
        const target = targets[speaker.speaker_label] ?? ''
        return (
          <section key={speaker.speaker_label} className="rounded-xl border border-slate-200 bg-white">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <UserRound size={15} className="text-slate-400" />
                  <h3 className="font-mono text-sm font-semibold text-slate-900">{speaker.speaker_label}</h3>
                  <RiskPill level={speaker.risk_level} />
                  {!speaker.cloneable_by_default && <StatusPill tone="amber">默认不建议克隆</StatusPill>}
                  {speaker.decision && <StatusPill tone="blue">已决策：{decisionLabel(speaker.decision.decision)}</StatusPill>}
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                  <span>片段 {speaker.segment_count}</span>
                  <span>语音 {formatSeconds(speaker.total_speech_sec)}</span>
                  <span>平均 {formatSeconds(speaker.avg_duration_sec)}</span>
                  <span>短句 {speaker.short_segment_count}</span>
                </div>
                <RiskFlags flags={speaker.risk_flags} />
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <ReviewActionButton
                  icon={Ban}
                  label="不克隆"
                  disabled={isSaving}
                  active={speaker.decision?.decision === 'mark_non_cloneable'}
                  onClick={() => onSave({
                    item_id: `speaker:${speaker.speaker_label}`,
                    item_type: 'speaker_profile',
                    decision: 'mark_non_cloneable',
                    source_speaker_label: speaker.speaker_label,
                    segment_ids: speaker.segment_ids,
                  })}
                />
                <ReviewActionButton
                  icon={Check}
                  label="保持独立"
                  disabled={isSaving}
                  active={speaker.decision?.decision === 'keep_independent'}
                  onClick={() => onSave({
                    item_id: `speaker:${speaker.speaker_label}`,
                    item_type: 'speaker_profile',
                    decision: 'keep_independent',
                    source_speaker_label: speaker.speaker_label,
                    segment_ids: speaker.segment_ids,
                  })}
                />
              </div>
            </div>
            <div className="grid gap-3 px-4 py-3.5 md:grid-cols-[minmax(0,1fr)_280px]">
              <div className="min-w-0 text-sm leading-6 text-slate-600">
                {speaker.risk_flags.length > 0
                  ? '优先判断这个 label 是否是真实角色。如果只是短孤岛或误分出来的临时说话人，应合并到上下文角色，或标记为不克隆。'
                  : '当前统计没有明显风险，通常可以保持独立。'}
              </div>
              <TargetSelect
                value={target}
                options={speakerOptions.filter(option => option !== speaker.speaker_label)}
                onChange={value => setTargets(current => ({ ...current, [speaker.speaker_label]: value }))}
                onApply={() => onSave({
                  item_id: `speaker:${speaker.speaker_label}`,
                  item_type: 'speaker_profile',
                  decision: 'merge_speaker',
                  source_speaker_label: speaker.speaker_label,
                  target_speaker_label: target,
                  segment_ids: speaker.segment_ids,
                })}
                disabled={isSaving || !target}
                label="合并到"
              />
            </div>
          </section>
        )
      })}
    </div>
  )
}

function RunPanel({
  runs,
  speakerOptions,
  isSaving,
  onSave,
}: {
  runs: SpeakerReviewRun[]
  speakerOptions: string[]
  isSaving: boolean
  onSave: (payload: SpeakerReviewDecisionPayload) => void
}) {
  const [targets, setTargets] = useState<Record<string, string>>({})
  const riskyRuns = useMemo(
    () => runs.filter(run => run.risk_flags.length > 0).sort((a, b) => riskSort(a.risk_level, b.risk_level) || a.start - b.start),
    [runs],
  )

  if (riskyRuns.length === 0) {
    return <EmptyState title="没有短孤岛风险" description="当前没有发现需要优先处理的 speaker run。" />
  }

  return (
    <div className="space-y-4">
      {riskyRuns.map(run => {
        const target = targets[run.run_id] ?? ''
        return (
          <section key={run.run_id} className="rounded-xl border border-slate-200 bg-white">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
              <RunHeader run={run} />
              <div className="flex flex-wrap justify-end gap-2">
                <NeighborButton run={run} direction="previous" disabled={isSaving} onSave={onSave} />
                <NeighborButton run={run} direction="next" disabled={isSaving} onSave={onSave} />
                <ReviewActionButton
                  icon={Check}
                  label="保持"
                  disabled={isSaving}
                  active={run.decision?.decision === 'keep_independent'}
                  onClick={() => onSave(baseRunPayload(run, 'keep_independent'))}
                />
              </div>
            </div>
            <div className="grid gap-3 px-4 py-3.5 md:grid-cols-[minmax(0,1fr)_280px]">
              <div className="min-w-0">
                <div className="text-sm leading-6 text-slate-700">{run.text || '无文本'}</div>
                <RiskFlags flags={run.risk_flags} />
              </div>
              <TargetSelect
                value={target}
                options={speakerOptions.filter(option => option !== run.speaker_label)}
                onChange={value => setTargets(current => ({ ...current, [run.run_id]: value }))}
                onApply={() => onSave({
                  ...baseRunPayload(run, 'relabel'),
                  target_speaker_label: target,
                })}
                disabled={isSaving || !target}
                label="改为"
              />
            </div>
          </section>
        )
      })}
    </div>
  )
}

function SegmentPanel({
  segments,
  speakerOptions,
  isSaving,
  onSave,
}: {
  segments: SpeakerReviewSegment[]
  speakerOptions: string[]
  isSaving: boolean
  onSave: (payload: SpeakerReviewDecisionPayload) => void
}) {
  const [targets, setTargets] = useState<Record<string, string>>({})
  const riskySegments = useMemo(
    () => segments.filter(segment => segment.risk_flags.length > 0).sort((a, b) => riskSort(a.risk_level, b.risk_level) || a.start - b.start),
    [segments],
  )

  if (riskySegments.length === 0) {
    return <EmptyState title="没有片段级风险" description="当前没有发现长段、短句或边界风险。" />
  }

  return (
    <div className="space-y-3">
      {riskySegments.map(segment => {
        const target = targets[segment.segment_id] ?? ''
        return (
          <section key={segment.segment_id} className="rounded-xl border border-slate-200 bg-white px-4 py-3.5">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_460px]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-slate-900">{segment.segment_id}</span>
                  <StatusPill tone="slate">{segment.speaker_label}</StatusPill>
                  <RiskPill level={segment.risk_level} />
                  {segment.decision && <StatusPill tone="blue">已决策：{decisionLabel(segment.decision.decision)}</StatusPill>}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {formatSeconds(segment.start)} - {formatSeconds(segment.end)} · {formatSeconds(segment.duration)}
                </div>
                <div className="mt-2 text-sm leading-6 text-slate-700">{segment.text || '无文本'}</div>
                <RiskFlags flags={segment.risk_flags} />
              </div>
              <div className="space-y-2">
                <div className="flex flex-wrap justify-end gap-2">
                  <SegmentNeighborButton segment={segment} direction="previous" disabled={isSaving} onSave={onSave} />
                  <SegmentNeighborButton segment={segment} direction="next" disabled={isSaving} onSave={onSave} />
                  <ReviewActionButton
                    icon={Check}
                    label="保持"
                    disabled={isSaving}
                    active={segment.decision?.decision === 'keep_independent'}
                    onClick={() => onSave(baseSegmentPayload(segment, 'keep_independent'))}
                  />
                </div>
                <TargetSelect
                  value={target}
                  options={speakerOptions.filter(option => option !== segment.speaker_label)}
                  onChange={value => setTargets(current => ({ ...current, [segment.segment_id]: value }))}
                  onApply={() => onSave({
                    ...baseSegmentPayload(segment, 'relabel'),
                    target_speaker_label: target,
                  })}
                  disabled={isSaving || !target}
                  label="改为"
                />
              </div>
            </div>
          </section>
        )
      })}
    </div>
  )
}

function RunHeader({ run }: { run: SpeakerReviewRun }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <Route size={15} className="text-slate-400" />
        <h3 className="font-mono text-sm font-semibold text-slate-900">{run.run_id}</h3>
        <StatusPill tone="slate">{run.speaker_label}</StatusPill>
        <RiskPill level={run.risk_level} />
        {run.decision && <StatusPill tone="blue">已决策：{decisionLabel(run.decision.decision)}</StatusPill>}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>{formatSeconds(run.start)} - {formatSeconds(run.end)}</span>
        <span>片段 {run.segment_count}</span>
        <span>上一个 {run.previous_speaker_label ?? '-'}</span>
        <span>下一个 {run.next_speaker_label ?? '-'}</span>
      </div>
    </div>
  )
}

function NeighborButton({
  run,
  direction,
  disabled,
  onSave,
}: {
  run: SpeakerReviewRun
  direction: 'previous' | 'next'
  disabled: boolean
  onSave: (payload: SpeakerReviewDecisionPayload) => void
}) {
  const target = direction === 'previous' ? run.previous_speaker_label : run.next_speaker_label
  if (!target) {
    return null
  }
  const decision = direction === 'previous' ? 'relabel_to_previous_speaker' : 'relabel_to_next_speaker'
  return (
    <ReviewActionButton
      icon={GitMerge}
      label={direction === 'previous' ? `改为上一个 ${target}` : `改为下一个 ${target}`}
      disabled={disabled}
      active={run.decision?.decision === decision}
      onClick={() => onSave({
        ...baseRunPayload(run, decision),
        target_speaker_label: target,
      })}
    />
  )
}

function SegmentNeighborButton({
  segment,
  direction,
  disabled,
  onSave,
}: {
  segment: SpeakerReviewSegment
  direction: 'previous' | 'next'
  disabled: boolean
  onSave: (payload: SpeakerReviewDecisionPayload) => void
}) {
  const target = direction === 'previous' ? segment.previous_speaker_label : segment.next_speaker_label
  if (!target) {
    return null
  }
  const decision = direction === 'previous' ? 'relabel_to_previous_speaker' : 'relabel_to_next_speaker'
  return (
    <ReviewActionButton
      icon={GitMerge}
      label={direction === 'previous' ? `改为上一个 ${target}` : `改为下一个 ${target}`}
      disabled={disabled}
      active={segment.decision?.decision === decision}
      onClick={() => onSave({
        ...baseSegmentPayload(segment, decision),
        target_speaker_label: target,
      })}
    />
  )
}

function TargetSelect({
  value,
  options,
  label,
  disabled,
  onChange,
  onApply,
}: {
  value: string
  options: string[]
  label: string
  disabled: boolean
  onChange: (value: string) => void
  onApply: () => void
}) {
  return (
    <div className="flex items-center justify-end gap-2">
      <label className="text-xs font-medium text-slate-400">{label}</label>
      <select
        value={value}
        onChange={event => onChange(event.target.value)}
        className="min-w-36 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none transition-colors focus:border-blue-400"
      >
        <option value="">选择 speaker</option>
        {options.map(option => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
      <ReviewActionButton icon={SlidersHorizontal} label="应用" disabled={disabled} onClick={onApply} />
    </div>
  )
}

function baseRunPayload(run: SpeakerReviewRun, decision: string): SpeakerReviewDecisionPayload {
  return {
    item_id: run.run_id,
    item_type: 'speaker_run',
    decision,
    source_speaker_label: run.speaker_label,
    segment_ids: run.segment_ids,
    payload: {
      previous_speaker_label: run.previous_speaker_label,
      next_speaker_label: run.next_speaker_label,
      start: run.start,
      end: run.end,
    },
  }
}

function baseSegmentPayload(segment: SpeakerReviewSegment, decision: string): SpeakerReviewDecisionPayload {
  return {
    item_id: `segment:${segment.segment_id}`,
    item_type: 'segment',
    decision,
    source_speaker_label: segment.speaker_label,
    segment_ids: [segment.segment_id],
    payload: {
      previous_speaker_label: segment.previous_speaker_label,
      next_speaker_label: segment.next_speaker_label,
      start: segment.start,
      end: segment.end,
    },
  }
}

function ReviewActionButton({
  icon: Icon,
  label,
  active,
  disabled,
  onClick,
}: {
  icon: LucideIcon
  label: string
  active?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
        active
          ? 'border-blue-500 bg-blue-50 text-blue-700'
          : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800'
      }`}
    >
      <Icon size={13} />
      {label}
    </button>
  )
}

function ReviewStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-slate-800">{value}</div>
    </div>
  )
}

function RiskFlags({ flags }: { flags: string[] }) {
  if (flags.length === 0) {
    return <div className="mt-2 text-xs text-slate-400">无明显风险</div>
  }
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {flags.map(flag => <StatusPill key={flag} tone={riskFlagTone(flag)}>{riskFlagLabel(flag)}</StatusPill>)}
    </div>
  )
}

function RiskPill({ level }: { level: string }) {
  if (level === 'high') {
    return <StatusPill tone="rose">高风险</StatusPill>
  }
  if (level === 'medium') {
    return <StatusPill tone="amber">中风险</StatusPill>
  }
  return <StatusPill tone="emerald">低风险</StatusPill>
}

function StatusPill({ tone, children }: { tone: 'slate' | 'blue' | 'emerald' | 'amber' | 'rose'; children: ReactNode }) {
  const cls = {
    slate: 'border-slate-200 bg-slate-100 text-slate-600',
    blue: 'border-blue-200 bg-blue-50 text-blue-700',
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    rose: 'border-rose-200 bg-rose-50 text-rose-700',
  }[tone]
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  )
}

function Notice({
  icon: Icon,
  tone,
  spin,
  children,
}: {
  icon: LucideIcon
  tone: 'slate' | 'emerald' | 'rose'
  spin?: boolean
  children: ReactNode
}) {
  const cls = {
    slate: 'border-slate-200 bg-slate-50 text-slate-500',
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    rose: 'border-rose-200 bg-rose-50 text-rose-700',
  }[tone]
  return (
    <div className={`mb-4 flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${cls}`}>
      <Icon size={16} className={`mt-0.5 shrink-0 ${spin ? 'animate-spin' : ''}`} />
      <div>{children}</div>
    </div>
  )
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-5">
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-sm leading-6 text-slate-500">{description}</div>
    </div>
  )
}

function summarizeReview(review: SpeakerReviewResponse | undefined) {
  if (!review) {
    return { speakers: '-', highRiskSpeakers: '-', runs: '-', segments: '-', decisions: '-' }
  }
  return {
    speakers: String(review.summary.speaker_count),
    highRiskSpeakers: String(review.summary.high_risk_speaker_count),
    runs: `${review.summary.review_run_count ?? review.summary.high_risk_run_count}/${review.summary.speaker_run_count}`,
    segments: String(review.summary.review_segment_count),
    decisions: String(review.summary.decision_count),
  }
}

function riskSort(left: string, right: string): number {
  const order: Record<string, number> = { high: 0, medium: 1, low: 2 }
  return (order[left] ?? 3) - (order[right] ?? 3)
}

function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)}s`
}

function riskFlagTone(flag: string): 'slate' | 'blue' | 'emerald' | 'amber' | 'rose' {
  if (flag.includes('single') || flag.includes('very_long') || flag.includes('sandwiched')) {
    return 'rose'
  }
  if (flag.includes('low') || flag.includes('short') || flag.includes('boundary')) {
    return 'amber'
  }
  return 'slate'
}

function riskFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    single_segment_speaker: '单段 speaker',
    low_sample_speaker: '样本不足',
    mostly_short_segments: '短句偏多',
    sparse_long_timing: '长时间戳异常',
    no_reference_safe_segment: '无安全参考段',
    single_segment_run: '单段 run',
    short_run: '短 run',
    sandwiched_run: '夹心孤岛',
    rapid_turn_boundary: '快速切换边界',
    short_segment: '短句',
    long_timing_short_text: '长时长短文本',
    very_long_segment: '超长片段',
    speaker_boundary_risk: '边界风险',
    speaker_sample_risk: 'speaker 样本风险',
  }
  return labels[flag] ?? flag
}

function decisionLabel(value: string): string {
  switch (value) {
    case 'mark_non_cloneable':
      return '不克隆'
    case 'keep_independent':
      return '保持独立'
    case 'merge_speaker':
      return '合并 speaker'
    case 'relabel':
      return '改 speaker'
    case 'relabel_to_previous_speaker':
      return '改为上一个'
    case 'relabel_to_next_speaker':
      return '改为下一个'
    case 'merge_to_surrounding_speaker':
      return '合并到上下文'
    default:
      return value
  }
}

function FlowProgress() {
  const steps: Array<{ label: string; state: 'done' | 'current' | 'todo' }> = [
    { label: 'Task A', state: 'done' },
    { label: '说话人核对', state: 'current' },
    { label: 'Task B/C/D', state: 'todo' },
    { label: '专业配音编辑台', state: 'todo' },
    { label: '导出成品', state: 'todo' },
  ]
  return (
    <div data-testid="speaker-review-flow-progress" className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
      {steps.map((step, idx) => (
        <span key={step.label} className="flex items-center gap-1.5">
          <span
            className={
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-medium ' +
              (step.state === 'done'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : step.state === 'current'
                ? 'border-blue-200 bg-blue-50 text-blue-700 ring-1 ring-blue-200'
                : 'border-slate-200 bg-slate-50 text-slate-400')
            }
          >
            {step.state === 'done' && <Check size={10} />}
            {step.state === 'current' && <span className="text-[10px]">●</span>}
            {step.label}
          </span>
          {idx < steps.length - 1 && <span className="text-slate-300">›</span>}
        </span>
      ))}
    </div>
  )
}
