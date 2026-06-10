import { describe, expect, it } from 'vitest'

import type { TaskListResponse } from '../../types'
import { diffFinishedTasks, notificationsRefetchInterval } from '../useTaskNotifications'

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

describe('notificationsRefetchInterval', () => {
  const makeQuery = (items: { status: string }[] | undefined) =>
    ({ state: { data: items ? ({ items } as TaskListResponse) : undefined } }) as {
      state: { data?: TaskListResponse }
    }

  it('returns false when there are no items yet (undefined data)', () => {
    expect(notificationsRefetchInterval(makeQuery(undefined))).toBe(false)
  })

  it('returns false when every task is terminal', () => {
    expect(
      notificationsRefetchInterval(
        makeQuery([{ status: 'succeeded' }, { status: 'failed' }, { status: 'interrupted' }]),
      ),
    ).toBe(false)
  })

  it('keeps polling at 5s while any task is running or pending', () => {
    expect(
      notificationsRefetchInterval(makeQuery([{ status: 'succeeded' }, { status: 'running' }])),
    ).toBe(5000)
    expect(notificationsRefetchInterval(makeQuery([{ status: 'pending' }]))).toBe(5000)
  })
})
