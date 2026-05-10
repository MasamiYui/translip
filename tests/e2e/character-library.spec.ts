import { test, expect, type Page } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

type PersonaRecord = {
  id: string
  name: string
  aliases?: string[]
  role?: string | null
  actor_name?: string | null
  gender?: string | null
  age_hint?: string | null
  tags?: string[]
  avatar_emoji?: string | null
  color?: string | null
  tts_voice_id?: string | null
  note?: string | null
  created_at?: string
  updated_at?: string
}

function seedPersonas(): PersonaRecord[] {
  return [
    {
      id: 'persona_amy',
      name: '艾米',
      aliases: ['Amy'],
      actor_name: 'Anne Hathaway',
      role: '女主',
      gender: 'female',
      age_hint: '青年',
      avatar_emoji: '👩',
      color: '#ef4444',
      tags: ['主线'],
      note: '第一女主角',
      updated_at: '2026-05-01T10:00:00',
      created_at: '2026-04-01T10:00:00',
    },
    {
      id: 'persona_bob',
      name: '鲍勃',
      aliases: [],
      actor_name: 'Bob Smith',
      role: '男配',
      gender: 'male',
      tags: ['配角'],
      avatar_emoji: '👨',
      color: '#3b82f6',
      updated_at: '2026-04-20T10:00:00',
    },
  ]
}

async function setupRoutes(page: Page, state: { personas: PersonaRecord[] }) {
  await page.route('**/api/global-personas/import', async route => {
    const body = route.request().postDataJSON() as {
      personas: PersonaRecord[]
      mode?: string
    }
    const now = new Date().toISOString()
    for (const incoming of body.personas ?? []) {
      const idx = state.personas.findIndex(
        p => p.name.toLowerCase().trim() === (incoming.name ?? '').toLowerCase().trim(),
      )
      const next: PersonaRecord = {
        ...incoming,
        id: incoming.id || `persona_${Math.random().toString(36).slice(2)}`,
        updated_at: now,
        created_at: idx >= 0 ? state.personas[idx].created_at ?? now : now,
      }
      if (idx >= 0) {
        state.personas[idx] = { ...state.personas[idx], ...next }
      } else {
        state.personas.push(next)
      }
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        accepted: body.personas.length,
        skipped: 0,
        total: state.personas.length,
        personas: state.personas.map(p => ({ ...p })),
      }),
    })
  })

  await page.route('**/api/global-personas/*', async route => {
    const url = route.request().url()
    if (url.endsWith('/import')) {
      await route.fallback()
      return
    }
    if (route.request().method() === 'DELETE') {
      const id = url.split('/').pop() || ''
      state.personas = state.personas.filter(p => p.id !== id)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, personas: state.personas }),
      })
      return
    }
    await route.fallback()
  })

  await page.route('**/api/global-personas', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          path: '/tmp/e2e-personas.json',
          personas: state.personas.map(p => ({ ...p })),
          version: 1,
          updated_at: new Date().toISOString(),
        }),
      })
      return
    }
    await route.fallback()
  })

  // 侧栏依赖的 atomic-tools 列表，避免 dev proxy 404 噪音
  await page.route('**/api/atomic-tools', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })
}

test.describe('角色库管理页', () => {
  test('从侧栏进入页面、搜索、编辑、删除', async ({ page }) => {
    const state = { personas: seedPersonas() }
    await setupRoutes(page, state)

    await page.goto('/')
    await page.getByTestId('sidebar-link-character-library').click()
    await expect(page).toHaveURL(/\/character-library$/)

    await expect(page.getByTestId('character-library-list')).toBeVisible()
    await expect(page.getByTestId('character-row-persona_amy')).toContainText('艾米')
    await expect(page.getByTestId('character-row-persona_amy')).toContainText('Anne Hathaway')
    await expect(page.getByTestId('character-row-persona_bob')).toContainText('鲍勃')
    await expect(page.getByTestId('character-library-count')).toContainText('2')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-list.png'),
      fullPage: true,
    })

    // 搜索
    await page.getByTestId('character-library-search').fill('Bob')
    await expect(page.getByTestId('character-row-persona_amy')).toHaveCount(0)
    await expect(page.getByTestId('character-row-persona_bob')).toBeVisible()

    await page.getByTestId('character-library-search').fill('')

    // 编辑艾米
    await page.getByTestId('character-edit-persona_amy').click()
    await expect(page.getByTestId('character-editor')).toBeVisible()
    const nameField = page.getByTestId('character-field-name')
    await expect(nameField).toHaveValue('艾米')
    await page.getByTestId('character-field-actor').fill('Anne H.')
    await page.getByTestId('character-field-tags').fill('主线, 女主角')
    await page.getByTestId('character-editor-save').click()

    await expect(page.getByTestId('character-library-flash-success')).toContainText('艾米')
    await expect(page.getByTestId('character-row-persona_amy')).toContainText('Anne H.')
    await expect(page.getByTestId('character-row-persona_amy')).toContainText('女主角')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-edited.png'),
      fullPage: true,
    })

    // 删除鲍勃（需要绕过 confirm 弹窗）
    page.once('dialog', dialog => dialog.accept())
    await page.getByTestId('character-delete-persona_bob').click()
    await expect(page.getByTestId('character-library-flash-success')).toContainText('鲍勃')
    await expect(page.getByTestId('character-row-persona_bob')).toHaveCount(0)
    await expect(page.getByTestId('character-library-count')).toContainText('1')
  })

  test('从空态创建第一个角色', async ({ page }) => {
    const state: { personas: PersonaRecord[] } = { personas: [] }
    await setupRoutes(page, state)

    await page.goto('/character-library')

    await expect(page.getByTestId('character-library-page-empty')).toBeVisible()
    await page.getByTestId('character-library-empty-cta').click()
    await expect(page.getByTestId('character-editor')).toBeVisible()

    await page.getByTestId('character-field-name').fill('李雷')
    await page.getByTestId('character-field-actor').fill('张三')
    await page.getByTestId('character-field-role').fill('学生')
    await page.getByTestId('character-field-gender').selectOption('male')
    await page.getByTestId('character-field-tags').fill('学生, 主角')
    await page.getByTestId('character-editor-save').click()

    await expect(page.getByTestId('character-library-flash-success')).toContainText('李雷')
    await expect(page.getByTestId('character-library-count')).toContainText('1')
    await expect(page.getByText('李雷', { exact: true })).toBeVisible()
    await expect(page.getByText('张三')).toBeVisible()

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'character-library-created.png'),
      fullPage: true,
    })
  })

  test('搜索无匹配时展示筛选空态', async ({ page }) => {
    const state = { personas: seedPersonas() }
    await setupRoutes(page, state)

    await page.goto('/character-library')

    await expect(page.getByTestId('character-library-list')).toBeVisible()
    await page.getByTestId('character-library-search').fill('zzz_no_match')
    await expect(page.getByTestId('character-library-empty-filtered')).toBeVisible()
  })
})
