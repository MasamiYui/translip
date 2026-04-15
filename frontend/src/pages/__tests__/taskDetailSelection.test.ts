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
      id: 'stage1',
      label: 'Stage 1',
      status: 'pending',
      progress_percent: 0,
      required: true,
      group: 'audio-spine',
    },
    {
      id: 'task-a',
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
    expect(resolveActiveStageId(undefined, 'task-a', graph)).toBe('task-a')
  })

  it('falls back to the first workflow node when there is no current stage', () => {
    expect(resolveActiveStageId(undefined, null, graph)).toBe('stage1')
  })

  it('preserves an explicit close action instead of auto-selecting again', () => {
    expect(resolveActiveStageId(null, 'task-a', graph)).toBeNull()
  })

  it('uses the effective selection as the default rerun stage', () => {
    expect(resolveRerunStage(undefined, 'task-a', graph)).toBe('task-a')
  })
})
