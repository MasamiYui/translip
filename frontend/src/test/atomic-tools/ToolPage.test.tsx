import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
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

afterEach(() => {
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
        asr_model: 'small',
        generate_srt: true,
      }),
    )
  })
})
