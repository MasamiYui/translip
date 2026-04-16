import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { tasksApi } from '../../api/tasks'
import { I18nProvider } from '../../i18n/I18nProvider'
import { TaskDetailPage } from '../TaskDetailPage'

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    get: vi.fn(),
    getGraph: vi.fn(),
    listArtifacts: vi.fn(),
    stop: vi.fn(),
    delete: vi.fn(),
    rerun: vi.fn(),
    createSubtitlePreview: vi.fn(),
    composeDelivery: vi.fn(),
  },
}))

vi.mock('../../api/progress', () => ({
  subscribeToProgress: vi.fn(() => () => {}),
}))

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter initialEntries={['/tasks/task-1']}>
            <Routes>
              <Route path="/tasks/:id" element={children} />
            </Routes>
          </MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

describe('TaskDetailPage delivery composer', () => {
  it('renders composer controls and preview section', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-1',
      name: 'Demo task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      config: { template: 'asr-dub-basic', video_source: 'original', audio_source: 'both', subtitle_source: 'asr' },
      overall_progress: 100,
      current_stage: 'task-g',
      created_at: '2026-04-16T00:00:00Z',
      updated_at: '2026-04-16T00:00:00Z',
      stages: [{ stage_name: 'task-g', status: 'succeeded', progress_percent: 100, cache_hit: false }],
    } as never)

    vi.mocked(tasksApi.listArtifacts).mockResolvedValue({
      artifacts: [
        { path: 'ocr-translate/ocr_subtitles.en.srt', size_bytes: 100, suffix: '.srt' },
        { path: 'task-g/final-preview/final_preview.en.mp4', size_bytes: 5000, suffix: '.mp4' },
      ],
    } as never)

    vi.mocked(tasksApi.getGraph).mockResolvedValue({
      workflow: { template_id: 'asr-dub-basic', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    expect(await screen.findByText('Delivery Composer')).toBeInTheDocument()
    expect(screen.getByText('生成字幕预览')).toBeInTheDocument()
    expect(screen.getByText('生成成品视频')).toBeInTheDocument()
    expect(screen.getByText('预览与导出结果')).toBeInTheDocument()
  })
})
