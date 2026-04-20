import type { StageStatus, TaskConfig, TaskStage, WorkflowGraph, WorkflowGraphEdge, WorkflowGraphNode } from '../types'

type TemplateId = TaskConfig['template']

interface NodeDefinition {
  group: WorkflowGraphNode['group']
  dependencies: readonly string[]
  column: number
}

export const WORKFLOW_LANES: Array<{ id: WorkflowGraphNode['group']; columnCount: number }> = [
  { id: 'audio-spine', columnCount: 7 },
  { id: 'ocr-subtitles', columnCount: 7 },
  { id: 'video-cleanup', columnCount: 7 },
  { id: 'delivery', columnCount: 7 },
]

export const WORKFLOW_NODE_DEFINITIONS: Record<string, NodeDefinition> = {
  stage1: { group: 'audio-spine', dependencies: [], column: 1 },
  'ocr-detect': { group: 'ocr-subtitles', dependencies: [], column: 2 },
  'task-a': { group: 'audio-spine', dependencies: ['stage1'], column: 2 },
  'asr-ocr-correct': { group: 'audio-spine', dependencies: ['task-a', 'ocr-detect'], column: 3 },
  'task-b': { group: 'audio-spine', dependencies: ['task-a'], column: 4 },
  'task-c': { group: 'audio-spine', dependencies: ['task-b'], column: 5 },
  'ocr-translate': { group: 'ocr-subtitles', dependencies: ['ocr-detect'], column: 4 },
  'task-d': { group: 'audio-spine', dependencies: ['task-c'], column: 6 },
  'task-e': { group: 'audio-spine', dependencies: ['task-d'], column: 6 },
  'subtitle-erase': { group: 'video-cleanup', dependencies: ['ocr-detect'], column: 5 },
  'task-g': { group: 'delivery', dependencies: ['task-e', 'ocr-translate', 'subtitle-erase'], column: 7 },
}

const TEMPLATE_DEFINITIONS: Record<
  TemplateId,
  { nodeIds: readonly string[]; requiredIds: readonly string[]; dependencyOverrides?: Record<string, readonly string[]> }
> = {
  'asr-dub-basic': {
    nodeIds: ['stage1', 'task-a', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'],
    requiredIds: ['stage1', 'task-a', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'],
  },
  'asr-dub+ocr-subs': {
    nodeIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'ocr-translate', 'task-d', 'task-e', 'task-g'],
    requiredIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'ocr-translate', 'task-d', 'task-e', 'task-g'],
    dependencyOverrides: { 'task-b': ['asr-ocr-correct'] },
  },
  'asr-dub+ocr-subs+erase': {
    nodeIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'ocr-translate', 'task-d', 'task-e', 'subtitle-erase', 'task-g'],
    requiredIds: ['stage1', 'ocr-detect', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'],
    dependencyOverrides: { 'task-b': ['asr-ocr-correct'] },
  },
}

export function getWorkflowColumn(nodeId: string) {
  return WORKFLOW_NODE_DEFINITIONS[nodeId]?.column ?? 1
}

function edgeState(sourceStatus: StageStatus, targetStatus: StageStatus): WorkflowGraphEdge['state'] {
  const completedStatuses = new Set<StageStatus>(['succeeded', 'cached'])
  if (completedStatuses.has(sourceStatus) && targetStatus === 'running') {
    return 'active'
  }
  if (completedStatuses.has(sourceStatus) && ['succeeded', 'cached', 'failed', 'skipped'].includes(targetStatus)) {
    return 'completed'
  }
  if (targetStatus === 'failed') {
    return 'blocked'
  }
  return 'inactive'
}

function buildEdges(nodes: WorkflowGraphNode[], dependencyOverrides: Record<string, readonly string[]> = {}) {
  const nodeSet = new Set(nodes.map(node => node.id))
  const statusByNode = new Map(nodes.map(node => [node.id, node.status]))
  const edges: WorkflowGraphEdge[] = []

  for (const node of nodes) {
    const definition = WORKFLOW_NODE_DEFINITIONS[node.id]
    const dependencies = dependencyOverrides[node.id] ?? definition?.dependencies ?? []
    for (const dependency of dependencies) {
      if (!nodeSet.has(dependency)) {
        continue
      }
      edges.push({
        from: dependency,
        to: node.id,
        state: edgeState(
          statusByNode.get(dependency) ?? 'pending',
          statusByNode.get(node.id) ?? 'pending',
        ),
      })
    }
  }

  return edges
}

export function buildTemplatePreviewGraph(templateId: TemplateId): WorkflowGraph {
  const template = TEMPLATE_DEFINITIONS[templateId]
  const nodes = template.nodeIds.map(nodeId => ({
    id: nodeId,
    label: nodeId,
    group: WORKFLOW_NODE_DEFINITIONS[nodeId].group,
    required: template.requiredIds.includes(nodeId),
    status: 'pending' as const,
    progress_percent: 0,
  }))

  return {
    workflow: {
      template_id: templateId,
      status: 'pending',
    },
    nodes,
    edges: buildEdges(nodes, template.dependencyOverrides),
  }
}

export function normalizeWorkflowGraph(graph: WorkflowGraph): WorkflowGraph {
  const nodes = graph.nodes.filter(node => node.id in WORKFLOW_NODE_DEFINITIONS)

  return {
    workflow: graph.workflow,
    nodes,
    edges: buildEdges(nodes, TEMPLATE_DEFINITIONS[graph.workflow.template_id]?.dependencyOverrides),
  }
}

export function buildGraphFromStages(stages: TaskStage[], templateId: TemplateId = 'asr-dub-basic'): WorkflowGraph {
  const nodes = stages
    .filter(stage => stage.stage_name in WORKFLOW_NODE_DEFINITIONS)
    .map(stage => ({
      id: stage.stage_name,
      label: stage.stage_name,
      group: WORKFLOW_NODE_DEFINITIONS[stage.stage_name].group,
      required: TEMPLATE_DEFINITIONS[templateId].requiredIds.includes(stage.stage_name),
      status: stage.status,
      progress_percent: stage.progress_percent,
      current_step: stage.current_step,
      cache_hit: stage.cache_hit,
      elapsed_sec: stage.elapsed_sec,
      manifest_path: stage.manifest_path,
      error_message: stage.error_message,
    }))
    .sort((left, right) => getWorkflowColumn(left.id) - getWorkflowColumn(right.id))

  return {
    workflow: {
      template_id: templateId,
      status: nodes.some(node => node.status === 'running') ? 'running' : 'pending',
    },
    nodes,
    edges: buildEdges(nodes, TEMPLATE_DEFINITIONS[templateId]?.dependencyOverrides),
  }
}
