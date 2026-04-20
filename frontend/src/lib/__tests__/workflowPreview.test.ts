import { describe, expect, it } from 'vitest'
import type { WorkflowGraph } from '../../types'
import { buildTemplatePreviewGraph, normalizeWorkflowGraph } from '../workflowPreview'

describe('normalizeWorkflowGraph', () => {
  it('rebuilds runtime graphs with only canonical direct dependencies', () => {
    const dirtyGraph: WorkflowGraph = {
      workflow: { template_id: 'asr-dub-basic', status: 'running' },
      nodes: [
        { id: 'stage1', label: 'Stage 1', group: 'audio-spine', required: true, status: 'failed', progress_percent: 16 },
        { id: 'task-a', label: 'Task A', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'task-b', label: 'Task B', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'task-c', label: 'Task C', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'task-d', label: 'Task D', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'task-e', label: 'Task E', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'pending', progress_percent: 0 },
      ],
      edges: [
        { from: 'stage1', to: 'task-a', state: 'inactive' },
        { from: 'stage1', to: 'task-b', state: 'inactive' },
        { from: 'task-a', to: 'task-c', state: 'inactive' },
        { from: 'stage1', to: 'task-e', state: 'inactive' },
        { from: 'task-a', to: 'task-g', state: 'inactive' },
      ],
    }

    const normalized = normalizeWorkflowGraph(dirtyGraph)

    expect(normalized.edges).toEqual([
      { from: 'stage1', to: 'task-a', state: 'inactive' },
      { from: 'task-a', to: 'task-b', state: 'inactive' },
      { from: 'task-b', to: 'task-c', state: 'inactive' },
      { from: 'task-c', to: 'task-d', state: 'inactive' },
      { from: 'task-d', to: 'task-e', state: 'inactive' },
      { from: 'task-e', to: 'task-g', state: 'inactive' },
    ])
  })

  it('routes OCR templates through ASR OCR correction before speaker registration', () => {
    const graph = buildTemplatePreviewGraph('asr-dub+ocr-subs')

    expect(graph.nodes.map(node => node.id)).toContain('asr-ocr-correct')
    expect(graph.edges).toContainEqual({ from: 'task-a', to: 'asr-ocr-correct', state: 'inactive' })
    expect(graph.edges).toContainEqual({ from: 'ocr-detect', to: 'asr-ocr-correct', state: 'inactive' })
    expect(graph.edges).toContainEqual({ from: 'asr-ocr-correct', to: 'task-b', state: 'inactive' })
    expect(graph.edges).not.toContainEqual({ from: 'task-a', to: 'task-b', state: 'inactive' })
  })
})
