import { useQuery } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import { TaskListPage } from '../TaskListPage'
import { tasksApi } from '../../api/tasks'

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>(
    '@tanstack/react-query',
  )
  return {
    ...actual,
    useQuery: vi.fn(),
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
  }
})

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    list: vi.fn(() => Promise.resolve({ items: [], total: 0, page: 1, size: 20 })),
    delete: vi.fn(),
  },
}))

const mockedUseQuery = vi.mocked(useQuery)
const mockedListApi = vi.mocked(tasksApi.list)

function makeTask(overrides: Partial<Record<string, unknown>>) {
  return {
    id: 'task-x',
    name: 'task-x-name',
    status: 'succeeded',
    input_path: '/a.mp4',
    output_root: '/out',
    source_lang: 'zh',
    target_lang: 'en',
    output_intent: 'dub_final',
    quality_preset: 'standard',
    config: {},
    delivery_config: {},
    asset_summary: {},
    export_readiness: { status: 'not_ready', recommended_profile: 'dub_no_subtitles', summary: '', blockers: [] },
    last_export_summary: { status: 'not_exported', profile: null, files: [] },
    overall_progress: 100,
    created_at: '2026-06-26T00:00:00Z',
    updated_at: '2026-06-26T00:00:00Z',
    stages: [],
    ...overrides,
  }
}

function renderPage() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <TaskListPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('TaskListPage intent filter', () => {
  beforeEach(() => {
    mockedListApi.mockClear()
    mockedUseQuery.mockImplementation((options: unknown) => {
      const opts = options as { queryFn: () => Promise<unknown>; queryKey: unknown[] }
      // Drive a real call into tasksApi.list so we can assert the params that
      // are sent for the current tab.
      void opts.queryFn()
      const intent = opts.queryKey[2] as string
      const items =
        intent === 'commentary'
          ? [
              makeTask({
                id: 'task-c-1',
                name: '解说预告0901',
                output_intent: 'commentary_recap',
              }),
            ]
          : intent === 'dub'
            ? [
                makeTask({ id: 'task-d-1', name: '任务-12:10', output_intent: 'dub_final' }),
                makeTask({
                  id: 'task-d-2',
                  name: '哪吒预告片0602',
                  output_intent: 'english_subtitle',
                }),
              ]
            : [
                makeTask({ id: 'task-d-1', name: '任务-12:10', output_intent: 'dub_final' }),
                makeTask({
                  id: 'task-c-1',
                  name: '解说预告0901',
                  output_intent: 'commentary_recap',
                }),
              ]
      return {
        data: { items, total: items.length, page: 1, size: 20 },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      } as never
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('defaults to the all-intent tab and renders both badge kinds', () => {
    renderPage()

    const allTab = screen.getByTestId('intent-tab-all')
    expect(allTab.getAttribute('aria-selected')).toBe('true')

    expect(screen.getByText('任务-12:10')).toBeTruthy()
    expect(screen.getByText('解说预告0901')).toBeTruthy()

    // Default render contains one of each badge type.
    expect(screen.getAllByTestId('intent-badge-dub').length).toBe(1)
    expect(screen.getAllByTestId('intent-badge-commentary').length).toBe(1)

    // Default request should not include the intent param.
    const lastCallParams = (mockedListApi.mock.calls as unknown as Array<[Record<string, unknown>]>)[0]?.[0]
    expect(lastCallParams?.intent).toBeUndefined()
  })

  it('switches to the commentary tab and requests intent=commentary', () => {
    renderPage()

    fireEvent.click(screen.getByTestId('intent-tab-commentary'))

    const commentaryTab = screen.getByTestId('intent-tab-commentary')
    expect(commentaryTab.getAttribute('aria-selected')).toBe('true')

    // The last list call (after the click) should carry intent=commentary.
    const calls = mockedListApi.mock.calls as unknown as Array<[Record<string, unknown>]>
    const lastParams = calls[calls.length - 1]?.[0]
    expect(lastParams?.intent).toBe('commentary')

    // Only commentary rows are rendered and they get the violet badge.
    expect(screen.queryByText('任务-12:10')).toBeNull()
    expect(screen.getByText('解说预告0901')).toBeTruthy()
    const badges = screen.getAllByTestId('intent-badge-commentary')
    expect(badges.length).toBe(1)
    expect(within(badges[0]).getByText('解说')).toBeTruthy()
  })

  it('switches to the dubbing tab and requests intent=dub', () => {
    renderPage()

    fireEvent.click(screen.getByTestId('intent-tab-dub'))

    const calls = mockedListApi.mock.calls as unknown as Array<[Record<string, unknown>]>
    const lastParams = calls[calls.length - 1]?.[0]
    expect(lastParams?.intent).toBe('dub')

    expect(screen.queryByText('解说预告0901')).toBeNull()
    expect(screen.getByText('任务-12:10')).toBeTruthy()
    expect(screen.getByText('哪吒预告片0602')).toBeTruthy()
    const badges = screen.getAllByTestId('intent-badge-dub')
    expect(badges.length).toBe(2)
    expect(within(badges[0]).getByText('配音')).toBeTruthy()
  })
})
