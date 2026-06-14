import { describe, expect, it } from 'vitest'
import type { WorkflowGraph } from '../../types'
import { mergeWorkflowProgressEvent } from '../useWorkflowRuntimeUpdates'

describe('mergeWorkflowProgressEvent', () => {
  it('updates matching nodes and keeps graph order stable', () => {
    const prev: WorkflowGraph = {
      workflow: { template_id: 'asr-dub+ocr-subs', status: 'running' },
      nodes: [
        {
          id: 'separation',
          label: 'Stage 1',
          group: 'audio-spine',
          required: true,
          status: 'succeeded',
          progress_percent: 100,
        },
        {
          id: 'ocr-detect',
          label: 'OCR Detect',
          group: 'ocr-subtitles',
          required: true,
          status: 'running',
          progress_percent: 25,
        },
      ],
      edges: [{ from: 'separation', to: 'ocr-detect', state: 'active' }],
    }

    const next = mergeWorkflowProgressEvent(prev, {
      type: 'progress',
      status: 'running',
      stages: [
        {
          stage_name: 'ocr-detect',
          status: 'running',
          progress_percent: 55,
          current_step: 'ocr step',
          cache_hit: false,
        },
      ],
    })

    expect(next.nodes.map(node => node.id)).toEqual(['separation', 'ocr-detect'])
    expect(next.nodes[1].progress_percent).toBe(55)
    expect(next.nodes[1].current_step).toBe('ocr step')
    expect(next.edges[0].state).toBe('active')
  })

  it('preserves completed upstream edges when a downstream node fails', () => {
    const prev: WorkflowGraph = {
      workflow: { template_id: 'asr-dub+ocr-subs+erase', status: 'running' },
      nodes: [
        {
          id: 'ocr-detect',
          label: 'OCR Detect',
          group: 'ocr-subtitles',
          required: true,
          status: 'succeeded',
          progress_percent: 100,
        },
        {
          id: 'subtitle-erase',
          label: 'Subtitle Erase',
          group: 'video-cleanup',
          required: false,
          status: 'running',
          progress_percent: 68,
        },
      ],
      edges: [{ from: 'ocr-detect', to: 'subtitle-erase', state: 'active' }],
    }

    const next = mergeWorkflowProgressEvent(prev, {
      type: 'progress',
      status: 'partial_success',
      stages: [
        {
          stage_name: 'subtitle-erase',
          status: 'failed',
          progress_percent: 68,
          current_step: 'frame context failed',
          cache_hit: false,
          error_message: 'IndexError',
        },
      ],
    })

    expect(next.workflow.status).toBe('partial_success')
    expect(next.nodes[1].status).toBe('failed')
    expect(next.nodes[1].error_message).toBe('IndexError')
    expect(next.edges[0].state).toBe('completed')
  })
})
