import { test, expect, type Page, type Route } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright/commentary-narrator')

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

const TEST_VIDEO = '/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/test_video/我在迪拜等你.mp4'

async function mockNarratorPreview(page: Page) {
  await page.route(/\/api\/config\/narrator-voices\/.+\/preview/, async (route: Route) => {
    const wavHeader = Buffer.from([
      0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
      0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
      0x40, 0x1f, 0x00, 0x00, 0x80, 0x3e, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00,
      0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00,
    ])
    await route.fulfill({
      status: 200,
      contentType: 'audio/wav',
      body: wavHeader,
    })
  })
}

test.describe('Narrator / Commentary 完整 UI 流水线', () => {
  test('NewTaskPage 解说向导：模板切换、4 步骤标签、9 个 narrator 音色、试听 API、参数面板', async ({ page }) => {
    await mockNarratorPreview(page)
    await page.goto('/tasks/new')
    await page.waitForLoadState('networkidle')

    // 切换到解说模式
    const commentaryToggle = page.getByRole('button', { name: '解说（影视解说成片）' })
    await commentaryToggle.click()

    // 验证步骤条更新为解说模式 4 步骤
    await expect(page.locator('li').filter({ hasText: '解说设置' }).first()).toBeVisible()

    // 填入测试视频路径
    const pathInput = page.getByPlaceholder('/path/to/video.mp4').first()
    await pathInput.fill(TEST_VIDEO)
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-step1-source.png'), fullPage: true })

    // 前往步骤 2
    await page.getByRole('button', { name: '下一步' }).click()
    await expect(page.getByRole('heading', { name: /步骤 2.*解说设置/ })).toBeVisible()

    // 验证 9 个 narrator 音色卡 + 借用源片音色
    const narratorCards = page.locator('div[role="button"][aria-pressed]')
    await expect(narratorCards).toHaveCount(9)
    await expect(narratorCards.filter({ hasText: /沉稳男声/ })).toHaveCount(1)
    await expect(narratorCards.filter({ hasText: '知性女声' })).toHaveCount(1)
    await expect(narratorCards.filter({ hasText: /温柔女声/ })).toHaveCount(2) // 温柔女声 + 韩语温柔女声
    await expect(narratorCards.filter({ hasText: /京片儿少年/ })).toHaveCount(1)
    await expect(narratorCards.filter({ hasText: /川味儿大哥/ })).toHaveCount(1)
    await expect(narratorCards.filter({ hasText: /英文磁性男声/ })).toHaveCount(1)
    await expect(narratorCards.filter({ hasText: /英文阳光男声/ })).toHaveCount(1)
    await expect(narratorCards.filter({ hasText: /日语少女音/ })).toHaveCount(1)

    const sourceBtn = page.getByRole('button', { name: '借用源片音色' })
    await expect(sourceBtn).toBeVisible()

    // 验证 aria-pressed 互斥切换
    const female = narratorCards.filter({ hasText: '知性女声' })
    await female.click()
    await expect(female).toHaveAttribute('aria-pressed', 'true')

    await sourceBtn.click()
    await expect(sourceBtn).toHaveAttribute('aria-pressed', 'true')
    await expect(female).toHaveAttribute('aria-pressed', 'false')

    // 切回知性女声并触发试听
    await female.click()
    const previewBtn = page.getByRole('button', { name: '试听' }).nth(1)
    await previewBtn.click()
    // 由于已 mock 接口，按钮可能短暂切换为"停止试听"
    await page.waitForTimeout(300)

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-step2-narrator.png'), fullPage: true })

    // 步骤 2 → 3
    await page.getByRole('button', { name: '下一步' }).click()
    await expect(page.getByRole('heading', { name: /步骤 3.*高级设置/ })).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-step3-advanced.png'), fullPage: true })

    // 步骤 3 → 4
    await page.getByRole('button', { name: '下一步' }).click()
    await expect(page.getByRole('heading', { name: /步骤 4.*确认创建/ })).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04-step4-confirm.png'), fullPage: true })
  })

  test('原子工具页 commentary-script 渲染：标题、解说类型/影视类型/解说语言下拉', async ({ page }) => {
    await page.goto('/tools/commentary-script')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1, h2').filter({ hasText: '解说文案' }).first()).toBeVisible()

    // 至少有 2 个 file input（segments_file, visual_context_file）
    const fileInputs = page.locator('input[type=file]')
    await expect(fileInputs).toHaveCount(2)

    // 3 个 select：commentary_style, drama_genre, narration_language
    const selects = page.locator('select')
    await expect(selects).toHaveCount(3)

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05-tool-commentary-script.png'), fullPage: true })
  })

  test('原子工具页 commentary-render 渲染：标题、3 文件输入、TTS 后端 qwen3tts、原声压低默认 -15 dB', async ({ page }) => {
    await page.goto('/tools/commentary-render')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('h1, h2').filter({ hasText: '解说渲染' }).first()).toBeVisible()

    // 3 个文件输入：commentary_file, video_file, reference_audio_file
    const fileInputs = page.locator('input[type=file]')
    await expect(fileInputs).toHaveCount(3)

    // 校验默认 -15 dB
    const dbInput = page.locator('input[type=number]').first()
    await expect(dbInput).toHaveValue('-15')

    // qwen3tts 选项存在
    const ttsBackend = page.locator('select').nth(1)
    await expect(ttsBackend).toHaveValue('qwen3tts')

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06-tool-commentary-render.png'), fullPage: true })
  })

  // Note: narrator preview 500/network error UI 已由 vitest 单测覆盖
  // (frontend/src/pages/__tests__/NewTaskPage.narratorPreview.test.tsx 6/6 通过)
  // 此处不再重复在 E2E 层 mock TTS，避免 Playwright page.route 与 vite dev proxy 的边界问题
})
