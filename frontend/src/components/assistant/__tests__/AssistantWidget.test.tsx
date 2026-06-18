import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { useAssistantStore, type ChatMessage } from '../../../stores/assistantStore'
import { AssistantWidget } from '../AssistantWidget'
import type { AssistantPlan, PlanResult, RunState } from '../../../types/assistant'

const apiMocks = vi.hoisted(() => ({
  plan: vi.fn(),
  execute: vi.fn(),
  getRun: vi.fn(),
  cancelRun: vi.fn(),
  upload: vi.fn(),
  getLlmKeys: vi.fn(),
}))

vi.mock('../../../api/assistant', () => ({
  assistantApi: {
    plan: apiMocks.plan,
    execute: apiMocks.execute,
    getRun: apiMocks.getRun,
    cancelRun: apiMocks.cancelRun,
  },
}))
vi.mock('../../../api/atomic-tools', () => ({ atomicToolsApi: { upload: apiMocks.upload } }))
vi.mock('../../../api/config', () => ({ systemApi: { getLlmKeys: apiMocks.getLlmKeys } }))

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

const PLAN_RESULT: PlanResult = { type: 'plan', plan: PLAN }

// A plan with no upload binding, so the pre-exec "needs upload" guard doesn't
// hide the run button when the test sends without attaching a file.
const RUNNABLE_RESULT: PlanResult = {
  type: 'plan',
  plan: {
    summary: '探测媒体信息',
    steps: [{ id: 'p', tool_id: 'probe', title: '媒体探测', rationale: '', params: {}, inputs: {} }],
    edges: [],
  },
}

const COMPLETED_RUN: RunState = {
  run_id: 'run-1',
  status: 'completed',
  message: '',
  summary: '',
  steps: [
    {
      id: 'p',
      tool_id: 'probe',
      title: '媒体探测',
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
        <MemoryRouter>
          <AssistantWidget />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useAssistantStore.setState({ isOpen: false, messages: [], attachments: [], availableFiles: [] })
  apiMocks.plan.mockReset()
  apiMocks.execute.mockReset()
  apiMocks.getRun.mockReset()
  apiMocks.cancelRun.mockReset()
  apiMocks.upload.mockReset()
  apiMocks.getLlmKeys.mockReset()
  // default: key is configured
  apiMocks.getLlmKeys.mockResolvedValue({ ok: true, providers: { deepseek: true }, base_urls: {} })
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
    apiMocks.plan.mockResolvedValue(RUNNABLE_RESULT)
    apiMocks.execute.mockResolvedValue({ run_id: 'run-1' })
    apiMocks.getRun.mockResolvedValue(COMPLETED_RUN)

    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    fireEvent.click(screen.getByText('提取这个视频里的人声'))

    await waitFor(() => expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument())
    expect(apiMocks.plan).toHaveBeenCalledOnce()

    fireEvent.click(screen.getByText('确认执行'))
    await waitFor(() => expect(apiMocks.execute).toHaveBeenCalledOnce())

    await waitFor(() => expect(screen.getByText('voice.wav')).toBeInTheDocument())
    const link = screen.getByText('voice.wav').closest('a')
    expect(link).toHaveAttribute('href', COMPLETED_RUN.steps[0].artifacts[0].download_url)
  })

  it('renders a clarification with options and re-plans with merged context on answer', async () => {
    apiMocks.plan
      .mockResolvedValueOnce({
        type: 'clarification',
        clarification: { question: '你想翻译成哪种语言？', options: ['中文', '英文'] },
      })
      .mockResolvedValueOnce(PLAN_RESULT)

    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    fireEvent.click(screen.getByText('提取这个视频里的人声'))

    await waitFor(() => expect(screen.getByText('你想翻译成哪种语言？')).toBeInTheDocument())
    // click a quick-reply option
    fireEvent.click(screen.getByText('中文'))

    await waitFor(() => expect(apiMocks.plan).toHaveBeenCalledTimes(2))
    const secondCallMessage = apiMocks.plan.mock.calls[1][0] as string
    expect(secondCallMessage).toContain('（补充说明：中文）')
  })

  it('shows an error bubble when planning fails', async () => {
    apiMocks.plan.mockRejectedValue(new Error('未配置 DeepSeek API Key'))
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    fireEvent.click(screen.getByText('提取这个视频里的人声'))
    await waitFor(() => expect(screen.getByText('未配置 DeepSeek API Key')).toBeInTheDocument())
  })

  it('sends prior conversation turns as history on a follow-up', async () => {
    apiMocks.plan.mockResolvedValue(RUNNABLE_RESULT)
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))

    fireEvent.click(screen.getByText('提取这个视频里的人声'))
    await waitFor(() => expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument())

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '再来一份' } })
    fireEvent.click(screen.getByLabelText('发送'))

    await waitFor(() => expect(apiMocks.plan).toHaveBeenCalledTimes(2))
    const history = apiMocks.plan.mock.calls[1][3] as { role: string; content: string }[]
    expect(history.some(t => t.role === 'user' && t.content === '提取这个视频里的人声')).toBe(true)
  })

  it('does not ask for an upload when a follow-up binds to a prior run output', () => {
    const planMsg: ChatMessage = {
      id: 'm1',
      role: 'assistant',
      kind: 'plan',
      createdAt: Date.now(),
      text: '把刚才的人声配成英文',
      fileIds: ['out1'],
      plan: {
        summary: '把刚才的人声配成英文',
        edges: [],
        steps: [
          {
            id: 'tts',
            tool_id: 'tts',
            title: '语音合成',
            rationale: '',
            params: { language: 'en' },
            inputs: { reference_audio_file_id: { source: 'upload', upload_index: 0 } },
          },
        ],
      },
    }
    useAssistantStore.setState({
      messages: [planMsg],
      availableFiles: [{ file_id: 'out1', filename: 'voice.wav', origin: 'output' }],
    })
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))

    expect(screen.getByText('确认执行')).toBeInTheDocument()
    expect(screen.queryByText(/请先上传文件/)).not.toBeInTheDocument()
  })

  it('confirms before starting a new chat, then clears the conversation', async () => {
    apiMocks.plan.mockResolvedValue(RUNNABLE_RESULT)
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    fireEvent.click(screen.getByText('提取这个视频里的人声'))
    await waitFor(() => expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument())

    // Clicking "新对话" with content opens a confirm popover — it must NOT clear yet.
    fireEvent.click(screen.getByRole('button', { name: '新对话' }))
    expect(screen.getByRole('dialog', { name: '开始新对话？' })).toBeInTheDocument()
    expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument()

    // Confirming clears the conversation back to the empty greeting state.
    fireEvent.click(screen.getByText('新建'))
    await waitFor(() => expect(screen.queryByTestId('call-chain-diagram')).not.toBeInTheDocument())
    expect(screen.getByText('识别这个视频的日语字幕并转成中文字幕')).toBeInTheDocument()
  })

  it('keeps the conversation when the new-chat confirm is dismissed', async () => {
    apiMocks.plan.mockResolvedValue(RUNNABLE_RESULT)
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))
    fireEvent.click(screen.getByText('提取这个视频里的人声'))
    await waitFor(() => expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: '新对话' }))
    fireEvent.click(screen.getByText('取消'))

    expect(screen.queryByRole('dialog', { name: '开始新对话？' })).not.toBeInTheDocument()
    expect(screen.getByTestId('call-chain-diagram')).toBeInTheDocument()
  })

  it('shows a setup banner and disables sending when the DeepSeek key is missing', async () => {
    apiMocks.getLlmKeys.mockResolvedValue({ ok: true, providers: { deepseek: false }, base_urls: {} })
    renderWidget()
    fireEvent.click(screen.getByLabelText('打开 AI 助手'))

    await waitFor(() => expect(screen.getByText('尚未配置 DeepSeek')).toBeInTheDocument())
    expect(screen.getByText('去设置').closest('a')).toHaveAttribute('href', '/settings')
    expect(screen.getByLabelText('发送')).toBeDisabled()
  })
})
