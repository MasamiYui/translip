import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { CallChainDiagram } from '../CallChainDiagram'
import type { AssistantPlan, RunState } from '../../../types/assistant'

const PLAN: AssistantPlan = {
  summary: '分离人声后转写',
  steps: [
    {
      id: 'sep',
      tool_id: 'separation',
      title: '人声分离',
      rationale: '去掉背景音',
      params: { quality: 'balanced' },
      inputs: { file_id: { source: 'upload', upload_index: 0 } },
    },
    {
      id: 'asr',
      tool_id: 'transcription',
      title: '语音转写',
      rationale: '转成文本',
      params: { language: 'ja' },
      inputs: { file_id: { source: 'step', step_id: 'sep', output: 'voice_file' } },
    },
  ],
  edges: [{ source: 'sep', target: 'asr' }],
}

function renderDiagram(props: Partial<React.ComponentProps<typeof CallChainDiagram>> = {}) {
  return render(
    <I18nProvider>
      <CallChainDiagram plan={PLAN} {...props} />
    </I18nProvider>,
  )
}

afterEach(cleanup)

describe('CallChainDiagram', () => {
  it('renders one node per step with its title and params', () => {
    renderDiagram()
    expect(screen.getByTestId('chain-node-sep')).toBeInTheDocument()
    expect(screen.getByTestId('chain-node-asr')).toBeInTheDocument()
    expect(screen.getByText('人声分离')).toBeInTheDocument()
    expect(screen.getByText('language: ja')).toBeInTheDocument()
  })

  it('reflects live run status on nodes', () => {
    const runState: RunState = {
      run_id: 'r1',
      status: 'running',
      message: '',
      summary: '',
      steps: [
        { id: 'sep', tool_id: 'separation', title: '人声分离', status: 'completed', progress_percent: 100, artifacts: [] },
        { id: 'asr', tool_id: 'transcription', title: '语音转写', status: 'running', progress_percent: 40, artifacts: [] },
      ],
    }
    renderDiagram({ runState })
    expect(screen.getByTestId('chain-node-sep')).toHaveAttribute('data-status', 'completed')
    expect(screen.getByTestId('chain-node-asr')).toHaveAttribute('data-status', 'running')
  })

  it('renders all nodes in vertical orientation', () => {
    renderDiagram({ orientation: 'vertical' })
    const diagram = screen.getByTestId('call-chain-diagram')
    expect(diagram).toHaveAttribute('data-orientation', 'vertical')
    expect(screen.getByTestId('chain-node-sep')).toBeInTheDocument()
    expect(screen.getByTestId('chain-node-asr')).toBeInTheDocument()
  })

  it('allows editing a param when editable and calls onChange', () => {
    const onChange = vi.fn()
    renderDiagram({ editable: true, onChange })
    // open the editor on the first step
    fireEvent.click(screen.getAllByText(/编辑参数/)[0])
    const input = screen.getByLabelText('quality') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'quality-high' } })
    expect(onChange).toHaveBeenCalled()
    const updated = onChange.mock.calls.at(-1)?.[0] as AssistantPlan
    expect(updated.steps[0].params.quality).toBe('quality-high')
  })
})
