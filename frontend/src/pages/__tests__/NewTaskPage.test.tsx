import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configApi } from '../../api/config'
import { tasksApi } from '../../api/tasks'
import { worksApi } from '../../api/works'
import { I18nProvider } from '../../i18n/I18nProvider'
import { NewTaskPage } from '../NewTaskPage'

vi.mock('../../api/config', () => ({
  configApi: {
    getDefaults: vi.fn(),
    getPresets: vi.fn(),
    createPreset: vi.fn(),
    deletePreset: vi.fn(),
  },
  systemApi: {
    getInfo: vi.fn(),
    probe: vi.fn(),
  },
}))

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    create: vi.fn(),
  },
}))

vi.mock('../../api/works', () => ({
  worksApi: {
    autoBindTask: vi.fn(),
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
        <I18nProvider>
          <MemoryRouter>{children}</MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

function renderStepTwo() {
  render(<NewTaskPage />, { wrapper: createWrapper() })
  fireEvent.change(screen.getByPlaceholderText('/path/to/video.mp4'), {
    target: { value: '/tmp/demo.mp4' },
  })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
}

function renderReviewStep() {
  render(<NewTaskPage />, { wrapper: createWrapper() })
  fireEvent.change(screen.getByPlaceholderText('/path/to/video.mp4'), {
    target: { value: '/tmp/demo.mp4' },
  })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
}

beforeEach(() => {
  vi.mocked(configApi.getDefaults).mockResolvedValue({})
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('NewTaskPage redesigned flow', () => {
  it('auto-detects and binds a work after creating a pipeline task', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])
    vi.mocked(tasksApi.create).mockResolvedValue({ id: 'task-auto-work' } as never)
    vi.mocked(worksApi.autoBindTask).mockResolvedValue({
      ok: true,
      bound: true,
      work_id: 'work_nezha',
      episode_label: 'E03',
      candidates: [],
    } as never)

    renderReviewStep()

    fireEvent.click(screen.getByRole('button', { name: '创建任务' }))

    await waitFor(() => {
      expect(worksApi.autoBindTask).toHaveBeenCalledWith('task-auto-work')
    })
  })

  it('shows output intent cards and updates the summary based on the selected result', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])
    vi.mocked(tasksApi.create).mockResolvedValue({ id: 'task-1' } as never)

    renderStepTwo()

    expect(screen.getByText('英文配音成片')).toBeInTheDocument()
    expect(screen.getByText('双语审片版')).toBeInTheDocument()
    expect(screen.getByText('英文字幕版')).toBeInTheDocument()
    expect(screen.getByText('快速验证版')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /英文字幕版/ }))

    expect(screen.getByText('语言方向')).toBeInTheDocument()
    expect(screen.getByText('默认导出')).toBeInTheDocument()
    expect(screen.getByText('处理策略')).toBeInTheDocument()
    expect(screen.getByText('系统将自动启用')).toBeInTheDocument()
    expect(screen.getByText('优先干净画面 + 英文字幕')).toBeInTheDocument()
    expect(screen.getByText('OCR 字幕链路、导出预览能力')).toBeInTheDocument()
    expect(screen.getByText('OCR 字幕链路')).toBeInTheDocument()
    expect(screen.getByText('配音合成')).toBeInTheDocument()
    expect(screen.getByText('字幕擦除')).toBeInTheDocument()
    expect(screen.getByText('该处理链路由成品目标自动生成。')).toBeInTheDocument()
    expect(screen.getByText('语言方向').closest('[data-ui-tone="neutral"]')).not.toBeNull()
    expect((screen.getByText('语言方向').closest('[data-ui-tone="neutral"]') as HTMLElement).className).not.toContain('shadow')
    expect(document.querySelector('[data-ui-layout="unified-dag"]')).not.toBeNull()
  })

  it('stacks the intent section and task summary vertically on step two', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderStepTwo()

    const summaryCard = screen.getByText('任务摘要').closest('section')
    const stepLayout = summaryCard?.parentElement
    const previewSection = screen.getByText('处理预览').closest('section')

    expect(stepLayout).not.toBeNull()
    expect(stepLayout?.className).toContain('space-y-6')
    expect(stepLayout?.className).not.toContain('lg:grid-cols')
    expect(screen.getAllByText('成品目标').at(-1)?.closest('section')?.className).toContain('space-y-3')
    expect(screen.getByText('处理预览').closest('section')?.className).toContain('space-y-3')
    expect(screen.getByText('任务摘要').closest('section')?.className).toContain('space-y-4')
    expect(previewSection?.querySelector('.rounded-xl.border.border-slate-100.bg-slate-50\\/70')).toBeNull()
  })

  it('keeps developer execution controls hidden by default on the creation flow', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderStepTwo()

    expect(screen.queryByText('工作流模板')).not.toBeInTheDocument()
    expect(screen.queryByText('从阶段')).not.toBeInTheDocument()
    expect(screen.queryByText('到阶段')).not.toBeInTheDocument()
    expect(screen.queryByText('字幕输入策略')).not.toBeInTheDocument()
  })

  it('defaults OCR-capable tasks to standard transcript correction and explains the setting', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderStepTwo()

    fireEvent.click(screen.getByRole('button', { name: /双语审片版/ }))
    fireEvent.click(screen.getByRole('button', { name: '下一步' }))

    expect(screen.getByText('台词校正')).toBeInTheDocument()
    expect(screen.getAllByText('标准').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /这个选项会做什么/ }))
    expect(screen.getByText(/保留 ASR 时间轴和说话人/)).toBeInTheDocument()
    expect(screen.getByText(/OCR 有但 ASR 没有的字幕只报告/)).toBeInTheDocument()
  })

  it('defaults task synthesis to MOSS-TTS-Nano ONNX while keeping Qwen and VoxCPM selectable', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderStepTwo()
    fireEvent.click(screen.getByRole('button', { name: '下一步' }))
    fireEvent.click(screen.getAllByRole('button', { name: '展开' })[0])

    const ttsField = screen.getByText('TTS 后端').parentElement as HTMLElement
    const ttsSelect = within(ttsField).getByRole('combobox') as HTMLSelectElement

    expect(ttsSelect.value).toBe('moss-tts-nano-onnx')
    expect(screen.getByRole('option', { name: 'MOSS-TTS-Nano ONNX' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Qwen3TTS' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'VoxCPM2' })).toBeInTheDocument()
  })

  it('applies global advanced ASR defaults to created task config', async () => {
    vi.mocked(configApi.getDefaults).mockResolvedValue({
      separation_mode: 'dialogue',
      separation_quality: 'high',
      stage1_output_format: 'wav',
      asr_model: 'iic/SenseVoiceSmall',
      asr_backend: 'funasr',
      diarizer_backend: 'pyannote',
      enable_diarization: false,
      vad_filter: false,
      vad_min_silence_duration_ms: 650,
      beam_size: 3,
      best_of: 2,
      temperature: 0.2,
      condition_on_previous_text: true,
      top_k: 4,
      translation_backend: 'siliconflow',
      translation_batch_size: 8,
      condense_mode: 'smart',
      tts_backend: 'qwen3tts',
      dubbing_workers: 2,
      dubbing_quality_check: 'duration-only',
      dub_repair_enabled: true,
      dub_repair_max_items: 6,
      dub_repair_attempts_per_item: 2,
      fit_policy: 'high_quality',
      fit_backend: 'rubberband',
      mix_profile: 'enhanced',
      ducking_mode: 'sidechain',
      background_gain_db: -10,
      window_ducking_db: -4,
      max_compress_ratio: 1.35,
      subtitle_mode: 'bilingual',
      subtitle_render_source: 'asr',
    })
    vi.mocked(configApi.getPresets).mockResolvedValue([])
    vi.mocked(tasksApi.create).mockResolvedValue({ id: 'task-asr-defaults' } as never)
    vi.mocked(worksApi.autoBindTask).mockResolvedValue({ ok: true, bound: false, candidates: [] } as never)

    renderReviewStep()

    await waitFor(() => {
      expect(configApi.getDefaults).toHaveBeenCalled()
    })
    fireEvent.click(screen.getByRole('button', { name: '创建任务' }))

    await waitFor(() => {
      expect(tasksApi.create).toHaveBeenCalled()
    })
    const request = vi.mocked(tasksApi.create).mock.calls[0][0]
    expect(request.config).toEqual(
      expect.objectContaining({
        asr_model: 'iic/SenseVoiceSmall',
        asr_backend: 'funasr',
        diarizer_backend: 'pyannote',
        enable_diarization: false,
        separation_mode: 'dialogue',
        separation_quality: 'high',
        stage1_output_format: 'wav',
        vad_filter: false,
        vad_min_silence_duration_ms: 650,
        beam_size: 3,
        best_of: 2,
        temperature: 0.2,
        condition_on_previous_text: true,
        top_k: 4,
        translation_backend: 'siliconflow',
        translation_batch_size: 8,
        condense_mode: 'smart',
        tts_backend: 'qwen3tts',
        dubbing_workers: 2,
        dubbing_quality_check: 'duration-only',
        dub_repair_enabled: true,
        dub_repair_max_items: 6,
        dub_repair_attempts_per_item: 2,
        fit_policy: 'high_quality',
        fit_backend: 'rubberband',
        mix_profile: 'enhanced',
        ducking_mode: 'sidechain',
        background_gain_db: -10,
        window_ducking_db: -4,
        max_compress_ratio: 1.35,
        subtitle_mode: 'bilingual',
        subtitle_render_source: 'asr',
      }),
    )
  })

  it('keeps delivery-only subtitle styling out of the new task flow', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderStepTwo()

    expect(screen.queryByText('成品字幕模式')).not.toBeInTheDocument()
    expect(screen.queryByText('英文字幕来源')).not.toBeInTheDocument()
    expect(screen.queryByText('字幕字体')).not.toBeInTheDocument()
    expect(screen.queryByText('字幕字号（0=自动推荐）')).not.toBeInTheDocument()
    expect(screen.queryByText('字幕位置')).not.toBeInTheDocument()
    expect(screen.queryByText('字幕颜色')).not.toBeInTheDocument()
  })

  it('keeps a single create action and still shows the workflow preview on the review step', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderReviewStep()

    const previewSection = screen.getByText('处理预览').closest('section')
    const confirmSection = screen.getAllByText('确认创建').at(-1)?.closest('section')
    const summarySection = screen.getByText('任务摘要').closest('section')
    const reviewLayout = previewSection?.parentElement
    const bottomRow = confirmSection?.parentElement

    expect(screen.getAllByRole('button', { name: '创建任务' })).toHaveLength(1)
    expect(screen.getByText('处理预览')).toBeInTheDocument()
    expect(reviewLayout).not.toBeNull()
    expect(reviewLayout?.className).toContain('space-y-6')
    expect(bottomRow).not.toBeNull()
    expect(bottomRow?.className).toContain('lg:grid-cols')
    expect(bottomRow?.contains(summarySection as Node)).toBe(true)
    expect(screen.queryByText('如需再次确认素材信息，可以回到第一步点击“检测”。')).not.toBeInTheDocument()
  })
})
