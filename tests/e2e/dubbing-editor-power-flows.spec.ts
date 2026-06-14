import { test, expect, Route } from '@playwright/test'
import path from 'path'

const TASK_ID = 'task-power-user-demo'
const EDITOR_URL = `/tasks/${TASK_ID}/dubbing-editor`
const CLIP_REL = 'render/voice/clips/seg-0042.wav'

interface SynthBody {
  unit_id?: string
  target_text?: string
  speed?: number
}

let synthRequests: SynthBody[] = []
let synthShouldFail = false

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
      score: 70,
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
        // Slot is 2.0s but TTS naturally read 2.4s, so the suggested speed
        // should snap to ~1.20× (the 5-step segmented's nearest level).
        duration: 2.0,
        source_text: 'They were the best of friends and the worst of enemies.',
        target_text: '他们是最好的朋友,也是最坏的敌人。',
        status: 'unreviewed',
        issue_ids: ['issue-seg-0042'],
        current_clip: {
          clip_id: 'clip_seg-0042',
          audio_path: null,
          audio_artifact_path: CLIP_REL,
          duration: 2.0,
          generated_duration: 2.4,
          source_duration: 2.0,
          backend: 'qwen',
          mix_status: 'placed',
          fit_strategy: 'compress',
        },
        candidates: [],
      },
      {
        unit_id: 'seg-0043',
        source_segment_ids: ['seg-0043'],
        speaker_id: 'SPEAKER_01',
        character_id: 'char_speaker_01',
        start: 12.0,
        end: 13.0,
        duration: 1.0,
        source_text: 'And so they marched on.',
        target_text: '于是他们继续前行。',
        status: 'unreviewed',
        issue_ids: ['issue-seg-0043'],
        current_clip: {
          clip_id: 'clip_seg-0043',
          audio_path: null,
          audio_artifact_path: CLIP_REL,
          duration: 1.0,
          generated_duration: 1.0,
          source_duration: 1.0,
          backend: 'qwen',
          mix_status: 'placed',
          fit_strategy: 'direct',
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
        title: 'compress',
        description: 'compress',
        status: 'open',
        time_sec: 10.0,
      },
      {
        issue_id: 'issue-seg-0043',
        type: 'duration_overrun',
        severity: 'P1',
        unit_id: 'seg-0043',
        character_id: 'char_speaker_01',
        title: 'direct',
        description: 'direct',
        status: 'open',
        time_sec: 12.0,
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
      quality_score: 70,
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
  synthRequests = []
  synthShouldFail = false

  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildProject()),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/synthesize-unit`, async (route: Route) => {
    const raw = route.request().postData() ?? '{}'
    let payload: SynthBody = {}
    try {
      payload = JSON.parse(raw) as SynthBody
    } catch {
      payload = {}
    }
    synthRequests.push(payload)
    if (synthShouldFail) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Backend voice model unavailable' }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'queued',
        unit_id: payload.unit_id ?? 'seg-0042',
        audio_artifact_path: CLIP_REL,
        synthesized_at: `2026-05-17T02:00:0${synthRequests.length}.000Z`,
        message: 'queued',
      }),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/operations`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', operations_applied: 1 }),
    })
  })

  await page.route('**/api/tasks/**/dubbing-editor/waveforms/**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ track: 'original', peaks: [], duration_sec: 0, available: false, pending: false }),
    })
  })
  await page.route('**/api/tasks/**/dubbing-editor/clip-preview**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ url: '/__fake__/clip.wav', start_sec: 0, end_sec: 1, duration_sec: 1 }),
    })
  })
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
  await expect(page.locator('[data-testid="clip-preview-card"]')).toBeVisible()
}

const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')

test.describe('Dubbing editor — power-user shortcuts & repair flows', () => {
  test('hotkey [ and ] step the preview playback rate', async ({ page }) => {
    await setupRoutes(page)

    // Pre-clear to start at 1×.
    await page.goto(EDITOR_URL)
    await page.waitForLoadState('domcontentloaded')
    await page.evaluate(() => window.localStorage.removeItem('dubbingEditor.playbackRate'))

    await openInspectorOn(page, 'issue-seg-0042')

    // ] steps up: 1 -> 1.25
    await page.keyboard.press(']')
    await expect(page.locator('[data-testid="clip-preview-rate-1.25"]')).toHaveAttribute('aria-checked', 'true')

    // ] again: 1.25 -> 1.5
    await page.keyboard.press(']')
    await expect(page.locator('[data-testid="clip-preview-rate-1.5"]')).toHaveAttribute('aria-checked', 'true')

    // [ steps down: 1.5 -> 1.25
    await page.keyboard.press('[')
    await expect(page.locator('[data-testid="clip-preview-rate-1.25"]')).toHaveAttribute('aria-checked', 'true')

    // localStorage holds the latest selection.
    const stored = await page.evaluate(() => window.localStorage.getItem('dubbingEditor.playbackRate'))
    expect(stored).toBe('1.25')
  })

  test('A advances to the next open issue after approving the current one', async ({ page }) => {
    await setupRoutes(page)
    await openInspectorOn(page, 'issue-seg-0042')

    // Sanity: seg-0042 is selected (the highlight class is added when
    // isSelected is true).
    await expect(page.locator('[data-testid="issue-item-issue-seg-0042"]')).toHaveClass(/bg-blue-50/)

    // Press A on the inspector to approve & advance.
    await page.keyboard.press('A')

    // The next open issue (issue-seg-0043) should now be selected.
    await expect(page.locator('[data-testid="issue-item-issue-seg-0043"]')).toHaveClass(/bg-blue-50/, { timeout: 3_000 })
  })

  test('ClipFitMeter Suggest button applies snapped speed and triggers resynth', async ({ page }) => {
    await setupRoutes(page)
    await openInspectorOn(page, 'issue-seg-0042')

    const suggest = page.locator('[data-testid="clip-fit-meter-suggest"]')
    await expect(suggest).toBeVisible()

    // generated/source = 2.4 / 2.0 = 1.2 → snap = 1.2
    await expect(suggest).toContainText('1.2×')

    await suggest.click()

    // The synth-speed segmented should have flipped to 1.2× and a synth
    // request should have fired with speed=1.2.
    await expect(page.locator('[data-testid="resynth-speed-1.2"]')).toHaveAttribute('aria-checked', 'true')
    await expect.poll(() => synthRequests.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1)
    expect(synthRequests[0].speed).toBeCloseTo(1.2, 5)

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'fit-meter-suggest-applied.png') })
  })

  test('failed resynth shows error banner and concurrent clicks are de-duped', async ({ page }) => {
    await setupRoutes(page)

    // Make the synthesize endpoint *slow* + failing so the second click can
    // overlap with the first while it's still in-flight. Without this delay
    // the route fulfills synchronously and clicks behave as a serial loop.
    await page.unroute(`**/api/tasks/${TASK_ID}/dubbing-editor/synthesize-unit`)
    await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/synthesize-unit`, async (route: Route) => {
      const raw = route.request().postData() ?? '{}'
      let payload: SynthBody = {}
      try {
        payload = JSON.parse(raw) as SynthBody
      } catch {
        payload = {}
      }
      synthRequests.push(payload)
      await new Promise(r => setTimeout(r, 800))
      if (synthShouldFail) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Backend voice model unavailable' }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'queued',
          unit_id: payload.unit_id ?? 'seg-0042',
          audio_artifact_path: CLIP_REL,
          synthesized_at: '2026-05-17T03:00:00.000Z',
          message: 'queued',
        }),
      })
    })

    synthShouldFail = true
    await openInspectorOn(page, 'issue-seg-0042')

    const btn = page.locator('[data-testid="resynthesize-btn"]')

    // Fire the first click and *don't* await its full settle; immediately
    // try two more times in rapid succession. The button gets disabled
    // synchronously after the first onClick, so the subsequent clicks
    // either bounce off the disabled attr or hit the synthInFlightRef
    // guard. In either case only one network request should go out.
    await btn.click()
    await btn.click({ force: true, timeout: 200 }).catch(() => {})
    await btn.click({ force: true, timeout: 200 }).catch(() => {})

    // Wait for the failed first request to resolve and surface the banner.
    const banner = page.locator('[data-testid="resynth-error-banner"]')
    await expect(banner).toBeVisible({ timeout: 5_000 })
    await expect(banner).toContainText('Backend voice model unavailable')

    // De-dup: only one request actually went out during the in-flight window.
    expect(synthRequests.length).toBe(1)

    // After a successful resynth, the banner should disappear.
    synthShouldFail = false
    await btn.click()
    await expect(banner).toBeHidden({ timeout: 5_000 })
  })
})
