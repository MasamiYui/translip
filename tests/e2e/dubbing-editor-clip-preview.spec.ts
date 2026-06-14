import { test, expect, Route } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-clip-preview-demo'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const EDITOR_URL = `/tasks/${TASK_ID}/dubbing-editor`

const CLIP_REL = 'render/voice/clips/seg-0003.wav'

let synthesizeCallCount = 0

function buildProject(): Record<string, unknown> {
  return {
    version: 'v1',
    created_at: '2026-05-16T09:00:00Z',
    task_id: TASK_ID,
    target_lang: 'en',
    status: 'ready',
    source_video_path: '/tmp/source.mp4',
    artifact_paths: {
      final_dub: 'delivery/final-dub/final_dub.en.mp4',
      dub_voice: 'render/voice/dub_voice.en.wav',
      preview_mix: 'render/voice/preview_mix.en.wav',
    },
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
        unit_id: 'seg-0003',
        source_segment_ids: ['seg-0003'],
        speaker_id: 'SPEAKER_01',
        character_id: 'char_speaker_01',
        start: 20.15,
        end: 21.15,
        duration: 1.0,
        source_text: 'by Haribata dog',
        target_text: 'by Haribata dog',
        status: 'unreviewed',
        issue_ids: ['issue-seg-0003'],
        current_clip: {
          clip_id: 'clip_seg-0003',
          audio_path: null,
          audio_artifact_path: CLIP_REL,
          duration: 0.94,
          backend: 'qwen',
          mix_status: 'placed_overlap',
          fit_strategy: 'overflow_unfitted',
        },
        candidates: [],
      },
    ],
    issues: [
      {
        issue_id: 'issue-seg-0003',
        type: 'duration_overrun',
        severity: 'P1',
        unit_id: 'seg-0003',
        character_id: 'char_speaker_01',
        title: '时长适配失败',
        description: 'overflow_unfitted',
        status: 'open',
        time_sec: 20.15,
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

// A tiny silent WAV (44.1 kHz, 16-bit mono, ~0.1s) so the <audio> element
// always has *something* to load, regardless of cache-bust query string.
const SILENT_WAV = Buffer.from(
  '52494646' + // 'RIFF'
    '24080000' + // chunk size
    '57415645' + // 'WAVE'
    '666d7420' + // 'fmt '
    '10000000' + // fmt chunk size
    '01000100' + // PCM, mono
    '44ac0000' + // sample rate 44100
    '88580100' + // byte rate
    '02001000' + // block align + bits per sample
    '64617461' + // 'data'
    '00080000', // data size
  'hex',
)

async function setupRoutes(page: import('@playwright/test').Page) {
  synthesizeCallCount = 0
  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildProject()),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/synthesize-unit`, async (route: Route) => {
    synthesizeCallCount += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'queued',
        unit_id: 'seg-0003',
        audio_artifact_path: CLIP_REL,
        synthesized_at: `2026-05-16T10:00:0${synthesizeCallCount}.000Z`,
        message: 'Re-synthesis queued.',
      }),
    })
  })

  // Stub waveform / clip preview / video preview / artifacts
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

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

test('inspector shows the per-segment preview audio and reloads it after re-synthesize', async ({ page }) => {
  await setupRoutes(page)

  await page.goto(EDITOR_URL)
  await page.waitForLoadState('networkidle')
  await page.locator('[data-testid="dubbing-editor"]').waitFor({ timeout: 15_000 })

  // Open issue queue (collapsed by default in the focus preset)
  await page.locator('[data-testid="toggle-issue-queue-panel"]').click()
  await page.locator('[data-testid="issue-item-issue-seg-0003"]').click()

  const previewCard = page.locator('[data-testid="clip-preview-card"]')
  await expect(previewCard).toBeVisible()
  await expect(previewCard).toContainText('试听这段配音')

  const audio = page.locator('[data-testid="clip-preview-audio"]')
  await expect(audio).toBeAttached()
  const initialSrc = await audio.getAttribute('src')
  expect(initialSrc, 'audio src should reference the clip artifact').toContain(
    `/api/tasks/${TASK_ID}/artifacts/${CLIP_REL}`,
  )

  // Annotated screenshot before clicking re-synthesize
  await page.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'clip-preview-before-resynth.png'),
    fullPage: true,
  })

  // Click 重新合成
  await page.locator('[data-testid="resynthesize-btn"]').click()

  // Wait for cache-bust: the audio src should now contain the synthesized_at token
  await expect
    .poll(async () => await audio.getAttribute('src'), { timeout: 5_000 })
    .toContain('2026-05-16T10%3A00%3A01.000Z')

  await page.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'clip-preview-after-resynth.png'),
    fullPage: true,
  })

  // Crop just the inspector preview card for a tightly-focused screenshot
  const box = await previewCard.boundingBox()
  if (box) {
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'clip-preview-card-zoom.png'),
      clip: {
        x: Math.max(0, box.x - 8),
        y: Math.max(0, box.y - 60),
        width: Math.min(800, box.width + 16),
        height: box.height + 120,
      },
    })
  }
})
