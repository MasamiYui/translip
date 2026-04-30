import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Ban,
  Check,
  GitMerge,
  Headphones,
  ListChecks,
  Loader2,
  RefreshCw,
  UserRound,
  Volume2,
  Wand2,
  X,
  type LucideIcon,
} from 'lucide-react'
import { tasksApi } from '../../api/tasks'
import type {
  DubbingReviewCharacter,
  DubbingReviewDecisionPayload,
  DubbingReviewMergeCandidate,
  DubbingReviewReferenceCandidate,
  DubbingReviewRepairItem,
  DubbingReviewResponse,
  DubbingReviewSpeaker,
} from '../../types'

type ReviewTab = 'quality' | 'reference' | 'merge' | 'repair'

const TAB_CONFIG: Array<{ id: ReviewTab; label: string; description: string }> = [
  { id: 'quality', label: '质量总览', description: '查看 Benchmark 与角色风险' },
  { id: 'reference', label: '音色审查', description: '为每个说话人选择 reference' },
  { id: 'merge', label: '短句合并', description: '确认同说话人合并边界' },
  { id: 'repair', label: '候选审听', description: '选择可用返修候选' },
]

export function DubbingReviewDrawer({
  taskId,
  isOpen,
  onClose,
}: {
  taskId: string
  isOpen: boolean
  onClose: () => void
}) {
  const [activeTab, setActiveTab] = useState<ReviewTab>('reference')
  const queryClient = useQueryClient()

  const reviewQuery = useQuery({
    queryKey: ['dubbing-review', taskId],
    queryFn: () => tasksApi.getDubbingReview(taskId),
    enabled: isOpen,
  })

  const decisionMutation = useMutation({
    mutationFn: (payload: DubbingReviewDecisionPayload) => tasksApi.saveDubbingReviewDecision(taskId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dubbing-review', taskId] })
    },
  })

  const review = reviewQuery.data
  const visibleStats = useMemo(() => summarizeReview(review), [review])

  if (!isOpen) {
    return null
  }

  function saveDecision(payload: DubbingReviewDecisionPayload) {
    decisionMutation.mutate(payload)
  }

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-30 bg-slate-950/25"
        onClick={onClose}
        aria-label="关闭配音返修审查"
      />
      <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-5xl flex-col border-l border-slate-200 bg-white">
        <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              <Headphones size={13} />
              配音返修
            </div>
            <h2 className="mt-2 text-xl font-semibold text-slate-900">配音返修审查</h2>
            <div className="mt-1 text-sm text-slate-500">
              只处理音色、短句合并和候选选择，决策会保存为任务产物供后续返修使用。
            </div>
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
          <div className="grid gap-3 md:grid-cols-4">
            <ReviewStat label="质量评分" value={visibleStats.quality} />
            <ReviewStat label="音色决策" value={visibleStats.reference} />
            <ReviewStat label="合并候选" value={visibleStats.merge} />
            <ReviewStat label="返修片段" value={visibleStats.repair} />
          </div>
        </div>

        <div className="border-b border-slate-100 px-6">
          <div className="flex gap-1 overflow-x-auto py-3">
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
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {reviewQuery.isLoading && (
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" />
              正在读取配音返修产物...
            </div>
          )}

          {reviewQuery.isError && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              配音返修数据读取失败，请确认任务产物是否完整。
            </div>
          )}

          {review && review.status === 'missing' && (
            <EmptyState
              title="当前还没有可审查的配音返修产物"
              description="需要先完成 Task D，并生成 repair_queue 或 reference_plan 后，这里才会显示音色、合并和候选数据。"
            />
          )}

          {review && review.status === 'available' && (
            <>
              {activeTab === 'quality' && <QualityOverviewPanel review={review} />}
              {activeTab === 'reference' && (
                <ReferenceReviewPanel
                  taskId={taskId}
                  speakers={review.speakers}
                  isSaving={decisionMutation.isPending}
                  onSave={saveDecision}
                />
              )}
              {activeTab === 'merge' && (
                <MergeReviewPanel
                  taskId={taskId}
                  candidates={review.merge_candidates}
                  isSaving={decisionMutation.isPending}
                  onSave={saveDecision}
                />
              )}
              {activeTab === 'repair' && (
                <RepairReviewPanel
                  taskId={taskId}
                  items={review.repair_items}
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

function QualityOverviewPanel({ review }: { review: DubbingReviewResponse }) {
  const benchmark = review.quality_benchmark
  const characters = review.characters ?? []
  if (!benchmark && characters.length === 0) {
    return <EmptyState title="没有质量 Benchmark" description="需要完成 Task E 后才会生成配音质量 Benchmark 和角色台账。" />
  }

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <ListChecks size={15} className="text-slate-400" />
              <h3 className="text-sm font-semibold text-slate-900">Benchmark</h3>
              {benchmark?.status && <StatusPill tone={qualityTone(benchmark.status)}>{benchmark.status}</StatusPill>}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              score {formatMetric(benchmark?.score)} · {benchmark?.reasons?.join(', ') || 'no blockers'}
            </div>
          </div>
        </div>
        <div className="grid gap-3 px-4 py-3.5 md:grid-cols-4">
          <ReviewStat label="覆盖率" value={formatMetric(benchmark?.metrics?.coverage_ratio)} />
          <ReviewStat label="无声字幕" value={String(asNumber(benchmark?.metrics?.audible_failed_count) ?? 0)} />
          <ReviewStat label="角色复核" value={String(asNumber(benchmark?.metrics?.character_review_count) ?? 0)} />
          <ReviewStat label="人工返修" value={String(asNumber(benchmark?.metrics?.repair_manual_required_count) ?? 0)} />
        </div>
        {benchmark?.gates && benchmark.gates.length > 0 && (
          <div className="divide-y divide-slate-100 border-t border-slate-100">
            {benchmark.gates.map((gate, index) => (
              <div key={String(gate['id'] ?? index)} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div>
                  <div className="text-sm font-medium text-slate-800">{String(gate['label'] ?? gate['id'] ?? 'gate')}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{String(gate['threshold'] ?? '')}</div>
                </div>
                <StatusPill tone={qualityTone(String(gate['status'] ?? 'unknown'))}>
                  {String(gate['status'] ?? 'unknown')}
                </StatusPill>
              </div>
            ))}
          </div>
        )}
      </section>

      <CharacterRiskPanel characters={characters} />
    </div>
  )
}

function CharacterRiskPanel({ characters }: { characters: DubbingReviewCharacter[] }) {
  if (characters.length === 0) {
    return <EmptyState title="没有角色台账" description="当前任务没有 Character Ledger 产物。" />
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-3.5">
        <div className="text-sm font-semibold text-slate-900">角色音色台账</div>
      </div>
      <div className="divide-y divide-slate-100">
        {characters.map(character => (
          <div key={character.character_id} className="grid gap-3 px-4 py-3.5 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <UserRound size={15} className="text-slate-400" />
                <span className="text-sm font-semibold text-slate-900">{character.display_name || character.character_id}</span>
                <StatusPill tone={qualityTone(character.review_status)}>{character.review_status}</StatusPill>
                <StatusPill tone="slate">{character.pitch_class ?? 'unknown'}</StatusPill>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {character.speaker_ids.join(', ') || 'unknown speaker'} · pitch {formatMetric(character.pitch_hz)}
              </div>
              {character.risk_flags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {character.risk_flags.map(flag => <StatusPill key={flag} tone="amber">{flag}</StatusPill>)}
                </div>
              )}
            </div>
            <MetricGrid
              metrics={[
                ['声纹失败率', formatMetric(character.stats.speaker_failed_ratio)],
                ['音色漂移', formatMetric(character.stats.voice_mismatch_count)],
              ]}
            />
          </div>
        ))}
      </div>
    </section>
  )
}

function ReferenceReviewPanel({
  taskId,
  speakers,
  isSaving,
  onSave,
}: {
  taskId: string
  speakers: DubbingReviewSpeaker[]
  isSaving: boolean
  onSave: (payload: DubbingReviewDecisionPayload) => void
}) {
  if (speakers.length === 0) {
    return <EmptyState title="没有说话人参考音频" description="当前任务没有 speaker_profiles 或 reference_plan。" />
  }

  return (
    <div className="space-y-4">
      {speakers.map(speaker => (
        <section key={speaker.speaker_id} className="rounded-xl border border-slate-200 bg-white">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <UserRound size={15} className="text-slate-400" />
                <h3 className="text-sm font-semibold text-slate-900">{speaker.display_name || speaker.speaker_id}</h3>
                <StatusPill tone={speaker.speaker_failed_count > 0 ? 'amber' : 'slate'}>
                  {speaker.speaker_id}
                </StatusPill>
                {speaker.decision && <StatusPill tone="blue">已选择：{decisionLabel(speaker.decision.decision)}</StatusPill>}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>语音 {formatSeconds(speaker.total_speech_sec)}</span>
                <span>片段 {speaker.segment_count}</span>
                <span>声纹失败 {speaker.speaker_failed_count}</span>
                <span>参考 {speaker.reference_clip_count}</span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <ReviewActionButton
                icon={Ban}
                label="不用克隆"
                disabled={isSaving}
                active={speaker.decision?.decision === 'use_base_voice'}
                onClick={() => onSave({
                  category: 'reference',
                  item_id: speaker.speaker_id,
                  decision: 'use_base_voice',
                  speaker_id: speaker.speaker_id,
                })}
              />
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {speaker.candidates.map(candidate => (
              <ReferenceCandidateRow
                key={`${speaker.speaker_id}-${candidate.path}`}
                taskId={taskId}
                speaker={speaker}
                candidate={candidate}
                isSaving={isSaving}
                onSave={onSave}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

function ReferenceCandidateRow({
  taskId,
  speaker,
  candidate,
  isSaving,
  onSave,
}: {
  taskId: string
  speaker: DubbingReviewSpeaker
  candidate: DubbingReviewReferenceCandidate
  isSaving: boolean
  onSave: (payload: DubbingReviewDecisionPayload) => void
}) {
  const selectedPath = speaker.decision?.reference_path
  const isSelected = selectedPath === candidate.path
  return (
    <div className="grid gap-3 px-4 py-3.5 lg:grid-cols-[minmax(0,1fr)_260px]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-semibold text-slate-700">{candidate.reference_id}</span>
          {candidate.is_current && <StatusPill tone="slate">当前</StatusPill>}
          {candidate.is_recommended && <StatusPill tone="emerald">推荐</StatusPill>}
          {candidate.source !== 'reference_plan' && <StatusPill tone="blue">{candidate.source}</StatusPill>}
          {isSelected && <StatusPill tone="blue">已选</StatusPill>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          <span>时长 {formatSeconds(candidate.duration_sec)}</span>
          <span>质量 {formatNumber(candidate.quality_score)}</span>
          <span>RMS {formatNumber(candidate.rms)}</span>
        </div>
        <div className="mt-2 truncate font-mono text-[11px] text-slate-400" title={candidate.path}>
          {candidate.path}
        </div>
        {candidate.text && (
          <div className="mt-2 max-h-12 overflow-hidden text-sm leading-6 text-slate-600">
            {candidate.text}
          </div>
        )}
      </div>
      <div className="space-y-2">
        <AudioPreview taskId={taskId} artifactPath={candidate.artifact_path} />
        <div className="flex flex-wrap justify-end gap-2">
          <ReviewActionButton
            icon={Check}
            label="使用"
            disabled={isSaving}
            active={isSelected}
            onClick={() => onSave({
              category: 'reference',
              item_id: speaker.speaker_id,
              decision: 'use_reference',
              speaker_id: speaker.speaker_id,
              reference_path: candidate.path,
              payload: {
                reference_id: candidate.reference_id,
                source: candidate.source,
                duration_sec: candidate.duration_sec,
              },
            })}
          />
          <ReviewActionButton
            icon={Ban}
            label="排除"
            disabled={isSaving}
            active={speaker.decision?.decision === 'reject_reference' && isSelected}
            onClick={() => onSave({
              category: 'reference',
              item_id: speaker.speaker_id,
              decision: 'reject_reference',
              speaker_id: speaker.speaker_id,
              reference_path: candidate.path,
              payload: { reference_id: candidate.reference_id },
            })}
          />
        </div>
      </div>
    </div>
  )
}

function MergeReviewPanel({
  taskId,
  candidates,
  isSaving,
  onSave,
}: {
  taskId: string
  candidates: DubbingReviewMergeCandidate[]
  isSaving: boolean
  onSave: (payload: DubbingReviewDecisionPayload) => void
}) {
  if (candidates.length === 0) {
    return (
      <EmptyState
        title="暂无短句合并候选"
        description="当前没有 merge_plan；系统也没有从 repair_queue 中找到可安全展示的同说话人相邻短句。"
      />
    )
  }

  return (
    <div className="space-y-4">
      {candidates.map(candidate => (
        <section key={candidate.group_id} className="rounded-xl border border-slate-200 bg-white">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <GitMerge size={15} className="text-slate-400" />
                <h3 className="font-mono text-sm font-semibold text-slate-900">{candidate.group_id}</h3>
                <StatusPill tone={candidate.source === 'merge_plan' ? 'blue' : 'slate'}>
                  {candidate.source === 'merge_plan' ? '计划产物' : '临时候选'}
                </StatusPill>
                {candidate.decision && <StatusPill tone="blue">已决策：{decisionLabel(candidate.decision.decision)}</StatusPill>}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {candidate.speaker_id ?? 'unknown speaker'} · {formatSeconds(candidate.anchor_start_sec)} - {formatSeconds(candidate.anchor_end_sec)}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <ReviewActionButton
                icon={Check}
                label="接受合并"
                disabled={isSaving}
                active={candidate.decision?.decision === 'accept_merge'}
                onClick={() => onSave({
                  category: 'merge',
                  item_id: candidate.group_id,
                  decision: 'accept_merge',
                  speaker_id: candidate.speaker_id,
                  payload: {
                    group_type: candidate.group_type,
                    source_segment_ids: candidate.source_segment_ids,
                  },
                })}
              />
              <ReviewActionButton
                icon={ListChecks}
                label="对话编组"
                disabled={isSaving}
                active={candidate.decision?.decision === 'dialogue_timing_group'}
                onClick={() => onSave({
                  category: 'merge',
                  item_id: candidate.group_id,
                  decision: 'dialogue_timing_group',
                  speaker_id: candidate.speaker_id,
                  payload: { source_segment_ids: candidate.source_segment_ids },
                })}
              />
              <ReviewActionButton
                icon={Ban}
                label="拒绝"
                disabled={isSaving}
                active={candidate.decision?.decision === 'reject_merge'}
                onClick={() => onSave({
                  category: 'merge',
                  item_id: candidate.group_id,
                  decision: 'reject_merge',
                  speaker_id: candidate.speaker_id,
                  payload: { source_segment_ids: candidate.source_segment_ids },
                })}
              />
            </div>
          </div>

          <div className="grid gap-4 px-4 py-3.5 lg:grid-cols-[minmax(0,1fr)_260px]">
            <div className="min-w-0 space-y-3">
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-slate-400">原始片段</div>
                <div className="mt-2 divide-y divide-slate-100 rounded-lg border border-slate-100">
                  {candidate.children.map(child => (
                    <div key={child.segment_id} className="grid gap-2 px-3 py-2 text-sm md:grid-cols-[96px_minmax(0,1fr)_minmax(0,1fr)]">
                      <span className="font-mono text-xs text-slate-500">{child.segment_id}</span>
                      <span className="text-slate-700">{child.source_text || '无原文'}</span>
                      <span className="text-slate-500">{child.target_text || '无译文'}</span>
                    </div>
                  ))}
                </div>
              </div>
              <TextPair label="建议合并原文" value={candidate.source_text} />
              <TextPair label="建议合并译文" value={candidate.target_text} />
            </div>
            <div className="space-y-3">
              <AudioPreview taskId={taskId} artifactPath={candidate.audio_artifact_path ?? null} />
              <MetricGrid
                metrics={[
                  ['片段数', String(candidate.source_segment_ids.length)],
                  ['总时长', formatSeconds(asNumber(candidate.metrics.combined_source_duration_sec))],
                ]}
              />
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                不同说话人只能做对话编组，不能合成一条 TTS。
              </div>
            </div>
          </div>
        </section>
      ))}
    </div>
  )
}

function RepairReviewPanel({
  taskId,
  items,
  isSaving,
  onSave,
}: {
  taskId: string
  items: DubbingReviewRepairItem[]
  isSaving: boolean
  onSave: (payload: DubbingReviewDecisionPayload) => void
}) {
  if (items.length === 0) {
    return <EmptyState title="没有返修片段" description="repair_queue 为空，当前没有需要人工选择的候选。" />
  }

  return (
    <div className="space-y-4">
      {items.map(item => (
        <section key={item.segment_id} className="rounded-xl border border-slate-200 bg-white">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3.5">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Wand2 size={15} className="text-slate-400" />
                <h3 className="font-mono text-sm font-semibold text-slate-900">{item.segment_id}</h3>
                <StatusPill tone={item.priority === 'high' ? 'rose' : item.priority === 'medium' ? 'amber' : 'slate'}>
                  {item.priority ?? 'unknown'}
                </StatusPill>
                {item.decision && <StatusPill tone="blue">已决策：{decisionLabel(item.decision.decision)}</StatusPill>}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {item.speaker_id ?? 'unknown speaker'} · {formatSeconds(item.anchor_start)} - {formatSeconds(item.anchor_end)}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <ReviewActionButton
                icon={RefreshCw}
                label="重生成"
                disabled={isSaving}
                active={item.decision?.decision === 'regenerate'}
                onClick={() => onSave({
                  category: 'repair',
                  item_id: item.segment_id,
                  decision: 'regenerate',
                  speaker_id: item.speaker_id,
                })}
              />
              <ReviewActionButton
                icon={Ban}
                label="人工返修"
                disabled={isSaving}
                active={item.decision?.decision === 'manual_review'}
                onClick={() => onSave({
                  category: 'repair',
                  item_id: item.segment_id,
                  decision: 'manual_review',
                  speaker_id: item.speaker_id,
                })}
              />
            </div>
          </div>

          <div className="grid gap-4 px-4 py-3.5 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0 space-y-3">
              <TextPair label="原文" value={item.source_text} />
              <TextPair label="当前译文" value={item.target_text} />
              <div className="flex flex-wrap gap-1.5">
                {item.failure_reasons.map(reason => <StatusPill key={reason} tone="rose">{reason}</StatusPill>)}
              </div>
              {item.rewrite_candidates.length > 0 && (
                <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                  改写候选：{item.rewrite_candidates.length} 个
                </div>
              )}
            </div>
            <div className="space-y-3">
              <AudioPreview taskId={taskId} artifactPath={item.audio_artifact_path ?? null} label="当前 TTS" />
              <MetricGrid
                metrics={[
                  ['源时长', formatSeconds(item.source_duration_sec)],
                  ['生成时长', formatSeconds(item.generated_duration_sec)],
                  ['时长比', formatMetric(item.metrics.duration_ratio)],
                  ['声纹', formatMetric(item.metrics.speaker_similarity)],
                  ['可懂度', formatMetric(item.metrics.text_similarity)],
                ]}
              />
            </div>
          </div>

          {item.attempts.length > 0 && (
            <div className="border-t border-slate-100 px-4 py-3.5">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">返修候选</div>
              <div className="space-y-2">
                {item.attempts.map(attempt => (
                  <div key={attempt.attempt_id} className="grid gap-3 rounded-lg border border-slate-100 px-3 py-3 lg:grid-cols-[minmax(0,1fr)_260px]">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold text-slate-700">{attempt.attempt_id}</span>
                        {attempt.status && <StatusPill tone={attempt.strict_accepted ? 'emerald' : 'slate'}>{attempt.status}</StatusPill>}
                        {item.decision?.attempt_id === attempt.attempt_id && <StatusPill tone="blue">已选</StatusPill>}
                      </div>
                      <div className="mt-1 text-sm text-slate-700">{attempt.target_text || item.target_text}</div>
                      <div className="mt-1 truncate font-mono text-[11px] text-slate-400">
                        {attempt.backend || 'unknown backend'}
                      </div>
                    </div>
                    <div className="space-y-2">
                      <AudioPreview taskId={taskId} artifactPath={attempt.audio_artifact_path ?? null} />
                      <div className="flex justify-end">
                        <ReviewActionButton
                          icon={Check}
                          label="选择"
                          disabled={isSaving}
                          active={item.decision?.attempt_id === attempt.attempt_id}
                          onClick={() => onSave({
                            category: 'repair',
                            item_id: item.segment_id,
                            decision: 'select_attempt',
                            speaker_id: item.speaker_id,
                            attempt_id: attempt.attempt_id,
                            payload: {
                              audio_path: attempt.audio_path,
                              target_text: attempt.target_text,
                              backend: attempt.backend,
                            },
                          })}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      ))}
    </div>
  )
}

function AudioPreview({
  taskId,
  artifactPath,
  label = '试听',
}: {
  taskId: string
  artifactPath: string | null
  label?: string
}) {
  if (!artifactPath) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-400">
        <Volume2 size={13} />
        暂无可播放音频
      </div>
    )
  }
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-slate-400">{label}</div>
      <audio
        controls
        preload="none"
        src={artifactPreviewHref(taskId, artifactPath)}
        className="h-9 w-full"
      />
    </div>
  )
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
      {disabled ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />}
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

function TextPair({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-sm leading-6 text-slate-700">{value || '无内容'}</div>
    </div>
  )
}

function MetricGrid({ metrics }: { metrics: Array<[string, string]> }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {metrics.map(([label, value]) => (
        <div key={label} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
          <div className="text-[11px] text-slate-400">{label}</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-700">{value}</div>
        </div>
      ))}
    </div>
  )
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

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-5">
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <div className="mt-1 text-sm leading-6 text-slate-500">{description}</div>
    </div>
  )
}

function summarizeReview(review: DubbingReviewResponse | undefined) {
  if (!review) {
    return { quality: '-', reference: '-', merge: '-', repair: '-' }
  }
  return {
    quality: review.summary.quality_score === null || review.summary.quality_score === undefined
      ? (review.summary.quality_status ?? '-')
      : `${review.summary.quality_score}`,
    reference: `${review.summary.reference_decision_count}/${review.summary.speaker_count}`,
    merge: `${review.summary.merge_decision_count}/${review.summary.merge_candidate_count}`,
    repair: `${review.summary.repair_decision_count}/${review.summary.repair_item_count}`,
  }
}

function artifactPreviewHref(taskId: string, artifactPath: string): string {
  const encodedPath = artifactPath.split('/').map(encodeURIComponent).join('/')
  return `/api/tasks/${taskId}/artifacts/${encodedPath}?preview=true`
}

function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)}s`
}

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return value.toFixed(3)
}

function formatMetric(value: unknown): string {
  const numberValue = asNumber(value)
  return numberValue === null ? '-' : formatNumber(numberValue)
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function qualityTone(value: string): 'slate' | 'blue' | 'emerald' | 'amber' | 'rose' {
  const normalized = value.toLowerCase()
  if (normalized.includes('blocked') || normalized === 'failed') {
    return 'rose'
  }
  if (normalized.includes('review')) {
    return 'amber'
  }
  if (normalized.includes('passed') || normalized.includes('deliverable')) {
    return 'emerald'
  }
  return 'slate'
}

function decisionLabel(value: string): string {
  switch (value) {
    case 'use_reference':
      return '使用参考'
    case 'reject_reference':
      return '排除参考'
    case 'use_base_voice':
      return '基础音色'
    case 'accept_merge':
      return '接受合并'
    case 'reject_merge':
      return '拒绝合并'
    case 'dialogue_timing_group':
      return '对话编组'
    case 'select_attempt':
      return '选择候选'
    case 'regenerate':
      return '重生成'
    case 'manual_review':
      return '人工返修'
    default:
      return value
  }
}
