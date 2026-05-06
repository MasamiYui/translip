/**
 * Capture annotated screenshots for the in-app help guide.
 * Run once: npx playwright test tests/e2e/capture-help-screenshots.spec.ts
 * Output: frontend/public/help/*.png
 */
import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-20260430-164759'
const EDITOR_URL = `/tasks/${TASK_ID}/dubbing-editor`
const HELP_DIR = path.join(__dirname, '../../frontend/public/help')

test.beforeAll(() => {
  fs.mkdirSync(HELP_DIR, { recursive: true })
})

async function gotoEditor(page: import('@playwright/test').Page) {
  await page.goto(EDITOR_URL)
  await page.waitForLoadState('networkidle')
  await page.locator('[data-testid="dubbing-editor"]').waitFor({ timeout: 15_000 })
}

// ── Step 1: Overview ───────────────────────────────────────────────────────

test('step 1 – full workbench overview', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  // Wait for waveform tracks to render
  await page.locator('[data-testid="timeline-header"]').waitFor()
  await page.waitForTimeout(600)
  await page.screenshot({
    path: path.join(HELP_DIR, '01-overview.png'),
    fullPage: false,
  })
})

// ── Step 2: Issue Queue ────────────────────────────────────────────────────

test('step 2 – issue queue panel', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  // Highlight left panel by clipping
  const queue = page.locator('[data-testid="dubbing-editor"]')
  await queue.waitFor()
  await page.waitForTimeout(400)
  // Clip to the left 340px
  await page.screenshot({
    path: path.join(HELP_DIR, '02-issue-queue.png'),
    clip: { x: 0, y: 52, width: 358, height: 768 },
  })
})

// ── Step 3: Select an issue and show Current Line ──────────────────────────

test('step 3 – select issue to see current line', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  // Click first issue item
  const firstIssue = page.locator('[data-testid^="issue-item-"]').first()
  await firstIssue.waitFor({ timeout: 10_000 })
  await firstIssue.click()
  await page.waitForTimeout(600)
  await page.screenshot({
    path: path.join(HELP_DIR, '03-current-line.png'),
    fullPage: false,
  })
})

// ── Step 4: Timeline ───────────────────────────────────────────────────────

test('step 4 – timeline waveform tracks', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  await page.waitForTimeout(800)
  const header = page.locator('[data-testid="timeline-header"]')
  const box = await header.boundingBox()
  if (!box) throw new Error('No timeline header')
  // Clip timeline area (below header)
  await page.screenshot({
    path: path.join(HELP_DIR, '04-timeline.png'),
    clip: { x: 358, y: box.y - 4, width: 1080 - 380, height: 240 },
  })
})

// ── Step 5: Segment Inspector ──────────────────────────────────────────────

test('step 5 – segment inspector panel', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  const firstIssue = page.locator('[data-testid^="issue-item-"]').first()
  await firstIssue.waitFor({ timeout: 10_000 })
  await firstIssue.click()
  await page.waitForTimeout(600)
  // Clip right panel (last 380px)
  await page.screenshot({
    path: path.join(HELP_DIR, '05-inspector.png'),
    clip: { x: 1060, y: 52, width: 380, height: 768 },
  })
})

// ── Step 6: Approve or needs review ───────────────────────────────────────

test('step 6 – approve and needs-review buttons', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  const firstIssue = page.locator('[data-testid^="issue-item-"]').first()
  await firstIssue.waitFor({ timeout: 10_000 })
  await firstIssue.click()
  await page.waitForTimeout(600)
  // Focus the approve/needs-review area
  const approveBtn = page.locator('[data-testid="approve-btn"]')
  const needsReviewBtn = page.locator('[data-testid="needs-review-btn"]')
  const btnVisible = await approveBtn.isVisible().catch(() => false)
  if (btnVisible) {
    const approveBox = await approveBtn.boundingBox()
    if (approveBox) {
      await page.screenshot({
        path: path.join(HELP_DIR, '06-approve-buttons.png'),
        clip: {
          x: approveBox.x - 8,
          y: approveBox.y - 8,
          width: 360,
          height: approveBox.height + 16,
        },
      })
    } else {
      await page.screenshot({ path: path.join(HELP_DIR, '06-approve-buttons.png') })
    }
  } else {
    await page.screenshot({ path: path.join(HELP_DIR, '06-approve-buttons.png') })
  }
})

// ── Step 7: Quality scores ─────────────────────────────────────────────────

test('step 7 – quality score bars in inspector', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  const firstIssue = page.locator('[data-testid^="issue-item-"]').first()
  await firstIssue.waitFor({ timeout: 10_000 })
  await firstIssue.click()
  await page.waitForTimeout(600)
  const scoreSection = page.locator('[data-testid="quality-scores"]')
  const scoreVisible = await scoreSection.isVisible().catch(() => false)
  if (scoreVisible) {
    const box = await scoreSection.boundingBox()
    if (box) {
      await page.screenshot({
        path: path.join(HELP_DIR, '07-quality-scores.png'),
        clip: { x: box.x - 8, y: box.y - 8, width: box.width + 16, height: box.height + 16 },
      })
      return
    }
  }
  await page.screenshot({ path: path.join(HELP_DIR, '07-quality-scores.png') })
})

// ── Step 8: Keyboard shortcuts ─────────────────────────────────────────────

test('step 8 – keyboard shortcuts popover', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 820 })
  await gotoEditor(page)
  await page.locator('[data-testid="keyboard-shortcuts-btn"]').click()
  await page.locator('[data-testid="shortcuts-popover"]').waitFor()
  await page.waitForTimeout(300)
  const popover = page.locator('[data-testid="shortcuts-popover"]')
  const box = await popover.boundingBox()
  if (box) {
    await page.screenshot({
      path: path.join(HELP_DIR, '08-shortcuts.png'),
      clip: { x: box.x - 12, y: box.y - 12, width: box.width + 24, height: box.height + 24 },
    })
  } else {
    await page.screenshot({ path: path.join(HELP_DIR, '08-shortcuts.png') })
  }
})
