import { describe, expect, it, vi } from 'vitest'
import { atomicToolsApi } from '../atomic-tools'
import api from '../client'

vi.mock('../client', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: { ok: true } })),
  },
}))

describe('atomicToolsApi job endpoints', () => {
  it('lists atomic jobs with filters', async () => {
    await atomicToolsApi.listJobs({
      status: 'completed',
      tool_id: 'probe',
      search: 'demo',
      page: 2,
      size: 10,
    })

    expect(api.get).toHaveBeenCalledWith('/api/atomic-tools/jobs', {
      params: {
        status: 'completed',
        tool_id: 'probe',
        search: 'demo',
        page: 2,
        size: 10,
      },
    })
  })

  it('loads recent jobs for the dashboard', async () => {
    await atomicToolsApi.listRecentJobs(5)

    expect(api.get).toHaveBeenCalledWith('/api/atomic-tools/jobs/recent', {
      params: { limit: 5 },
    })
  })

  it('loads, deletes, and reruns an atomic job', async () => {
    await atomicToolsApi.getJobDetail('job-1')
    await atomicToolsApi.deleteJob('job-1', false)
    await atomicToolsApi.rerunJob('job-1')

    expect(api.get).toHaveBeenCalledWith('/api/atomic-tools/jobs/job-1')
    expect(api.delete).toHaveBeenCalledWith('/api/atomic-tools/jobs/job-1', {
      params: { delete_artifacts: false },
    })
    expect(api.post).toHaveBeenCalledWith('/api/atomic-tools/jobs/job-1/rerun')
  })
})
