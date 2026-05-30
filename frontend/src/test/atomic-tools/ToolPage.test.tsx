import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configApi } from '../../api/config'
import { I18nProvider } from '../../i18n/I18nProvider'
import { ToolPage } from '../../pages/ToolPage'

const apiMocks = vi.hoisted(() => ({
  listTools: vi.fn(),
}))

const atomicToolMocks = vi.hoisted(() => ({
  runTool: vi.fn(),
  reset: vi.fn(),
  uploadFile: vi.fn(),
  getDownloadUrl: vi.fn(),
}))

vi.mock('../../api/atomic-tools', () => ({
  atomicToolsApi: apiMocks,
}))

vi.mock('../../api/config', () => ({
  configApi: {
    getDefaults: vi.fn(),
  },
}))

vi.mock('../../hooks/useAtomicTool', () => ({
  useAtomicTool: vi.fn(() => ({
    uploadFile: atomicToolMocks.uploadFile,
    job: null,
    artifacts: [],
    runTool: atomicToolMocks.runTool,
    isRunning: false,
    getDownloadUrl: atomicToolMocks.getDownloadUrl,
    errorMessage: '',
    reset: atomicToolMocks.reset,
  })),
}))

function createWrapper(initialEntries = ['/tools/transcription']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

beforeEach(() => {
  vi.mocked(configApi.getDefaults).mockResolvedValue({})
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ToolPage', () => {
  it('lets transcription users choose Japanese from a localized language dropdown', async () => {
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'transcription',
        name_zh: '语音转文字',
        name_en: 'Speech to Text',
        description_zh: '语音识别并生成带时间戳的文字与字幕',
        description_en: 'Transcribe audio/video into timestamped text and subtitles',
        category: 'speech',
        icon: 'MessageSquareText',
        accept_formats: ['.mp4'],
        max_file_size_mb: 500,
        max_files: 1,
      },
    ])

    render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper() },
    )

    expect(await screen.findByRole('heading', { name: '语音转文字' })).toBeInTheDocument()

    const languageSelect = screen.getByRole('combobox', { name: '语言' }) as HTMLSelectElement
    expect(screen.getByRole('option', { name: '日语 (ja)' })).toBeInTheDocument()

    fireEvent.change(languageSelect, { target: { value: 'ja' } })
    fireEvent.click(screen.getByRole('button', { name: '开始处理' }))

    expect(atomicToolMocks.runTool).toHaveBeenCalledWith(
      expect.objectContaining({
        language: 'ja',
        asr_model: 'paraformer-zh',
        generate_srt: true,
      }),
    )
  })

  it('applies global transcription defaults to atomic transcription params', async () => {
    vi.mocked(configApi.getDefaults).mockResolvedValue({
      asr_backend: 'faster-whisper',
      asr_model: 'medium',
      vad_filter: false,
      vad_min_silence_duration_ms: 650,
      beam_size: 3,
      best_of: 2,
      temperature: 0.2,
      condition_on_previous_text: true,
      generate_srt: false,
    })
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'transcription',
        name_zh: '语音转文字',
        name_en: 'Speech to Text',
        description_zh: '语音识别并生成带时间戳的文字与字幕',
        description_en: 'Transcribe audio/video into timestamped text and subtitles',
        category: 'speech',
        icon: 'MessageSquareText',
        accept_formats: ['.mp4'],
        max_file_size_mb: 500,
        max_files: 1,
      },
    ])

    render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper() },
    )

    expect(await screen.findByRole('heading', { name: '语音转文字' })).toBeInTheDocument()
    await screen.findByDisplayValue('medium')
    fireEvent.click(screen.getByRole('button', { name: '开始处理' }))

    expect(atomicToolMocks.runTool).toHaveBeenCalledWith(
      expect.objectContaining({
        asr_model: 'medium',
        generate_srt: false,
        vad_filter: false,
        vad_min_silence_duration_ms: 650,
        beam_size: 3,
        best_of: 2,
        temperature: 0.2,
        condition_on_previous_text: true,
      }),
    )
  })

  it('lets translation users choose auto and Japanese from localized language dropdowns', async () => {
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'translation',
        name_zh: '文本翻译',
        name_en: 'Text Translation',
        description_zh: '翻译文本或字幕文件',
        description_en: 'Translate plain text or subtitle files',
        category: 'speech',
        icon: 'Languages',
        accept_formats: ['.txt', '.srt', '.json'],
        max_file_size_mb: 20,
        max_files: 2,
      },
    ])

    render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper(['/tools/translation']) },
    )

    expect(await screen.findByRole('heading', { name: '文本翻译' })).toBeInTheDocument()

    const sourceSelect = screen.getByRole('combobox', { name: '源语言' }) as HTMLSelectElement
    const targetSelect = screen.getByRole('combobox', { name: '目标语言' }) as HTMLSelectElement

    expect(within(sourceSelect).getByRole('option', { name: '自动检测 (auto)' })).toBeInTheDocument()
    expect(within(sourceSelect).getByRole('option', { name: '日语 (ja)' })).toBeInTheDocument()
    expect(within(targetSelect).getByRole('option', { name: '日语 (ja)' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('文本内容'), {
      target: { value: 'こんにちは。今日は京都に行きます。' },
    })
    fireEvent.change(sourceSelect, { target: { value: 'auto' } })
    fireEvent.change(targetSelect, { target: { value: 'ja' } })
    fireEvent.click(screen.getByRole('button', { name: '开始处理' }))

    expect(atomicToolMocks.runTool).toHaveBeenCalledWith(
      expect.objectContaining({
        source_lang: 'auto',
        target_lang: 'ja',
        backend: 'local-m2m100',
        text: 'こんにちは。今日は京都に行きます。',
      }),
    )
  })

  it('sends both ASR and OCR file ids plus preset for transcript-correction', async () => {
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'transcript-correction',
        name_zh: '台词校正',
        name_en: 'Transcript Correction',
        description_zh: '使用 OCR 字幕校正 ASR 文稿，保留 ASR 时间轴和说话人',
        description_en: 'Correct ASR transcript text with OCR subtitle events',
        category: 'speech',
        icon: 'ScanText',
        accept_formats: ['.json'],
        max_file_size_mb: 500,
        max_files: 2,
      },
    ])
    atomicToolMocks.uploadFile
      .mockResolvedValueOnce({ file_id: 'asr-1', filename: 'segments.zh.json' })
      .mockResolvedValueOnce({ file_id: 'ocr-1', filename: 'ocr_events.json' })

    render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper(['/tools/transcript-correction']) },
    )

    expect(await screen.findByRole('heading', { name: '台词校正' })).toBeInTheDocument()

    const asrInput = screen.getByLabelText('ASR 文稿') as HTMLInputElement
    const ocrInput = screen.getByLabelText('OCR 字幕事件') as HTMLInputElement
    fireEvent.change(asrInput, {
      target: { files: [new File(['{}'], 'segments.zh.json', { type: 'application/json' })] },
    })
    fireEvent.change(ocrInput, {
      target: { files: [new File(['{}'], 'ocr_events.json', { type: 'application/json' })] },
    })

    await screen.findByText('segments.zh.json')
    await screen.findByText('ocr_events.json')

    fireEvent.click(screen.getByRole('button', { name: /激进/ }))
    fireEvent.click(screen.getByRole('button', { name: '开始处理' }))

    expect(atomicToolMocks.runTool).toHaveBeenCalledWith(
      expect.objectContaining({
        preset: 'aggressive',
        segments_file_id: 'asr-1',
        ocr_events_file_id: 'ocr-1',
      }),
    )
  })

  it('defaults the tts backend to qwen3tts and runs without a reference', async () => {
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'tts',
        name_zh: '语音合成',
        name_en: 'Text to Speech',
        description_zh: '将文本转为语音，并可选参考音色克隆',
        description_en: 'Synthesize speech from text with optional reference voice cloning',
        category: 'speech',
        icon: 'Mic',
        accept_formats: ['.wav', '.mp3', '.flac', '.m4a', '.ogg', '.txt'],
        max_file_size_mb: 100,
        max_files: 1,
      },
    ])

    render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper(['/tools/tts']) },
    )

    expect(await screen.findByRole('heading', { name: '语音合成' })).toBeInTheDocument()

    const backendSelect = screen.getByRole('combobox', { name: 'TTS 后端' }) as HTMLSelectElement
    expect(backendSelect.value).toBe('qwen3tts')
    // qwen3tts can synthesize without a reference (voice design), so run stays enabled.
    expect(screen.getByRole('button', { name: '开始处理' })).not.toBeDisabled()

    fireEvent.change(screen.getByLabelText('文本内容'), { target: { value: 'Hello there' } })
    fireEvent.click(screen.getByRole('button', { name: '开始处理' }))

    expect(atomicToolMocks.runTool).toHaveBeenCalledWith(
      expect.objectContaining({ backend: 'qwen3tts', text: 'Hello there' }),
    )
  })

  it('disables run and shows a hint when a clone-only tts backend has no reference', async () => {
    apiMocks.listTools.mockResolvedValue([
      {
        tool_id: 'tts',
        name_zh: '语音合成',
        name_en: 'Text to Speech',
        description_zh: '将文本转为语音，并可选参考音色克隆',
        description_en: 'Synthesize speech from text with optional reference voice cloning',
        category: 'speech',
        icon: 'Mic',
        accept_formats: ['.wav', '.mp3', '.flac', '.m4a', '.ogg', '.txt'],
        max_file_size_mb: 100,
        max_files: 1,
      },
    ])

    render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper(['/tools/tts']) },
    )

    expect(await screen.findByRole('heading', { name: '语音合成' })).toBeInTheDocument()

    const backendSelect = screen.getByRole('combobox', { name: 'TTS 后端' }) as HTMLSelectElement
    fireEvent.change(backendSelect, { target: { value: 'voxcpm2' } })

    expect(backendSelect.value).toBe('voxcpm2')
    expect(screen.getByRole('button', { name: '开始处理' })).toBeDisabled()
    expect(screen.getByText(/所选后端需要上传参考音频/)).toBeInTheDocument()
  })
})
