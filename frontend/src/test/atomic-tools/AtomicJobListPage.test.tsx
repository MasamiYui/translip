import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import { AtomicJobListPage } from '../../pages/AtomicJobListPage'

const apiMocks = vi.hoisted(() => ({
  listJobs: vi.fn(),
  listTools: vi.fn(),
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
          <MemoryRouter>{children}</MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('AtomicJobListPage', () => {
  it('renders persisted atomic jobs as an independent task list', async () => {
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'probe',
        name_zh: '媒体信息探测',
        name_en: 'Media Probe',
        description_zh: '查看媒体参数',
        description_en: 'Inspect media info',
        category: 'video',
        icon: 'ScanSearch',
        accept_formats: ['.mp4'],
        max_file_size_mb: 2000,
        max_files: 1,
      },
    ])
    apiMocks.listJobs.mockResolvedValue({
      items: [
        {
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
          result: { format_name: 'mp4' },
          input_files: [{ file_id: 'file-1', filename: 'demo.mp4', size_bytes: 10, content_type: 'video/mp4' }],
          artifact_count: 1,
        },
      ],
      total: 1,
      page: 1,
      size: 20,
    })

    render(<AtomicJobListPage />, { wrapper: createWrapper() })

    expect(await screen.findByRole('heading', { name: '原子任务' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: /媒体信息探测/ })).toBeInTheDocument()
    expect(screen.getByText('demo.mp4')).toBeInTheDocument()
    expect(screen.getByText('共 1 条')).toBeInTheDocument()
  })

  it('uses the same top toolbar pattern as the pipeline task list', async () => {
    apiMocks.listTools.mockResolvedValue([])
    apiMocks.listJobs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 50,
    })

    render(<AtomicJobListPage />, { wrapper: createWrapper() })

    expect(await screen.findByRole('heading', { name: '原子任务' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('搜索 job、文件名或能力...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '全部' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行中' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '状态' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '运行中' }))

    await waitFor(() => expect(apiMocks.listJobs).toHaveBeenLastCalledWith({
      status: 'running',
      tool_id: undefined,
      search: undefined,
      size: 50,
    }))
  })
})
