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
        id: 'persona_amy',
        name: '艾米',
        actor_name: 'Anne Hathaway',
        role: '女主',
        gender: 'female',
        avatar_emoji: '👩',
        color: '#ef4444',
        work_id: null,
        updated_at: now,
        created_at: now,
      },
      {
        id: 'persona_rachel',
        name: '瑞秋',
        actor_name: 'Jennifer Aniston',
        role: '女主',
        gender: 'female',
        avatar_emoji: '👱',
        color: '#3b5bdb',
        work_id: 'work_friends',
        updated_at: now,
        created_at: now,
      },
    ],
    works: [
      {
        id: 'work_friends',
        title: '老友记',
        type: 'tv',
        year: 1994,
        aliases: ['Friends', '六人行'],
        cover_emoji: '🎬',
        color: '#3b5bdb',
        note: null,
        tags: [],
        updated_at: now,
        created_at: now,
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
  // ---- global personas ----
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

  await page.route('**/api/global-personas/import', async route => {
    const body = route.request().postDataJSON() as {
      personas: PersonaRecord[]
    }
    const now = new Date().toISOString()
    for (const incoming of body.personas ?? []) {
      const idx = state.personas.findIndex(
        p => p.name.toLowerCase().trim() === (incoming.name ?? '').toLowerCase().trim(),
      )
      const next = {
        ...incoming,
        id: incoming.id || `persona_${Math.random().toString(36).slice(2)}`,
        updated_at: now,
        created_at: idx >= 0 ? state.personas[idx].created_at ?? now : now,
      }
      if (idx >= 0) state.personas[idx] = { ...state.personas[idx], ...next }
      else state.personas.push(next)
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

  // ---- atomic tools (avoid proxy noise) ----
  await page.route('**/api/atomic-tools', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  // ---- work types (more specific, register BEFORE /api/works/** fallback) ----
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
      const exists = state.types.some(t => t.key === body.key)
      if (!exists) {
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

  // ---- works specific endpoints (register BEFORE catch-all) ----
  // 使用正则避免误命中 Vite 模块路径 /src/api/works.ts
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
        state.works[idx] = { ...state.works[idx], ...patch, updated_at: new Date().toISOString() }
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
      const before = state.works.length
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
          removed: before - state.works.length,
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

test.describe('角色库 · 作品下拉', () => {
  test('作品下拉筛选角色，不展示作品管理入口', async ({ page }) => {
    const state = seedState()
    await setupRoutes(page, state)

    await page.goto('/character-library')

    await expect(page.getByTestId('works-sidebar')).toBeVisible()
    const workSelect = page.getByTestId('works-sidebar-select')
    await expect(workSelect).toBeVisible()
    await expect(workSelect).toHaveValue('__all__')
    await expect(workSelect).toContainText('全部角色')
    await expect(workSelect).toContainText('未归属')
    await expect(workSelect).toContainText('老友记')
    await expect(page.getByTestId('works-sidebar-create')).toHaveCount(0)
    await expect(page.locator('[data-testid^="works-sidebar-edit-"]')).toHaveCount(0)
    await expect(page.locator('[data-testid^="works-sidebar-delete-"]')).toHaveCount(0)

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'works-dropdown-filter.png'),
      fullPage: true,
    })

    await expect(page.getByTestId('character-row-persona_amy')).toBeVisible()
    await expect(page.getByTestId('character-row-persona_rachel')).toBeVisible()

    await workSelect.selectOption('work_friends')
    await expect(page.getByTestId('character-row-persona_rachel')).toBeVisible()
    await expect(page.getByTestId('character-row-persona_amy')).toHaveCount(0)

    await workSelect.selectOption('__unassigned__')
    await expect(page.getByTestId('character-row-persona_amy')).toBeVisible()
    await expect(page.getByTestId('character-row-persona_rachel')).toHaveCount(0)

    await workSelect.selectOption('__all__')
    await expect(page.getByTestId('character-row-persona_amy')).toBeVisible()
    await expect(page.getByTestId('character-row-persona_rachel')).toBeVisible()
  })
})
