import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-20260430-164759'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const TASK_URL = `/tasks/${TASK_ID}`

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

async function gotoTask(page: import('@playwright/test').Page, search = '') {
  await page.goto(`${TASK_URL}${search}`)
  await page.waitForLoadState('networkidle')
  await page.locator('[data-testid="flow-step-speaker-review"]').waitFor({ timeout: 15_000 })
}

test('delivery flow strip renders three ordered steps', async ({ page }) => {
  await gotoTask(page)

  await expect(page.locator('[data-testid="flow-step-speaker-review"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="flow-step-dubbing-editor"]').first()).toBeVisible()
  await expect(page.locator('[data-testid="flow-step-export"]').first()).toBeVisible()

  await page.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'flow-strip-01-task-detail.png'),
    fullPage: true,
  })

  const strip = page.locator('[data-testid="delivery-flow-strip"]').first()
  await strip.scrollIntoViewIfNeeded()
  await strip.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'flow-strip-01b-zoomed.png'),
  })
})

test('speaker review step opens the drawer with Step 1 header and flow progress', async ({ page }) => {
  await gotoTask(page)

  await page.locator('[data-testid="flow-step-speaker-review"]').first().click()

  await expect(page.getByRole('heading', { name: '说话人核对' })).toBeVisible()
  await expect(page.locator('[data-testid="speaker-review-flow-progress"]')).toBeVisible()
  await expect(page.getByText(/Step 1 · Speaker Review/)).toBeVisible()

  await page.screenshot({
    path: path.join(SCREENSHOTS_DIR, 'flow-strip-02-speaker-review-drawer.png'),
    fullPage: true,
  })
})

test('auto-opens speaker review drawer when speakerReview=1 query param is set', async ({ page }) => {
  await gotoTask(page, '?speakerReview=1')

  await expect(page.getByRole('heading', { name: '说话人核对' })).toBeVisible({ timeout: 10_000 })
  await expect(page.locator('[data-testid="speaker-review-flow-progress"]')).toBeVisible()
})

test('dubbing editor step navigates to editor route', async ({ page }) => {
  await gotoTask(page)

  const dubbingEditorStep = page.locator('[data-testid="flow-step-dubbing-editor"]').first()
  await expect(dubbingEditorStep).toBeVisible()
  await dubbingEditorStep.click()

  await page.waitForURL(`**/tasks/${TASK_ID}/dubbing-editor`, { timeout: 10_000 })
  await expect(page.locator('[data-testid="dubbing-editor"]')).toBeVisible({ timeout: 15_000 })
})
