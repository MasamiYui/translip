import { test, expect, type Page } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-mock-speaker-review'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const PAGE_URL = `/harness/speaker-review/${TASK_ID}`

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

function buildTask() {
  return {
    id: TASK_ID,
    title: '说话人核对 v2 e2e mock',
    status: 'completed',
    progress: 100,
    error: null,
    output_root: '/tmp/mock',
    source_path: '/tmp/mock/input.mp4',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    duration_sec: 120,
    languages: ['zh'],
    artifacts: {},
    pipeline: { stages: [] },
    config_snapshot: {},
  }
}

function buildSpeakerReview(decisions: Array<Record<string, unknown>> = []) {
  const decisionMap: Record<string, Record<string, unknown>> = {}
  decisions.forEach(d => {
    decisionMap[String(d.item_id)] = d
  })
  const speakerA = {
    speaker_label: 'speakerA',
    segment_count: 8,
    segment_ids: ['seg-1', 'seg-2'],
    total_speech_sec: 32.5,
    avg_duration_sec: 4.0,
    short_segment_count: 1,
    risk_flags: ['low_sample'],
    risk_level: 'medium',
    cloneable_by_default: true,
    decision: decisionMap['speaker:speakerA'] ?? null,
    reference_clips: [
      {
        clip_id: 'speakerA::seg-1',
        segment_id: 'seg-1',
        start: 1.0,
        end: 3.5,
        duration: 2.5,
        text: 'Hello world from speaker A',
        is_best: true,
        score: 0.9,
        url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=1&end=3.5`,
      },
    ],
    best_reference_clip_id: 'speakerA::seg-1',
    similar_peers: [{ label: 'speakerB', similarity: 0.72, suggest_merge: true }],
    recommended_action: 'merge_speaker',
  }
  const speakerB = {
    speaker_label: 'speakerB',
    segment_count: 12,
    segment_ids: ['seg-3'],
    total_speech_sec: 60.0,
    avg_duration_sec: 5.0,
    short_segment_count: 0,
    risk_flags: [],
    risk_level: 'low',
    cloneable_by_default: true,
    decision: decisionMap['speaker:speakerB'] ?? null,
    reference_clips: [],
    similar_peers: [],
    recommended_action: 'keep_independent',
  }
  const run1 = {
    run_id: 'run-1',
    speaker_label: 'speakerA',
    start: 10.0,
    end: 11.2,
    duration: 1.2,
    segment_count: 1,
    segment_ids: ['seg-1'],
    text: '这是一个高风险孤岛 run',
    previous_speaker_label: 'speakerB',
    next_speaker_label: 'speakerB',
    gap_before_sec: 0.3,
    gap_after_sec: 0.4,
    risk_flags: ['short_island'],
    risk_level: 'high',
    decision: decisionMap['run-1'] ?? null,
    audio_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=10&end=11.2`,
    prev_context_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=8.5&end=10`,
    next_context_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=11.2&end=12.7`,
    recommended_action: 'merge_to_surrounding_speaker',
  }
  const seg1 = {
    segment_id: 'seg-2',
    index: 2,
    speaker_label: 'speakerA',
    start: 22.0,
    end: 23.0,
    duration: 1.0,
    text: '过短风险段',
    previous_speaker_label: 'speakerA',
    next_speaker_label: 'speakerB',
    risk_flags: ['short_segment'],
    risk_level: 'medium',
    decision: decisionMap['seg-2'] ?? null,
    audio_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=22&end=23`,
    prev_context_url: null,
    next_context_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=23&end=24.5`,
    recommended_action: 'keep_independent',
  }

  return {
    task_id: TASK_ID,
    status: 'available',
    summary: {
      segment_count: 20,
      speaker_count: 2,
      high_risk_speaker_count: 0,
      speaker_run_count: 5,
      review_run_count: 1,
      high_risk_run_count: 1,
      review_segment_count: 2,
      decision_count: decisions.length,
      corrected_exists: false,
    },
    artifact_paths: {},
    speakers: [speakerA, speakerB],
    speaker_runs: [run1],
    segments: [seg1],
    similarity: {
      labels: ['speakerA', 'speakerB'],
      matrix: [
        [1.0, 0.72],
        [0.72, 1.0],
      ],
      threshold_suggest_merge: 0.55,
      method: 'profile_heuristic',
    },
    review_plan: { items: [] },
    decisions,
    manifest: {},
  }
}

async function setupRoutes(page: Page) {
  const decisions: Array<Record<string, unknown>> = []

  await page.route(`**/api/tasks/${TASK_ID}`, async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildTask()) })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review`, async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildSpeakerReview(decisions)),
      })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/decisions`, async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      const existingIdx = decisions.findIndex(d => d.item_id === body.item_id)
      const record = { ...body, updated_at: new Date().toISOString() }
      if (existingIdx >= 0) decisions[existingIdx] = record
      else decisions.push(record)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/decisions/*`, async route => {
    if (route.request().method() === 'DELETE') {
      const url = route.request().url()
      const segs = url.split('/decisions/')
      const itemId = decodeURIComponent(segs[1])
      const idx = decisions.findIndex(d => d.item_id === itemId)
      if (idx >= 0) decisions.splice(idx, 1)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/apply`, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        path: '/tmp/segments.zh.speaker-corrected.json',
        srt_path: '/tmp/segments.zh.speaker-corrected.srt',
        manifest_path: '/tmp/speaker-review-manifest.json',
        archive_path: '/tmp/_archive/20260101-120000',
        summary: {},
        applied_at: new Date().toISOString(),
      }),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/audio**`, async route => {
    const wavHeader = Buffer.from([
      0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
      0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
      0x80, 0x3e, 0x00, 0x00, 0x00, 0x7d, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00,
      0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00,
    ])
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: wavHeader })
  })

  await page.route('**/api/tasks/' + TASK_ID + '/workflow', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ nodes: [], edges: [] }) })
  })

  await page.route('**/api/tasks/' + TASK_ID + '/delivery', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })

  await page.route('**/api/tasks/' + TASK_ID + '/progress**', async route => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
  })
}

async function openDrawer(page: Page) {
  await page.goto(PAGE_URL)
  await page.waitForLoadState('domcontentloaded')
  await page.locator('[data-testid="speaker-review-drawer"]').waitFor({ timeout: 15_000 })
}

test.describe('Speaker Review v2 drawer', () => {
  test.beforeEach(async ({ page }) => {
    await setupRoutes(page)
  })

  test('打开抽屉并展示三栏布局', async ({ page }) => {
    await openDrawer(page)
    await expect(page.locator('[data-testid="speaker-review-topbar"]')).toBeVisible()
    await expect(page.locator('[data-testid="roster-panel"]')).toBeVisible()
    await expect(page.locator('[data-testid="review-queue"]')).toBeVisible()
    await expect(page.locator('[data-testid="inspector-panel"]')).toBeVisible()
    await expect(page.locator('[data-testid="roster-item-speakerA"]')).toBeVisible()
    await expect(page.locator('[data-testid="roster-item-speakerB"]')).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'speaker-review-v2-loaded.png'), fullPage: true })
  })

  test('选择条目后展示检视面板与建议动作', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="queue-item-run-1"]').click()
    await expect(page.locator('[data-testid="inspector-panel"]')).toContainText('Run run-1')
    await expect(page.locator('[data-testid="inspector-panel"]')).toContainText('建议')
    await expect(page.locator('[data-testid="action-relabel-prev"]')).toBeVisible()
    await expect(page.locator('[data-testid="action-merge-surrounding"]')).toBeVisible()
  })

  test('应用决策并展示归档提示', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="filter-undecided"]').uncheck()
    await page.locator('[data-testid="queue-item-run-1"]').click()
    await page.locator('[data-testid="action-merge-surrounding"]').click()
    await expect(page.locator('[data-testid="queue-item-run-1"]')).toContainText(
      'merge_to_surrounding_speaker',
      { timeout: 5000 },
    )
    await page.locator('[data-testid="apply-decisions"]').click()
    await expect(page.locator('[data-testid="apply-result"]')).toContainText('已归档旧产物')
  })

  test('合并建议触发二次确认弹窗', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="suggest-merge-speakerA-speakerB"]').click()
    await expect(page.locator('[data-testid="merge-confirm-modal"]')).toBeVisible()
    await page.locator('[data-testid="merge-cancel"]').click()
    await expect(page.locator('[data-testid="merge-confirm-modal"]')).toHaveCount(0)
    await page.locator('[data-testid="suggest-merge-speakerA-speakerB"]').click()
    await page.locator('[data-testid="merge-confirm"]').click()
    await expect(page.locator('[data-testid="merge-confirm-modal"]')).toHaveCount(0)
  })

  test('快捷键面板：按钮打开后 Esc 关闭', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="shortcuts-button"]').click()
    await expect(page.locator('[data-testid="shortcuts-modal"]')).toBeVisible()
    await page.locator('[data-testid="shortcuts-modal"]').click({ position: { x: 5, y: 5 } })
    await expect(page.locator('[data-testid="shortcuts-modal"]')).toHaveCount(0)
  })

  test('撤销已保存的决策', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="queue-item-run-1"]').click()
    await page.locator('[data-testid="action-keep"]').click()
    await expect(page.locator('[data-testid="delete-decision"]')).toBeVisible({ timeout: 5000 })
    await page.locator('[data-testid="delete-decision"]').click()
    await expect(page.locator('[data-testid="delete-decision"]')).toHaveCount(0, { timeout: 5000 })
  })
})
