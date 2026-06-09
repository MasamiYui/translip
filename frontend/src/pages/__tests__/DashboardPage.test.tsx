import { useQuery } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { APP_CONTENT_MAX_WIDTH } from '../../components/layout/PageContainer'
import { I18nProvider } from '../../i18n/I18nProvider'
import { DashboardPage } from '../DashboardPage'

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(() => ({
    data: {
      items: [],
      total: 0,
    },
  })),
}))

vi.mock('../../components/pipeline/PipelineGraph', () => ({
  PipelineGraph: () => <div data-testid="pipeline-graph" />,
}))

const mockedUseQuery = vi.mocked(useQuery)

/** Drive the two dashboard queries by their queryKey root. */
function mockQueries({
  tasks = { items: [] as unknown[], total: 0 },
  atomic = { items: [] as unknown[], total: 0 },
}: {
  tasks?: { items: unknown[]; total: number }
  atomic?: { items: unknown[]; total: number }
}) {
  mockedUseQuery.mockImplementation((options: unknown) => {
    const queryKey = (options as { queryKey?: unknown[] }).queryKey ?? []
    if (queryKey[0] === 'atomic-tool-jobs') {
      return { data: atomic } as never
    }
    return { data: tasks } as never
  })
}

function renderDashboard() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}

const runningTask = {
  id: 'task-running',
  name: '任务-01:58',
  source_lang: 'zh',
  target_lang: 'en',
  overall_progress: 1,
  status: 'running',
  config: { template: 'asr-dub-basic' },
  current_stage: 'stage1',
  stages: [],
  elapsed_sec: 90,
  created_at: '2026-04-16T00:00:00Z',
  updated_at: '2026-04-16T00:00:00Z',
}

const doneTask = {
  id: 'task-done',
  name: '任务-已完成',
  source_lang: 'zh',
  target_lang: 'en',
  overall_progress: 100,
  status: 'succeeded',
  config: { template: 'asr-dub-basic' },
  current_stage: 'task-g',
  stages: [],
  elapsed_sec: 180,
  created_at: '2026-04-16T00:00:00Z',
  updated_at: '2026-04-16T01:00:00Z',
  finished_at: '2026-04-16T01:00:00Z',
}

const completedJob = {
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
}

beforeEach(() => {
  cleanup()
  mockedUseQuery.mockReset()
  mockQueries({})
})

describe('DashboardPage layout', () => {
  it('uses a wider page container for the dashboard overview', () => {
    const { container } = renderDashboard()

    expect(screen.getByRole('heading', { name: '仪表盘' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
  })

  it('renders an active pipeline card and the recent activity feed', () => {
    mockQueries({ tasks: { items: [runningTask, doneTask], total: 2 } })

    renderDashboard()

    // Running task shows as an active card linking to its detail page.
    expect(screen.getByRole('link', { name: /任务-01:58/ })).toHaveAttribute('href', '/tasks/task-running')
    // Finished task moves into the unified recent-activity feed; both the
    // >=sm table and the <sm card list render the same link in jsdom.
    const doneLinks = screen.getAllByRole('link', { name: /任务-已完成/ })
    expect(doneLinks.length).toBeGreaterThan(0)
    doneLinks.forEach((link) => expect(link).toHaveAttribute('href', '/tasks/task-done'))
    expect(screen.getByText('最近任务')).toBeInTheDocument()
  })

  it('merges pipeline tasks and atomic jobs into the unified stats and feed', () => {
    mockQueries({
      tasks: { items: [doneTask], total: 1 },
      atomic: { items: [completedJob], total: 1 },
    })

    renderDashboard()

    // Total task stat counts both systems (1 pipeline + 1 atomic = 2).
    expect(screen.getByText('总任务').parentElement).toHaveTextContent('2')

    // Both kinds appear in the unified recent-activity feed (table + card list).
    expect(screen.getByText('最近任务')).toBeInTheDocument()
    const doneLinks = screen.getAllByRole('link', { name: /任务-已完成/ })
    expect(doneLinks.length).toBeGreaterThan(0)
    doneLinks.forEach((link) => expect(link).toHaveAttribute('href', '/tasks/task-done'))
    const probeLinks = screen.getAllByRole('link', { name: /媒体信息探测/ })
    expect(probeLinks.length).toBeGreaterThan(0)
    probeLinks.forEach((link) => expect(link).toHaveAttribute('href', '/tools/jobs/job-probe-1'))
    expect(screen.getAllByText('demo.mp4').length).toBeGreaterThan(0)
  })

  it('shows a running atomic job as an active card', () => {
    mockQueries({
      atomic: {
        items: [{ ...completedJob, job_id: 'job-running', status: 'running', progress_percent: 42, finished_at: null }],
        total: 1,
      },
    })

    renderDashboard()

    expect(screen.getAllByText('进行中').length).toBeGreaterThan(0)
    const links = screen.getAllByRole('link', { name: /媒体信息探测/ })
    expect(links.length).toBeGreaterThan(0)
    links.forEach((link) => expect(link).toHaveAttribute('href', '/tools/jobs/job-running'))
  })

  it('only shows the empty state when both pipeline and atomic lists are empty', () => {
    mockQueries({})

    renderDashboard()

    expect(screen.getByText('还没有任务')).toBeInTheDocument()
  })
})
