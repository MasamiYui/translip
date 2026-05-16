import { test, expect, Route } from '@playwright/test'

const TASK_ID = 'task-live-fit-demo'
const EDITOR_URL = `/tasks/${TASK_ID}/dubbing-editor`
const CLIP_REL = 'task-l/voice/clips/seg-0042.wav'

// Baseline calibration:
//   target_text length = 20 (we use a 20-char ascii baseline so the test
//   doesn't depend on Unicode char counting).
//   generated_duration = 2.0s -> implied 0.10s per char for *this* unit.
//   slot duration = 2.0s
//
// That makes the math trivial: predicted ≈ chars * 0.10s.
//   - 20 chars -> 2.00s, ratio = 1.00 -> safe
//   - 25 chars -> 2.50s, ratio = 1.25 -> over
//   -  6 chars -> 0.60s, ratio = 0.30 -> under
//   - 23 chars -> 2.30s, ratio = 1.15 -> borderline
const BASELINE_TEXT = 'a'.repeat(20)

function buildProject(): Record<string, unknown> {
  return {
    version: 'v1',
    created_at: '2026-05-17T01:00:00Z',
    task_id: TASK_ID,
    target_lang: 'en',
    status: 'ready',
    source_video_path: '/tmp/source.mp4',
    artifact_paths: { final_dub: '', dub_voice: '', preview_mix: '' },
    quality_benchmark: {
      version: 'v1',
      status: 'review_required',
      score: 80,
      reasons: [],
      metrics: {},
      gates: [],
    },
    characters: [
      {
        character_id: 'char_speaker_01',
        display_name: 'SPEAKER_01',
        speaker_ids: ['SPEAKER_01'],
        review_status: 'passed',
        risk_flags: [],
        pitch_class: 'mid',
        pitch_hz: 186.1,
        stats: {
          segment_count: 2,
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
        unit_id: 'seg-0042',
        source_segment_ids: ['seg-0042'],
        speaker_id: 'SPEAKER_01',
        character_id: 'char_speaker_01',
        start: 10.0,
        end: 12.0,
        duration: 2.0,
        source_text: 'A baseline source line.',
        target_text: BASELINE_TEXT,
        status: 'unreviewed',
        issue_ids: ['issue-seg-0042'],
        current_clip: {
          clip_id: 'clip_seg-0042',
          audio_path: null,
          audio_artifact_path: CLIP_REL,
          duration: 2.0,
          generated_duration: 2.0,
          source_duration: 2.0,
          backend: 'qwen',
          mix_status: 'placed',
          fit_strategy: 'direct',
        },
        candidates: [],
      },
      // A second unit with NO baseline (generated_duration is null) so we
      // can exercise the "live estimate appears after first synth" fallback.
      {
        unit_id: 'seg-0099',
        source_segment_ids: ['seg-0099'],
        speaker_id: 'SPEAKER_01',
        character_id: 'char_speaker_01',
        start: 20.0,
        end: 21.0,
        duration: 1.0,
        source_text: 'Never synthesised.',
        target_text: 'pending',
        status: 'unreviewed',
        issue_ids: ['issue-seg-0099'],
        current_clip: {
          clip_id: 'clip_seg-0099',
          audio_path: null,
          audio_artifact_path: null,
          duration: null,
          generated_duration: null,
          source_duration: 1.0,
          backend: 'qwen',
          mix_status: 'pending',
          fit_strategy: null,
        },
        candidates: [],
      },
    ],
    issues: [
      {
        issue_id: 'issue-seg-0042',
        type: 'duration_overrun',
        severity: 'P1',
        unit_id: 'seg-0042',
        character_id: 'char_speaker_01',
        title: 'baseline',
        description: 'baseline',
        status: 'open',
        time_sec: 10.0,
      },
      {
        issue_id: 'issue-seg-0099',
        type: 'duration_overrun',
        severity: 'P1',
        unit_id: 'seg-0099',
        character_id: 'char_speaker_01',
        title: 'no-baseline',
        description: 'no-baseline',
        status: 'open',
        time_sec: 20.0,
      },
    ],
    operations: [],
    summary: {
      unit_count: 2,
      character_count: 1,
      issue_count: 2,
      p0_count: 0,
      candidate_count: 0,
      approved_count: 0,
      char_review_count: 0,
      quality_status: 'review_required',
      quality_score: 80,
    },
  }
}

const SILENT_WAV = Buffer.from(
  '52494646' +
    '24080000' +
    '57415645' +
    '666d7420' +
    '10000000' +
    '01000100' +
    '44ac0000' +
    '88580100' +
    '02001000' +
    '64617461' +
    '00080000',
  'hex',
)

async function setupRoutes(page: import('@playwright/test').Page) {
  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildProject()),
    })
  })
  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/synthesize-unit`, async (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'queued',
        unit_id: 'seg-0042',
        audio_artifact_path: CLIP_REL,
        synthesized_at: '2026-05-17T02:00:00.000Z',
        message: 'queued',
      }),
    }),
  )
  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/operations`, async (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', operations_applied: 1 }) }),
  )
  await page.route('**/api/tasks/**/dubbing-editor/waveforms/**', async (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ track: 'original', peaks: [], duration_sec: 0, available: false, pending: false }),
    }),
  )
  await page.route('**/api/tasks/**/dubbing-editor/clip-preview**', async (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ url: '/__fake__/clip.wav', start_sec: 0, end_sec: 1, duration_sec: 1 }),
    }),
  )
  await page.route('**/api/tasks/**/dubbing-editor/video-preview', async (route: Route) =>
    route.fulfill({ status: 404, contentType: 'text/plain', body: 'not found' }),
  )
  await page.route('**/api/tasks/**/artifacts/**', async (route: Route) =>
    route.fulfill({ status: 200, contentType: 'audio/wav', body: SILENT_WAV }),
  )
}

async function openInspectorOn(page: import('@playwright/test').Page, issueId: string) {
  await page.goto(EDITOR_URL)
  await page.waitForLoadState('networkidle')
  await page.locator('[data-testid="dubbing-editor"]').waitFor({ timeout: 15_000 })
  const issueItem = page.locator(`[data-testid="issue-item-${issueId}"]`)
  if (!(await issueItem.isVisible().catch(() => false))) {
    await page.locator('[data-testid="toggle-issue-queue-panel"]').click()
  }
  await issueItem.click()
}

test.describe('Dubbing editor — live fit predictor', () => {
  test('predictor switches tone safe -> borderline -> over -> under as the user types', async ({ page }) => {
    await setupRoutes(page)
    await openInspectorOn(page, 'issue-seg-0042')

    const predictor = page.locator('[data-testid="live-fit-predictor"]')
    await expect(predictor).toBeVisible()
    // Baseline text is 20 chars at 0.10s/char => predicted 2.00s, slot 2.00s
    // ratio = 1.00 -> safe.
    await expect(predictor).toHaveAttribute('data-tone', 'safe')
    await expect(predictor).toHaveAttribute('data-predicted', '2.000')
    await expect(predictor).toHaveAttribute('data-slot', '2.000')

    const textarea = page.locator('textarea').first()

    // 25 chars -> 2.50s -> ratio 1.25 -> over
    await textarea.fill('a'.repeat(25))
    await expect(predictor).toHaveAttribute('data-tone', 'over')
    await expect(predictor).toHaveAttribute('data-predicted', '2.500')

    // 23 chars -> 2.30s -> ratio 1.15 -> borderline
    await textarea.fill('a'.repeat(23))
    await expect(predictor).toHaveAttribute('data-tone', 'borderline')
    await expect(predictor).toHaveAttribute('data-predicted', '2.300')

    // 6 chars -> 0.60s -> ratio 0.30 -> under
    await textarea.fill('a'.repeat(6))
    await expect(predictor).toHaveAttribute('data-tone', 'under')
    await expect(predictor).toHaveAttribute('data-predicted', '0.600')

    // 19 chars -> 1.90s -> ratio 0.95 -> safe
    await textarea.fill('a'.repeat(19))
    await expect(predictor).toHaveAttribute('data-tone', 'safe')
    await expect(predictor).toHaveAttribute('data-predicted', '1.900')
  })

  test('predictor degrades to "no baseline" hint when the unit has never been synthesised', async ({ page }) => {
    await setupRoutes(page)
    await openInspectorOn(page, 'issue-seg-0099')

    const predictor = page.locator('[data-testid="live-fit-predictor"]')
    await expect(predictor).toBeVisible()
    await expect(predictor).toHaveAttribute('data-tone', 'unknown')
    // The chip is not rendered in the unknown branch, only the hint.
    await expect(page.locator('[data-testid="live-fit-predictor-chip"]')).toHaveCount(0)
  })
})
