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

beforeEach(() => {
  cleanup()
  mockedUseQuery.mockReset()
  mockedUseQuery.mockImplementation((options: unknown) => {
    const queryKey = (options as { queryKey?: unknown[] }).queryKey ?? []
    if (queryKey[0] === 'atomic-tool-jobs') {
      return { data: [] } as never
    }
    return {
      data: {
        items: [],
        total: 0,
      },
    } as never
  })
})

describe('DashboardPage layout', () => {
  it('uses a wider page container for the dashboard overview', () => {
    const { container } = render(
      <I18nProvider>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </I18nProvider>,
    )

    expect(screen.getByRole('heading', { name: '仪表盘' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
  })

  it('renders running and completed task sections from pipeline data', () => {
    mockedUseQuery.mockImplementation((options: unknown) => {
      const queryKey = (options as { queryKey?: unknown[] }).queryKey ?? []
      if (queryKey[0] === 'atomic-tool-jobs') {
        return { data: [] } as never
      }
      return {
        data: {
          items: [
            {
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
            },
            {
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
            },
          ],
          total: 2,
        },
      } as never
    })

    render(
      <I18nProvider>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </I18nProvider>,
    )

    expect(screen.getByRole('link', { name: /任务-01:58/ })).toHaveAttribute('href', '/tasks/task-running')
    expect(screen.getByText('任务-已完成')).toBeInTheDocument()
  })

  it('shows recent atomic jobs without changing pipeline task totals', () => {
    mockedUseQuery.mockImplementation((options: unknown) => {
      const queryKey = (options as { queryKey?: unknown[] }).queryKey ?? []
      if (queryKey[0] === 'atomic-tool-jobs') {
        return {
          data: [
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
        } as never
      }
      return {
        data: {
          items: [],
          total: 0,
        },
      } as never
    })

    render(
      <I18nProvider>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </I18nProvider>,
    )

    expect(screen.getAllByText('总任务')[0]).toBeInTheDocument()
    expect(screen.getByText('最近原子任务')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /媒体信息探测/ })).toHaveAttribute(
      'href',
      '/tools/jobs/job-probe-1',
    )
    expect(screen.getByText('demo.mp4')).toBeInTheDocument()
  })
})
