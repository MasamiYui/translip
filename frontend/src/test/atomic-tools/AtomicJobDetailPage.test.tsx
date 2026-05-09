import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import { AtomicJobDetailPage } from '../../pages/AtomicJobDetailPage'

const apiMocks = vi.hoisted(() => ({
  getJobDetail: vi.fn(),
  deleteJob: vi.fn(),
  rerunJob: vi.fn(),
}))

vi.mock('../../api/atomic-tools', () => ({
  atomicToolsApi: apiMocks,
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter initialEntries={['/tools/jobs/job-probe-1']}>{children}</MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('AtomicJobDetailPage', () => {
  it('shows persisted inputs, params, result, and artifacts for one atomic job', async () => {
    apiMocks.getJobDetail.mockResolvedValue({
      job_id: 'job-probe-1',
      tool_id: 'probe',
      tool_name: '媒体信息探测',
      status: 'completed',
      progress_percent: 100,
      current_step: 'completed',
      created_at: '2026-05-09T08:00:00Z',
      updated_at: '2026-05-09T08:00:05Z',
      started_at: '2026-05-09T08:00:01Z',
      finished_at: '2026-05-09T08:00:05Z',
      elapsed_sec: 4,
      error_message: null,
      params: { file_id: 'file-1' },
      result: { format_name: 'mp4' },
      input_files: [{ file_id: 'file-1', filename: 'demo.mp4', size_bytes: 10, content_type: 'video/mp4' }],
      artifact_count: 1,
      artifacts: [
        {
          filename: 'probe.json',
          size_bytes: 20,
          content_type: 'application/json',
          download_url: '/api/atomic-tools/probe/jobs/job-probe-1/artifacts/probe.json',
          file_id: 'artifact-1',
        },
      ],
    })

    render(
      <Routes>
        <Route path="/tools/jobs/:jobId" element={<AtomicJobDetailPage />} />
      </Routes>,
      { wrapper: createWrapper() },
    )

    expect(await screen.findByRole('heading', { name: '媒体信息探测' })).toBeInTheDocument()
    expect(screen.getByText('job-probe-1')).toBeInTheDocument()
    expect(screen.getByText('demo.mp4')).toBeInTheDocument()
    expect(screen.getByText('probe.json')).toBeInTheDocument()
    expect(screen.getByText(/format_name/)).toBeInTheDocument()
  })
})
