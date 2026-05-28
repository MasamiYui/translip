import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import type { WorkflowGraph as WorkflowGraphPayload } from '../../../types'
import { WorkflowGraph } from '../WorkflowGraph'

const graph: WorkflowGraphPayload = {
  workflow: { template_id: 'asr-dub+ocr-subs', status: 'running' },
  nodes: [
    { id: 'stage1', label: 'Stage 1', group: 'audio-spine', required: true, status: 'succeeded', progress_percent: 100 },
    { id: 'ocr-detect', label: 'OCR Detect', group: 'ocr-subtitles', required: true, status: 'running', progress_percent: 55 },
    { id: 'task-g', label: 'Task G', group: 'delivery', required: true, status: 'pending', progress_percent: 0 },
  ],
  edges: [
    { from: 'stage1', to: 'task-g', state: 'inactive' },
    { from: 'ocr-detect', to: 'task-g', state: 'active' },
  ],
}

describe('WorkflowGraph', () => {
  it('renders lanes, nodes, and legend content', () => {
    render(
      <I18nProvider>
        <WorkflowGraph graph={graph} showLegend />
      </I18nProvider>,
    )

    expect(screen.getByText('音频主干')).toBeInTheDocument()
    expect(screen.getByText('OCR 字幕线')).toBeInTheDocument()
    expect(screen.getByText('交付线')).toBeInTheDocument()
    expect(screen.getByText('字幕定位')).toBeInTheDocument()
    expect(screen.getByText('状态图例')).toBeInTheDocument()
  })
})
