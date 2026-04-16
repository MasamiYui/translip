import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { configApi, systemApi } from '../../api/config'
import { tasksApi } from '../../api/tasks'
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

function getStepTwoSelects() {
  const selects = screen.getAllByRole('combobox') as HTMLSelectElement[]
  return {
    template: selects[0],
    subtitleSource: selects[1],
    videoSource: selects[2],
    audioSource: selects[3],
    fromStage: selects[4],
    toStage: selects[5],
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('NewTaskPage defaults', () => {
  it('defaults the execution range to task-g', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])
    vi.mocked(tasksApi.create).mockResolvedValue({ id: 'task-1' } as never)

    renderStepTwo()

    const { toStage } = getStepTwoSelects()
    expect(toStage).toHaveValue('task-g')
  })

  it('switches erase template to clean-if-available video while preserving manual overrides', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])
    vi.mocked(systemApi.probe).mockResolvedValue({} as never)

    renderStepTwo()

    const { template, videoSource, toStage } = getStepTwoSelects()
    expect(videoSource).toHaveValue('original')
    expect(toStage).toHaveValue('task-g')

    fireEvent.change(template, { target: { value: 'asr-dub+ocr-subs+erase' } })
    expect(videoSource).toHaveValue('clean_if_available')
    expect(toStage).toHaveValue('task-g')

    fireEvent.change(videoSource, { target: { value: 'clean' } })
    fireEvent.change(toStage, { target: { value: 'task-e' } })
    fireEvent.change(template, { target: { value: 'asr-dub-basic' } })

    expect(videoSource).toHaveValue('clean')
    expect(toStage).toHaveValue('task-e')
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
})
