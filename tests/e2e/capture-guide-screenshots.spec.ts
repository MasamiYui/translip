/**
 * Capture fresh screenshots for the in-app User Guide (使用文档).
 * Run once against the live dev stack (./scripts/dev.sh start):
 *   npx playwright test tests/e2e/capture-guide-screenshots.spec.ts
 * Output: frontend/public/guide/*.png
 *
 * Each capture is independent and defensive: it navigates, waits for the page
 * to settle, and screenshots whatever rendered. A single flaky route never
 * blocks the rest.
 */
import { test } from '@playwright/test'
import path from 'path'
import fs from 'fs'

// A succeeded, data-rich pipeline task (10 stages) used for the detail /
// dubbing-editor / evaluation captures. Swap if it is ever pruned.
const TASK_ID = 'task-20260612-090340'
const OUT_DIR = path.join(__dirname, '../../frontend/public/guide')
const VIEWPORT = { width: 1440, height: 900 }

test.beforeAll(() => {
  fs.mkdirSync(OUT_DIR, { recursive: true })
})

async function settle(page: import('@playwright/test').Page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}

async function shot(page: import('@playwright/test').Page, name: string, fullPage = true) {
  await page.screenshot({ path: path.join(OUT_DIR, name), fullPage })
}

test.use({ viewport: VIEWPORT })

test('dashboard', async ({ page }) => {
  await page.goto('/')
  await settle(page)
  await shot(page, 'dashboard.png')
})

test('task list', async ({ page }) => {
  await page.goto('/tasks')
  await settle(page)
  await shot(page, 'task-list.png')
})

test('new task wizard', async ({ page }) => {
  await page.goto('/tasks/new')
  await settle(page)
  await shot(page, 'new-task.png')
})

test('task detail + pipeline graph', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}`)
  await settle(page, 1400)
  await shot(page, 'task-detail.png')
  // A tighter crop of just the pipeline runtime graph for the "concepts" chapter.
  const strip = page.locator('[data-testid="delivery-flow-strip"]')
  const hasStrip = await strip.isVisible().catch(() => false)
  if (hasStrip) {
    // Graph sits above the delivery strip; clip the top viewport band.
    await page.screenshot({
      path: path.join(OUT_DIR, 'pipeline-graph.png'),
      clip: { x: 0, y: 150, width: VIEWPORT.width, height: 560 },
    })
  }
})

test('atomic tools list', async ({ page }) => {
  await page.goto('/tools')
  await settle(page)
  await shot(page, 'atomic-tools.png')
})

test('single tool (separation)', async ({ page }) => {
  await page.goto('/tools/separation')
  await settle(page)
  await shot(page, 'tool-separation.png')
})

test('single tool (video trim)', async ({ page }) => {
  await page.goto('/tools/video-trim')
  await settle(page)
  await shot(page, 'tool-video-trim.png')
})

test('atomic job history', async ({ page }) => {
  await page.goto('/tools/jobs')
  await settle(page)
  await shot(page, 'atomic-jobs.png')
})

test('ai assistant task list', async ({ page }) => {
  await page.goto('/assistant/tasks')
  await settle(page)
  await shot(page, 'ai-tasks.png')
})

// Note: the populated AI-assistant widget shot (ai-assistant-widget.png) and the
// rich dubbing-editor / evaluation shots are sourced from docs/assets/readme/*
// (curated, data-rich) rather than captured here, since a fresh local stack may
// have empty queues. See frontend/public/guide/.

test('dubbing editor overview', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}/dubbing-editor`)
  await page
    .locator('[data-testid="dubbing-editor"]')
    .waitFor({ timeout: 15_000 })
    .catch(() => {})
  await settle(page, 900)
  await shot(page, 'dubbing-editor.png', false)
})

test('dubbing editor shortcuts', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}/dubbing-editor`)
  await page
    .locator('[data-testid="dubbing-editor"]')
    .waitFor({ timeout: 15_000 })
    .catch(() => {})
  await settle(page, 600)
  const btn = page.locator('[data-testid="keyboard-shortcuts-btn"]')
  if (await btn.isVisible().catch(() => false)) {
    await btn.click().catch(() => {})
    const pop = page.locator('[data-testid="shortcuts-popover"]')
    await pop.waitFor({ timeout: 5000 }).catch(() => {})
    await page.waitForTimeout(300)
    const box = await pop.boundingBox().catch(() => null)
    if (box) {
      await page.screenshot({
        path: path.join(OUT_DIR, 'dubbing-shortcuts.png'),
        clip: { x: box.x - 12, y: box.y - 12, width: box.width + 24, height: box.height + 24 },
      })
    }
  }
})

test('evaluation list', async ({ page }) => {
  await page.goto('/evaluation')
  await settle(page)
  await shot(page, 'evaluation-list.png')
})

test('evaluation detail', async ({ page }) => {
  await page.goto(`/evaluation/${TASK_ID}`)
  await settle(page, 1400)
  await shot(page, 'evaluation-detail.png')
})

test('works library', async ({ page }) => {
  await page.goto('/works')
  await settle(page)
  await shot(page, 'works.png')
})

test('character library', async ({ page }) => {
  await page.goto('/character-library')
  await settle(page)
  await shot(page, 'character-library.png')
})

test('settings', async ({ page }) => {
  await page.goto('/settings')
  await settle(page)
  await shot(page, 'settings.png')
})
