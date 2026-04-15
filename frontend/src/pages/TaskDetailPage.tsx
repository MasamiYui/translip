import { useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, RotateCcw, Sparkles, Square, Trash2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { PageContainer } from '../components/layout/PageContainer'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { WorkflowNodeDrawer } from '../components/workflow/WorkflowNodeDrawer'
import { useWorkflowGraph } from '../hooks/useWorkflowGraph'
import { useWorkflowRuntimeUpdates } from '../hooks/useWorkflowRuntimeUpdates'
import { formatBytes } from '../lib/utils'
import { subscribeToProgress } from '../api/progress'
import type { Artifact, Task, TaskConfig } from '../types'
import { useI18n } from '../i18n/useI18n'
import { resolveActiveStageId, resolveRerunStage } from './taskDetailSelection'

const ARTIFACT_PREFIX: Record<string, string[]> = {
  stage1: ['stage1/', 'voice/', 'background/'],
  'ocr-detect': ['ocr-detect/'],
  'task-a': ['task-a/voice/', 'task-a/'],
  'task-b': ['task-b/voice/', 'task-b/'],
  'task-c': ['task-c/voice/', 'task-c/'],
  'ocr-translate': ['ocr-translate/'],
  'task-d': ['task-d/'],
  'task-e': ['task-e/voice/', 'task-e/'],
  'subtitle-erase': ['subtitle-erase/'],
  'task-g': ['task-g/', 'delivery/'],
}

export function TaskDetailPage() {
  const { t, formatDuration, getStageLabel } = useI18n()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedNodeId, setSelectedNodeId] = useState<string | null | undefined>(undefined)
  const [rerunStage, setRerunStage] = useState<string | undefined>(undefined)

  const { data: task, refetch } = useQuery({
    queryKey: ['task', id],
    queryFn: () => tasksApi.get(id!),
    refetchInterval: (query) => {
      const data = query.state.data as Task | undefined
      return data?.status === 'running' || data?.status === 'pending' ? 3000 : false
    },
  })

  const templateId = normalizeTemplateId(task?.config.template)
  const { graph } = useWorkflowGraph(id ?? '', Boolean(id))
  useWorkflowRuntimeUpdates(id, task?.status === 'running')

  const { data: artifactsData } = useQuery({
    queryKey: ['artifacts', id],
    queryFn: () => tasksApi.listArtifacts(id!),
    enabled: Boolean(id),
    refetchInterval: task?.status === 'running' ? 4000 : false,
  })

  useEffect(() => {
    if (!id || !task) return
    if (task.status !== 'running') return
    const unsub = subscribeToProgress(id, event => {
      refetch()
      if (event.type === 'done') {
        queryClient.invalidateQueries({ queryKey: ['task-graph', id] })
        queryClient.invalidateQueries({ queryKey: ['artifacts', id] })
      }
    })
    return unsub
  }, [id, queryClient, refetch, task])

  const stopMutation = useMutation({
    mutationFn: () => tasksApi.stop(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', id] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => tasksApi.delete(id!),
    onSuccess: () => navigate('/tasks'),
  })

  const rerunMutation = useMutation({
    mutationFn: () => tasksApi.rerun(id!, effectiveRerunStage),
    onSuccess: newTask => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/tasks/${newTask.id}`)
    },
  })

  if (!task) {
    return (
      <PageContainer className="max-w-4xl py-20 text-center text-slate-400">
        <div className="text-lg">{t.taskDetail.loading}</div>
      </PageContainer>
    )
  }

  const elapsedSec = task.elapsed_sec
  const artifacts: Artifact[] = artifactsData?.artifacts ?? []
  const activeStageId = resolveActiveStageId(selectedNodeId, task.current_stage, graph)
  const effectiveRerunStage = resolveRerunStage(rerunStage, task.current_stage, graph)
  const selectedNode = graph?.nodes.find(node => node.id === activeStageId) ?? null
  const selectedStage = activeStageId
    ? task.stages.find(stage => stage.stage_name === activeStageId) ?? null
    : null
  const selectedArtifacts = selectedNode
    ? artifacts.filter(artifact => (ARTIFACT_PREFIX[selectedNode.id] ?? []).some(prefix => artifact.path.startsWith(prefix)))
    : []

  const deliveryPolicy = [
    task.config.video_source,
    task.config.audio_source,
    task.config.subtitle_source,
  ].filter(Boolean).join(' · ')

  const previewFiles = artifacts.filter(artifact => artifact.path.startsWith('task-g/') || artifact.path.startsWith('delivery/')).slice(0, 4)

  return (
    <PageContainer className="max-w-6xl space-y-6">
      <div>
        <Link to="/tasks" className="mb-3 flex w-fit items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600">
          <ArrowLeft size={14} />
          {t.taskDetail.backToList}
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">{task.name}</h1>
            <div className="mt-1 text-sm text-slate-500">{task.id}</div>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={task.status} />
            <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
              {t.workflow.templates[templateId]}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.55fr_0.85fr]">
        <div className="rounded-[30px] border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">
                {t.workflow.runtimeTitle}
              </div>
              <div className="mt-1 text-sm text-slate-500">
                {task.status === 'running'
                  ? t.taskDetail.runningFor(formatDuration(elapsedSec))
                  : formatDuration(task.elapsed_sec)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-semibold text-slate-900">{task.overall_progress.toFixed(0)}%</div>
              <div className="text-xs text-slate-400">{t.taskDetail.overallProgress}</div>
            </div>
          </div>

          <ProgressBar
            value={task.overall_progress}
            size="lg"
            color={
              task.status === 'succeeded'
                ? 'bg-emerald-500'
                : task.status === 'partial_success'
                  ? 'bg-amber-500'
                  : task.status === 'failed'
                    ? 'bg-rose-500'
                    : 'bg-sky-500'
            }
          />

          {task.error_message && (
            <div className="mt-4 rounded-[22px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {task.error_message}
            </div>
          )}

          {graph ? (
            <div className="mt-5">
              <PipelineGraph
                graph={graph}
                activeStage={activeStageId ?? undefined}
                onStageClick={nodeId => {
                  setSelectedNodeId(nodeId)
                  setRerunStage(nodeId)
                }}
                showLegend
              />
            </div>
          ) : (
            <div className="mt-5">
              <PipelineGraph
                stages={task.stages}
                templateId={templateId}
                activeStage={activeStageId ?? undefined}
                onStageClick={nodeId => {
                  setSelectedNodeId(nodeId)
                  setRerunStage(nodeId)
                }}
                showLegend
              />
            </div>
          )}
        </div>

        <div className="space-y-5">
          <div className="rounded-[30px] border border-slate-100 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              <Sparkles size={13} />
              Runtime Summary
            </div>
            <div className="mt-4 space-y-4 text-sm">
              <InfoRow label={t.newTask.summary.direction} value={`${task.source_lang} → ${task.target_lang}`} />
              <InfoRow label={t.newTask.summary.template} value={t.workflow.templates[templateId]} />
              <InfoRow label={t.newTask.summary.deliveryPolicy} value={deliveryPolicy || t.common.notAvailable} />
              <InfoRow
                label={t.taskDetail.currentStage(getStageLabel((task.current_stage ?? 'stage1') as keyof typeof t.stages))}
                value={selectedNode ? getStageLabel(selectedNode.id as keyof typeof t.stages) : t.workflow.emptySelection}
              />
            </div>
          </div>

          <div className="rounded-[30px] border border-slate-100 bg-white p-5 shadow-sm">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              Delivery Artifacts
            </div>
            {previewFiles.length === 0 ? (
              <div className="text-sm text-slate-400">{t.workflow.drawer.noArtifacts}</div>
            ) : (
              <div className="space-y-2">
                {previewFiles.map(artifact => (
                  <div key={artifact.path} className="flex items-center justify-between rounded-[20px] bg-slate-50 px-3 py-2 text-sm">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-700">{artifact.path.split('/').pop()}</div>
                      <div className="text-xs text-slate-400">{formatBytes(artifact.size_bytes)}</div>
                    </div>
                    <a
                      href={`/api/tasks/${task.id}/artifacts/${artifact.path}`}
                      download
                      className="rounded-2xl p-2 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-700"
                    >
                      <Download size={14} />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-[30px] border border-slate-100 bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold text-slate-700">{t.taskDetail.actions}</h2>
            <div className="flex flex-wrap gap-3">
              <div className="flex items-center gap-2">
                <select
                  value={effectiveRerunStage}
                  onChange={event => setRerunStage(event.target.value)}
                  className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none"
                >
                  {task.stages.map(stage => (
                    <option key={stage.stage_name} value={stage.stage_name}>
                      {getStageLabel(stage.stage_name as keyof typeof t.stages)}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => rerunMutation.mutate()}
                  disabled={rerunMutation.isPending}
                  className="inline-flex items-center gap-2 rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100"
                >
                  <RotateCcw size={13} />
                  {t.taskDetail.rerunFromStage}
                </button>
              </div>

              {(task.status === 'running' || task.status === 'pending') && (
                <button
                  onClick={() => stopMutation.mutate()}
                  className="inline-flex items-center gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100"
                >
                  <Square size={13} />
                  {t.taskDetail.stopTask}
                </button>
              )}

              <button
                onClick={() => {
                  if (confirm(t.taskDetail.deleteConfirm)) deleteMutation.mutate()
                }}
                className="inline-flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 transition-colors hover:bg-rose-100"
              >
                <Trash2 size={13} />
                {t.taskDetail.deleteTask}
              </button>
            </div>
          </div>
        </div>
      </div>

      <WorkflowNodeDrawer
        node={selectedNode}
        stage={selectedStage}
        artifacts={selectedArtifacts}
        taskId={task.id}
        onClose={() => setSelectedNodeId(null)}
      />
    </PageContainer>
  )
}

function normalizeTemplateId(value: unknown): TaskConfig['template'] {
  if (
    value === 'asr-dub-basic' ||
    value === 'asr-dub+ocr-subs' ||
    value === 'asr-dub+ocr-subs+erase'
  ) {
    return value
  }
  return 'asr-dub-basic'
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <span className="w-28 shrink-0 text-slate-400">{label}</span>
      <span className="font-medium text-slate-700">{value}</span>
    </div>
  )
}
