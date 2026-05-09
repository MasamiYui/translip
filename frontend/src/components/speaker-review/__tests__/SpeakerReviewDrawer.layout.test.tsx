import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { tasksApi } from '../../../api/tasks'
import type { SpeakerReviewResponse } from '../../../types'
import { SpeakerReviewDrawer } from '../SpeakerReviewDrawer'
import { useSpeakerReviewStore } from '../speakerReviewStore'

vi.mock('../../../api/tasks', () => ({
  tasksApi: {
    getSpeakerReview: vi.fn(),
    saveSpeakerReviewDecision: vi.fn(),
    deleteSpeakerReviewDecision: vi.fn(),
    applySpeakerReviewDecisions: vi.fn(),
    createSpeakerPersona: vi.fn(),
    updateSpeakerPersona: vi.fn(),
    bindSpeakerPersona: vi.fn(),
    unbindSpeakerPersona: vi.fn(),
    bulkCreateSpeakerPersonas: vi.fn(),
    suggestSpeakerPersonas: vi.fn(),
    undoSpeakerPersonas: vi.fn(),
    redoSpeakerPersonas: vi.fn(),
    previewSpeakerReviewApply: vi.fn(),
    listGlobalPersonas: vi.fn(),
    exportTaskPersonasToGlobal: vi.fn(),
    importPersonasFromGlobal: vi.fn(),
    suggestPersonasFromGlobal: vi.fn(),
    deleteGlobalPersona: vi.fn(),
  },
}))

const STORAGE_KEY = 'translip:speaker-review-layout'

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

function resetSpeakerReviewStore() {
  useSpeakerReviewStore.setState({
    selection: null,
    bulkSelection: new Set(),
    filters: { risk: ['high', 'medium', 'low'], onlyUndecided: true, sortBy: 'risk' },
    showShortcuts: false,
    showDiffModal: false,
    pendingMerge: null,
    renamingSpeaker: null,
    renameDraft: '',
    continuousRenaming: false,
    showPersonaBulk: false,
    showPersonaSuggest: false,
    lastUndoAt: null,
    lastRedoAt: null,
    pendingConflict: null,
    showApplyPreview: false,
    applyPreviewData: null,
    showOnboarding: false,
    showGlobalPersonas: false,
    globalMatchToast: null,
  })
}

function mockReview(): SpeakerReviewResponse {
  return {
    task_id: 'task-speaker-layout',
    status: 'available',
    summary: {
      segment_count: 8,
      speaker_count: 2,
      high_risk_speaker_count: 0,
      speaker_run_count: 1,
      review_run_count: 1,
      high_risk_run_count: 1,
      review_segment_count: 1,
      decision_count: 0,
      corrected_exists: false,
      unnamed_speaker_count: 2,
    },
    artifact_paths: {},
    speakers: [
      {
        speaker_label: 'speakerA',
        segment_count: 5,
        segment_ids: ['seg-1'],
        total_speech_sec: 14,
        avg_duration_sec: 2.8,
        short_segment_count: 1,
        risk_flags: ['short_sample'],
        risk_level: 'medium',
        cloneable_by_default: true,
        reference_clips: [],
        similar_peers: [{ label: 'speakerB', similarity: 0.68, suggest_merge: true }],
      },
      {
        speaker_label: 'speakerB',
        segment_count: 3,
        segment_ids: ['seg-2'],
        total_speech_sec: 18,
        avg_duration_sec: 6,
        short_segment_count: 0,
        risk_flags: [],
        risk_level: 'low',
        cloneable_by_default: true,
        reference_clips: [],
        similar_peers: [],
      },
    ],
    speaker_runs: [
      {
        run_id: 'run-1',
        speaker_label: 'speakerA',
        start: 1,
        end: 3,
        duration: 2,
        segment_count: 1,
        segment_ids: ['seg-1'],
        text: '需要核对的说话人片段',
        previous_speaker_label: 'speakerB',
        next_speaker_label: 'speakerB',
        gap_before_sec: 0.2,
        gap_after_sec: 0.3,
        risk_flags: ['short_island'],
        risk_level: 'high',
        recommended_action: 'merge_to_surrounding_speaker',
      },
    ],
    segments: [],
    similarity: {
      labels: ['speakerA', 'speakerB'],
      matrix: [
        [1, 0.68],
        [0.68, 1],
      ],
      threshold_suggest_merge: 0.55,
    },
    review_plan: { items: [] },
    decisions: [],
    personas: {
      items: [],
      unassigned_bindings: ['speakerA', 'speakerB'],
      by_speaker: {
        speakerA: { persona_id: null, name: null, color: null, avatar_emoji: null },
        speakerB: { persona_id: null, name: null, color: null, avatar_emoji: null },
      },
    },
    manifest: {},
  }
}

describe('SpeakerReviewDrawer resizable side panels', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    resetSpeakerReviewStore()
    window.localStorage.clear()
    window.localStorage.setItem('speaker-review-onboarded-v1', '1')
    vi.mocked(tasksApi.getSpeakerReview).mockResolvedValue(mockReview())
    vi.mocked(tasksApi.suggestPersonasFromGlobal).mockResolvedValue({ ok: true, matches: [] })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('collapses both side panels while keeping the review queue usable', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-layout" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    expect(await screen.findByTestId('speaker-roster-panel-shell')).toBeInTheDocument()
    expect(screen.getByTestId('speaker-inspector-panel-shell')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-speaker-inspector-panel'))
    expect(screen.queryByTestId('speaker-inspector-panel-shell')).not.toBeInTheDocument()
    expect(screen.getByTestId('speaker-inspector-rail')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-speaker-roster-panel'))
    expect(screen.queryByTestId('speaker-roster-panel-shell')).not.toBeInTheDocument()
    expect(screen.getByTestId('speaker-roster-rail')).toBeInTheDocument()
    expect(screen.getByTestId('review-queue')).toBeVisible()

    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}')).toMatchObject({
      leftOpen: false,
      rightOpen: false,
    })
  })

  it('resizes side panels with drag handles and persists the layout', async () => {
    render(<SpeakerReviewDrawer taskId="task-speaker-layout" isOpen onClose={vi.fn()} />, {
      wrapper: createWrapper(),
    })

    const rosterPanel = await screen.findByTestId('speaker-roster-panel-shell')
    const inspectorPanel = screen.getByTestId('speaker-inspector-panel-shell')

    expect(rosterPanel).toHaveStyle({ width: '300px' })
    expect(inspectorPanel).toHaveStyle({ width: '380px' })

    fireEvent.mouseDown(screen.getByTestId('resize-speaker-roster-panel'), { clientX: 300 })
    fireEvent.mouseMove(document, { clientX: 360 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      expect(screen.getByTestId('speaker-roster-panel-shell')).toHaveStyle({ width: '360px' })
    })

    fireEvent.mouseDown(screen.getByTestId('resize-speaker-inspector-panel'), { clientX: 1500 })
    fireEvent.mouseMove(document, { clientX: 1440 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      expect(screen.getByTestId('speaker-inspector-panel-shell')).toHaveStyle({ width: '440px' })
    })

    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '{}')).toMatchObject({
      leftWidth: 360,
      rightWidth: 440,
      leftOpen: true,
      rightOpen: true,
    })
  })
})
