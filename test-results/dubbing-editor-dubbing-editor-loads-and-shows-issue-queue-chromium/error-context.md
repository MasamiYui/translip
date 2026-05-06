# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dubbing-editor.spec.ts >> dubbing editor loads and shows issue queue
- Location: tests/e2e/dubbing-editor.spec.ts:12:5

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.goto: net::ERR_ABORTED; maybe frame was detached?
Call log:
  - navigating to "http://localhost:5173/tasks/task-20260430-164759", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test'
  2  | import path from 'path'
  3  | import fs from 'fs'
  4  | 
  5  | const TASK_ID = 'task-20260430-164759'
  6  | const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
  7  | 
  8  | test.beforeAll(() => {
  9  |   fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
  10 | })
  11 | 
  12 | test('dubbing editor loads and shows issue queue', async ({ page }) => {
  13 |   // Navigate to the task detail page
> 14 |   await page.goto(`/tasks/${TASK_ID}`)
     |              ^ Error: page.goto: net::ERR_ABORTED; maybe frame was detached?
  15 |   await page.waitForLoadState('networkidle')
  16 |   await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-task-detail.png'), fullPage: true })
  17 | 
  18 |   // Click the "专业配音编辑台" link
  19 |   const editorLink = page.getByRole('link', { name: /专业配音编辑台/ })
  20 |   await expect(editorLink).toBeVisible()
  21 |   await editorLink.click()
  22 | 
  23 |   // Wait for the dubbing editor to load
  24 |   await page.waitForURL(`**/tasks/${TASK_ID}/dubbing-editor`)
  25 |   await page.waitForLoadState('networkidle')
  26 |   await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-dubbing-editor-loaded.png'), fullPage: true })
  27 | 
  28 |   // Check the top bar has the title
  29 |   await expect(page.getByText(/专业影视配音编辑台|配音编辑/).first()).toBeVisible()
  30 | 
  31 |   // Check the issue queue is visible
  32 |   await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-dubbing-editor-issues.png') })
  33 | })
  34 | 
  35 | test('dubbing editor issue interaction', async ({ page }) => {
  36 |   await page.goto(`/tasks/${TASK_ID}/dubbing-editor`)
  37 |   await page.waitForLoadState('networkidle')
  38 | 
  39 |   // Screenshot of the full editor
  40 |   await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04-editor-full.png'), fullPage: true })
  41 | 
  42 |   // Look for a P0 issue and click it
  43 |   const p0Issue = page.locator('[data-severity="p0"], .issue-card').first()
  44 |   if (await p0Issue.count() > 0) {
  45 |     await p0Issue.click()
  46 |     await page.waitForTimeout(500)
  47 |     await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05-issue-selected.png'), fullPage: true })
  48 |   }
  49 | })
  50 | 
```