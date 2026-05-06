import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-20260430-164759'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

test('dubbing editor loads and shows issue queue', async ({ page }) => {
  // Navigate to the task detail page
  await page.goto(`/tasks/${TASK_ID}`)
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-task-detail.png'), fullPage: true })

  // Click the "专业配音编辑台" link
  const editorLink = page.getByRole('link', { name: /专业配音编辑台/ })
  await expect(editorLink).toBeVisible()
  await editorLink.click()

  // Wait for the dubbing editor to load
  await page.waitForURL(`**/tasks/${TASK_ID}/dubbing-editor`)
  await page.waitForLoadState('networkidle')
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-dubbing-editor-loaded.png'), fullPage: true })

  // Check the top bar has the title
  await expect(page.getByText(/专业影视配音编辑台|配音编辑/).first()).toBeVisible()

  // Check the issue queue is visible
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-dubbing-editor-issues.png') })
})

test('dubbing editor issue interaction', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}/dubbing-editor`)
  await page.waitForLoadState('networkidle')

  // Screenshot of the full editor
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04-editor-full.png'), fullPage: true })

  // Look for a P0 issue and click it
  const p0Issue = page.locator('[data-severity="p0"], .issue-card').first()
  if (await p0Issue.count() > 0) {
    await p0Issue.click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05-issue-selected.png'), fullPage: true })
  }
})
