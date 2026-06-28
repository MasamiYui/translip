import { useQuery } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
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

function renderWith(items: ReturnType<typeof makeTask>[]) {
  mockedUseQuery.mockImplementation((options: unknown) => {
    const opts = options as { queryFn?: () => Promise<unknown> }
    if (opts.queryFn) void opts.queryFn()
    return {
      data: { items, total: items.length, page: 1, size: 20 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    } as never
  })
  return render(
    <I18nProvider>
      <MemoryRouter>
        <TaskListPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('TaskListPage language column', () => {
  beforeEach(() => {
    vi.mocked(tasksApi.list).mockClear()
  })
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders source → target for dubbing tasks (existing behavior preserved)', () => {
    renderWith([
      makeTask({
        id: 'task-dub-1',
        name: '我在迪拜等你0604',
        output_intent: 'dub_final',
        source_lang: 'zh',
        target_lang: 'en',
        config: { template: 'asr-dub-basic' },
      }),
    ])

    const cell = screen.getByTestId('task-language-dub')
    expect(cell.textContent).toContain('中文')
    expect(cell.textContent).toContain('英语')
    expect(cell.textContent).toContain('→')
    // 解说占位不应该出现
    expect(screen.queryByTestId('task-language-commentary')).toBeNull()
  })

  it('renders a single narration language (no arrow) for commentary tasks', () => {
    renderWith([
      makeTask({
        id: 'task-c-1',
        name: '解说预告0901',
        output_intent: 'commentary_recap',
        source_lang: 'zh',
        target_lang: 'en',
        config: {
          template: 'asr-commentary',
          commentary_narration_language: 'zh',
        },
      }),
    ])

    const cell = screen.getByTestId('task-language-commentary')
    expect(cell.textContent).toBe('中文')
    expect(cell.textContent).not.toContain('→')
    expect(cell.textContent).not.toContain('英语')
    // tooltip 提供解释
    expect(cell.getAttribute('title')).toContain('解说')
  })

  it('falls back to source_lang when commentary_narration_language is missing', () => {
    renderWith([
      makeTask({
        id: 'task-c-2',
        name: '解说-缺省语言',
        output_intent: 'commentary_recap',
        source_lang: 'zh',
        target_lang: 'en',
        // commentary_narration_language 缺省
        config: { template: 'asr-commentary' },
      }),
    ])

    const cell = screen.getByTestId('task-language-commentary')
    expect(cell.textContent).toBe('中文')
    expect(cell.textContent).not.toContain('英语')
  })
})
