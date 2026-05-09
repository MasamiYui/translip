import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { dubbingEditorApi } from '../../api/dubbing-editor'
import type { DubbingEditorProject } from '../../api/dubbing-editor'
import { tasksApi } from '../../api/tasks'
import { I18nProvider } from '../../i18n/I18nProvider'
import { DubbingEditorPage } from '../DubbingEditorPage'

vi.mock('../../api/dubbing-editor', () => ({
  dubbingEditorApi: {
    getProject: vi.fn(),
    replayTo: vi.fn(),
    saveOperations: vi.fn(),
    renderRange: vi.fn(),
    getWaveform: vi.fn(),
    getClipPreview: vi.fn(),
    synthesizeUnit: vi.fn(),
    assignCharacterVoice: vi.fn(),
    getBacktranslation: vi.fn(),
  },
}))

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    get: vi.fn(),
  },
}))

const STORAGE_KEY = 'translip:dubbing-editor-layout'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter initialEntries={['/tasks/task-layout/dubbing-editor']}>
            <Routes>
              <Route path="/tasks/:id/dubbing-editor" element={children} />
            </Routes>
          </MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

function mockProject(): DubbingEditorProject {
  return {
    version: 'v1',
    created_at: '2026-05-09T00:00:00Z',
    task_id: 'task-layout',
    target_lang: 'en',
    status: 'ready',
    source_video_path: '/tmp/source.mp4',
    artifact_paths: { final_dub: 'task-g/final-dub/final_dub.en.mp4' },
    quality_benchmark: {
      version: 'v1',
      status: 'review_required',
      score: 72,
      reasons: [],
      metrics: {},
      gates: [],
    },
    characters: [
      {
        character_id: 'char-nana',
        display_name: 'Nana',
        speaker_ids: ['SPEAKER_00'],
        review_status: 'passed',
        risk_flags: [],
        pitch_class: 'mid',
        pitch_hz: 220,
        stats: {
          segment_count: 1,
          speaker_failed_count: 0,
          overall_failed_count: 0,
          voice_mismatch_count: 0,
          speaker_failed_ratio: 0,
        },
        voice_lock: false,
        default_voice: { backend: 'qwen', reference_path: null },
      },
    ],
    units: [
      {
        unit_id: 'unit-1',
        source_segment_ids: ['seg-1'],
        speaker_id: 'SPEAKER_00',
        character_id: 'char-nana',
        start: 1,
        end: 3,
        duration: 2,
        source_text: '娜娜你在哪儿啊',
        target_text: 'Nana, where are you?',
        status: 'unreviewed',
        issue_ids: ['issue-1'],
        current_clip: {
          clip_id: 'clip-1',
          audio_path: null,
          audio_artifact_path: null,
          duration: 2.1,
          backend: 'qwen',
          mix_status: 'mixed',
          fit_strategy: 'compress',
        },
        candidates: [],
      },
    ],
    issues: [
      {
        issue_id: 'issue-1',
        type: 'duration_overrun',
        severity: 'P1',
        unit_id: 'unit-1',
        character_id: 'char-nana',
        title: '时长超出',
        description: '配音片段略长',
        status: 'open',
        time_sec: 1,
      },
    ],
    operations: [],
    summary: {
      unit_count: 1,
      character_count: 1,
      issue_count: 1,
      p0_count: 0,
      candidate_count: 0,
      approved_count: 0,
      char_review_count: 0,
      quality_status: 'review_required',
      quality_score: 72,
    },
  }
}

describe('DubbingEditorPage resizable workbench layout', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    window.localStorage.clear()
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
      return window.setTimeout(() => callback(performance.now()), 16)
    })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => {
      window.clearTimeout(id)
    })
    vi.mocked(dubbingEditorApi.getProject).mockResolvedValue(mockProject())
    vi.mocked(dubbingEditorApi.getWaveform).mockResolvedValue({
      track: 'original',
      peaks: [0.1, 0.4, 0.2, 0.8],
      duration_sec: 4,
      available: true,
    })
    vi.mocked(tasksApi.get).mockResolvedValue({ id: 'task-layout', name: '任务-14:52' } as never)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    cleanup()
  })

  it('collapses both edit side panels and restores them from layout presets', async () => {
    render(<DubbingEditorPage />, { wrapper: createWrapper() })

    expect(await screen.findByTestId('issue-queue-panel')).toBeInTheDocument()
    expect(screen.getByTestId('inspector-panel-shell')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-inspector-panel'))
    expect(screen.queryByTestId('inspector-panel-shell')).not.toBeInTheDocument()
    expect(screen.getByTestId('inspector-panel-rail')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-issue-queue-panel'))
    expect(screen.queryByTestId('issue-queue-panel')).not.toBeInTheDocument()
    expect(screen.getByTestId('issue-queue-rail')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('layout-preset-review'))
    expect(await screen.findByTestId('issue-queue-panel')).toBeInTheDocument()
    expect(screen.getByTestId('inspector-panel-shell')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('layout-preset-timeline'))
    expect(screen.getByTestId('issue-queue-rail')).toBeInTheDocument()
    expect(screen.getByTestId('inspector-panel-rail')).toBeInTheDocument()
    expect(screen.getByTestId('timeline-header')).toBeVisible()
  })

  it('resizes side panels with drag handles and persists the layout', async () => {
    render(<DubbingEditorPage />, { wrapper: createWrapper() })

    const leftPanel = await screen.findByTestId('issue-queue-panel')
    const rightPanel = screen.getByTestId('inspector-panel-shell')

    expect(leftPanel).toHaveStyle({ width: '300px' })
    expect(rightPanel).toHaveStyle({ width: '380px' })

    fireEvent.mouseDown(screen.getByTestId('resize-issue-queue-panel'), { clientX: 300 })
    fireEvent.mouseMove(document, { clientX: 360 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      expect(screen.getByTestId('issue-queue-panel')).toHaveStyle({ width: '360px' })
    })

    fireEvent.mouseDown(screen.getByTestId('resize-inspector-panel'), { clientX: 1500 })
    fireEvent.mouseMove(document, { clientX: 1440 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      expect(screen.getByTestId('inspector-panel-shell')).toHaveStyle({ width: '440px' })
    })

    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}')).toMatchObject({
      leftWidth: 360,
      rightWidth: 440,
      leftOpen: true,
      rightOpen: true,
    })
  })
})
