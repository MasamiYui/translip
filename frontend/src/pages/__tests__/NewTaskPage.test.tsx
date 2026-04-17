import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { configApi } from '../../api/config'
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

function renderReviewStep() {
  render(<NewTaskPage />, { wrapper: createWrapper() })
  fireEvent.change(screen.getByPlaceholderText('/path/to/video.mp4'), {
    target: { value: '/tmp/demo.mp4' },
  })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('NewTaskPage redesigned flow', () => {
  it('shows output intent cards and updates the summary based on the selected result', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])
    vi.mocked(tasksApi.create).mockResolvedValue({ id: 'task-1' } as never)

    renderStepTwo()

    expect(screen.getByText('英文配音成片')).toBeInTheDocument()
    expect(screen.getByText('中英双语审片版')).toBeInTheDocument()
    expect(screen.getByText('英文字幕版')).toBeInTheDocument()
    expect(screen.getByText('快速验证版')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /英文字幕版/ }))

    expect(screen.getByText('本次任务将生成：')).toBeInTheDocument()
    expect(screen.getByText('优先干净画面 + 英文字幕')).toBeInTheDocument()
    expect(screen.getByText('OCR 字幕链路、导出预览能力')).toBeInTheDocument()
  })

  it('keeps developer execution controls hidden by default on the creation flow', async () => {
    vi.mocked(configApi.getPresets).mockResolvedValue([])

    renderStepTwo()

    expect(screen.queryByText('工作流模板')).not.toBeInTheDocument()
    expect(screen.queryByText('从阶段')).not.toBeInTheDocument()
    expect(screen.queryByText('到阶段')).not.toBeInTheDocument()
    expect(screen.queryByText('字幕输入策略')).not.toBeInTheDocument()
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

    expect(screen.getAllByRole('button', { name: '创建任务' })).toHaveLength(1)
    expect(screen.getByText('处理预览')).toBeInTheDocument()
  })
})
