import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { tasksApi } from '../../../api/tasks'
import { cacheApi } from '../../../api/config'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { CacheSection } from '../CacheSection'

vi.mock('../../../api/config', () => ({
  cacheApi: {
    getBreakdown: vi.fn(),
    removeItem: vi.fn(),
    cleanup: vi.fn(),
    setDir: vi.fn(),
    resetDefault: vi.fn(),
    startMigrate: vi.fn(),
    pollMigrate: vi.fn(),
    cancelMigrate: vi.fn(),
  },
}))

vi.mock('../../../api/tasks', () => ({
  tasksApi: {
    list: vi.fn(),
    delete: vi.fn(),
  },
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
        <I18nProvider>{children}</I18nProvider>
      </QueryClientProvider>
    )
  }
}

function mockBreakdown() {
  vi.mocked(cacheApi.getBreakdown).mockResolvedValue({
    cache_dir: '/cache',
    huggingface_hub_dir: '/cache/hf',
    total_bytes: 300,
    items: [
      {
        key: 'pipeline_outputs',
        label: 'Pipeline Outputs',
        group: 'pipeline',
        bytes: 300,
        paths: ['/cache/output-pipeline'],
        removable: true,
        present: true,
      },
    ],
  })
}

function task(id: string, name: string, outputRoot: string, status = 'succeeded') {
  return {
    id,
    name,
    status,
    input_path: '/input.mp4',
    output_root: outputRoot,
    source_lang: 'zh',
    target_lang: 'en',
    output_intent: 'dub_final',
    quality_preset: 'standard',
    config: {},
    delivery_config: {},
    asset_summary: {},
    export_readiness: {},
    last_export_summary: {},
    overall_progress: 100,
    created_at: '2026-05-08T00:00:00Z',
    updated_at: '2026-05-08T00:00:00Z',
    stages: [],
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

describe('CacheSection pipeline cleanup', () => {
  it('integrates cache management controls into the cache size row', async () => {
    render(<CacheSection cacheSize="300 B" />, { wrapper: createWrapper() })

    const row = screen.getByTestId('cache-size-row')
    expect(row).toHaveTextContent('缓存大小')
    expect(row).toHaveTextContent('300 B')
    expect(row).not.toHaveTextContent('缓存管理')
    expect(screen.getByTestId('cache-toggle-details')).toBeInTheDocument()
    expect(screen.getByTestId('cache-cleanup')).toBeInTheDocument()
    expect(screen.getByTestId('cache-more-actions')).toBeInTheDocument()
    expect(screen.queryByTestId('cache-change-dir')).not.toBeInTheDocument()
    expect(screen.queryByTestId('cache-migrate')).not.toBeInTheDocument()
    expect(screen.queryByTestId('cache-reset-default')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('cache-more-actions'))

    expect(await screen.findByTestId('cache-actions-menu')).toBeInTheDocument()
    expect(screen.getByTestId('cache-change-dir')).toBeInTheDocument()
    expect(screen.getByTestId('cache-migrate')).toBeInTheDocument()
    expect(screen.getByTestId('cache-reset-default')).toBeInTheDocument()
  })

  it('opens a task selection dialog for Pipeline Outputs and deletes selected tasks with artifacts', async () => {
    mockBreakdown()
    vi.mocked(tasksApi.list).mockResolvedValue({
      items: [
        task('task-a', '任务 A', '/cache/output-pipeline/task-a'),
        task('task-b', '任务 B', '/cache/output-pipeline/task-b'),
        task('task-running', '运行中任务', '/cache/output-pipeline/task-running', 'running'),
        task('task-outside', '其他任务', '/other/output/task-outside'),
      ],
      total: 3,
      page: 1,
      size: 100,
    } as never)
    vi.mocked(tasksApi.delete).mockResolvedValue({ ok: true } as never)
    vi.mocked(cacheApi.removeItem).mockResolvedValue({ ok: true, key: 'pipeline_outputs', freed_bytes: 300 })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<CacheSection cacheSize="300 B" />, { wrapper: createWrapper() })

    fireEvent.click(screen.getByTestId('cache-toggle-details'))
    await screen.findByTestId('cache-item-pipeline_outputs')

    fireEvent.click(screen.getByTestId('cache-item-clean-pipeline_outputs'))

    const dialog = await screen.findByTestId('cache-pipeline-tasks-dialog')
    expect(dialog).toHaveTextContent('选择要删除的任务')
    await screen.findByText('任务 A')
    expect(dialog).toHaveTextContent('任务 B')
    expect(dialog).toHaveTextContent('运行中任务')
    expect(dialog).not.toHaveTextContent('其他任务')
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(screen.getByTestId('cache-pipeline-task-checkbox-task-running')).toBeDisabled()

    fireEvent.click(screen.getByTestId('cache-pipeline-task-checkbox-task-b'))
    fireEvent.click(screen.getByTestId('cache-pipeline-tasks-submit'))

    await waitFor(() => {
      expect(tasksApi.delete).toHaveBeenCalledWith('task-a', true)
    })
    expect(tasksApi.delete).toHaveBeenCalledTimes(1)
    expect(tasksApi.delete).not.toHaveBeenCalledWith('task-running', true)
    expect(cacheApi.removeItem).not.toHaveBeenCalled()
  })
})
