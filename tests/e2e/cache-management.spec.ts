import { test, expect, type Page, type Route } from '@playwright/test'

// ---------------------------------------------------------------------------
// Cache management Playwright E2E.
//
// These specs mock /api/system/* responses so we never touch the real user
// cache. All interactions go through the SettingsPage and exercise:
//   - breakdown expansion
//   - change-dir dialog validation error
//   - change-dir success flow
//   - cleanup dialog submission
//   - migration progress polling + cancel
// ---------------------------------------------------------------------------

type CacheItem = {
  key: string
  label: string
  group: 'model' | 'hub' | 'pipeline' | 'temp'
  bytes: number
  paths: string[]
  removable: boolean
  present: boolean
}

type Breakdown = {
  cache_dir: string
  huggingface_hub_dir: string
  total_bytes: number
  items: CacheItem[]
}

function buildBreakdown(): Breakdown {
  const items: CacheItem[] = [
    {
      key: 'cdx23',
      label: 'CDX23 dialogue model',
      group: 'model',
      bytes: 3_400_000_000,
      paths: ['/tmp/cache/cdx23'],
      removable: true,
      present: true,
    },
    {
      key: 'faster_whisper_small',
      label: 'Faster-Whisper (small)',
      group: 'model',
      bytes: 480_000_000,
      paths: ['/tmp/cache/whisper'],
      removable: true,
      present: true,
    },
    {
      key: 'hf_hub',
      label: 'HuggingFace Hub cache',
      group: 'hub',
      bytes: 1_200_000_000,
      paths: ['/tmp/cache/hf'],
      removable: true,
      present: true,
    },
    {
      key: 'pipeline_outputs',
      label: 'Pipeline outputs',
      group: 'pipeline',
      bytes: 2_100_000_000,
      paths: ['/tmp/cache/outputs'],
      removable: true,
      present: true,
    },
    {
      key: 'temp',
      label: 'Temporary files',
      group: 'temp',
      bytes: 50_000_000,
      paths: ['/tmp/cache/tmp'],
      removable: true,
      present: true,
    },
  ]
  return {
    cache_dir: '/tmp/cache',
    huggingface_hub_dir: '/tmp/cache/hf',
    total_bytes: items.reduce((s, i) => s + i.bytes, 0),
    items,
  }
}

async function mockSystemApis(page: Page) {
  await page.route('**/api/system/info', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        python_version: '3.11.0',
        platform: 'darwin',
        device: 'mps',
        cache_dir: '/tmp/cache',
        cache_size_bytes: 7_230_000_000,
        models: [
          { name: 'CDX23', status: 'available' },
          { name: 'Faster-Whisper', status: 'available' },
        ],
      }),
    })
  })

  await page.route('**/api/system/cache/breakdown', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildBreakdown()),
    })
  })
}

test.describe('cache management', () => {
  test('expand breakdown and show items', async ({ page }) => {
    await mockSystemApis(page)

    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: '全局设置' })).toBeVisible()

    await page.getByTestId('cache-toggle-details').click()
    const breakdown = page.getByTestId('cache-breakdown')
    await expect(breakdown).toBeVisible()
    await expect(page.getByTestId('cache-item-cdx23')).toBeVisible()
    await expect(page.getByTestId('cache-item-hf_hub')).toBeVisible()
    await expect(page.getByTestId('cache-item-pipeline_outputs')).toBeVisible()
  })

  test('change-dir dialog surfaces validation errors', async ({ page }) => {
    await mockSystemApis(page)
    await page.route('**/api/system/cache/set-dir', async (route: Route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { code: 'target_in_forbidden_prefix', message: 'forbidden' },
        }),
      })
    })

    await page.goto('/settings')
    await page.getByTestId('cache-change-dir').click()
    const dialog = page.getByTestId('cache-change-dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByTestId('cache-target-input').fill('/etc/nope')
    await dialog.getByTestId('cache-dialog-submit').click()

    await expect(dialog.getByTestId('cache-dialog-error')).toContainText('受保护的系统目录')
  })

  test('change-dir success flow updates toast', async ({ page }) => {
    await mockSystemApis(page)
    await page.route('**/api/system/cache/set-dir', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, cache_dir: '/new/cache' }),
      })
    })

    await page.goto('/settings')
    await page.getByTestId('cache-change-dir').click()
    const dialog = page.getByTestId('cache-change-dialog')

    await dialog.getByTestId('cache-target-input').fill('/new/cache')
    await dialog.getByTestId('cache-dialog-submit').click()

    await expect(dialog).toBeHidden()
    await expect(page.getByTestId('cache-toast')).toContainText('配置已保存')
  })

  test('cleanup dialog submits selected keys', async ({ page }) => {
    await mockSystemApis(page)
    let cleanupPayload: { keys: string[] } | null = null
    await page.route('**/api/system/cache/cleanup', async (route: Route) => {
      cleanupPayload = JSON.parse(route.request().postData() ?? '{}')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          freed_bytes: 1_800_000_000,
          details: [
            { key: 'temp', freed_bytes: 50_000_000 },
            { key: 'pipeline_outputs', freed_bytes: 1_750_000_000 },
          ],
        }),
      })
    })

    await page.goto('/settings')
    await page.getByTestId('cache-toggle-details').click()
    await expect(page.getByTestId('cache-breakdown')).toBeVisible()
    await page.getByTestId('cache-cleanup').click()

    const dialog = page.getByTestId('cache-cleanup-dialog')
    await expect(dialog).toBeVisible()

    // Uncheck model weights to keep only pipeline + temp + hub.
    await dialog.getByTestId('cache-cleanup-checkbox-cdx23').uncheck()
    await dialog.getByTestId('cache-cleanup-checkbox-faster_whisper_small').uncheck()

    await dialog.getByTestId('cache-cleanup-submit').click()

    await expect(dialog).toBeHidden()
    await expect(page.getByTestId('cache-toast')).toContainText('一键清理')
    expect(cleanupPayload).not.toBeNull()
    expect(cleanupPayload!.keys).toEqual(
      expect.arrayContaining(['hf_hub', 'pipeline_outputs', 'temp']),
    )
    expect(cleanupPayload!.keys).not.toContain('cdx23')
  })

  test('migration polls progress and can be cancelled', async ({ page }) => {
    await mockSystemApis(page)

    const taskId = 'task-e2e-1'
    let pollCount = 0
    let cancelRequested = false

    await page.route('**/api/system/cache/migrate', async (route: Route) => {
      if (route.request().method() !== 'POST') {
        await route.fallback()
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: taskId,
          status: 'running',
          state: 'running',
          src: '/tmp/cache',
          dst: '/tmp/new-cache',
          mode: 'move',
          switch_after: true,
          progress: { total_bytes: 1000, copied_bytes: 0, current_file: null, speed_bps: 0 },
          error: null,
          started_at: Date.now() / 1000,
          finished_at: null,
        }),
      })
    })

    await page.route(`**/api/system/cache/migrate/${taskId}`, async (route: Route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback()
        return
      }
      pollCount += 1
      const copied = Math.min(400, pollCount * 100)
      const status = cancelRequested ? 'cancelled' : 'running'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: taskId,
          status,
          state: status,
          src: '/tmp/cache',
          dst: '/tmp/new-cache',
          mode: 'move',
          switch_after: true,
          progress: {
            total_bytes: 1000,
            copied_bytes: cancelRequested ? copied : copied,
            current_file: `/tmp/cache/file-${pollCount}`,
            speed_bps: 100,
          },
          error: null,
          started_at: Date.now() / 1000,
          finished_at: cancelRequested ? Date.now() / 1000 : null,
        }),
      })
    })

    await page.route(`**/api/system/cache/migrate/${taskId}/cancel`, async (route: Route) => {
      cancelRequested = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      })
    })

    await page.goto('/settings')
    await page.getByTestId('cache-migrate').click()

    const dialog = page.getByTestId('cache-migrate-dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByTestId('cache-target-input').fill('/tmp/new-cache')
    await dialog.getByTestId('cache-dialog-submit').click()

    const banner = page.getByTestId('cache-migration-banner')
    await expect(banner).toBeVisible()
    await expect(banner.getByTestId('cache-migration-cancel')).toBeVisible()

    await banner.getByTestId('cache-migration-cancel').click()

    await expect(banner.locator('[data-testid="cache-migration-status"]')).toContainText(
      '已取消',
      { timeout: 5_000 },
    )
  })
})
