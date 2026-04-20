import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import type { WorkflowGraph as WorkflowGraphPayload } from '../../../types'
import { PipelineGraph } from '../PipelineGraph'

const graph: WorkflowGraphPayload = {
  workflow: { template_id: 'asr-dub+ocr-subs', status: 'running' },
  nodes: [
    {
      id: 'stage1',
      label: 'Stage 1',
      group: 'audio-spine',
      required: true,
      status: 'succeeded',
      progress_percent: 100,
    },
    {
      id: 'task-a',
      label: 'Task A',
      group: 'audio-spine',
      required: true,
      status: 'running',
      progress_percent: 42,
      current_step: '正在对齐语音片段',
    },
    {
      id: 'task-g',
      label: 'Task G',
      group: 'delivery',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
  ],
  edges: [
    { from: 'stage1', to: 'task-a', state: 'completed' },
    { from: 'task-a', to: 'task-g', state: 'active' },
  ],
}

const previewGraph: WorkflowGraphPayload = {
  workflow: { template_id: 'asr-dub+ocr-subs', status: 'pending' },
  nodes: [
    {
      id: 'stage1',
      label: 'Stage 1',
      group: 'audio-spine',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'task-a',
      label: 'Task A',
      group: 'audio-spine',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'task-g',
      label: 'Task G',
      group: 'delivery',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
  ],
  edges: [
    { from: 'stage1', to: 'task-a', state: 'inactive' },
    { from: 'task-a', to: 'task-g', state: 'inactive' },
  ],
}

const previewGraphWithCorrection: WorkflowGraphPayload = {
  workflow: { template_id: 'asr-dub+ocr-subs', status: 'pending' },
  nodes: [
    {
      id: 'stage1',
      label: 'Stage 1',
      group: 'audio-spine',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'ocr-detect',
      label: 'OCR Detect',
      group: 'ocr-subtitles',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'task-a',
      label: 'Task A',
      group: 'audio-spine',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'asr-ocr-correct',
      label: 'ASR OCR Correct',
      group: 'audio-spine',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'task-b',
      label: 'Task B',
      group: 'audio-spine',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
    {
      id: 'task-g',
      label: 'Task G',
      group: 'delivery',
      required: true,
      status: 'pending',
      progress_percent: 0,
    },
  ],
  edges: [
    { from: 'stage1', to: 'task-a', state: 'inactive' },
    { from: 'ocr-detect', to: 'asr-ocr-correct', state: 'inactive' },
    { from: 'task-a', to: 'asr-ocr-correct', state: 'inactive' },
    { from: 'asr-ocr-correct', to: 'task-b', state: 'inactive' },
    { from: 'task-b', to: 'task-g', state: 'inactive' },
  ],
}

describe('PipelineGraph', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders pending template previews inside a zoomable flow canvas without runtime metadata', () => {
    render(
      <I18nProvider>
        <PipelineGraph graph={previewGraph} compact />
      </I18nProvider>,
    )

    const graphRoot = document.querySelector('[data-ui-layout="unified-dag"]')

    expect(graphRoot).not.toBeNull()
    expect(screen.getAllByRole('application')).toHaveLength(1)
    expect(screen.queryByText('等待中')).not.toBeInTheDocument()
    expect(screen.queryByText('状态')).not.toBeInTheDocument()
    expect(screen.queryByText('进度')).not.toBeInTheDocument()
    expect(graphRoot?.querySelector('[data-ui-band]')).toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="start"]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="end"]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="start"] [data-ui-anchor-size="xl"]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="end"] [data-ui-anchor-size="xl"]')).not.toBeNull()
    expect(screen.getByText('音频分离').closest('button')?.getAttribute('data-ui-elevation')).toBe('flat')
    expect(screen.getByText('音频分离').closest('button')?.querySelector('[data-ui-node-icon="corner"]')).not.toBeNull()
    expect(screen.getByText('音频分离').closest('button')?.querySelector('[data-ui-title-scale="xl"]')).not.toBeNull()
    expect(screen.getByText('音频分离').closest('button')?.querySelector('.absolute.inset-y-3.left-0')).toBeNull()
    expect(screen.getAllByText('视频交付')[0].closest('button')?.getAttribute('data-ui-card-size')).toBe('matched')
    expect(screen.queryByText('拆分人声与背景轨。')).not.toBeInTheDocument()
    expect(screen.getByText('悬停节点可查看说明，点击节点可锁定。')).toBeInTheDocument()
    expect(screen.queryByText('最终交付包')).not.toBeInTheDocument()
    expect(screen.getByText('音频分离').closest('button')?.querySelector('[data-ui-title-scale="xl"]')).toHaveClass('text-center')
    expect(screen.getByText('音频分离').closest('button')?.querySelector('[data-ui-title-frame]')).toHaveClass('items-center', 'justify-center')
  })

  it('renders the OCR correction node with compact metadata instead of the raw node id', () => {
    render(
      <I18nProvider>
        <PipelineGraph graph={previewGraphWithCorrection} compact />
      </I18nProvider>,
    )

    const correctionNode = screen.getByText('文稿校正').closest('button')
    const flowNode = correctionNode?.closest('.react-flow__node')

    expect(correctionNode).not.toBeNull()
    expect(correctionNode).toHaveTextContent('A2')
    expect(correctionNode).not.toHaveTextContent('asr-ocr-correct')
    expect(correctionNode?.querySelector('[data-ui-title-frame]')).toHaveClass('items-center', 'justify-center')
    expect(flowNode?.getAttribute('style')).not.toContain('translate(0px, 0px)')
  })

  it('shows lane headers and stage detail text in compact preview mode', () => {
    render(
      <I18nProvider>
        <PipelineGraph graph={graph} compact activeStage="task-a" />
      </I18nProvider>,
    )

    const graphRoot = document.querySelector('[data-ui-layout="unified-dag"]')

    expect(graphRoot).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="start"]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="end"]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="start"] [data-ui-anchor-size="xl"]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-anchor="end"] [data-ui-anchor-size="xl"]')).not.toBeNull()
    expect(screen.getByText('正在对齐语音片段')).toBeInTheDocument()
    const runningNode = screen.getAllByText('语音转写')[0].closest('button')

    expect(screen.getAllByText(/运行中/).length).toBeGreaterThan(0)
    expect(runningNode?.getAttribute('data-ui-elevation')).toBe('flat')
    expect(runningNode?.querySelector('[data-ui-title-scale="xl"]')).not.toBeNull()
    expect(runningNode?.querySelector('[data-ui-status-chip]')).toBeNull()
    expect(runningNode?.querySelector('[data-ui-status-rail]')).toBeNull()
    expect(runningNode?.querySelector('[data-ui-status-marker]')).not.toBeNull()
    expect(runningNode?.querySelector('[data-ui-progress-bar]')).not.toBeNull()
    expect(screen.getAllByText('视频交付')[0].closest('button')?.getAttribute('data-ui-card-size')).toBe('matched')
    expect(screen.queryByText('最终交付包')).not.toBeInTheDocument()
    expect(screen.queryByText('生成时间对齐转写。')).not.toBeInTheDocument()
    expect(runningNode?.querySelector('[data-ui-title-scale="xl"]')).toHaveClass('text-center')
    expect(runningNode?.querySelector('[data-ui-title-frame]')).toHaveClass('items-center', 'justify-center')
  })

  it('renders runtime graphs with the unified dag layout in full mode', () => {
    render(
      <I18nProvider>
        <PipelineGraph graph={graph} activeStage="task-a" showLegend />
      </I18nProvider>,
    )

    const graphRoot = document.querySelector('[data-ui-layout="unified-dag"]')

    expect(graphRoot).not.toBeNull()
    expect(screen.getByText('状态图例')).toBeInTheDocument()
    expect(screen.getByText('正在对齐语音片段')).toBeInTheDocument()
    expect(screen.getAllByText(/运行中/).length).toBeGreaterThan(0)
    expect(graphRoot?.querySelector('[data-ui-focus-rail]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-focus-status]')).not.toBeNull()
    expect(graphRoot?.querySelector('[data-ui-focus-status-chip]')).toBeNull()
    expect(graphRoot?.querySelector('[data-ui-focus-icon-frame]')).toBeNull()
    expect(graphRoot?.querySelector('[data-ui-focus-icon="inline"]')).not.toBeNull()
    expect(screen.queryByText('生成时间对齐转写。')).not.toBeInTheDocument()
  })

  it('reveals node details in the focus rail when hovering a compact node', () => {
    render(
      <I18nProvider>
        <PipelineGraph graph={previewGraph} compact />
      </I18nProvider>,
    )

    const audioNode = screen.getAllByText('音频分离').at(-1)?.closest('button')

    expect(audioNode).not.toBeNull()
    expect(screen.queryByText('拆分人声与背景轨。')).not.toBeInTheDocument()

    fireEvent.mouseEnter(audioNode!)

    expect(screen.getByText('拆分人声与背景轨。')).toBeInTheDocument()
  })
})
