import { describe, expect, it } from 'vitest'
import { resolveActiveStageId, resolveRerunStage } from '../taskDetailSelection'
import type { WorkflowGraph } from '../../types'

const graph: WorkflowGraph = {
  workflow: {
    template_id: 'asr-dub-basic',
    status: 'pending',
  },
  nodes: [
    {
      id: 'separation',
      label: 'Stage 1',
      status: 'pending',
      progress_percent: 0,
      required: true,
      group: 'audio-spine',
    },
    {
      id: 'transcription',
      label: 'Task A',
      status: 'pending',
      progress_percent: 0,
      required: true,
      group: 'audio-spine',
    },
  ],
  edges: [],
}

describe('task detail selection helpers', () => {
  it('defaults to the current task stage when the user has not made a selection', () => {
    expect(resolveActiveStageId(undefined, 'transcription', graph)).toBe('transcription')
  })

  it('falls back to the first workflow node when there is no current stage', () => {
    expect(resolveActiveStageId(undefined, null, graph)).toBe('separation')
  })

  it('preserves an explicit close action instead of auto-selecting again', () => {
    expect(resolveActiveStageId(null, 'transcription', graph)).toBeNull()
  })

  it('uses the effective selection as the default rerun stage', () => {
    expect(resolveRerunStage(undefined, 'transcription', graph)).toBe('transcription')
  })
})
