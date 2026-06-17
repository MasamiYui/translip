import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import { AssistantRunListPage } from '../AssistantRunListPage'
import type { AssistantRunListResponse } from '../../types/assistant'

const apiMocks = vi.hoisted(() => ({ listRuns: vi.fn() }))

vi.mock('../../api/assistant', () => ({
  assistantApi: {
    listRuns: apiMocks.listRuns,
    rerunRun: vi.fn(),
    cancelRun: vi.fn(),
    deleteRun: vi.fn(),
  },
}))

const RUNS: AssistantRunListResponse = {
  total: 1,
  page: 1,
  size: 20,
  items: [
    {
      run_id: 'run-1',
      status: 'completed',
      message: '提取这个视频里的人声',
      summary: '先分离人声',
      tools: ['separation', 'mixing'],
      step_count: 2,
      completed_steps: 2,
      created_at: new Date().toISOString(),
      updated_at: null,
      finished_at: null,
      elapsed_sec: 12.3,
      error_message: null,
    },
  ],
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <AssistantRunListPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => apiMocks.listRuns.mockReset())
afterEach(cleanup)

describe('AssistantRunListPage', () => {
  it('renders run rows from the API', async () => {
    apiMocks.listRuns.mockResolvedValue(RUNS)
    renderPage()
    await waitFor(() => expect(screen.getByText('提取这个视频里的人声')).toBeInTheDocument())
    expect(screen.getByText('run-1')).toBeInTheDocument()
    expect(screen.getByText('2/2 步')).toBeInTheDocument()
  })

  it('shows the empty state when there are no runs', async () => {
    apiMocks.listRuns.mockResolvedValue({ total: 0, page: 1, size: 20, items: [] })
    renderPage()
    await waitFor(() => expect(screen.getByText(/还没有 AI 任务/)).toBeInTheDocument())
  })
})
