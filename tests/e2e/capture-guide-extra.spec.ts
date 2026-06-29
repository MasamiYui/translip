/**
 * Capture the *detail* screenshots the User Guide needs but the basic sweep
 * doesn't cover: each new-task wizard step, the export & speaker-review drawers,
 * and the settings model panel. Defensive — each capture screenshots whatever
 * rendered and never hard-fails the suite.
 *
 *   npx playwright test tests/e2e/capture-guide-extra.spec.ts
 *   Output: frontend/public/guide/*.png
 */
import { test } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-20260612-090340'
const SAMPLE_VIDEO = '/Users/yinyijun/Desktop/测试视频/哪吒预告片 (1).mp4'
const OUT_DIR = path.join(__dirname, '../../frontend/public/guide')
const VIEWPORT = { width: 1440, height: 980 }

test.use({ viewport: VIEWPORT })

async function settle(page: import('@playwright/test').Page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}
function out(name: string) {
  return path.join(OUT_DIR, name)
}

test('new-task wizard – all four steps', async ({ page }) => {
  await page.goto('/tasks/new')
  await settle(page, 700)

  // Step 1 — fill the path, let the media probe populate, then capture.
  const pathField = page.getByPlaceholder('/path/to/video.mp4')
  if (await pathField.isVisible().catch(() => false)) {
    await pathField.fill(SAMPLE_VIDEO)
    await pathField.blur()
    await page.waitForTimeout(2800) // server-side ffprobe
  }
  await page.screenshot({ path: out('new-task-step1.png'), fullPage: true })

  // Advance through steps 2 → 4, screenshotting each.
  for (const n of [2, 3, 4]) {
    const nextBtn = page.getByRole('button', { name: '下一步' })
    if (!(await nextBtn.isEnabled().catch(() => false))) break
    await nextBtn.click().catch(() => {})
    await page.waitForTimeout(900)
    await page.screenshot({ path: out(`new-task-step${n}.png`), fullPage: true })
  }
})

test('task detail – export drawer', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}`)
  await page
    .locator('[data-testid="delivery-flow-strip"]')
    .waitFor({ timeout: 15_000 })
    .catch(() => {})
  await settle(page, 800)
  const exportStep = page.locator('[data-testid="flow-step-export"]').first()
  if (await exportStep.isVisible().catch(() => false)) {
    await exportStep.click().catch(() => {})
    await page.waitForTimeout(900)
    // Only save if the drawer actually opened (heading present).
    const opened = await page
      .getByText('导出向导')
      .first()
      .isVisible()
      .catch(() => false)
    if (opened) await page.screenshot({ path: out('export-drawer.png'), fullPage: false })
  }
})

test('task detail – speaker review drawer', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}`)
  await page
    .locator('[data-testid="delivery-flow-strip"]')
    .waitFor({ timeout: 15_000 })
    .catch(() => {})
  await settle(page, 800)
  const srStep = page.locator('[data-testid="flow-step-speaker-review"]').first()
  if (await srStep.isVisible().catch(() => false)) {
    await srStep.click().catch(() => {})
    const drawer = page.locator('[data-testid="speaker-review-drawer"]')
    await drawer.waitFor({ timeout: 8000 }).catch(() => {})
    await page.waitForTimeout(800)
    if (await drawer.isVisible().catch(() => false)) {
      await page.screenshot({ path: out('speaker-review.png'), fullPage: false })
    }
  }
})

test('task detail – stage detail drawer', async ({ page }) => {
  await page.goto(`/tasks/${TASK_ID}`)
  await settle(page, 1400)
  // Pipeline nodes carry no testid; click a stage by its visible label.
  for (const label of ['翻译', '合成', '转写', '分离']) {
    const node = page.getByText(label, { exact: true }).first()
    if (await node.isVisible().catch(() => false)) {
      await node.click().catch(() => {})
      await page.waitForTimeout(900)
      // A dialog/aside opening is the signal we hit a node detail.
      const dlg = page.locator('[role="dialog"], aside').last()
      if (await dlg.isVisible().catch(() => false)) {
        await page.screenshot({ path: out('stage-drawer.png'), fullPage: false })
        return
      }
    }
  }
})

test('settings – model management panel', async ({ page }) => {
  await page.goto('/settings')
  await settle(page, 900)
  const modelsNav = page.getByRole('button', { name: /模型管理|模型/ }).first()
  if (await modelsNav.isVisible().catch(() => false)) {
    await modelsNav.click().catch(() => {})
    await page.waitForTimeout(800)
  }
  await page.screenshot({ path: out('settings-models.png'), fullPage: true })
})
