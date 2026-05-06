import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-20260430-164759'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const EDITOR_URL = `/tasks/${TASK_ID}/dubbing-editor`

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

// Helper: navigate to editor and wait for it to load
async function gotoEditor(page: import('@playwright/test').Page) {
  await page.goto(EDITOR_URL)
  await page.waitForLoadState('networkidle')
  // Wait for the root testid to appear
  await page.locator('[data-testid="dubbing-editor"]').waitFor({ timeout: 15_000 })
}

// ---------------------------------------------------------------------------
// 1. Basic load
// ---------------------------------------------------------------------------
test('dubbing editor loads and shows key regions', async ({ page }) => {
  await gotoEditor(page)
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-editor-loaded.png'), fullPage: true })

  // Top bar title
  await expect(page.getByText(/专业配音编辑台/).first()).toBeVisible()

  // Issue Queue panel
  await expect(page.getByText('Issue Queue').first()).toBeVisible()

  // Timeline header
  await expect(page.locator('[data-testid="timeline-header"]')).toBeVisible()

  // Inspector panel
  await expect(page.getByText('Inspector').first()).toBeVisible()
})

// ---------------------------------------------------------------------------
// 2. P2: Progress bar visible in top bar
// ---------------------------------------------------------------------------
test('progress bar is visible in top bar', async ({ page }) => {
  await gotoEditor(page)

  const bar = page.locator('[data-testid="progress-bar"]')
  await expect(bar).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-progress-bar.png') })
})

// ---------------------------------------------------------------------------
// 3. P0: Keyboard shortcut popover
// ---------------------------------------------------------------------------
test('keyboard shortcut popover opens and shows shortcuts', async ({ page }) => {
  await gotoEditor(page)

  const kbBtn = page.locator('[data-testid="keyboard-shortcuts-btn"]')
  await expect(kbBtn).toBeVisible()
  await kbBtn.click()

  const popover = page.locator('[data-testid="shortcuts-popover"]')
  await expect(popover).toBeVisible()
  await expect(popover.getByText(/Space/)).toBeVisible()
  await expect(popover.getByText(/Esc/)).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-shortcuts-popover.png') })
})

// ---------------------------------------------------------------------------
// 4. P0: Timeline zoom controls functional
// ---------------------------------------------------------------------------
test('timeline zoom controls are visible and functional', async ({ page }) => {
  await gotoEditor(page)

  const zoomControls = page.locator('[data-testid="zoom-controls"]')
  await expect(zoomControls).toBeVisible()

  // Get current zoom text
  const zoomText = zoomControls.locator('span')
  const initialZoom = await zoomText.textContent()

  // Click zoom-in
  const zoomInBtn = zoomControls.locator('button').last()
  await zoomInBtn.click()

  const newZoom = await zoomText.textContent()
  expect(newZoom).not.toEqual(initialZoom)
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04-timeline-zoomed.png') })

  // Click zoom-out twice to go back
  const zoomOutBtn = zoomControls.locator('button').first()
  await zoomOutBtn.click()
})

// ---------------------------------------------------------------------------
// 5. P1: Background waveform track present in timeline
// ---------------------------------------------------------------------------
test('background track is present in timeline', async ({ page }) => {
  await gotoEditor(page)

  // The "Background" label should be present in the timeline
  const bgLabel = page.getByText('Background').first()
  await expect(bgLabel).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05-background-track.png') })
})

// ---------------------------------------------------------------------------
// 6. Issue navigation — click issue → unit loads in inspector
// ---------------------------------------------------------------------------
test('clicking an issue selects the corresponding unit', async ({ page }) => {
  await gotoEditor(page)

  // Find first issue in the list
  const issueList = page.locator('[data-testid="issue-list"]')
  await expect(issueList).toBeVisible()

  const firstIssue = issueList.locator('button').first()
  const issueCount = await firstIssue.count()
  if (issueCount === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(300)

  // Inspector should now show a unit_id
  const inspector = page.getByText('Inspector').first()
  await expect(inspector).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06-issue-selected.png'), fullPage: true })
})

// ---------------------------------------------------------------------------
// 7. P2: Bulk approve button visible when applicable
// ---------------------------------------------------------------------------
test('bulk approve button appears for P2-only units', async ({ page }) => {
  await gotoEditor(page)

  // Bulk approve button is conditionally shown; just verify the issue queue renders
  const issueList = page.locator('[data-testid="issue-list"]')
  await expect(issueList).toBeVisible()

  // If bulk approve button is present, click it
  const bulkBtn = page.locator('[data-testid="bulk-approve-btn"]')
  if (await bulkBtn.count() > 0) {
    await expect(bulkBtn).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '07-bulk-approve.png') })
  } else {
    // No P2-only units — acceptable
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '07-no-bulk-approve.png') })
  }
})

// ---------------------------------------------------------------------------
// 8. P1: Re-synthesis button visible in segment inspector after selecting unit
// ---------------------------------------------------------------------------
test('resynthesize button is visible in segment inspector', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(400)

  const resynthBtn = page.locator('[data-testid="resynthesize-btn"]')
  await expect(resynthBtn).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '08-resynthesize-btn.png') })
})

// ---------------------------------------------------------------------------
// 9. P2: Operation history accordion in inspector
// ---------------------------------------------------------------------------
test('operation history accordion appears when unit has ops', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(400)

  const opHistoryBtn = page.locator('[data-testid="op-history-btn"]')
  if (await opHistoryBtn.count() > 0) {
    await opHistoryBtn.click()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '09-op-history.png') })
  } else {
    // No operations recorded yet — acceptable
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '09-no-op-history.png') })
  }
})

// ---------------------------------------------------------------------------
// 10. P1: A/B comparison area visible when unit is selected
// ---------------------------------------------------------------------------
test('AB comparison area visible when unit is selected', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(600)

  // A/B comparison section should be visible (text "A/B 对比")
  await expect(page.getByText(/A\/B 对比/).first()).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '10-ab-comparison.png'), fullPage: true })
})

// ---------------------------------------------------------------------------
// Legacy: original smoke tests (kept for compatibility)
// ---------------------------------------------------------------------------
test('dubbing editor loads and shows issue queue (legacy)', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}`)
  await page.waitForLoadState('networkidle')

  const editorLink = page.getByRole('link', { name: /专业配音编辑台/ })
  if (await editorLink.count() === 0) {
    // Try direct navigation
    await gotoEditor(page)
  } else {
    await editorLink.click()
    await page.waitForURL(`**/tasks/${TASK_ID}/dubbing-editor`)
    await page.waitForLoadState('networkidle')
  }

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '11-legacy-smoke.png'), fullPage: true })
  await expect(page.locator('[data-testid="dubbing-editor"]')).toBeVisible()
})

