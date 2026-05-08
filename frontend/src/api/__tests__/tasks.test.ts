import { describe, expect, it, vi } from 'vitest'
import { tasksApi } from '../tasks'
import api from '../client'

vi.mock('../client', () => ({
  default: {
    delete: vi.fn(() => Promise.resolve({ data: { ok: true } })),
  },
}))

describe('tasksApi.delete', () => {
  it('deletes task artifacts by default', async () => {
    await tasksApi.delete('task-1')

    expect(api.delete).toHaveBeenCalledWith('/api/tasks/task-1', {
      params: { delete_artifacts: true },
    })
  })

  it('can preserve artifacts when explicitly requested', async () => {
    await tasksApi.delete('task-1', false)

    expect(api.delete).toHaveBeenCalledWith('/api/tasks/task-1', {
      params: { delete_artifacts: false },
    })
  })
})
