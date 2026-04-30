import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
    getDubbingReview: vi.fn(),
    saveDubbingReviewDecision: vi.fn(),
    getSpeakerReview: vi.fn(),
    saveSpeakerReviewDecision: vi.fn(),
    applySpeakerReviewDecisions: vi.fn(),
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

function mockTask(id: string) {
  return {
    id,
    name: 'Demo task',
    status: 'succeeded',
    input_path: '/tmp/demo.mp4',
    output_root: '/tmp/output',
    source_lang: 'zh',
    target_lang: 'en',
    output_intent: 'dub_final',
    quality_preset: 'standard',
    config: { template: 'asr-dub-basic', video_source: 'original', audio_source: 'both', subtitle_source: 'asr' },
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
        ocr_translated: { status: 'missing', path: null },
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
      recommended_profile: 'dub_no_subtitles',
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
  }
}

describe('TaskDetailPage export workflow', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('opens speaker review drawer and saves speaker decisions', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue(mockTask('task-speaker') as never)
    vi.mocked(tasksApi.listArtifacts).mockResolvedValue({ artifacts: [] } as never)
    vi.mocked(tasksApi.getGraph).mockResolvedValue({
      workflow: { template_id: 'asr-dub-basic', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)
    vi.mocked(tasksApi.getSpeakerReview).mockResolvedValue({
      task_id: 'task-speaker',
      status: 'available',
      summary: {
        segment_count: 4,
        speaker_count: 2,
        high_risk_speaker_count: 1,
        speaker_run_count: 3,
        high_risk_run_count: 1,
        review_segment_count: 2,
        decision_count: 0,
        corrected_exists: false,
      },
      artifact_paths: {},
      speakers: [
        {
          speaker_label: 'SPEAKER_01',
          segment_count: 1,
          segment_ids: ['seg-0002'],
          total_speech_sec: 0.6,
          avg_duration_sec: 0.6,
          short_segment_count: 1,
          risk_flags: ['single_segment_speaker', 'low_sample_speaker'],
          risk_level: 'high',
          cloneable_by_default: false,
          decision: null,
        },
        {
          speaker_label: 'SPEAKER_00',
          segment_count: 3,
          segment_ids: ['seg-0001', 'seg-0003', 'seg-0004'],
          total_speech_sec: 6,
          avg_duration_sec: 2,
          short_segment_count: 0,
          risk_flags: [],
          risk_level: 'low',
          cloneable_by_default: true,
          decision: null,
        },
      ],
      speaker_runs: [],
      segments: [],
      review_plan: { items: [] },
      decisions: [],
      manifest: {},
    } as never)
    vi.mocked(tasksApi.saveSpeakerReviewDecision).mockResolvedValue({ ok: true } as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByRole('button', { name: '说话人审查' }))

    expect(await screen.findByText('说话人识别审查')).toBeInTheDocument()
    expect((await screen.findAllByText('SPEAKER_01')).length).toBeGreaterThan(0)
    expect(screen.getByText('单段 speaker')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: '不克隆' })[0])

    await waitFor(() => {
      expect(tasksApi.saveSpeakerReviewDecision).toHaveBeenCalledWith('task-speaker', expect.objectContaining({
        item_id: 'speaker:SPEAKER_01',
        item_type: 'speaker_profile',
        decision: 'mark_non_cloneable',
        source_speaker_label: 'SPEAKER_01',
      }))
    })
  })

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
      transcription_correction_summary: {
        status: 'available',
        corrected_count: 18,
        kept_asr_count: 5,
        review_count: 2,
        ocr_only_count: 1,
        auto_correction_rate: 0.692,
        algorithm_version: 'ocr-guided-asr-correction-v1',
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

    const { container } = render(<TaskDetailPage />, { wrapper: createWrapper() })

    expect(await screen.findByText('导出成品')).toBeInTheDocument()
    expect(screen.queryByText('Delivery Composer')).not.toBeInTheDocument()
    expect(screen.queryByText('节点详情')).not.toBeInTheDocument()
    expect(screen.getByText('当前素材已经满足推荐导出条件，可以直接生成成品视频。')).toBeInTheDocument()
    expect(screen.getByText('台词校正')).toBeInTheDocument()
    expect(screen.getByText('已校正 18 段')).toBeInTheDocument()
    expect(screen.getByText('2 段建议复核')).toBeInTheDocument()
    expect(screen.getByText('OCR 漏配 1 条')).toBeInTheDocument()
    expect((container.querySelector('.overflow-hidden.rounded-xl.border.border-slate-200.bg-white') as HTMLElement).className).not.toContain('shadow')

    fireEvent.click(screen.getByRole('button', { name: '导出成品' }))

    expect(await screen.findByText('1. 默认导出')).toBeInTheDocument()
    expect(screen.getByText('将导出为')).toBeInTheDocument()
    expect(screen.getByText(/来自成品目标/)).toBeInTheDocument()
    const toggleProfilesButton = screen.getByRole('button', { name: '切换其他版本' })
    expect(toggleProfilesButton).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('1. 选择导出版本')).not.toBeInTheDocument()
    expect(screen.queryByText('无字幕配音版')).not.toBeInTheDocument()
    expect(screen.getByText('2. 确认素材来源')).toBeInTheDocument()
    const audioSourceCard = screen.getByText('音轨来源').closest('.rounded-xl') as HTMLElement
    expect(within(audioSourceCard).getByText('配音+背景混音音轨')).toBeInTheDocument()
    expect(within(audioSourceCard).getByText('task-e/voice/preview_mix.en.wav')).toBeInTheDocument()
    expect(screen.getByText('3. 选择字幕样式')).toBeInTheDocument()
    expect(screen.getByText('4. 预览并导出')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Source Han Sans')).toBeInTheDocument()
    expect((screen.getByText('导出向导').closest('aside') as HTMLElement).className).not.toContain('shadow')

    fireEvent.click(toggleProfilesButton)

    expect(screen.getByRole('button', { name: '收起其他版本' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('无字幕配音版')).toBeInTheDocument()
    ;['1. 默认导出', '2. 确认素材来源', '3. 选择字幕样式', '4. 预览并导出'].forEach(title => {
      expect((screen.getByText(title).closest('section') as HTMLElement).className).not.toContain('shadow')
    })
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

  it('provides download links for available asset items only', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-3',
      name: 'Asset task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'english_subtitle',
      quality_preset: 'high_quality',
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

    const originalVideoDownload = await screen.findByRole('link', { name: '下载原始视频' })
    expect(originalVideoDownload).toHaveAttribute('href', '/api/tasks/task-3/input-file')

    expect(screen.getByRole('link', { name: '下载纯配音音轨' })).toHaveAttribute(
      'href',
      '/api/tasks/task-3/artifacts/task-e/voice/dub_voice.en.wav',
    )
    expect(screen.getByRole('link', { name: '下载预览混音音轨' })).toHaveAttribute(
      'href',
      '/api/tasks/task-3/artifacts/task-e/voice/preview_mix.en.wav',
    )
    expect(screen.getByRole('link', { name: '下载OCR 英文字幕' })).toHaveAttribute(
      'href',
      '/api/tasks/task-3/artifacts/ocr-translate/ocr_subtitles.en.srt',
    )

    expect(screen.queryByRole('link', { name: '下载干净画面' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '下载ASR 英文字幕' })).not.toBeInTheDocument()
  })

  it('warns about confirmed hard subtitles and uses the recommended preserve strategy by default', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-hard-subtitles',
      name: 'Bilingual review task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'bilingual_review',
      quality_preset: 'standard',
      config: { template: 'asr-dub+ocr-subs', video_source: 'original', audio_source: 'both', subtitle_source: 'both' },
      delivery_config: {
        subtitle_mode: 'bilingual',
        subtitle_render_source: 'ocr',
        bilingual_export_strategy: 'auto_standard_bilingual',
      },
      hard_subtitle_status: 'confirmed',
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
        recommended_profile: 'bilingual_review',
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
      workflow: { template_id: 'asr-dub+ocr-subs', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)
    vi.mocked(tasksApi.composeDelivery).mockResolvedValue({} as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByRole('button', { name: '导出成品' }))

    expect(await screen.findByText('检测到原片已有中文字幕')).toBeInTheDocument()
    expect(screen.getByText('推荐：保留原字 + 补英文')).toBeInTheDocument()
    expect(screen.getByText('当前任务没有干净画面，暂不可用。')).toBeInTheDocument()

    const exportSection = screen.getByText('4. 预览并导出').closest('section')
    expect(exportSection).not.toBeNull()
    fireEvent.click(within(exportSection as HTMLElement).getByRole('button', { name: '导出成品' }))

    await waitFor(() => {
      expect(tasksApi.composeDelivery).toHaveBeenCalledWith(
        'task-1',
        expect.objectContaining({
          subtitle_mode: 'bilingual',
          subtitle_source: 'ocr',
          bilingual_export_strategy: 'preserve_hard_subtitles_add_english',
          export_preview: true,
          export_dub: false,
        }),
      )
    })
  })

  it('can switch bilingual review export to clean rebuild when clean video is available', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-hard-subtitles-clean',
      name: 'Bilingual review clean task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'bilingual_review',
      quality_preset: 'standard',
      config: { template: 'asr-dub+ocr-subs+erase', video_source: 'original', audio_source: 'both', subtitle_source: 'both' },
      delivery_config: {
        subtitle_mode: 'bilingual',
        subtitle_render_source: 'ocr',
        bilingual_export_strategy: 'auto_standard_bilingual',
      },
      hard_subtitle_status: 'confirmed',
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
        recommended_profile: 'bilingual_review',
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
    vi.mocked(tasksApi.composeDelivery).mockResolvedValue({} as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByRole('button', { name: '导出成品' }))

    fireEvent.click(screen.getByText('清理原字 + 重做双语'))

    const exportSection = screen.getByText('4. 预览并导出').closest('section')
    expect(exportSection).not.toBeNull()
    fireEvent.click(within(exportSection as HTMLElement).getByRole('button', { name: '导出成品' }))

    await waitFor(() => {
      expect(tasksApi.composeDelivery).toHaveBeenCalledWith(
        'task-1',
        expect.objectContaining({
          subtitle_mode: 'bilingual',
          subtitle_source: 'ocr',
          bilingual_export_strategy: 'clean_video_rebuild_bilingual',
        }),
      )
    })
  })

  it('keeps the selected subtitle source after generating a preview in the export drawer', async () => {
    const task = {
      id: 'task-preview-source',
      name: 'Preview source task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'bilingual_review',
      quality_preset: 'standard',
      config: { template: 'asr-dub+ocr-subs', video_source: 'original', audio_source: 'both', subtitle_source: 'both' },
      delivery_config: {
        subtitle_mode: 'bilingual',
        subtitle_render_source: 'ocr',
        bilingual_export_strategy: 'preserve_hard_subtitles_add_english',
      },
      hard_subtitle_status: 'confirmed',
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
        recommended_profile: 'bilingual_review',
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
    }

    vi.mocked(tasksApi.get).mockResolvedValue(task as never)
    vi.mocked(tasksApi.listArtifacts).mockResolvedValue({ artifacts: [] } as never)
    vi.mocked(tasksApi.getGraph).mockResolvedValue({
      workflow: { template_id: 'asr-dub+ocr-subs', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)
    vi.mocked(tasksApi.createSubtitlePreview).mockResolvedValue({} as never)
    vi.mocked(tasksApi.composeDelivery).mockResolvedValue({} as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByRole('button', { name: '导出成品' }))
    fireEvent.change(screen.getByRole('combobox', { name: /英文字幕来源/ }), { target: { value: 'asr' } })

    const exportSection = screen.getByText('4. 预览并导出').closest('section')
    expect(exportSection).not.toBeNull()
    fireEvent.click(within(exportSection as HTMLElement).getByRole('button', { name: '生成字幕预览' }))

    await waitFor(() => {
      expect(tasksApi.createSubtitlePreview).toHaveBeenCalledWith(
        'task-1',
        expect.objectContaining({
          subtitle_path: 'task-c/voice/translation.en.srt',
        }),
      )
    })
    await waitFor(() => {
      expect(vi.mocked(tasksApi.get).mock.calls.length).toBeGreaterThan(1)
    })

    fireEvent.click(within(exportSection as HTMLElement).getByRole('button', { name: '导出成品' }))

    await waitFor(() => {
      expect(tasksApi.composeDelivery).toHaveBeenCalledWith(
        'task-1',
        expect.objectContaining({
          subtitle_mode: 'bilingual',
          subtitle_source: 'asr',
        }),
      )
    })
  })

  it('uses the same download button style in export results and asset items', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-4',
      name: 'Styled downloads',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'english_subtitle',
      quality_preset: 'high_quality',
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
          final_preview: { status: 'available', path: 'task-g/final-preview/final_preview.en.mp4' },
          final_dub: { status: 'available', path: 'task-g/final-dub/final_dub.en.mp4' },
        },
      },
      export_readiness: {
        status: 'exported',
        recommended_profile: 'english_subtitle_burned',
        summary: 'already_exported',
        blockers: [],
      },
      last_export_summary: {
        status: 'exported',
        profile: 'english_subtitle_burned',
        updated_at: '2026-04-16T00:00:00Z',
        files: [
          { kind: 'preview', label: '预览成品', path: 'task-g/final-preview/final_preview.en.mp4' },
          { kind: 'dub', label: '正式成品', path: 'task-g/final-dub/final_dub.en.mp4' },
        ],
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

    const exportDownload = await screen.findByRole('link', { name: '下载预览成品' })
    const assetDownload = screen.getByRole('link', { name: '下载原始视频' })
    const exportIconShell = exportDownload.querySelector('span[aria-hidden="true"]')

    expect(exportIconShell?.className).toBe(assetDownload.className)
    expect(assetDownload.className).not.toContain('border')
  })

  it('opens the dubbing review drawer and saves a reference decision', async () => {
    vi.mocked(tasksApi.get).mockResolvedValue({
      id: 'task-review',
      name: 'Review task',
      status: 'succeeded',
      input_path: '/tmp/demo.mp4',
      output_root: '/tmp/output',
      source_lang: 'zh',
      target_lang: 'en',
      output_intent: 'dub_final',
      quality_preset: 'standard',
      config: { template: 'asr-dub-basic', video_source: 'original', audio_source: 'both', subtitle_source: 'asr' },
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
          ocr_translated: { status: 'missing', path: null },
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
        recommended_profile: 'dub_no_subtitles',
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
      workflow: { template_id: 'asr-dub-basic', status: 'succeeded' },
      nodes: [{ id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'succeeded', progress_percent: 100 }],
      edges: [],
    } as never)
    vi.mocked(tasksApi.getDubbingReview).mockResolvedValue({
      task_id: 'task-review',
      target_lang: 'en',
      status: 'available',
      summary: {
        speaker_count: 1,
        merge_candidate_count: 0,
        repair_item_count: 1,
        reference_decision_count: 0,
        merge_decision_count: 0,
        repair_decision_count: 0,
      },
      stats: {},
      artifact_paths: {},
      speakers: [
        {
          speaker_id: 'spk_0001',
          profile_id: 'profile_0001',
          display_name: 'SPEAKER_01',
          status: 'registered',
          total_speech_sec: 12.5,
          segment_count: 4,
          reference_clip_count: 1,
          speaker_failed_count: 2,
          repair_item_count: 2,
          candidates: [
            {
              reference_id: 'clip_0001',
              source: 'reference_plan',
              path: '/tmp/output/task-b/voice/reference_clips/profile_0001/clip_0001.wav',
              artifact_path: 'task-b/voice/reference_clips/profile_0001/clip_0001.wav',
              duration_sec: 8.2,
              text: '测试参考音频',
              rms: 0.08,
              quality_score: 0.9,
              risk_flags: [],
              is_current: true,
              is_recommended: true,
            },
          ],
        },
      ],
      merge_candidates: [],
      repair_items: [],
      decisions: { reference: [], merge: [], repair: [] },
    } as never)
    vi.mocked(tasksApi.saveDubbingReviewDecision).mockResolvedValue({ ok: true } as never)

    render(<TaskDetailPage />, { wrapper: createWrapper() })

    fireEvent.click(await screen.findByRole('button', { name: '配音返修审查' }))

    expect(await screen.findByText('音色审查')).toBeInTheDocument()
    expect(await screen.findByText('SPEAKER_01')).toBeInTheDocument()
    expect(screen.getByText('clip_0001')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '使用' }))

    await waitFor(() => {
      expect(tasksApi.saveDubbingReviewDecision).toHaveBeenCalledWith(
        'task-review',
        expect.objectContaining({
          category: 'reference',
          item_id: 'spk_0001',
          decision: 'use_reference',
        }),
      )
    })
  })
})
