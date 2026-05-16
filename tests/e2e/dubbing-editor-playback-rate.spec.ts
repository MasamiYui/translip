import { test, expect, Route } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-playback-rate-demo'
const EDITOR_URL = `/tasks/${TASK_ID}/dubbing-editor`
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const CLIP_REL = 'task-e/voice/clips/seg-0007.wav'

interface SynthRequestPayload {
  unit_id?: string
  target_text?: string
  speed?: number
}

let synthRequests: SynthRequestPayload[] = []

function buildProject(): Record<string, unknown> {
  return {
    version: 'v1',
    created_at: '2026-05-17T01:00:00Z',
    task_id: TASK_ID,
    target_lang: 'en',
    status: 'ready',
    source_video_path: '/tmp/source.mp4',
    artifact_paths: {
      final_dub: 'task-g/final-dub/final_dub.en.mp4',
      dub_voice: 'task-e/voice/dub_voice.en.wav',
      preview_mix: 'task-e/voice/preview_mix.en.wav',
    },
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
        unit_id: 'seg-0007',
        source_segment_ids: ['seg-0007'],
        speaker_id: 'SPEAKER_01',
        character_id: 'char_speaker_01',
        start: 12.0,
        end: 14.4,
        duration: 2.4,
        source_text: 'They were the very best of friends.',
        target_text: '他们是最好的朋友。',
        status: 'unreviewed',
        issue_ids: ['issue-seg-0007'],
        current_clip: {
          clip_id: 'clip_seg-0007',
          audio_path: null,
          audio_artifact_path: CLIP_REL,
          duration: 2.6,
          generated_duration: 3.1,
          source_duration: 2.4,
          backend: 'qwen',
          mix_status: 'placed',
          fit_strategy: 'compress',
        },
        candidates: [],
      },
    ],
    issues: [
      {
        issue_id: 'issue-seg-0007',
        type: 'duration_overrun',
        severity: 'P1',
        unit_id: 'seg-0007',
        character_id: 'char_speaker_01',
        title: '需要压缩',
        description: 'compress',
        status: 'open',
        time_sec: 12.0,
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

  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildProject()),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/synthesize-unit`, async (route: Route) => {
    const raw = route.request().postData() ?? '{}'
    let payload: SynthRequestPayload = {}
    try {
      payload = JSON.parse(raw) as SynthRequestPayload
    } catch {
      payload = {}
    }
    synthRequests.push(payload)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'queued',
        unit_id: payload.unit_id ?? 'seg-0007',
        audio_artifact_path: CLIP_REL,
        synthesized_at: `2026-05-17T02:00:0${synthRequests.length}.000Z`,
        message: 'Re-synthesis queued.',
      }),
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
  await page.route('**/api/tasks/**/dubbing-editor/video-preview', async (route: Route) => {
    await route.fulfill({ status: 404, contentType: 'text/plain', body: 'not found' })
  })
  await page.route('**/api/tasks/**/artifacts/**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: SILENT_WAV,
    })
  })
}

async function openInspector(page: import('@playwright/test').Page) {
  await page.goto(EDITOR_URL)
  await page.waitForLoadState('networkidle')
  await page.locator('[data-testid="dubbing-editor"]').waitFor({ timeout: 15_000 })
  const issueItem = page.locator('[data-testid="issue-item-issue-seg-0007"]')
  if (!(await issueItem.isVisible().catch(() => false))) {
    await page.locator('[data-testid="toggle-issue-queue-panel"]').click()
  }
  await issueItem.click()
  await expect(page.locator('[data-testid="clip-preview-card"]')).toBeVisible()
}

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

test.describe('Dubbing editor — A+B playback / synth speed', () => {
  test('A. preview rate segmented updates audio.playbackRate and persists to localStorage', async ({ page }) => {
    await setupRoutes(page)

    // First navigate to the page so we have a valid origin, then clear any
    // previously-persisted preference before mounting the editor.
    await page.goto(EDITOR_URL)
    await page.waitForLoadState('domcontentloaded')
    await page.evaluate(() => {
      try {
        window.localStorage.removeItem('dubbingEditor.playbackRate')
      } catch {
        /* noop */
      }
    })

    await openInspector(page)

    const segmented = page.locator('[data-testid="clip-preview-rate"]')
    await expect(segmented).toBeVisible()

    // Default is 1× and the underlying audio reflects that.
    const audio = page.locator('[data-testid="clip-preview-audio"]')
    await expect(audio).toBeAttached()
    const initialRate = await audio.evaluate(el => (el as HTMLAudioElement).playbackRate)
    expect(initialRate).toBe(1)

    // 1× chip is aria-checked initially.
    await expect(page.locator('[data-testid="clip-preview-rate-1"]')).toHaveAttribute('aria-checked', 'true')

    // Switch to 1.5×.
    await page.locator('[data-testid="clip-preview-rate-1.5"]').click()
    await expect(page.locator('[data-testid="clip-preview-rate-1.5"]')).toHaveAttribute('aria-checked', 'true')
    await expect(page.locator('[data-testid="clip-preview-rate-1"]')).toHaveAttribute('aria-checked', 'false')

    // The audio element's runtime playbackRate should follow the segmented control.
    await expect
      .poll(async () => await audio.evaluate(el => (el as HTMLAudioElement).playbackRate), { timeout: 2_000 })
      .toBe(1.5)

    // localStorage should now hold "1.5".
    const stored = await page.evaluate(() => window.localStorage.getItem('dubbingEditor.playbackRate'))
    expect(stored).toBe('1.5')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'playback-rate-segmented-1.5x.png'),
      fullPage: false,
    })

    // Reload — preference should still be 1.5×.
    await page.reload()
    await page.waitForLoadState('networkidle')
    await page.locator('[data-testid="dubbing-editor"]').waitFor({ timeout: 15_000 })

    // The issue queue panel may already be expanded from the persisted layout
    // preset; only toggle it when the issue item isn't visible yet.
    const issueItem = page.locator('[data-testid="issue-item-issue-seg-0007"]')
    if (!(await issueItem.isVisible().catch(() => false))) {
      await page.locator('[data-testid="toggle-issue-queue-panel"]').click()
    }
    await issueItem.click()
    await expect(page.locator('[data-testid="clip-preview-rate-1.5"]')).toHaveAttribute('aria-checked', 'true')
    await expect
      .poll(async () => await audio.evaluate(el => (el as HTMLAudioElement).playbackRate), { timeout: 2_000 })
      .toBe(1.5)
  })

  test('B. synth speed segmented forwards `speed` to the resynthesize endpoint', async ({ page }) => {
    await setupRoutes(page)
    await openInspector(page)

    const speedControl = page.locator('[data-testid="resynth-speed-control"]')
    await expect(speedControl).toBeVisible()

    // Initial synth at 1× should NOT include `speed` in the request body.
    await page.locator('[data-testid="resynthesize-btn"]').click()
    await expect.poll(() => synthRequests.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(1)
    expect(synthRequests[0].speed, 'speed should be omitted at 1×').toBeUndefined()

    // Pick 1.1× and re-trigger; the request body must carry speed = 1.1.
    await page.locator('[data-testid="resynth-speed-1.1"]').click()
    await expect(page.locator('[data-testid="resynth-speed-1.1"]')).toHaveAttribute('aria-checked', 'true')

    // Button label should advertise the active speed.
    await expect(page.locator('[data-testid="resynthesize-btn"]')).toContainText('1.1×')

    await page.locator('[data-testid="resynthesize-btn"]').click()
    await expect.poll(() => synthRequests.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(2)
    const lastReq = synthRequests[synthRequests.length - 1]
    expect(lastReq.speed).toBeCloseTo(1.1, 5)

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'synth-speed-1.1x.png'),
      fullPage: false,
    })

    // Pick a slow setting (0.85×) — sanity check the lower end of the range.
    await page.locator('[data-testid="resynth-speed-0.85"]').click()
    await expect(page.locator('[data-testid="resynth-speed-0.85"]')).toHaveAttribute('aria-checked', 'true')
    await page.locator('[data-testid="resynthesize-btn"]').click()
    await expect.poll(() => synthRequests.length, { timeout: 5_000 }).toBeGreaterThanOrEqual(3)
    expect(synthRequests[synthRequests.length - 1].speed).toBeCloseTo(0.85, 5)
  })
})
