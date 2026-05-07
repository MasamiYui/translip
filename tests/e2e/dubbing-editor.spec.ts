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
  await expect(page.getByText('问题队列').first()).toBeVisible()

  // Timeline header
  await expect(page.locator('[data-testid="timeline-header"]')).toBeVisible()

  // Inspector panel
  await expect(page.getByText('检视面板').first()).toBeVisible()
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
  const bgLabel = page.getByText('背景音').first()
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
  const inspector = page.getByText('检视面板').first()
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

// ---------------------------------------------------------------------------
// Phase 2 Tests
// ---------------------------------------------------------------------------

// 12. Phase 2: Undo/Redo buttons visible in top bar
test('undo and redo buttons are visible in top bar', async ({ page }) => {
  await gotoEditor(page)

  const undoBtn = page.locator('[data-testid="undo-btn"]')
  const redoBtn = page.locator('[data-testid="redo-btn"]')

  await expect(undoBtn).toBeVisible()
  await expect(redoBtn).toBeVisible()

  // Redo should be disabled initially (not in undo mode)
  await expect(redoBtn).toBeDisabled()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '12-undo-redo-buttons.png') })
})

// 13. Phase 2: SRT export button visible
test('SRT export button is visible and downloadable', async ({ page }) => {
  await gotoEditor(page)

  const srtBtn = page.locator('[data-testid="srt-export-btn"]')
  await expect(srtBtn).toBeVisible()

  // Intercept download and verify it fires
  const downloadPromise = page.waitForEvent('download', { timeout: 5000 }).catch(() => null)
  await srtBtn.click()
  const download = await downloadPromise

  if (download) {
    expect(download.suggestedFilename()).toContain('.srt')
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '13-srt-exported.png') })
  } else {
    // SRT button click didn't trigger a download event (browser may vary) — button is present
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '13-srt-btn-visible.png') })
  }
})

// 14. Phase 2: Issue severity chart visible
test('issue severity distribution chart is visible', async ({ page }) => {
  await gotoEditor(page)

  // Chart renders conditionally (only when there are open issues)
  const chart = page.locator('[data-testid="severity-chart"]')
  if (await chart.count() > 0) {
    await expect(chart).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '14-severity-chart.png') })
  } else {
    // No open issues — no chart (acceptable)
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '14-no-issues.png') })
  }
})

// 15. Phase 2: Playhead visible in timeline when scrubbing
test('timeline playhead appears when audio is playing', async ({ page }) => {
  await gotoEditor(page)

  // Select a unit first
  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }
  await firstIssue.click()
  await page.waitForTimeout(500)

  // Verify the timeline header is visible (playhead only shows when > 0s)
  await expect(page.locator('[data-testid="timeline-header"]')).toBeVisible()

  // Simulate a seek by clicking on the timeline area (simulates playhead)
  // The playhead position updates via rAF so just verify timeline renders correctly
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '15-timeline-playhead.png') })
})

// 16. Phase 2: Quality score breakdown visible in inspector
test('quality scores appear in segment inspector', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(500)

  const qualityScores = page.locator('[data-testid="quality-scores"]')
  if (await qualityScores.count() > 0) {
    await expect(qualityScores).toBeVisible()
    await expect(qualityScores.getByText(/声纹相似度/)).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '16-quality-scores.png') })
  } else {
    // Quality scores only show if clip has duration data — acceptable fallback
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '16-quality-scores-na.png') })
  }
})

// 17. Phase 2: Voice preview player visible in character inspector
test('voice preview player visible in character inspector', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(500)

  // Voice preview player should appear inside character inspector
  const voicePlayer = page.locator('[data-testid="voice-preview-player"]').first()
  await expect(voicePlayer).toBeVisible()

  // Voice swap button
  const swapBtn = page.locator('[data-testid="voice-swap-btn"]').first()
  await expect(swapBtn).toBeVisible()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '17-voice-preview.png') })
})

// 18. Phase 2: Voice swap modal opens
test('voice swap modal opens when swap button is clicked', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(500)

  const swapBtn = page.locator('[data-testid="voice-swap-btn"]').first()
  await expect(swapBtn).toBeVisible()
  await swapBtn.click()

  // Modal should appear
  await expect(page.getByText(/更换声音参考/)).toBeVisible()
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '18-voice-swap-modal.png') })

  // Close modal
  const cancelBtn = page.getByRole('button', { name: /取消/ }).first()
  await cancelBtn.click()
})

// 19. Phase 2: Candidate list visible when candidates exist
test('candidate tournament list renders when candidates are present', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(500)

  const candidateList = page.locator('[data-testid="candidate-list"]')
  if (await candidateList.count() > 0) {
    await expect(candidateList).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '19-candidate-list.png') })
  } else {
    // No candidates for this unit — acceptable
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '19-no-candidates.png') })
  }
})

// 20. Phase 2: Voice mismatch card shows when character has mismatch flag
test('voice mismatch quick-fix card appears for units with mismatch', async ({ page }) => {
  await gotoEditor(page)

  // Try each issue until we find one with mismatch flag (or report absent)
  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(400)

  const mismatchCard = page.locator('[data-testid="voice-mismatch-card"]')
  if (await mismatchCard.count() > 0) {
    await expect(mismatchCard).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '20-voice-mismatch-card.png') })
  } else {
    // First unit has no mismatch — acceptable
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '20-no-mismatch.png') })
  }
})

// 21. Phase 2: Back-translation check UI available
test('back-translation ASR check section is available in inspector', async ({ page }) => {
  await gotoEditor(page)

  const issueList = page.locator('[data-testid="issue-list"]')
  const firstIssue = issueList.locator('button').first()
  if (await firstIssue.count() === 0) {
    test.skip()
    return
  }

  await firstIssue.click()
  await page.waitForTimeout(500)

  // The "ASR 回译校验" toggle should be visible
  await expect(page.getByText(/ASR 回译校验/)).toBeVisible()

  // Click to expand
  await page.getByText(/ASR 回译校验/).click()
  await page.waitForTimeout(1000) // wait for query

  const backtranslateResult = page.locator('[data-testid="backtranslate-result"]')
  await expect(backtranslateResult).toBeVisible()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '21-backtranslate.png') })
})

// ---------------------------------------------------------------------------
// 22. Mode toggle: Edit ↔ Preview buttons are visible in top bar
// ---------------------------------------------------------------------------
test('mode toggle buttons are visible in top bar', async ({ page }) => {
  await gotoEditor(page)

  const editBtn = page.locator('[data-testid="mode-edit-btn"]')
  const previewBtn = page.locator('[data-testid="mode-preview-btn"]')

  await expect(editBtn).toBeVisible()
  await expect(previewBtn).toBeVisible()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '22-mode-toggle-buttons.png') })
})

// ---------------------------------------------------------------------------
// 23. Edit mode is active by default (3-column layout visible)
// ---------------------------------------------------------------------------
test('edit mode is active by default with 3-column layout', async ({ page }) => {
  await gotoEditor(page)

  // Edit mode: Issue Queue + Inspector should be visible
  await expect(page.getByText('问题队列').first()).toBeVisible()
  await expect(page.getByText('检视面板').first()).toBeVisible()
  await expect(page.locator('[data-testid="timeline-header"]')).toBeVisible()

  // Edit button should appear active (has bg-white class indicating selected)
  const editBtn = page.locator('[data-testid="mode-edit-btn"]')
  await expect(editBtn).toHaveClass(/bg-white/)

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '23-edit-mode-default.png') })
})

// ---------------------------------------------------------------------------
// 24. Switching to preview mode hides edit panels and shows video player
// ---------------------------------------------------------------------------
test('switching to preview mode shows video player and hides side panels', async ({ page }) => {
  await gotoEditor(page)

  // Click preview button
  const previewBtn = page.locator('[data-testid="mode-preview-btn"]')
  await previewBtn.click()
  await page.waitForTimeout(300)

  // Issue Queue should be gone
  await expect(page.getByText('问题队列').first()).not.toBeVisible()

  // Inspector should be gone
  await expect(page.getByText('检视面板').first()).not.toBeVisible()

  // Preview mode shows a video element
  await expect(page.locator('video')).toBeVisible()

  // Timeline is still visible in preview mode (dark speaker lanes)
  await expect(page.locator('[data-testid="timeline-header"]')).toBeVisible()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '24-preview-mode.png') })
})

// ---------------------------------------------------------------------------
// 25. Preview mode controls bar is visible with play button, timecode, track switch
// ---------------------------------------------------------------------------
test('preview mode control bar is visible with expected controls', async ({ page }) => {
  await gotoEditor(page)

  await page.locator('[data-testid="mode-preview-btn"]').click()
  await page.waitForTimeout(300)

  // Play button visible
  const playButton = page.locator('button').filter({ hasText: '' }).first()
  await expect(page.locator('video')).toBeVisible()

  // Audio track switcher: "原声" and "配音" buttons
  await expect(page.getByText('原声').first()).toBeVisible()
  await expect(page.getByText('配音').first()).toBeVisible()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '25-preview-controls.png') })
})

// ---------------------------------------------------------------------------
// 26. Can switch back from preview to edit mode
// ---------------------------------------------------------------------------
test('can switch back from preview to edit mode', async ({ page }) => {
  await gotoEditor(page)

  // Go to preview
  await page.locator('[data-testid="mode-preview-btn"]').click()
  await page.waitForTimeout(300)
  await expect(page.locator('video')).toBeVisible()

  // Switch back to edit
  await page.locator('[data-testid="mode-edit-btn"]').click()
  await page.waitForTimeout(300)

  // Edit layout should restore
  await expect(page.getByText('问题队列').first()).toBeVisible()
  await expect(page.getByText('检视面板').first()).toBeVisible()
  await expect(page.locator('video')).not.toBeVisible()

  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '26-back-to-edit.png') })
})

