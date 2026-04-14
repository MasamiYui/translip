import { useState, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RotateCcw, Square, Trash2, Download, Eye } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { StatusBadge } from '../components/shared/StatusBadge'
import { ProgressBar } from '../components/shared/ProgressBar'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { formatDuration, formatDateTime, formatBytes, STAGE_LABELS } from '../lib/utils'
import { subscribeToProgress } from '../api/progress'
import type { Task, Artifact } from '../types'

const STAGES = Object.keys(STAGE_LABELS)

export function TaskDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [activeStage, setActiveStage] = useState<string | null>(null)
  const [rerunStage, setRerunStage] = useState('stage1')

  const { data: task, refetch } = useQuery({
    queryKey: ['task', id],
    queryFn: () => tasksApi.get(id!),
    refetchInterval: (query) => {
      const data = (query as any).state?.data as Task | undefined
      return data?.status === 'running' || data?.status === 'pending' ? 3000 : false
    },
  })

  const { data: artifactsData } = useQuery({
    queryKey: ['artifacts', id],
    queryFn: () => tasksApi.listArtifacts(id!),
    enabled: task?.status === 'succeeded',
  })

  useEffect(() => {
    if (!id || !task) return
    if (task.status !== 'running') return
    const unsub = subscribeToProgress(id, () => refetch())
    return unsub
  }, [id, task?.status])

  useEffect(() => {
    if (task?.current_stage && !activeStage) {
      setActiveStage(task.current_stage)
    }
  }, [task?.current_stage])

  const stopMutation = useMutation({
    mutationFn: () => tasksApi.stop(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['task', id] }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => tasksApi.delete(id!),
    onSuccess: () => navigate('/tasks'),
  })

  const rerunMutation = useMutation({
    mutationFn: () => tasksApi.rerun(id!, rerunStage),
    onSuccess: newTask => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/tasks/${newTask.id}`)
    },
  })

  if (!task) {
    return (
      <div className="py-20 text-center text-slate-400">
        <div className="text-lg">加载中...</div>
      </div>
    )
  }

  const elapsedSec = task.started_at
    ? task.elapsed_sec ?? (Date.now() - new Date(task.started_at).getTime()) / 1000
    : undefined

  const currentStageObj = activeStage
    ? task.stages.find(s => s.stage_name === activeStage)
    : null

  const artifacts: Artifact[] = artifactsData?.artifacts ?? []

  return (
    <div className="max-w-4xl space-y-5">
      {/* Header */}
      <div>
        <Link to="/tasks" className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-3 w-fit">
          <ArrowLeft size={14} />
          返回列表
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{task.name}</h1>
            <div className="text-sm text-slate-500 mt-1">{task.id}</div>
          </div>
          <StatusBadge status={task.status} />
        </div>
      </div>

      {/* Progress overview */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm text-slate-600">
            整体进度 · {task.status === 'running' ? `已运行 ${formatDuration(elapsedSec)}` : formatDuration(task.elapsed_sec)}
          </div>
          <span className="font-semibold text-slate-900">{task.overall_progress.toFixed(0)}%</span>
        </div>
        <ProgressBar value={task.overall_progress} size="lg"
          color={task.status === 'succeeded' ? 'bg-emerald-500' : task.status === 'failed' ? 'bg-red-500' : 'bg-blue-500'} />
        {task.current_stage && task.status === 'running' && (
          <div className="text-xs text-slate-400 mt-2">当前阶段: {STAGE_LABELS[task.current_stage] ?? task.current_stage}</div>
        )}
        {task.error_message && (
          <div className="mt-3 p-3 bg-red-50 rounded-xl text-sm text-red-700 border border-red-200">
            {task.error_message}
          </div>
        )}
      </div>

      {/* Pipeline graph */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">流水线进度</h2>
        <PipelineGraph
          stages={task.stages}
          activeStage={activeStage ?? task.current_stage ?? undefined}
          onStageClick={sn => setActiveStage(sn)}
        />
      </div>

      {/* Stage detail tabs */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <div className="flex overflow-x-auto border-b border-slate-100">
          {STAGES.map(sn => {
            const stage = task.stages.find(s => s.stage_name === sn)
            const isActive = activeStage === sn
            if (!stage) return null
            return (
              <button
                key={sn}
                onClick={() => setActiveStage(sn)}
                className={`px-4 py-3 text-sm font-medium whitespace-nowrap flex items-center gap-1.5 border-b-2 -mb-px transition-colors ${
                  isActive
                    ? 'border-blue-500 text-blue-700'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                {sn.toUpperCase().replace('-', ' ')}
                {stage.status === 'running' && (
                  <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                )}
              </button>
            )
          })}
        </div>

        <div className="p-5">
          {!activeStage || !currentStageObj ? (
            <div className="text-sm text-slate-400 text-center py-8">点击上方流水线节点查看详情</div>
          ) : (
            <StageDetail
              stage={currentStageObj}
              taskId={id!}
              artifacts={artifacts.filter(a => {
                const stagePrefix: Record<string, string[]> = {
                  'stage1': ['stage1', 'voice/', 'background/'],
                  'task-a': ['voice/task-a', 'voice/segments'],
                  'task-b': ['voice/task-b', 'voice/speaker'],
                  'task-c': ['voice/task-c', 'voice/translation'],
                  'task-d': ['voice/task-d'],
                  'task-e': ['voice/task-e'],
                  'task-g': ['delivery/'],
                }
                return (stagePrefix[currentStageObj.stage_name] ?? []).some(p => a.path.startsWith(p))
              })}
            />
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
        <h2 className="text-sm font-semibold text-slate-700 mb-4">操作</h2>
        <div className="flex flex-wrap gap-3 items-center">
          <div className="flex items-center gap-2">
            <select
              value={rerunStage}
              onChange={e => setRerunStage(e.target.value)}
              className="text-sm border border-slate-200 rounded-xl px-3 py-2 bg-white focus:outline-none"
            >
              {STAGES.map(s => (
                <option key={s} value={s}>{STAGE_LABELS[s]?.split(': ')[0] ?? s}</option>
              ))}
            </select>
            <button
              onClick={() => rerunMutation.mutate()}
              disabled={rerunMutation.isPending}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-xl hover:bg-blue-100 transition-colors"
            >
              <RotateCcw size={13} />
              从此阶段重跑
            </button>
          </div>

          {(task.status === 'running' || task.status === 'pending') && (
            <button
              onClick={() => stopMutation.mutate()}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-xl hover:bg-amber-100 transition-colors"
            >
              <Square size={13} />
              停止任务
            </button>
          )}

          <button
            onClick={() => {
              if (confirm('确定删除此任务？')) deleteMutation.mutate()
            }}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-xl hover:bg-red-100 transition-colors"
          >
            <Trash2 size={13} />
            删除
          </button>
        </div>
      </div>
    </div>
  )
}

function StageDetail({ stage, taskId, artifacts }: {
  stage: NonNullable<Task['stages'][number]>
  taskId: string
  artifacts: Artifact[]
}) {
  const [manifest, setManifest] = useState<unknown>(null)
  const [showManifest, setShowManifest] = useState(false)

  async function loadManifest() {
    try {
      const data = await tasksApi.getStageManifest(taskId, stage.stage_name)
      setManifest(data)
      setShowManifest(true)
    } catch {}
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-800">{STAGE_LABELS[stage.stage_name] ?? stage.stage_name}</h3>
        <StatusBadge status={stage.status} size="sm" />
      </div>

      <div className="grid grid-cols-3 gap-4 text-sm">
        <div>
          <div className="text-slate-500 mb-1">进度</div>
          <div className="flex items-center gap-2">
            <ProgressBar value={stage.progress_percent} className="flex-1" />
            <span className="font-medium">{stage.progress_percent.toFixed(0)}%</span>
          </div>
        </div>
        <div>
          <div className="text-slate-500 mb-1">耗时</div>
          <div className="font-medium">{formatDuration(stage.elapsed_sec)}</div>
        </div>
        <div>
          <div className="text-slate-500 mb-1">缓存</div>
          <div className="font-medium">{stage.cache_hit ? '命中' : '未命中'}</div>
        </div>
      </div>

      {stage.current_step && (
        <div className="text-sm text-slate-600 bg-slate-50 rounded-lg px-3 py-2">
          当前步骤: {stage.current_step}
        </div>
      )}

      {stage.error_message && (
        <div className="p-3 bg-red-50 rounded-xl text-sm text-red-700 border border-red-200">
          错误: {stage.error_message}
        </div>
      )}

      {artifacts.length > 0 && (
        <div>
          <div className="text-sm font-medium text-slate-700 mb-2">产物文件</div>
          <div className="space-y-1.5">
            {artifacts.map(a => (
              <div key={a.path} className="flex items-center justify-between p-2.5 bg-slate-50 rounded-lg text-sm">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-slate-400">📄</span>
                  <span className="text-slate-700 truncate">{a.path.split('/').pop()}</span>
                  <span className="text-slate-400 text-xs shrink-0">{formatBytes(a.size_bytes)}</span>
                </div>
                <div className="flex gap-2 shrink-0">
                  <a
                    href={`/api/tasks/${taskId}/artifacts/${a.path}`}
                    download
                    className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-500 hover:text-slate-700 transition-colors"
                    title="下载"
                  >
                    <Download size={13} />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {stage.status === 'succeeded' && (
        <div>
          <button
            onClick={loadManifest}
            className="text-sm text-blue-600 hover:underline flex items-center gap-1.5"
          >
            <Eye size={13} />
            查看 Manifest
          </button>
          {showManifest && manifest && (
            <div className="mt-3 p-4 bg-slate-900 rounded-xl text-xs font-mono text-slate-300 overflow-auto max-h-60">
              <pre>{JSON.stringify(manifest, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
