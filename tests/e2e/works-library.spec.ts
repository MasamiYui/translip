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
  work_id?: string | null
  updated_at?: string
  created_at?: string
}

type WorkRecord = {
  id: string
  title: string
  type: string
  year?: number | null
  aliases?: string[]
  cover_emoji?: string | null
  color?: string | null
  note?: string | null
  tags?: string[]
  external_refs?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  cast_snapshot?: unknown[] | null
  updated_at?: string
  created_at?: string
}

type WorkTypeRecord = {
  key: string
  label_zh: string
  label_en: string
  builtin: boolean
}

interface State {
  personas: PersonaRecord[]
  works: WorkRecord[]
  types: WorkTypeRecord[]
}

function seedState(): State {
  const now = new Date().toISOString()
  return {
    personas: [
      {
        id: 'persona_nezha',
        name: '哪吒',
        role: '主角',
        gender: 'male',
        avatar_emoji: '🔥',
        color: '#ef4444',
        work_id: 'work_nezha',
        updated_at: now,
        created_at: now,
      },
      {
        id: 'persona_aobing',
        name: '敖丙',
        role: '配角',
        gender: 'male',
        avatar_emoji: '🐉',
        color: '#3b5bdb',
        work_id: 'work_nezha',
        updated_at: now,
        created_at: now,
      },
    ],
    works: [
      {
        id: 'work_nezha',
        title: '哪吒之魔童闹海',
        type: 'movie',
        year: 2025,
        aliases: ['Ne Zha 2'],
        cover_emoji: '🔥',
        color: '#ef4444',
        note: null,
        tags: [],
        external_refs: { tmdb_id: 1234567 },
        metadata: {
          poster_url: 'https://example.com/poster.jpg',
          overview: '魔童哪吒再战天劫,与龙族终极对决。',
          release_date: '2025-01-29',
          source: 'tmdb',
        },
        cast_snapshot: [],
        created_at: now,
        updated_at: now,
      },
    ],
    types: [
      { key: 'tv', label_zh: '电视剧', label_en: 'TV Series', builtin: true },
      { key: 'movie', label_zh: '电影', label_en: 'Movie', builtin: true },
      { key: 'anime', label_zh: '动画', label_en: 'Anime', builtin: true },
    ],
  }
}

function personasCountByWork(state: State) {
  const map = new Map<string, number>()
  let unassigned = 0
  for (const p of state.personas) {
    if (!p.work_id) unassigned += 1
    else map.set(p.work_id, (map.get(p.work_id) ?? 0) + 1)
  }
  return { map, unassigned }
}

function worksWithCount(state: State) {
  const { map } = personasCountByWork(state)
  return state.works.map(w => ({ ...w, persona_count: map.get(w.id) ?? 0 }))
}

async function setupRoutes(page: Page, state: State) {
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

  await page.route('**/api/atomic-tools', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await page.route('**/api/work-types/**', async route => {
    const method = route.request().method()
    if (method === 'DELETE') {
      const url = route.request().url()
      const key = decodeURIComponent(url.split('/').pop() ?? '')
      state.types = state.types.filter(t => !(t.key === key && !t.builtin))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, types: state.types.map(t => ({ ...t })) }),
      })
      return
    }
    await route.fallback()
  })

  await page.route('**/api/work-types', async route => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, types: state.types.map(t => ({ ...t })) }),
      })
      return
    }
    if (method === 'POST') {
      const body = route.request().postDataJSON() as {
        key: string
        label_zh: string
        label_en: string
      }
      if (!state.types.some(t => t.key === body.key)) {
        state.types.push({
          key: body.key,
          label_zh: body.label_zh,
          label_en: body.label_en,
          builtin: false,
        })
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, types: state.types.map(t => ({ ...t })) }),
      })
      return
    }
    await route.fallback()
  })

  await page.route(/\/api\/works\/[^/]+\/personas(\?|$)/, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, personas: [] }),
    })
  })

  await page.route(/\/api\/works\/[^/?#]+(\?|$)/, async route => {
    const url = route.request().url()
    const m = url.match(/\/api\/works\/([^/?#]+)(?:[?#]|$)/)
    const workId = m ? decodeURIComponent(m[1]) : ''
    const method = route.request().method()
    if (method === 'PATCH') {
      const patch = route.request().postDataJSON() as Partial<WorkRecord>
      const idx = state.works.findIndex(w => w.id === workId)
      if (idx >= 0) {
        state.works[idx] = {
          ...state.works[idx],
          ...patch,
          updated_at: new Date().toISOString(),
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, work: state.works[idx] }),
        })
        return
      }
      await route.fulfill({ status: 404, body: 'not found' })
      return
    }
    if (method === 'DELETE') {
      state.works = state.works.filter(w => w.id !== workId)
      for (const p of state.personas) {
        if (p.work_id === workId) p.work_id = null
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          reassigned: 0,
          deleted_personas: 0,
        }),
      })
      return
    }
    await route.fallback()
  })

  await page.route(/\/api\/works(\?|$)/, async route => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          path: '/tmp/e2e-works.json',
          works: worksWithCount(state),
          unassigned_count: personasCountByWork(state).unassigned,
          updated_at: new Date().toISOString(),
          version: 1,
        }),
      })
      return
    }
    if (method === 'POST') {
      const body = route.request().postDataJSON() as WorkRecord
      const id = `work_${Math.random().toString(36).slice(2, 8)}`
      const now = new Date().toISOString()
      const work: WorkRecord = {
        id,
        title: body.title,
        type: body.type,
        year: body.year ?? null,
        aliases: body.aliases ?? [],
        cover_emoji: body.cover_emoji ?? null,
        color: body.color ?? null,
        note: body.note ?? null,
        tags: body.tags ?? [],
        external_refs: body.external_refs ?? null,
        metadata: body.metadata ?? null,
        cast_snapshot: body.cast_snapshot ?? null,
        created_at: now,
        updated_at: now,
      }
      state.works.push(work)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, work }),
      })
      return
    }
    await route.fallback()
  })
}

test.describe('作品库 · 独立页面', () => {
  test('侧栏入口进入作品库 → 看到海报卡片 → TMDb 徽章 → 创建第二部作品 → 编辑 → 删除', async ({
    page,
  }) => {
    const state = seedState()
    await setupRoutes(page, state)

    await page.goto('/')

    // 侧栏存在「作品库」入口
    const worksNav = page.getByTestId('sidebar-link-works-library')
    await expect(worksNav).toBeVisible()
    await worksNav.click()

    await expect(page).toHaveURL(/\/works$/)

    // 顶部 hero 数量徽章出现
    await expect(page.getByTestId('works-library-count')).toBeVisible()

    // 卡片网格渲染出既有作品
    const nezhaCard = page.getByTestId('works-card-work_nezha')
    await expect(nezhaCard).toBeVisible()
    await expect(nezhaCard).toContainText('哪吒之魔童闹海')

    // TMDb 徽章出现(因为 external_refs.tmdb_id 存在)
    await expect(page.getByTestId('works-card-tmdb-badge-work_nezha')).toBeVisible()

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'works-library-initial.png'),
      fullPage: true,
    })

    // 通过顶部 "新建" 按钮创建第二部作品
    await page.getByTestId('works-library-create').click()
    await expect(page.getByTestId('work-editor')).toBeVisible()
    await page.getByTestId('work-field-title').fill('流浪地球')
    await page.getByTestId('work-field-year').fill('2019')
    await page.getByTestId('work-editor-save').click()

    // 网格中应出现两张卡片(既有 + 新建)
    const grid = page.getByTestId('works-library-grid')
    await expect(grid.locator('[data-testid^="works-card-work_"]')).toHaveCount(2)
    await expect(grid).toContainText('流浪地球')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'works-library-two-cards.png'),
      fullPage: true,
    })

    // 搜索过滤
    await page.getByTestId('works-library-search').fill('哪吒')
    await expect(grid.locator('[data-testid^="works-card-work_"]')).toHaveCount(1)
    await page.getByTestId('works-library-search').fill('不存在的片名XYZ')
    await expect(page.getByTestId('works-library-empty-filtered')).toBeVisible()
    await page.getByTestId('works-library-search').fill('')

    // 编辑既有卡片
    await page.getByTestId('works-card-edit-work_nezha').click()
    await expect(page.getByTestId('work-editor')).toBeVisible()
    await page.getByTestId('work-field-title').fill('哪吒之魔童闹海(修订)')
    await page.getByTestId('work-editor-save').click()
    await expect(nezhaCard).toContainText('哪吒之魔童闹海(修订)')

    // 删除既有卡片(需要 confirm)
    page.once('dialog', dialog => dialog.accept())
    await page.getByTestId('works-card-delete-work_nezha').click()
    await expect(nezhaCard).toHaveCount(0)
  })

  test('清空作品库后空态 CTA 可直接创建', async ({ page }) => {
    const state: State = {
      personas: [],
      works: [],
      types: [
        { key: 'movie', label_zh: '电影', label_en: 'Movie', builtin: true },
      ],
    }
    await setupRoutes(page, state)

    await page.goto('/works')

    const empty = page.getByTestId('works-library-empty')
    await expect(empty).toBeVisible()

    await page.getByTestId('works-library-empty-cta').click()
    await expect(page.getByTestId('work-editor')).toBeVisible()
    await page.getByTestId('work-field-title').fill('First Work')
    await page.getByTestId('work-editor-save').click()

    await expect(page.getByTestId('works-library-grid')).toContainText('First Work')
  })
})
