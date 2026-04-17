import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
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

describe('TaskDetailPage export workflow', () => {
  it('shows export readiness instead of the inline delivery composer and opens the export drawer', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-1',
      name: 'Demo task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'english_subtitle',
      quality_preset: 'high_quality',
      config: { template: 'asr-dub+ocr-subs+erase', video_source: 'clean_if_available', audio_source: 'both', subtitle_source: 'both' },
      delivery_config: {
        subtitle_mode: 'english_only',
        subtitle_render_source: 'ocr',
        subtitle_font: 'Source Han Sans',
        subtitle_font_size: 36,
        subtitle_position: 'top',
        subtitle_margin_v: 18,
        subtitle_color: '#FFEEAA',
        subtitle_outline_color: '#111111',
        subtitle_outline_width: 3,
        subtitle_bold: true,
      },
      asset_summary: {
        video: {
          original: { status: 'available', path: '/tmp/demo.mp4' },
          clean: { status: 'available', path: 'subtitle-erase/clean_video.mp4' },
        },
        audio: {
          preview: { status: 'available', path: 'task-e/voice/preview_mix.en.wav' },
          dub: { status: 'available', path: 'task-e/voice/dub_voice.en.wav' },
        },
        subtitles: {
          ocr_translated: { status: 'available', path: 'ocr-translate/ocr_subtitles.en.srt' },
          asr_translated: { status: 'available', path: 'task-c/voice/translation.en.srt' },
        },
        exports: {
          subtitle_preview: { status: 'missing', path: null },
          final_preview: { status: 'missing', path: null },
          final_dub: { status: 'missing', path: null },
        },
      },
      export_readiness: {
        status: 'ready',
        recommended_profile: 'english_subtitle_burned',
        summary: 'ready_for_export',
        blockers: [],
      },
      last_export_summary: {
        status: 'not_exported',
        profile: null,
        updated_at: null,
        files: [],
      },
      overall_progress: 100,
      current_stage: 'task-g',
      created_at: '2026-04-16T00:00:00Z',
      updated_at: '2026-04-16T00:00:00Z',
      stages: [{ stage_name: 'task-g', status: 'succeeded', progress_percent: 100, cache_hit: false }],
    } as never)

    vi.mocked(tasksApi.listArtifacts).mockResolvedValue({ artifacts: [] } as never)
    vi.mocked(tasksApi.getGraph).mockResolvedValue({
      workflow: { template_id: 'asr-dub+ocr-subs+erase', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    expect(await screen.findByText('导出成品')).toBeInTheDocument()
    expect(screen.queryByText('Delivery Composer')).not.toBeInTheDocument()
    expect(screen.queryByText('节点详情')).not.toBeInTheDocument()
    expect(screen.getByText('当前素材已经满足推荐导出条件，可以直接生成成品视频。')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '导出成品' }))

    expect(await screen.findByText('1. 选择导出版本')).toBeInTheDocument()
    expect(screen.getByText('2. 确认素材来源')).toBeInTheDocument()
    expect(screen.getByText('3. 选择字幕样式')).toBeInTheDocument()
    expect(screen.getByText('4. 预览并导出')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Source Han Sans')).toBeInTheDocument()
  })

  it('surfaces blockers for tasks that still need more assets before export', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-2',
      name: 'Blocked task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'english_subtitle',
      quality_preset: 'standard',
      config: { template: 'asr-dub+ocr-subs+erase', video_source: 'clean_if_available', audio_source: 'both', subtitle_source: 'both' },
      delivery_config: {},
      asset_summary: {
        video: {
          original: { status: 'available', path: '/tmp/demo.mp4' },
          clean: { status: 'missing', path: null },
        },
        audio: {
          preview: { status: 'available', path: 'task-e/voice/preview_mix.en.wav' },
          dub: { status: 'available', path: 'task-e/voice/dub_voice.en.wav' },
        },
        subtitles: {
          ocr_translated: { status: 'available', path: 'ocr-translate/ocr_subtitles.en.srt' },
          asr_translated: { status: 'missing', path: null },
        },
        exports: {
          subtitle_preview: { status: 'missing', path: null },
          final_preview: { status: 'missing', path: null },
          final_dub: { status: 'missing', path: null },
        },
      },
      export_readiness: {
        status: 'blocked',
        recommended_profile: 'english_subtitle_burned',
        summary: 'missing_required_assets',
        blockers: [
          {
            code: 'missing_clean_video',
            message: '当前没有干净画面，无法导出英文字幕版。',
            action: 'rerun_subtitle_erase',
            action_label: '补跑擦字幕',
          },
        ],
      },
      last_export_summary: {
        status: 'not_exported',
        profile: null,
        updated_at: null,
        files: [],
      },
      overall_progress: 100,
      current_stage: 'task-g',
      created_at: '2026-04-16T00:00:00Z',
      updated_at: '2026-04-16T00:00:00Z',
      stages: [{ stage_name: 'task-g', status: 'succeeded', progress_percent: 100, cache_hit: false }],
    } as never)

    vi.mocked(tasksApi.listArtifacts).mockResolvedValue({ artifacts: [] } as never)
    vi.mocked(tasksApi.getGraph).mockResolvedValue({
      workflow: { template_id: 'asr-dub+ocr-subs+erase', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    expect(await screen.findByText('当前没有干净画面，无法导出英文字幕版。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '补跑擦字幕' })).toBeInTheDocument()
  })
})
