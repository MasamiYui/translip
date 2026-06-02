import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configApi } from '../../api/config'
import { worksApi } from '../../api/works'
import { I18nProvider } from '../../i18n/I18nProvider'
import { SettingsPage } from '../SettingsPage'

vi.mock('../../api/config', () => ({
  configApi: {
    getDefaults: vi.fn(),
    getGlobal: vi.fn(),
    updateGlobal: vi.fn(),
    getPresets: vi.fn(),
    createPreset: vi.fn(),
    deletePreset: vi.fn(),
  },
  systemApi: {
    getInfo: vi.fn(() =>
      Promise.resolve({
        python_version: '3.11',
        platform: 'macOS',
        device: 'cpu',
        cache_dir: '/tmp/cache',
        cache_size_bytes: 0,
        models: [],
      }),
    ),
  },
  modelsApi: {
    downloadMissing: vi.fn(),
    getJob: vi.fn(),
    cancelJob: vi.fn(),
  },
  cacheApi: {
    getBreakdown: vi.fn(() =>
      Promise.resolve({
        cache_dir: '/tmp/cache',
        huggingface_hub_dir: '/tmp/hf',
        total_bytes: 0,
        items: [],
      }),
    ),
    setDir: vi.fn(),
    resetDefault: vi.fn(),
    removeItem: vi.fn(),
    cleanup: vi.fn(),
    startMigrate: vi.fn(),
    pollMigrate: vi.fn(),
    cancelMigrate: vi.fn(),
  },
}))

vi.mock('../../api/works', () => ({
  worksApi: {
    tmdbGetConfig: vi.fn(),
    tmdbSaveConfig: vi.fn(),
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

beforeEach(() => {
  vi.mocked(configApi.getGlobal).mockResolvedValue({
    device: 'auto',
    use_cache: true,
    keep_intermediate: false,
    separation_mode: 'dialogue',
    separation_quality: 'high',
    stage1_output_format: 'wav',
    asr_model: 'medium',
    asr_backend: 'faster-whisper',
    diarizer_backend: 'ecapa',
    enable_diarization: true,
    generate_srt: true,
    vad_filter: false,
    vad_min_silence_duration_ms: 650,
    beam_size: 3,
    best_of: 2,
    temperature: 0.2,
    condition_on_previous_text: true,
    top_k: 4,
    translation_backend: 'deepseek',
    translation_batch_size: 8,
    condense_mode: 'smart',
    deepseek_model: 'deepseek-v4-pro',
    tts_backend: 'qwen3tts',
    dubbing_workers: 2,
    dubbing_quality_check: 'duration-only',
    dub_repair_enabled: true,
    dub_repair_backend: ['moss-tts-nano-onnx', 'qwen3tts'],
    dub_repair_max_items: 6,
    dub_repair_attempts_per_item: 2,
    dub_repair_include_risk: true,
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
  vi.mocked(configApi.updateGlobal).mockResolvedValue({ ok: true, config: {} })
  vi.mocked(worksApi.tmdbGetConfig).mockResolvedValue({
    ok: true,
    api_key_v3_set: false,
    api_key_v4_set: false,
    default_language: 'zh-CN',
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('SettingsPage global and advanced settings', () => {
  it('splits settings into global and advanced sections with ASR effect controls', async () => {
    render(<SettingsPage />, { wrapper: createWrapper() })

    expect(await screen.findByRole('button', { name: '常规' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '任务默认参数' }))

    expect(screen.getByText('语音转写')).toBeInTheDocument()
    expect(screen.getByLabelText('ASR 后端')).toHaveValue('faster-whisper')
    expect(screen.getByLabelText('ASR 模型')).toHaveValue('medium')
    expect(within(screen.getByLabelText('ASR 后端')).getByRole('option', { name: 'FunASR' })).toBeInTheDocument()
    expect(screen.getByLabelText('启用说话人分离')).toBeChecked()
    expect(screen.getByLabelText('说话人后端')).toHaveValue('ecapa')
    expect(screen.getByLabelText('启用 VAD')).not.toBeChecked()
    expect(screen.getByLabelText('VAD 最小静音毫秒')).toHaveValue(650)
    expect(screen.getByLabelText('Beam Size')).toHaveValue(3)
    expect(screen.getByLabelText('Best Of')).toHaveValue(2)
    expect(screen.getByLabelText('Temperature')).toHaveValue(0.2)
    expect(screen.getByLabelText('使用前文上下文')).toBeChecked()
  })

  it('shows grouped advanced node defaults beyond transcription', async () => {
    render(<SettingsPage />, { wrapper: createWrapper() })
    fireEvent.click(await screen.findByRole('button', { name: '任务默认参数' }))

    expect(screen.getByText('音频分离')).toBeInTheDocument()
    expect(screen.getByText('说话人匹配')).toBeInTheDocument()
    expect(screen.getByText('翻译')).toBeInTheDocument()
    expect(screen.getByText('配音')).toBeInTheDocument()
    expect(screen.getByText('混音与时间轴')).toBeInTheDocument()
    expect(screen.getByText('导出与字幕')).toBeInTheDocument()

    expect(screen.getByLabelText('分离模式')).toHaveValue('dialogue')
    expect(screen.getByLabelText('分离质量')).toHaveValue('high')
    expect(screen.getByLabelText('Stage 1 输出格式')).toHaveValue('wav')
    expect(screen.getByLabelText('说话人候选数 Top K')).toHaveValue(4)
    expect(screen.getByLabelText('翻译后端')).toHaveValue('deepseek')
    expect(screen.getByLabelText('翻译批量大小')).toHaveValue(8)
    expect(screen.getByLabelText('译文压缩')).toHaveValue('smart')
    expect(screen.getByLabelText('DeepSeek 模型')).toHaveValue('deepseek-v4-pro')
    expect(screen.getByLabelText('TTS 后端')).toHaveValue('qwen3tts')
    expect(within(screen.getByLabelText('TTS 后端')).getByRole('option', { name: 'VoxCPM2' })).toBeInTheDocument()
    expect(screen.getByLabelText('配音并发数')).toHaveValue(2)
    expect(screen.getByLabelText('配音质检')).toHaveValue('duration-only')
    expect(screen.getByLabelText('启用配音修复')).toBeChecked()
    expect(screen.getByLabelText('VoxCPM2')).not.toBeChecked()
    expect(screen.getByLabelText('修复最大条数')).toHaveValue(6)
    expect(screen.getByLabelText('修复每条尝试次数')).toHaveValue(2)
    expect(screen.getByLabelText('允许修复风险段落')).toBeChecked()
    expect(screen.getByLabelText('时间伸缩策略')).toHaveValue('high_quality')
    expect(screen.getByLabelText('时间伸缩后端')).toHaveValue('rubberband')
    expect(screen.getByLabelText('混音配置')).toHaveValue('enhanced')
    expect(screen.getByLabelText('压低背景模式')).toHaveValue('sidechain')
    expect(screen.getByLabelText('背景音量 dB')).toHaveValue(-10)
    expect(screen.getByLabelText('窗口压低 dB')).toHaveValue(-4)
    expect(screen.getByLabelText('最大压缩比例')).toHaveValue(1.35)
    expect(screen.getByLabelText('成品字幕模式')).toHaveValue('bilingual')
    expect(screen.getByLabelText('字幕渲染来源')).toHaveValue('asr')
  })

  it('saves advanced ASR defaults through the global config API', async () => {
    render(<SettingsPage />, { wrapper: createWrapper() })
    fireEvent.click(await screen.findByRole('button', { name: '任务默认参数' }))

    fireEvent.change(screen.getByLabelText('Beam Size'), { target: { value: '4' } })
    fireEvent.change(screen.getByLabelText('ASR 后端'), { target: { value: 'funasr' } })
    fireEvent.change(screen.getByLabelText('说话人后端'), { target: { value: 'pyannote' } })
    fireEvent.click(screen.getByLabelText('启用说话人分离'))
    fireEvent.change(screen.getByLabelText('背景音量 dB'), { target: { value: '-12' } })
    fireEvent.click(screen.getByLabelText('允许修复风险段落'))
    fireEvent.click(screen.getByRole('button', { name: '保存默认参数' }))

    await waitFor(() => {
      expect(configApi.updateGlobal).toHaveBeenCalledWith(
        expect.objectContaining({
          asr_model: 'paraformer-zh',
          asr_backend: 'funasr',
          diarizer_backend: 'pyannote',
          enable_diarization: false,
          vad_filter: false,
          vad_min_silence_duration_ms: 650,
          beam_size: 4,
          best_of: 2,
          temperature: 0.2,
          condition_on_previous_text: true,
          separation_mode: 'dialogue',
          stage1_output_format: 'wav',
          translation_backend: 'deepseek',
          translation_batch_size: 8,
          tts_backend: 'qwen3tts',
          dub_repair_enabled: true,
          dub_repair_include_risk: false,
          fit_policy: 'high_quality',
          background_gain_db: -12,
          subtitle_mode: 'bilingual',
        }),
      )
    })
  })

  it('saves the transcript-correction LLM arbitration default', async () => {
    render(<SettingsPage />, { wrapper: createWrapper() })
    fireEvent.click(await screen.findByRole('button', { name: '任务默认参数' }))

    const arbitration = screen.getByLabelText('文稿校正 LLM 仲裁')
    expect(arbitration).toHaveValue('off')
    fireEvent.change(arbitration, { target: { value: 'deepseek' } })
    fireEvent.click(screen.getByRole('button', { name: '保存默认参数' }))

    await waitFor(() => {
      expect(configApi.updateGlobal).toHaveBeenCalledWith(
        expect.objectContaining({
          transcription_correction: expect.objectContaining({ llm_arbitration: 'deepseek' }),
        }),
      )
    })
  })

  it('sends null when optional advanced defaults are cleared', async () => {
    render(<SettingsPage />, { wrapper: createWrapper() })
    fireEvent.click(await screen.findByRole('button', { name: '任务默认参数' }))

    const deepseekModel = screen.getByLabelText('DeepSeek 模型')
    const dubbingWorkers = screen.getByLabelText('配音并发数')
    expect(deepseekModel).toHaveValue('deepseek-v4-pro')
    expect(dubbingWorkers).toHaveValue(2)

    fireEvent.change(deepseekModel, { target: { value: '' } })
    fireEvent.change(dubbingWorkers, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: '保存默认参数' }))

    await waitFor(() => {
      expect(configApi.updateGlobal).toHaveBeenCalledWith(
        expect.objectContaining({
          deepseek_model: null,
          dubbing_workers: null,
        }),
      )
    })
  })
})
