import { test, expect, type Page } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-character-library-mock'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const PAGE_URL = `/harness/speaker-review/${TASK_ID}`

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

function buildReview() {
  return {
    task_id: TASK_ID,
    status: 'available',
    summary: {
      segment_count: 2,
      speaker_count: 2,
      high_risk_speaker_count: 0,
      speaker_run_count: 2,
      review_run_count: 0,
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
        segment_count: 1,
        segment_ids: ['seg-a'],
        total_speech_sec: 3,
        avg_duration_sec: 3,
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
        segment_ids: ['seg-b'],
        total_speech_sec: 3,
        avg_duration_sec: 3,
        short_segment_count: 0,
        risk_flags: ['single_segment_speaker'],
        risk_level: 'medium',
        cloneable_by_default: false,
        reference_clips: [],
        similar_peers: [],
      },
    ],
    speaker_runs: [],
    segments: [
      {
        segment_id: 'seg-a',
        index: 1,
        speaker_label: 'SPEAKER_00',
        start: 0,
        end: 3,
        duration: 3,
        text: '第一句台词',
        next_speaker_label: 'SPEAKER_01',
        risk_flags: [],
        risk_level: 'low',
      },
      {
        segment_id: 'seg-b',
        index: 2,
        speaker_label: 'SPEAKER_01',
        start: 3,
        end: 6,
        duration: 3,
        text: '这里是女主角的台词',
        previous_speaker_label: 'SPEAKER_00',
        risk_flags: ['speaker_boundary_risk'],
        risk_level: 'medium',
      },
    ],
    similarity: {
      labels: ['SPEAKER_00', 'SPEAKER_01'],
      matrix: [
        [1, 0.3],
        [0.3, 1],
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

async function setupRoutes(page: Page) {
  await page.route(`**/api/tasks/${TASK_ID}/speaker-review`, async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildReview()),
      })
      return
    }
    await route.continue()
  })

  await page.route(
    `**/api/tasks/${TASK_ID}/speaker-review/personas/suggest-from-global`,
    async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          matches: [
            {
              speaker_label: 'SPEAKER_01',
              candidates: [
                {
                  persona_id: 'p-amy',
                  name: '艾米',
                  score: 0.92,
                  reason: '历史任务常用角色',
                  role: '女主',
                },
                {
                  persona_id: 'p-bob',
                  name: '鲍勃',
                  score: 0.71,
                  reason: '名字相似',
                  role: '男配',
                },
              ],
            },
          ],
        }),
      })
    },
  )

  await page.route(
    `**/api/tasks/${TASK_ID}/speaker-review/personas/import-from-global`,
    async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          imported: [
            {
              id: 'p-amy',
              name: '艾米',
              bindings: ['SPEAKER_01'],
            },
          ],
          conflicts: [],
          personas: {
            items: [
              {
                id: 'p-amy',
                name: '艾米',
                bindings: ['SPEAKER_01'],
                aliases: [],
                color: null,
                avatar_emoji: null,
                tts_skip: false,
                tts_voice_id: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ],
            unassigned_bindings: ['SPEAKER_00'],
            by_speaker: {
              SPEAKER_00: { persona_id: null, name: null, color: null, avatar_emoji: null },
              SPEAKER_01: {
                persona_id: 'p-amy',
                name: '艾米',
                color: null,
                avatar_emoji: null,
              },
            },
            updated_at: new Date().toISOString(),
          },
        }),
      })
    },
  )

  await page.route(
    `**/api/tasks/${TASK_ID}/speaker-review/global-personas/export-from-task`,
    async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          exported: ['艾米', '鲍勃'],
          skipped: [],
          total: 2,
        }),
      })
    },
  )

  // Fallback: video preview request should 404 silently.
  await page.route(`**/api/tasks/${TASK_ID}/dubbing-editor/video-preview`, async route => {
    await route.fulfill({ status: 204, body: '' })
  })
}

test.describe('角色库匹配卡片 & 回灌入口', () => {
  test('在抽屉内展示候选并绑定，且头部回灌按钮能回灌到角色库', async ({ page }) => {
    await setupRoutes(page)

    await page.goto(PAGE_URL)

    await expect(page.getByTestId('speaker-review-drawer')).toBeVisible()

    // 选择有匹配的 SPEAKER_01 段落
    await page.getByTestId('transcript-row-seg-b').click()

    const card = page.getByTestId('character-library-match-card')
    await expect(card).toBeVisible()

    const amy = page.getByTestId('character-library-candidate-p-amy')
    await expect(amy).toBeVisible()
    await expect(amy).toContainText('艾米')
    await expect(amy).toContainText('女主')
    await expect(amy).toContainText('92%')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-candidates.png'),
      fullPage: true,
    })

    // 绑定艾米到 SPEAKER_01
    await page.getByTestId('bind-character-library-p-amy').click()
    await expect(page.getByTestId('character-library-flash')).toContainText('已绑定角色：艾米')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-bound.png'),
      fullPage: true,
    })

    // 触发回灌
    await page.getByTestId('push-to-character-library').click()
    await expect(page.getByTestId('character-library-flash')).toContainText(
      '已回灌 2 个角色到角色库',
    )

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-pushed.png'),
      fullPage: true,
    })
  })

  test('当 SPEAKER 没有候选时展示空态占位', async ({ page }) => {
    await setupRoutes(page)

    await page.goto(PAGE_URL)

    await expect(page.getByTestId('speaker-review-drawer')).toBeVisible()

    // 选择没有匹配的 SPEAKER_00 段落
    await page.getByTestId('transcript-row-seg-a').click()

    await expect(page.getByTestId('character-library-match-card')).toBeVisible()
    await expect(page.getByTestId('character-library-empty')).toBeVisible()

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-empty.png'),
      fullPage: true,
    })
  })
})
