import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import type { Analysis, DubQaReport } from '../../api/evaluation'
import { EvaluationDetailPage } from '../EvaluationDetailPage'

const listAnalyses = vi.fn()
const getReport = vi.fn()
const createAnalysis = vi.fn()
const removeAnalysis = vi.fn()

vi.mock('../../api/evaluation', async importOriginal => {
  const actual = await importOriginal<typeof import('../../api/evaluation')>()
  return {
    ...actual,
    evaluationApi: {
      list: (...args: unknown[]) => listAnalyses(...args),
      get: vi.fn(),
      getReport: (...args: unknown[]) => getReport(...args),
      create: (...args: unknown[]) => createAnalysis(...args),
      remove: (...args: unknown[]) => removeAnalysis(...args),
    },
  }
})

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    get: () => Promise.resolve({ id: 'task-x', name: '哪吒预告片', target_lang: 'en', source_lang: 'zh' }),
  },
}))

function buildAnalysis(): Analysis {
  return {
    id: 'ana-1',
    task_id: 'task-x',
    analysis_type: 'dub-qa',
    status: 'succeeded',
    target_lang: 'en',
    source_lang: 'zh',
    params: { run_translation_judge: false },
    result: { score: 72, status: 'review_required', problem_segment_count: 1, issue_counts: { undubbed: 1 } },
    report_path: 'analysis/ana-1/dub_qa_report.en.json',
    created_at: '2026-06-01T10:00:00',
    updated_at: '2026-06-01T10:00:05',
  }
}

function buildReport(): DubQaReport {
  return {
    version: 'dub-qa-v0',
    created_at: '2026-06-01T10:00:00',
    target_lang: 'en',
    source_lang: 'zh',
    scorecard: { version: 'dub-benchmark-v0', status: 'review_required', score: 72, reasons: [], metrics: {}, gates: [
      { id: 'undubbed_coverage', label: 'Undubbed', status: 'failed', value: 1, threshold: 'x' },
    ] },
    qa_summary: {
      segment_count: 2,
      problem_segment_count: 1,
      issue_counts: { undubbed: 1, timbre_mismatch: 0, dropout: 0, pacing: 0, low_intelligibility: 0, inaudible: 0, bad_translation: 0 },
      severity_counts: { P0: 1, P1: 0, P2: 0, ok: 1 },
      skip_reason_counts: { skipped_missing_audio: 1 },
      coverage: { translated_count: 2, dubbed_count: 1, undubbed_count: 1, coverage_ratio: 0.5 },
      dropout: { affected_count: 0, average_ratio: null },
      translation_judge: null,
      judge_status: 'skipped',
    },
    segments: [
      {
        segment_id: 's1', speaker_id: 'SPK1', start: 0, end: 2, duration: 2,
        source_text: '你好世界', target_text: 'Hello world', backread_text: 'hello world',
        dub_audio_path: 'task-d/voice/clip/s1.wav', placed: true, mix_status: 'placed',
        fit_strategy: 'as_is', overall_status: 'passed', speaker_status: 'passed',
        intelligibility_status: 'passed', duration_status: 'passed',
        speaker_similarity: 0.7, text_similarity: 0.95, duration_ratio: 1.0, subtitle_coverage_ratio: 0.9,
        qa_flags: [], dropout_token_count: 0, dropout_total_tokens: 2, dropout_ratio: 0,
        judge_score: null, judge_adequacy: null, judge_fluency: null, judge_reason: null,
        issue_tags: [], severity: 'ok',
      },
      {
        segment_id: 's2', speaker_id: 'SPK2', start: 2, end: 4, duration: 2,
        source_text: '这句没有配音', target_text: 'This was never dubbed', backread_text: '',
        dub_audio_path: null, placed: false, mix_status: 'skipped_missing_audio',
        fit_strategy: null, overall_status: null, speaker_status: null,
        intelligibility_status: null, duration_status: null,
        speaker_similarity: null, text_similarity: null, duration_ratio: null, subtitle_coverage_ratio: null,
        qa_flags: [], dropout_token_count: 0, dropout_total_tokens: 4, dropout_ratio: 1,
        judge_score: null, judge_adequacy: null, judge_fluency: null, judge_reason: null,
        issue_tags: ['undubbed'], severity: 'P0',
      },
    ],
    input: {},
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter initialEntries={['/evaluation/task-x']}>
          <Routes>
            <Route path="/evaluation/:taskId" element={<EvaluationDetailPage />} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('EvaluationDetailPage', () => {
  it('renders the scorecard and drills from a problem segment into the detail drawer', async () => {
    listAnalyses.mockResolvedValue([buildAnalysis()])
    getReport.mockResolvedValue(buildReport())

    renderPage()

    // Scorecard score from the benchmark.
    await waitFor(() => expect(screen.getByText('72')).toBeInTheDocument())

    // Default filter is "problems only" → the undubbed segment is shown, the clean one is not.
    expect(screen.getByText('这句没有配音')).toBeInTheDocument()
    expect(screen.queryByText('你好世界')).not.toBeInTheDocument()

    // Switching to "all" reveals the clean segment too.
    fireEvent.click(screen.getByText(/全部片段/))
    await waitFor(() => expect(screen.getByText('你好世界')).toBeInTheDocument())

    // Open the drawer for the undubbed segment.
    fireEvent.click(screen.getByText('这句没有配音'))
    await waitFor(() => expect(screen.getByText('片段详情')).toBeInTheDocument())
    // Original-vs-dub players + "no dub audio" note for the undubbed segment.
    expect(screen.getByText('该片段没有配音音频')).toBeInTheDocument()
  })

  it('shows the empty state when there is no analysis yet', async () => {
    listAnalyses.mockResolvedValue([])

    renderPage()

    await waitFor(() =>
      expect(screen.getByText(/尚无评测结果/)).toBeInTheDocument(),
    )
  })
})
