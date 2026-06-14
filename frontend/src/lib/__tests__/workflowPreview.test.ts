import { describe, expect, it } from 'vitest'
import type { WorkflowGraph } from '../../types'
import { buildTemplatePreviewGraph, normalizeWorkflowGraph } from '../workflowPreview'

describe('normalizeWorkflowGraph', () => {
  it('rebuilds runtime graphs with only canonical direct dependencies', () => {
    const dirtyGraph: WorkflowGraph = {
      workflow: { template_id: 'asr-dub-basic', status: 'running' },
      nodes: [
        { id: 'separation', label: 'Stage 1', group: 'audio-spine', required: true, status: 'failed', progress_percent: 16 },
        { id: 'transcription', label: 'Task A', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'speaker-registry', label: 'Task B', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'translation', label: 'Task C', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'synthesis', label: 'Task D', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'render', label: 'Task E', group: 'audio-spine', required: true, status: 'pending', progress_percent: 0 },
        { id: 'delivery', label: 'Task G', group: 'delivery', required: true, status: 'pending', progress_percent: 0 },
      ],
      edges: [
        { from: 'separation', to: 'transcription', state: 'inactive' },
        { from: 'separation', to: 'speaker-registry', state: 'inactive' },
        { from: 'transcription', to: 'translation', state: 'inactive' },
        { from: 'separation', to: 'render', state: 'inactive' },
        { from: 'transcription', to: 'delivery', state: 'inactive' },
      ],
    }

    const normalized = normalizeWorkflowGraph(dirtyGraph)

    expect(normalized.edges).toEqual([
      { from: 'separation', to: 'transcription', state: 'inactive' },
      { from: 'transcription', to: 'speaker-registry', state: 'inactive' },
      { from: 'speaker-registry', to: 'translation', state: 'inactive' },
      { from: 'translation', to: 'synthesis', state: 'inactive' },
      { from: 'synthesis', to: 'render', state: 'inactive' },
      { from: 'render', to: 'delivery', state: 'inactive' },
    ])
  })

  it('routes OCR templates through ASR OCR correction before speaker registration', () => {
    const graph = buildTemplatePreviewGraph('asr-dub+ocr-subs')

    expect(graph.nodes.map(node => node.id)).toContain('asr-ocr-correct')
    expect(graph.edges).toContainEqual({ from: 'transcription', to: 'asr-ocr-correct', state: 'inactive' })
    expect(graph.edges).toContainEqual({ from: 'ocr-detect', to: 'asr-ocr-correct', state: 'inactive' })
    expect(graph.edges).toContainEqual({ from: 'asr-ocr-correct', to: 'speaker-registry', state: 'inactive' })
    expect(graph.edges).not.toContainEqual({ from: 'transcription', to: 'speaker-registry', state: 'inactive' })
  })
})
