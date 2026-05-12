import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { tasksApi } from '../../../api/tasks'
import type { SpeakerReviewResponse, SuggestFromGlobalCandidate } from '../../../types'
import { SpeakerReviewDrawer } from '../SpeakerReviewDrawer'

vi.mock('../../../api/tasks', () => ({
  tasksApi: {
    getSpeakerReview: vi.fn(),
    saveSpeakerReviewDecision: vi.fn(),
    deleteSpeakerReviewDecision: vi.fn(),
    applySpeakerReviewDecisions: vi.fn(),
    createSpeakerPersona: vi.fn(),
    updateSpeakerPersona: vi.fn(),
    suggestPersonasFromGlobal: vi.fn(),
    importPersonasFromGlobal: vi.fn(),
    exportTaskPersonasToGlobal: vi.fn(),
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  }
}

function mockReview(): SpeakerReviewResponse {
  return {
    task_id: 'task-speaker-video',
    status: 'available',
    summary: {
      segment_count: 3,
      speaker_count: 2,
      high_risk_speaker_count: 0,
      speaker_run_count: 3,
      review_run_count: 1,
      high_risk_run_count: 0,
      review_segment_count: 1,
      decision_count: 0,
      corrected_exists: false,
      unnamed_speaker_count: 2,
    },
    artifact_paths: {},
    speakers: [
      {
        speaker_label: 'SPEAKER_00',
        segment_count: 2,
        segment_ids: ['seg-1', 'seg-3'],
        total_speech_sec: 5,
        avg_duration_sec: 2.5,
        short_segment_count: 0,
        risk_flags: [],
        risk_level: 'low',
        cloneable_by_default: true,
        reference_clips: [],
        similar_peers: [],
      },
      {
        speaker_label: 'SPEAKER_01',
        segment_count: 1,
        segment_ids: ['seg-2'],
        total_speech_sec: 2,
        avg_duration_sec: 2,
        short_segment_count: 0,
        risk_flags: ['single_segment_speaker'],
        risk_level: 'high',
        cloneable_by_default: false,
        reference_clips: [],
        similar_peers: [],
      },
    ],
    speaker_runs: [],
    segments: [
      {
        segment_id: 'seg-1',
        index: 1,
        speaker_label: 'SPEAKER_00',
        start: 1,
        end: 3,
        duration: 2,
        text: '第一句台词',
        next_speaker_label: 'SPEAKER_01',
        risk_flags: [],
        risk_level: 'low',
      },
      {
        segment_id: 'seg-2',
        index: 2,
        speaker_label: 'SPEAKER_01',
        start: 3.2,
        end: 5.2,
        duration: 2,
        text: '需要改人的台词',
        previous_speaker_label: 'SPEAKER_00',
        next_speaker_label: 'SPEAKER_00',
        risk_flags: ['speaker_boundary_risk'],
        risk_level: 'medium',
        recommended_action: 'relabel_to_previous_speaker',
      },
      {
        segment_id: 'seg-3',
        index: 3,
        speaker_label: 'SPEAKER_00',
        start: 5.6,
        end: 8,
        duration: 2.4,
        text: '第三句台词',
        previous_speaker_label: 'SPEAKER_01',
        risk_flags: [],
        risk_level: 'low',
      },
    ],
    similarity: {
      labels: ['SPEAKER_00', 'SPEAKER_01'],
      matrix: [
        [1, 0.4],
        [0.4, 1],
      ],
      threshold_suggest_merge: 0.55,
    },
    review_plan: { items: [] },
    decisions: [],
    personas: {
      items: [],
      unassigned_bindings: ['SPEAKER_00', 'SPEAKER_01'],
      by_speaker: {
        SPEAKER_00: { persona_id: null, name: null, color: null, avatar_emoji: null },
        SPEAKER_01: { persona_id: null, name: null, color: null, avatar_emoji: null },
      },
    },
    manifest: {},
  }
}

describe('SpeakerReviewDrawer video review workbench', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(tasksApi.getSpeakerReview).mockResolvedValue(mockReview())
    vi.mocked(tasksApi.saveSpeakerReviewDecision).mockResolvedValue({
      ok: true,
      item_id: 'seg-2',
      decision: 'relabel',
      path: 'manual_speaker_decisions.zh.json',
      decision_count: 1,
    })
    vi.mocked(tasksApi.applySpeakerReviewDecisions).mockResolvedValue({
      ok: true,
      path: 'segments.zh.speaker-corrected.json',
      srt_path: 'segments.zh.speaker-corrected.srt',
      manifest_path: 'speaker-review-manifest.json',
      summary: { changed_segment_count: 1 },
      applied_at: '2026-05-09T00:00:00+08:00',
    })
    vi.mocked(tasksApi.createSpeakerPersona).mockResolvedValue({
      ok: true,
      persona: {
        id: 'persona-1',
        name: '女主',
        bindings: ['SPEAKER_01'],
      },
      personas: {
        items: [],
        unassigned_bindings: [],
        by_speaker: {},
      },
    })
    vi.mocked(tasksApi.updateSpeakerPersona).mockResolvedValue({
      ok: true,
      persona: {
        id: 'persona-1',
        name: '女主',
        bindings: ['SPEAKER_01'],
      },
      personas: {
        items: [],
        unassigned_bindings: [],
        by_speaker: {},
      },
    })
    vi.mocked(tasksApi.deleteSpeakerReviewDecision).mockResolvedValue({ ok: true })
    vi.mocked(tasksApi.suggestPersonasFromGlobal).mockResolvedValue({
      ok: true,
      matches: [],
    })
    vi.mocked(tasksApi.importPersonasFromGlobal).mockResolvedValue({
      ok: true,
      imported: [],
      conflicts: [],
      personas: { items: [], unassigned_bindings: [], by_speaker: {} },
    })
    vi.mocked(tasksApi.exportTaskPersonasToGlobal).mockResolvedValue({
      ok: true,
      exported: [],
      skipped: [],
      total: 0,
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders the source video and complete transcript track', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    const video = await screen.findByTestId('speaker-review-video')
    expect(video).toHaveAttribute(
      'src',
      '/api/tasks/task-speaker-video/dubbing-editor/video-preview',
    )
    expect(screen.getByTestId('transcript-row-seg-1')).toHaveTextContent('第一句台词')
    expect(screen.getByTestId('transcript-row-seg-2')).toHaveTextContent('需要改人的台词')
    expect(screen.getByTestId('transcript-row-seg-3')).toHaveTextContent('第三句台词')
  })

  it('keeps the application sidebar and header chrome visible', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    const drawer = await screen.findByTestId('speaker-review-drawer')

    expect(drawer).toHaveClass('md:left-[var(--sidebar-offset,220px)]')
    expect(drawer).toHaveClass('top-[var(--app-header-height,60px)]')
    expect(drawer).toHaveClass('z-20')
    expect(drawer).not.toHaveClass('inset-0')
    expect(drawer).not.toHaveClass('z-50')
  })

  it('seeks the video when a transcript row is selected and shows speaker choices', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    const video = await screen.findByTestId('speaker-review-video') as HTMLVideoElement
    Object.defineProperty(video, 'currentTime', { configurable: true, writable: true, value: 0 })

    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    expect(video.currentTime).toBeCloseTo(3.21)
    expect(await screen.findByTestId('speaker-choice-SPEAKER_01')).toBeInTheDocument()
    expect(screen.getByTestId('speaker-choice-SPEAKER_00')).toBeInTheDocument()
  })

  it('explains the active segment risk level and risk flags', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    expect(screen.getByTestId('transcript-row-seg-2')).toHaveTextContent('中风险')
    const riskSummary = screen.getByTestId('active-risk-summary')
    expect(riskSummary).toHaveTextContent('风险等级')
    expect(riskSummary).toHaveTextContent('中风险')
    expect(riskSummary).toHaveTextContent('风险点')
    expect(riskSummary).toHaveTextContent('边界风险')
  })

  it('translates system recommendation action codes', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    expect(screen.getByTestId('system-recommendation')).toHaveTextContent('归到上一句说话人')
    expect(screen.queryByText('relabel_to_previous_speaker')).not.toBeInTheDocument()
  })

  it('uses number keys to relabel the active segment during review', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))
    fireEvent.keyDown(window, { key: '2' })

    await waitFor(() => {
      expect(tasksApi.saveSpeakerReviewDecision).toHaveBeenCalledWith('task-speaker-video', {
        item_id: 'seg-2',
        item_type: 'segment',
        decision: 'relabel',
        source_speaker_label: 'SPEAKER_01',
        target_speaker_label: 'SPEAKER_00',
        segment_ids: ['seg-2'],
        payload: {
          source_speaker: 'SPEAKER_01',
          target_speaker: 'SPEAKER_00',
          source: 'video_timeline',
        },
      })
    })
  })

  it('confirms the current speaker without relabeling', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))
    fireEvent.click(screen.getByTestId('action-keep-current'))

    await waitFor(() => {
      expect(tasksApi.saveSpeakerReviewDecision).toHaveBeenCalledWith('task-speaker-video', {
        item_id: 'seg-2',
        item_type: 'segment',
        decision: 'keep_independent',
        source_speaker_label: 'SPEAKER_01',
        segment_ids: ['seg-2'],
        payload: {
          source_speaker: 'SPEAKER_01',
          source: 'video_timeline',
        },
      })
    })
  })

  it('renames the active speaker by creating a bound persona', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))
    fireEvent.click(await screen.findByTestId('rename-active-speaker'))
    fireEvent.change(screen.getByTestId('rename-active-speaker-input'), {
      target: { value: '女主' },
    })
    fireEvent.keyDown(screen.getByTestId('rename-active-speaker-input'), { key: 'Enter' })

    await waitFor(() => {
      expect(tasksApi.createSpeakerPersona).toHaveBeenCalledWith('task-speaker-video', {
        name: '女主',
        bindings: ['SPEAKER_01'],
      })
    })
  })

  it('renders filter tabs with correct counts and supports filtering segments', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    expect(screen.getByTestId('filter-tab-all')).toHaveTextContent('3')
    expect(screen.getByTestId('filter-tab-undecided')).toHaveTextContent('3')
    expect(screen.getByTestId('filter-tab-risk')).toHaveTextContent('1')
    expect(screen.getByTestId('filter-tab-decided')).toHaveTextContent('0')

    fireEvent.click(screen.getByTestId('filter-tab-risk'))
    expect(screen.getByTestId('transcript-row-seg-2')).toBeInTheDocument()
    expect(screen.queryByTestId('transcript-row-seg-1')).not.toBeInTheDocument()
    expect(screen.queryByTestId('transcript-row-seg-3')).not.toBeInTheDocument()
  })

  it('exposes auto-advance toggle (default on)', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    const toggle = (await screen.findByTestId('toggle-auto-advance')) as HTMLInputElement
    expect(toggle.checked).toBe(true)
    fireEvent.click(toggle)
    expect(toggle.checked).toBe(false)
  })

  it('toggles loop button via L key and reflects state', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))
    const loopButton = await screen.findByTestId('toggle-loop-active')
    expect(loopButton).toHaveAttribute('aria-pressed', 'false')
    fireEvent.keyDown(window, { key: 'l' })
    expect(loopButton).toHaveAttribute('aria-pressed', 'true')
    expect(loopButton).toHaveTextContent('循环中')
  })

  it('shows undo button after a decision is saved and calls deleteSpeakerReviewDecision', async () => {
    const review = mockReview()
    review.segments[1] = {
      ...review.segments[1],
      decision: {
        item_id: 'seg-2',
        item_type: 'segment',
        decision: 'relabel',
        source_speaker_label: 'SPEAKER_01',
        target_speaker_label: 'SPEAKER_00',
        segment_ids: ['seg-2'],
        payload: {},
      },
    }
    vi.mocked(tasksApi.getSpeakerReview).mockResolvedValue(review)

    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))
    const undoButton = await screen.findByTestId('undo-active-decision')
    fireEvent.click(undoButton)

    await waitFor(() => {
      expect(tasksApi.deleteSpeakerReviewDecision).toHaveBeenCalledWith(
        'task-speaker-video',
        'seg-2',
      )
    })
  })

  it('hides risk details for low-risk segments unless expanded', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-1'))
    expect(screen.queryByTestId('active-risk-summary')).not.toBeInTheDocument()
    expect(screen.getByTestId('toggle-risk-details')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-risk-details'))
    expect(screen.getByTestId('active-risk-summary')).toBeInTheDocument()
  })

  it('renders the character library match card with empty placeholder when no match', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    expect(await screen.findByTestId('character-library-match-card')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-empty')).toBeInTheDocument()
    expect(screen.getByTestId('refresh-character-library')).toBeInTheDocument()
    expect(screen.getByTestId('push-to-character-library')).toBeInTheDocument()
  })

  it('shows the task work binding and marks same-work character candidates', async () => {
    const review = mockReview() as SpeakerReviewResponse & {
      work_binding: {
        work_id: string
        episode_label: string
        work: { id: string; title: string }
        candidates: unknown[]
      }
    }
    review.work_binding = {
      work_id: 'work_nezha',
      episode_label: 'E03',
      work: { id: 'work_nezha', title: '哪吒之魔童闹海', type: 'movie' },
      candidates: [],
    }
    vi.mocked(tasksApi.getSpeakerReview).mockResolvedValue(review)
    vi.mocked(tasksApi.suggestPersonasFromGlobal).mockResolvedValue({
      ok: true,
      matches: [
        {
          speaker_label: 'SPEAKER_01',
          candidates: [
            {
              persona_id: 'p-nezha',
              name: 'Young Nezha',
              score: 0.45,
              reason: '当前作品',
              role: '主角',
              work_id: 'work_nezha',
            } satisfies SuggestFromGlobalCandidate,
          ],
        },
      ],
    })

    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    expect(await screen.findByTestId('speaker-review-work-binding')).toHaveTextContent(
      '哪吒之魔童闹海',
    )
    expect(screen.getByTestId('speaker-review-work-binding')).toHaveTextContent('E03')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    const candidate = await screen.findByTestId('character-library-candidate-p-nezha')
    expect(candidate).toHaveTextContent('Young Nezha')
    expect(candidate).toHaveTextContent('当前作品')
  })

  it('does not keep rematching global personas after the initial candidate load', async () => {
    vi.mocked(tasksApi.suggestPersonasFromGlobal).mockResolvedValue({
      ok: true,
      matches: [
        {
          speaker_label: 'SPEAKER_01',
          candidates: [
            { persona_id: 'p-once', name: '一次匹配', score: 0.8, reason: '当前作品', work_id: 'work_nezha' },
          ],
        },
      ],
    })

    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    await waitFor(() => {
      expect(tasksApi.suggestPersonasFromGlobal).toHaveBeenCalledTimes(1)
    })
    await new Promise(resolve => window.setTimeout(resolve, 100))
    expect(tasksApi.suggestPersonasFromGlobal).toHaveBeenCalledTimes(1)
  })

  it('shows every same-work character candidate returned for the active speaker', async () => {
    vi.mocked(tasksApi.suggestPersonasFromGlobal).mockResolvedValue({
      ok: true,
      matches: [
        {
          speaker_label: 'SPEAKER_01',
          candidates: [
            { persona_id: 'p-young', name: 'Young Nezha', score: 0.45, reason: '当前作品', work_id: 'work_nezha' },
            { persona_id: 'p-youth', name: 'Youth Nezha', score: 0.45, reason: '当前作品', work_id: 'work_nezha' },
            { persona_id: 'p-ao-bing', name: 'Ao Bing', score: 0.45, reason: '当前作品', work_id: 'work_nezha' },
            { persona_id: 'p-li-jing', name: 'Li Jing', score: 0.45, reason: '当前作品', work_id: 'work_nezha' },
            { persona_id: 'p-mrs-yin', name: 'Mrs. Yin', score: 0.45, reason: '当前作品', work_id: 'work_nezha' },
          ],
        },
      ],
    })

    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    expect(await screen.findByTestId('character-library-candidate-p-young')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-candidate-p-youth')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-candidate-p-ao-bing')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-candidate-p-li-jing')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-candidate-p-mrs-yin')).toBeInTheDocument()
  })

  it('lists top global persona candidates and binds the selected one to the active speaker', async () => {
    vi.mocked(tasksApi.suggestPersonasFromGlobal).mockResolvedValue({
      ok: true,
      matches: [
        {
          speaker_label: 'SPEAKER_01',
          candidates: [
            { persona_id: 'p-amy', name: '艾米', score: 0.92, reason: '名字相似', role: '女主' },
            { persona_id: 'p-bob', name: '鲍勃', score: 0.71, reason: '历史绑定', role: '男配' },
          ],
        },
      ],
    })

    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-2'))

    const candidate = await screen.findByTestId('character-library-candidate-p-amy')
    expect(candidate).toHaveTextContent('艾米')
    expect(candidate).toHaveTextContent('女主')
    expect(candidate).toHaveTextContent('92%')

    fireEvent.click(screen.getByTestId('bind-character-library-p-amy'))

    await waitFor(() => {
      expect(tasksApi.importPersonasFromGlobal).toHaveBeenCalledWith('task-speaker-video', {
        persona_ids: ['p-amy'],
        bindings_by_id: { 'p-amy': ['SPEAKER_01'] },
      })
    })
    expect(await screen.findByTestId('character-library-flash')).toHaveTextContent('已绑定角色：艾米')
  })

  it('triggers task → global library export when push button clicked', async () => {
    vi.mocked(tasksApi.exportTaskPersonasToGlobal).mockResolvedValue({
      ok: true,
      exported: ['艾米', '鲍勃'],
      skipped: [],
      total: 2,
    })

    render(<SpeakerReviewDrawer taskId="task-speaker-video" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    await screen.findByTestId('speaker-review-video')
    fireEvent.click(screen.getByTestId('transcript-row-seg-1'))

    fireEvent.click(screen.getByTestId('push-to-character-library'))

    await waitFor(() => {
      expect(tasksApi.exportTaskPersonasToGlobal).toHaveBeenCalledWith('task-speaker-video', {
        overwrite: true,
      })
    })
    expect(await screen.findByTestId('character-library-flash')).toHaveTextContent(
      '已保存 2 个角色到角色库',
    )
  })
})
