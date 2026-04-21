import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { WorkflowNodeDrawer } from '../WorkflowNodeDrawer'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('WorkflowNodeDrawer', () => {
  it('keeps the node detail drawer free of large panel shadow styling', () => {
    render(
      <I18nProvider>
        <WorkflowNodeDrawer
          node={{
            id: 'task-e',
            label: 'Task E',
            group: 'audio-spine',
            required: true,
            status: 'running',
            progress_percent: 65,
            elapsed_sec: 12,
          }}
          artifacts={[]}
          onClose={() => {}}
        />
      </I18nProvider>,
    )

    expect(screen.getByText('节点详情')).toBeInTheDocument()
    expect((screen.getByText('节点详情').closest('aside') as HTMLElement).className).not.toContain('shadow')
  })

  it('expands a wav artifact into an inline audio player', () => {
    const { container } = render(
      <I18nProvider>
        <WorkflowNodeDrawer
          node={{
            id: 'task-d',
            label: 'Task D',
            group: 'audio-spine',
            required: true,
            status: 'succeeded',
            progress_percent: 100,
          }}
          artifacts={[{ path: 'task-d/spk_0000/seg-0001.wav', size_bytes: 146_000, suffix: '.wav' }]}
          taskId="task-1"
          onClose={() => {}}
        />
      </I18nProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: '播放 seg-0001.wav' }))

    const audio = container.querySelector('audio')
    expect(audio).toBeInTheDocument()
    expect(audio).toHaveAttribute('controls')
    expect(audio).toHaveAttribute('src', '/api/tasks/task-1/artifacts/task-d/spk_0000/seg-0001.wav?preview=1')
  })

  it('loads and formats a json artifact inline', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('{"segments":[{"id":"seg-1","text":"hello"}]}'),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <I18nProvider>
        <WorkflowNodeDrawer
          node={{
            id: 'task-a',
            label: 'Task A',
            group: 'audio-spine',
            required: true,
            status: 'succeeded',
            progress_percent: 100,
          }}
          artifacts={[{ path: 'task-a/voice/segments.zh.json', size_bytes: 540, suffix: '.json' }]}
          taskId="task-1"
          onClose={() => {}}
        />
      </I18nProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: '查看 segments.zh.json' }))

    await screen.findByText(/"segments":/)
    expect(screen.getByText(/"text": "hello"/)).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/tasks/task-1/artifacts/task-a/voice/segments.zh.json?preview=1')
    })
  })

  it('collapses an expanded json artifact when clicked again', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve('{"segments":[{"id":"seg-1","text":"hello"}]}'),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <I18nProvider>
        <WorkflowNodeDrawer
          node={{
            id: 'task-a',
            label: 'Task A',
            group: 'audio-spine',
            required: true,
            status: 'succeeded',
            progress_percent: 100,
          }}
          artifacts={[{ path: 'task-a/voice/segments.zh.json', size_bytes: 540, suffix: '.json' }]}
          taskId="task-1"
          onClose={() => {}}
        />
      </I18nProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: '查看 segments.zh.json' }))

    await screen.findByText(/"text": "hello"/)

    fireEvent.click(screen.getByRole('button', { name: '查看 segments.zh.json' }))

    expect(screen.queryByText(/"text": "hello"/)).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
