import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { useAssistantStore } from '../../../stores/assistantStore'
import { AssistantWidget } from '../AssistantWidget'
import type { AssistantPlan, RunState } from '../../../types/assistant'

const apiMocks = vi.hoisted(() => ({
  plan: vi.fn(),
  execute: vi.fn(),
  getRun: vi.fn(),
  cancelRun: vi.fn(),
}))

vi.mock('../../../api/assistant', () => ({ assistantApi: apiMocks }))
vi.mock('../../../api/atomic-tools', () => ({
  atomicToolsApi: { upload: vi.fn() },
}))

const PLAN: AssistantPlan = {
  summary: '我会先分离人声，再做转写。',
  steps: [
    {
      id: 'sep',
      tool_id: 'separation',
      title: '人声分离',
      rationale: '',
      params: {},
      inputs: { file_id: { source: 'upload', upload_index: 0 } },
    },
  ],
  edges: [],
}

const COMPLETED_RUN: RunState = {
  run_id: 'run-1',
  status: 'completed',
  message: '',
  summary: '',
  steps: [
    {
      id: 'sep',
      tool_id: 'separation',
      title: '人声分离',
      status: 'completed',
      progress_percent: 100,
      artifacts: [
        {
          filename: 'voice.wav',
          download_url: '/api/atomic-tools/separation/jobs/j1/artifacts/voice.wav',
          file_id: 'f1',
          size_bytes: 2048,
          content_type: 'audio/wav',
        },
      ],
    },
  ],
}

function renderWidget() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AssistantWidget />
      </I18nProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAssistantStore.setState({ isOpen: false, messages: [], attachments: [] })
  apiMocks.plan.mockReset()
  apiMocks.execute.mockReset()
  apiMocks.getRun.mockReset()
  apiMocks.cancelRun.mockReset()
})

afterEach(cleanup)

describe('AssistantWidget', () => {
  it('opens the panel and shows greeting + examples', () => {
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    expect(screen.getByRole('dialog', { name: 'AI 助手' })).toBeInTheDocument()
    expect(screen.getByText('识别这个视频的日语字幕并转成中文字幕')).toBeInTheDocument()
  })

  it('plans from a request, then executes and shows the completed artifacts', async () => {
    apiMocks.plan.mockResolvedValue(PLAN)
    apiMocks.execute.mockResolvedValue({ run_id: 'run-1' })
    apiMocks.getRun.mockResolvedValue(COMPLETED_RUN)

    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))

    // send via an example chip
    fireEvent.click(screen.getByText('提取这个视频里的人声'))

    // the call-chain diagram appears once the plan resolves
    await waitFor(() => expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument())
    expect(apiMocks.plan).toHaveBeenCalledOnce()

    // confirm execution
    fireEvent.click(screen.getByText('确认执行'))
    await waitFor(() => expect(apiMocks.execute).toHaveBeenCalledOnce())

    // polling resolves to a completed run -> artifact download link is rendered
    await waitFor(() => expect(screen.getByText('voice.wav')).toBeInTheDocument())
    const link = screen.getByText('voice.wav').closest('a')
    expect(link).toHaveAttribute('href', COMPLETED_RUN.steps[0].artifacts[0].download_url)
  })

  it('shows an error bubble when planning fails', async () => {
    apiMocks.plan.mockRejectedValue(new Error('未配置 DeepSeek API Key'))
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    fireEvent.click(screen.getByText('提取这个视频里的人声'))
    await waitFor(() => expect(screen.getByText('未配置 DeepSeek API Key')).toBeInTheDocument())
  })
})
