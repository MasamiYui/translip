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
    <PageContainer className="max-w-6xl">
      {/* Back link */}
      <Link to="/tasks" className="mb-5 flex w-fit items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600">
        <ArrowLeft size={14} />
        {t.taskDetail.backToList}
      </Link>

      {/* Unified panel */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">

        {/* ── Title section ── */}
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{task.name}</h1>
              <div className="mt-1 font-mono text-xs text-slate-400">{task.id}</div>
            </div>
            <div className="flex items-center gap-2.5">
              <StatusBadge status={task.status} />
              <span className="border-l border-slate-200 pl-2.5 text-xs font-medium text-slate-400 uppercase tracking-widest">
                {t.workflow.templates[templateId]}
              </span>
            </div>
          </div>
        </div>

        {/* ── Progress + meta section ── */}
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="mb-4 flex items-baseline gap-3">
            <span className="text-4xl font-bold tabular-nums text-slate-900">
              {task.overall_progress.toFixed(0)}%
            </span>
            <span className="text-sm text-slate-400">{t.taskDetail.overallProgress}</span>
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
            <div className="mt-4 border-l-2 border-rose-400 bg-rose-50 py-2.5 pl-4 pr-4 text-sm text-rose-700">
              {task.error_message}
            </div>
          )}
          <div className="mt-5 flex flex-wrap gap-x-8 gap-y-3">
            <MetaItem
              label={t.workflow.runtimeTitle}
              value={
                task.status === 'running'
                  ? t.taskDetail.runningFor(formatDuration(elapsedSec))
                  : formatDuration(task.elapsed_sec)
              }
            />
            <MetaItem label={t.newTask.summary.direction} value={`${task.source_lang} → ${task.target_lang}`} />
            <MetaItem label={t.newTask.summary.template} value={t.workflow.templates[templateId]} />
            <MetaItem label={t.newTask.summary.deliveryPolicy} value={deliveryPolicy || t.common.notAvailable} />
            {task.current_stage && (
              <MetaItem
                label={t.taskDetail.currentStage('')}
                value={selectedNode ? getStageLabel(selectedNode.id as keyof typeof t.stages) : getStageLabel((task.current_stage) as keyof typeof t.stages)}
              />
            )}
          </div>
        </div>

        {/* ── Pipeline graph section ── */}
        <div className="border-b border-slate-100 px-7 py-5">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            <Sparkles size={12} />
            {t.workflow.runtimeTitle}
          </div>
          {graph ? (
            <PipelineGraph
              graph={graph}
              activeStage={activeStageId ?? undefined}
              onStageClick={nodeId => {
                setSelectedNodeId(nodeId)
                setRerunStage(nodeId)
              }}
              showLegend
            />
          ) : (
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
          )}
        </div>

        {/* ── Artifacts + Actions section ── */}
        <div className="grid sm:grid-cols-2 sm:divide-x divide-y sm:divide-y-0 divide-slate-100">
          {/* Delivery Artifacts */}
          <div className="px-7 py-5">
            <div className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
              Delivery Artifacts
            </div>
            {previewFiles.length === 0 ? (
              <div className="text-sm text-slate-400">{t.workflow.drawer.noArtifacts}</div>
            ) : (
              <div className="divide-y divide-slate-100">
                {previewFiles.map(artifact => (
                  <div key={artifact.path} className="flex items-center justify-between py-2.5 text-sm">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-700">{artifact.path.split('/').pop()}</div>
                      <div className="text-xs text-slate-400">{formatBytes(artifact.size_bytes)}</div>
                    </div>
                    <a
                      href={`/api/tasks/${task.id}/artifacts/${artifact.path}`}
                      download
                      className="ml-3 shrink-0 rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                    >
                      <Download size={14} />
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="px-7 py-5">
            <div className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
              {t.taskDetail.actions}
            </div>
            <div className="flex flex-wrap gap-2.5">
              <div className="flex items-center gap-2">
                <select
                  value={effectiveRerunStage}
                  onChange={event => setRerunStage(event.target.value)}
                  className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-300"
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
                  className="inline-flex items-center gap-1.5 rounded-md border border-sky-200 bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700 transition-colors hover:bg-sky-100 disabled:opacity-50"
                >
                  <RotateCcw size={13} />
                  {t.taskDetail.rerunFromStage}
                </button>
              </div>

              {(task.status === 'running' || task.status === 'pending') && (
                <button
                  onClick={() => stopMutation.mutate()}
                  className="inline-flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100"
                >
                  <Square size={13} />
                  {t.taskDetail.stopTask}
                </button>
              )}

              <button
                onClick={() => {
                  if (confirm(t.taskDetail.deleteConfirm)) deleteMutation.mutate()
                }}
                className="inline-flex items-center gap-1.5 rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-sm font-medium text-rose-700 transition-colors hover:bg-rose-100"
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

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-slate-700">{value}</div>
    </div>
  )
}
