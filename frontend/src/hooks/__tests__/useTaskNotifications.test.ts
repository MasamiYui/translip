import { describe, expect, it } from 'vitest'

import { diffFinishedTasks } from '../useTaskNotifications'

describe('diffFinishedTasks', () => {
  it('returns only tasks that transitioned from active to terminal', () => {
    const prev = new Map<string, string>([
      ['a', 'running'],
      ['b', 'succeeded'],
      ['c', 'pending'],
      ['e', 'running'],
    ])
    const items = [
      { id: 'a', name: 'A', status: 'succeeded' }, // running -> succeeded ✓
      { id: 'b', name: 'B', status: 'succeeded' }, // already terminal ✗
      { id: 'c', name: 'C', status: 'running' }, // pending -> running ✗
      { id: 'd', name: 'D', status: 'failed' }, // unknown before ✗
      { id: 'e', name: 'E', status: 'failed' }, // running -> failed ✓
    ]

    expect(diffFinishedTasks(prev, items)).toEqual([
      { name: 'A', status: 'succeeded' },
      { name: 'E', status: 'failed' },
    ])
  })

  it('treats interrupted as a terminal status', () => {
    const prev = new Map<string, string>([['a', 'running']])
    expect(diffFinishedTasks(prev, [{ id: 'a', name: 'A', status: 'interrupted' }])).toEqual([
      { name: 'A', status: 'interrupted' },
    ])
  })
})
