import { test, expect, type Page } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const TASK_ID = 'task-mock-speaker-review'
const SCREENSHOTS_DIR = path.join(__dirname, '../../output/playwright')
const PAGE_URL = `/harness/speaker-review/${TASK_ID}`

test.beforeAll(() => {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })
})

function buildTask() {
  return {
    id: TASK_ID,
    title: '说话人核对 v2 e2e mock',
    status: 'completed',
    progress: 100,
    error: null,
    output_root: '/tmp/mock',
    source_path: '/tmp/mock/input.mp4',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    duration_sec: 120,
    languages: ['zh'],
    artifacts: {},
    pipeline: { stages: [] },
    config_snapshot: {},
  }
}

type PersonaRecord = {
  id: string
  name: string
  bindings: string[]
  aliases: string[]
  color: string | null
  avatar_emoji: string | null
  tts_skip: boolean
  tts_voice_id: string | null
  created_at: string
  updated_at: string
}

function buildPersonaBundle(personas: PersonaRecord[], speakers: string[]) {
  const bySpeaker: Record<string, Record<string, unknown>> = {}
  const bound = new Set<string>()
  personas.forEach(p => {
    p.bindings.forEach(b => {
      bySpeaker[b] = {
        persona_id: p.id,
        name: p.name,
        color: p.color,
        avatar_emoji: p.avatar_emoji,
      }
      bound.add(b)
    })
  })
  speakers.forEach(s => {
    if (!bySpeaker[s]) {
      bySpeaker[s] = {
        persona_id: null,
        name: null,
        color: null,
        avatar_emoji: null,
      }
    }
  })
  const unassigned = speakers.filter(s => !bound.has(s))
  return {
    items: personas,
    unassigned_bindings: unassigned,
    by_speaker: bySpeaker,
    updated_at: new Date().toISOString(),
  }
}

function buildSpeakerReview(
  decisions: Array<Record<string, unknown>> = [],
  personas: PersonaRecord[] = [],
) {
  const decisionMap: Record<string, Record<string, unknown>> = {}
  decisions.forEach(d => {
    decisionMap[String(d.item_id)] = d
  })
  const speakerA = {
    speaker_label: 'speakerA',
    segment_count: 8,
    segment_ids: ['seg-1', 'seg-2'],
    total_speech_sec: 32.5,
    avg_duration_sec: 4.0,
    short_segment_count: 1,
    risk_flags: ['low_sample'],
    risk_level: 'medium',
    cloneable_by_default: true,
    decision: decisionMap['speaker:speakerA'] ?? null,
    reference_clips: [
      {
        clip_id: 'speakerA::seg-1',
        segment_id: 'seg-1',
        start: 1.0,
        end: 3.5,
        duration: 2.5,
        text: 'Hello world from speaker A',
        is_best: true,
        score: 0.9,
        url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=1&end=3.5`,
      },
    ],
    best_reference_clip_id: 'speakerA::seg-1',
    similar_peers: [{ label: 'speakerB', similarity: 0.72, suggest_merge: true }],
    recommended_action: 'merge_speaker',
  }
  const speakerB = {
    speaker_label: 'speakerB',
    segment_count: 12,
    segment_ids: ['seg-3'],
    total_speech_sec: 60.0,
    avg_duration_sec: 5.0,
    short_segment_count: 0,
    risk_flags: [],
    risk_level: 'low',
    cloneable_by_default: true,
    decision: decisionMap['speaker:speakerB'] ?? null,
    reference_clips: [],
    similar_peers: [],
    recommended_action: 'keep_independent',
  }
  const run1 = {
    run_id: 'run-1',
    speaker_label: 'speakerA',
    start: 10.0,
    end: 11.2,
    duration: 1.2,
    segment_count: 1,
    segment_ids: ['seg-1'],
    text: '这是一个高风险孤岛 run',
    previous_speaker_label: 'speakerB',
    next_speaker_label: 'speakerB',
    gap_before_sec: 0.3,
    gap_after_sec: 0.4,
    risk_flags: ['short_island'],
    risk_level: 'high',
    decision: decisionMap['run-1'] ?? null,
    audio_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=10&end=11.2`,
    prev_context_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=8.5&end=10`,
    next_context_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=11.2&end=12.7`,
    recommended_action: 'merge_to_surrounding_speaker',
  }
  const seg1 = {
    segment_id: 'seg-2',
    index: 2,
    speaker_label: 'speakerA',
    start: 22.0,
    end: 23.0,
    duration: 1.0,
    text: '过短风险段',
    previous_speaker_label: 'speakerA',
    next_speaker_label: 'speakerB',
    risk_flags: ['short_segment'],
    risk_level: 'medium',
    decision: decisionMap['seg-2'] ?? null,
    audio_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=22&end=23`,
    prev_context_url: null,
    next_context_url: `/api/tasks/${TASK_ID}/speaker-review/audio?start=23&end=24.5`,
    recommended_action: 'keep_independent',
  }

  return {
    task_id: TASK_ID,
    status: 'available',
    summary: {
      segment_count: 20,
      speaker_count: 2,
      high_risk_speaker_count: 0,
      speaker_run_count: 5,
      review_run_count: 1,
      high_risk_run_count: 1,
      review_segment_count: 2,
      decision_count: decisions.length,
      corrected_exists: false,
      unnamed_speaker_count: ['speakerA', 'speakerB'].filter(
        s => !personas.some(p => p.bindings.includes(s)),
      ).length,
    },
    artifact_paths: {},
    speakers: [speakerA, speakerB],
    speaker_runs: [run1],
    segments: [seg1],
    similarity: {
      labels: ['speakerA', 'speakerB'],
      matrix: [
        [1.0, 0.72],
        [0.72, 1.0],
      ],
      threshold_suggest_merge: 0.55,
      method: 'profile_heuristic',
    },
    review_plan: { items: [] },
    decisions,
    personas: buildPersonaBundle(personas, ['speakerA', 'speakerB']),
    manifest: {},
  }
}

async function setupRoutes(page: Page) {
  const decisions: Array<Record<string, unknown>> = []
  const personas: PersonaRecord[] = []
  const history: Array<{ type: string; persona: PersonaRecord }> = []

  const nowIso = () => new Date().toISOString()
  const genId = () => `persona-${Math.random().toString(36).slice(2, 10)}`
  const palette = ['#10b981', '#06b6d4', '#6366f1', '#f59e0b', '#ec4899', '#ef4444']
  const pickColor = () => palette[personas.length % palette.length]
  const snapshot = (p: PersonaRecord): PersonaRecord => JSON.parse(JSON.stringify(p))
  const detachBinding = (speaker: string) => {
    personas.forEach(p => {
      p.bindings = p.bindings.filter(b => b !== speaker)
    })
  }

  await page.route(`**/api/tasks/${TASK_ID}`, async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildTask()) })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review`, async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildSpeakerReview(decisions, personas)),
      })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/decisions`, async route => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON()
      const existingIdx = decisions.findIndex(d => d.item_id === body.item_id)
      const record = { ...body, updated_at: new Date().toISOString() }
      if (existingIdx >= 0) decisions[existingIdx] = record
      else decisions.push(record)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/decisions/*`, async route => {
    if (route.request().method() === 'DELETE') {
      const url = route.request().url()
      const segs = url.split('/decisions/')
      const itemId = decodeURIComponent(segs[1])
      const idx = decisions.findIndex(d => d.item_id === itemId)
      if (idx >= 0) decisions.splice(idx, 1)
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    } else {
      await route.continue()
    }
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/apply-preview`, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        summary: {
          total_segments: 20,
          changed_segments: 3,
          unassigned_segments: 2,
          personas_used: { speakerA: 8, speakerB: 7 },
          merges: {},
        },
        sample_changes: [
          {
            segment_id: 'seg-1',
            start: 1.0,
            end: 3.5,
            original_speaker: 'speakerA',
            new_speaker: 'speakerA',
            original_persona: null,
            new_persona: null,
          },
        ],
      }),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/apply`, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        path: '/tmp/segments.zh.speaker-corrected.json',
        srt_path: '/tmp/segments.zh.speaker-corrected.srt',
        manifest_path: '/tmp/speaker-review-manifest.json',
        archive_path: '/tmp/_archive/20260101-120000',
        summary: {},
        applied_at: new Date().toISOString(),
      }),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/personas/**`, async route => {
    const url = new URL(route.request().url())
    const tail = url.pathname.split('/personas/')[1] ?? ''
    const method = route.request().method()
    const speakers = ['speakerA', 'speakerB']
    const respondBundle = (extra: Record<string, unknown> = {}) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          personas: buildPersonaBundle(personas, speakers),
          ...extra,
        }),
      })
    }

    if (tail === 'bulk' && method === 'POST') {
      const payload = route.request().postDataJSON() as { template: string }
      const unassigned = speakers.filter(s => !personas.some(p => p.bindings.includes(s)))
      const created: PersonaRecord[] = []
      unassigned.forEach((sp, idx) => {
        let name = sp
        if (payload.template === 'role_abc') name = `角色 ${String.fromCharCode(65 + idx)}`
        else if (payload.template === 'protagonist') name = idx === 0 ? '主持人' : `嘉宾 ${idx}`
        else if (payload.template === 'by_index') name = `说话人 ${idx + 1}`
        const persona: PersonaRecord = {
          id: genId(),
          name,
          bindings: [sp],
          aliases: [],
          color: pickColor(),
          avatar_emoji: null,
          tts_skip: false,
          tts_voice_id: null,
          created_at: nowIso(),
          updated_at: nowIso(),
        }
        personas.push(persona)
        history.push({ type: 'create', persona: snapshot(persona) })
        created.push(persona)
      })
      await respondBundle({ created })
      return
    }

    if (tail === 'suggest' && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          suggestions: {
            speakerA: [{ name: '小明', confidence: 0.86, source: 'self-intro' }],
            speakerB: [{ name: '小红', confidence: 0.72, source: 'addressed' }],
          },
        }),
      })
      return
    }

    if (tail === 'undo' && method === 'POST') {
      const last = history.pop()
      if (last) {
        if (last.type === 'create') {
          const idx = personas.findIndex(p => p.id === last.persona.id)
          if (idx >= 0) personas.splice(idx, 1)
        } else if (last.type === 'update') {
          const idx = personas.findIndex(p => p.id === last.persona.id)
          if (idx >= 0) personas[idx] = last.persona
        }
      }
      await respondBundle({ reverted: last ? { type: last.type } : null })
      return
    }

    if (tail === 'redo' && method === 'POST') {
      await respondBundle({ reverted: null })
      return
    }

    if (tail === 'history' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          history: {
            total: history.length,
            cursor: history.length,
            can_undo: history.length > 0,
            can_redo: false,
            last_undo_op: null,
            next_redo_op: null,
          },
        }),
      })
      return
    }

    // /personas/{id} or /personas/{id}/bind|unbind
    const parts = tail.split('/')
    const personaId = decodeURIComponent(parts[0])
    const action = parts[1]
    const idx = personas.findIndex(p => p.id === personaId)

    if (!action) {
      if (method === 'PATCH') {
        if (idx < 0) {
          await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
          return
        }
        const prev = snapshot(personas[idx])
        const payload = route.request().postDataJSON() as Record<string, unknown>
        if (typeof payload.name === 'string') personas[idx].name = payload.name
        if (payload.color !== undefined) personas[idx].color = payload.color as string | null
        if (payload.avatar_emoji !== undefined)
          personas[idx].avatar_emoji = payload.avatar_emoji as string | null
        personas[idx].updated_at = nowIso()
        history.push({ type: 'update', persona: prev })
        await respondBundle({ persona: personas[idx] })
        return
      }
      if (method === 'DELETE') {
        if (idx >= 0) {
          history.push({ type: 'delete', persona: snapshot(personas[idx]) })
          personas.splice(idx, 1)
        }
        await respondBundle()
        return
      }
    }

    if (action === 'bind' && method === 'POST') {
      if (idx < 0) {
        await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
        return
      }
      const prev = snapshot(personas[idx])
      const payload = route.request().postDataJSON() as { speaker: string }
      detachBinding(payload.speaker)
      if (!personas[idx].bindings.includes(payload.speaker)) {
        personas[idx].bindings.push(payload.speaker)
      }
      personas[idx].updated_at = nowIso()
      history.push({ type: 'update', persona: prev })
      await respondBundle({ persona: personas[idx] })
      return
    }

    if (action === 'unbind' && method === 'POST') {
      if (idx < 0) {
        await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
        return
      }
      const prev = snapshot(personas[idx])
      const payload = route.request().postDataJSON() as { speaker: string }
      personas[idx].bindings = personas[idx].bindings.filter(b => b !== payload.speaker)
      personas[idx].updated_at = nowIso()
      history.push({ type: 'update', persona: prev })
      await respondBundle({ persona: personas[idx] })
      return
    }

    await route.continue()
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/personas`, async route => {
    const method = route.request().method()
    const speakers = ['speakerA', 'speakerB']
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildPersonaBundle(personas, speakers)),
      })
      return
    }
    if (method === 'POST') {
      const payload = route.request().postDataJSON() as {
        name: string
        bindings?: string[]
        color?: string | null
        avatar_emoji?: string | null
        force?: boolean
        tts_voice_id?: string | null
        tts_skip?: boolean
      }
      if (!payload.force) {
        const conflict = personas.find(
          p => (p.name || '').trim().toLowerCase() === (payload.name || '').trim().toLowerCase(),
        )
        if (conflict) {
          await route.fulfill({
            status: 409,
            contentType: 'application/json',
            body: JSON.stringify({
              detail: {
                code: 'persona_name_conflict',
                existing_id: conflict.id,
                existing_name: conflict.name,
                message: `Persona name '${payload.name}' already exists`,
              },
            }),
          })
          return
        }
      }
      const bindings = payload.bindings ?? []
      bindings.forEach(b => detachBinding(b))
      const persona: PersonaRecord = {
        id: genId(),
        name: payload.name,
        bindings,
        aliases: [],
        color: payload.color ?? pickColor(),
        avatar_emoji: payload.avatar_emoji ?? null,
        tts_skip: payload.tts_skip ?? false,
        tts_voice_id: payload.tts_voice_id ?? null,
        created_at: nowIso(),
        updated_at: nowIso(),
      }
      personas.push(persona)
      history.push({ type: 'create', persona: snapshot(persona) })
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          persona,
          personas: buildPersonaBundle(personas, speakers),
        }),
      })
      return
    }
    await route.continue()
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/audio**`, async route => {
    const wavHeader = Buffer.from([
      0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
      0x66, 0x6d, 0x74, 0x20, 0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
      0x80, 0x3e, 0x00, 0x00, 0x00, 0x7d, 0x00, 0x00, 0x02, 0x00, 0x10, 0x00,
      0x64, 0x61, 0x74, 0x61, 0x00, 0x00, 0x00, 0x00,
    ])
    await route.fulfill({ status: 200, contentType: 'audio/wav', body: wavHeader })
  })

  await page.route('**/api/tasks/' + TASK_ID + '/workflow', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ nodes: [], edges: [] }) })
  })

  await page.route('**/api/tasks/' + TASK_ID + '/delivery', async route => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })

  await page.route('**/api/tasks/' + TASK_ID + '/progress**', async route => {
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body: '' })
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/personas/suggest-from-global`, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, matches: [] }),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/global-personas/export-from-task`, async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, exported: ['艾米'], skipped: [], total: 1 }),
    })
  })

  await page.route(`**/api/tasks/${TASK_ID}/speaker-review/personas/import-from-global`, async route => {
    const body = route.request().postDataJSON() as { persona_ids?: string[] }
    const ids = body?.persona_ids ?? []
    const imported = ids.map(id => ({
      id: `imp-${id}`,
      name: id === 'g-1' ? '旁白老王' : `角色-${id}`,
      bindings: [],
      aliases: [],
      color: '#f59e0b',
      avatar_emoji: null,
      tts_skip: false,
      tts_voice_id: null,
      created_at: nowIso(),
      updated_at: nowIso(),
    }))
    personas.push(...imported)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        imported,
        conflicts: [],
        personas: buildPersonaBundle(personas, ['speakerA', 'speakerB']),
      }),
    })
  })

  await page.route('**/api/global-personas', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          path: '/tmp/mock/personas.json',
          version: 1,
          updated_at: nowIso(),
          personas: [
            {
              id: 'g-1',
              name: '旁白老王',
              role: 'narrator',
              gender: 'male',
              avatar_emoji: '👴',
              color: '#f59e0b',
              tts_voice_id: 'voice-abc',
            },
            {
              id: 'g-2',
              name: '女主小美',
              role: 'protagonist',
              gender: 'female',
              color: '#ec4899',
            },
          ],
        }),
      })
      return
    }
    await route.continue()
  })

  await page.route('**/api/global-personas/*', async route => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, personas: [] }),
      })
      return
    }
    await route.continue()
  })
}

async function openDrawer(page: Page) {
  await page.goto(PAGE_URL)
  await page.waitForLoadState('domcontentloaded')
  await page.locator('[data-testid="speaker-review-drawer"]').waitFor({ timeout: 15_000 })
}

test.describe('Speaker Review v2 drawer', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('speaker-review-onboarded-v1', '1')
      } catch {}
    })
    await setupRoutes(page)
  })

  test('打开抽屉并展示三栏布局', async ({ page }) => {
    await openDrawer(page)
    await expect(page.locator('[data-testid="speaker-review-topbar"]')).toBeVisible()
    await expect(page.locator('[data-testid="roster-panel"]')).toBeVisible()
    await expect(page.locator('[data-testid="review-queue"]')).toBeVisible()
    await expect(page.locator('[data-testid="inspector-panel"]')).toBeVisible()
    await expect(page.locator('[data-testid="roster-item-speakerA"]')).toBeVisible()
    await expect(page.locator('[data-testid="roster-item-speakerB"]')).toBeVisible()
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'speaker-review-v2-loaded.png'), fullPage: true })
  })

  test('选择条目后展示检视面板与建议动作', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="queue-item-run-1"]').click()
    await expect(page.locator('[data-testid="inspector-panel"]')).toContainText('Run run-1')
    await expect(page.locator('[data-testid="inspector-panel"]')).toContainText('建议')
    await expect(page.locator('[data-testid="action-relabel-prev"]')).toBeVisible()
    await expect(page.locator('[data-testid="action-merge-surrounding"]')).toBeVisible()
  })

  test('应用决策并展示归档提示', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="filter-undecided"]').uncheck()
    await page.locator('[data-testid="queue-item-run-1"]').click()
    await page.locator('[data-testid="action-merge-surrounding"]').click()
    await expect(page.locator('[data-testid="queue-item-run-1"]')).toContainText(
      'merge_to_surrounding_speaker',
      { timeout: 5000 },
    )
    await page.locator('[data-testid="apply-decisions"]').click()
    await expect(page.locator('[data-testid="apply-result"]')).toContainText('已归档旧产物')
  })

  test('合并建议触发二次确认弹窗', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="suggest-merge-speakerA-speakerB"]').click()
    await expect(page.locator('[data-testid="merge-confirm-modal"]')).toBeVisible()
    await page.locator('[data-testid="merge-cancel"]').click()
    await expect(page.locator('[data-testid="merge-confirm-modal"]')).toHaveCount(0)
    await page.locator('[data-testid="suggest-merge-speakerA-speakerB"]').click()
    await page.locator('[data-testid="merge-confirm"]').click()
    await expect(page.locator('[data-testid="merge-confirm-modal"]')).toHaveCount(0)
  })

  test('快捷键面板：按钮打开后 Esc 关闭', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="shortcuts-button"]').click()
    await expect(page.locator('[data-testid="shortcuts-modal"]')).toBeVisible()
    await page.locator('[data-testid="shortcuts-modal"]').click({ position: { x: 5, y: 5 } })
    await expect(page.locator('[data-testid="shortcuts-modal"]')).toHaveCount(0)
  })

  test('撤销已保存的决策', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="queue-item-run-1"]').click()
    await page.locator('[data-testid="action-keep"]').click()
    await expect(page.locator('[data-testid="delete-decision"]')).toBeVisible({ timeout: 5000 })
    await page.locator('[data-testid="delete-decision"]').click()
    await expect(page.locator('[data-testid="delete-decision"]')).toHaveCount(0, { timeout: 5000 })
  })

  test('Persona：点击重命名按钮后输入昵称并回车', async ({ page }) => {
    await openDrawer(page)
    await expect(page.locator('[data-testid="unnamed-badge"]')).toContainText('2')
    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('speakerA')

    await page.locator('[data-testid="rename-speakerA"]').click()
    const input = page.locator('[data-testid="rename-input-speakerA"]')
    await expect(input).toBeVisible()
    await input.fill('艾米')
    await input.press('Enter')

    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('艾米', {
      timeout: 5000,
    })
    await expect(page.locator('[data-testid="unnamed-badge"]')).toContainText('1')
  })

  test('Persona：快捷键 H 激活内联重命名', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="roster-item-speakerA"]').click()
    await page.keyboard.press('h')
    await expect(page.locator('[data-testid="rename-input-speakerA"]')).toBeVisible({ timeout: 5000 })
    await page.keyboard.press('Escape')
    await expect(page.locator('[data-testid="rename-input-speakerA"]')).toHaveCount(0)
  })

  test('Persona：批量命名模板 by_index 一键给全部未命名说话人起名', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="persona-bulk-button"]').click()
    await expect(page.locator('[data-testid="persona-bulk-modal"]')).toBeVisible()
    await page.locator('[data-testid="bulk-template-by_index"]').click()

    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('说话人 1', {
      timeout: 5000,
    })
    await expect(page.locator('[data-testid="speaker-display-speakerB"]')).toHaveText('说话人 2')
    await expect(page.locator('[data-testid="unnamed-badge"]')).toHaveCount(0)
  })

  test('Persona：智能建议弹窗采纳候选', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="persona-suggest-button"]').click()
    await expect(page.locator('[data-testid="persona-suggest-modal"]')).toBeVisible()
    await expect(page.locator('[data-testid="suggest-row-speakerA"]')).toBeVisible()

    await page.locator('[data-testid="suggest-accept-speakerA-小明"]').click()

    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('小明', {
      timeout: 5000,
    })
  })

  test('Persona：Cmd+Z 撤销最近一次 persona 操作', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="rename-speakerA"]').click()
    const input = page.locator('[data-testid="rename-input-speakerA"]')
    await input.fill('临时昵称')
    await input.press('Enter')

    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('临时昵称', {
      timeout: 5000,
    })

    const isMac = process.platform === 'darwin'
    await page.keyboard.press(isMac ? 'Meta+z' : 'Control+z')

    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('speakerA', {
      timeout: 5000,
    })
  })

  test('Persona：Topbar 撤销按钮还原批量命名', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="persona-bulk-button"]').click()
    await page.locator('[data-testid="bulk-template-by_index"]').click()
    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('说话人 1', {
      timeout: 5000,
    })

    await page.locator('[data-testid="persona-undo-button"]').click()
    await page.locator('[data-testid="persona-undo-button"]').click()

    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('speakerA', {
      timeout: 5000,
    })
    await expect(page.locator('[data-testid="speaker-display-speakerB"]')).toHaveText('speakerB')
  })

  test('Persona：未命名说话人显示红点指示', async ({ page }) => {
    await openDrawer(page)
    // 首次打开如有引导遮罩，关闭之
    const onboarding = page.locator('[data-testid="onboarding-guide"]')
    if (await onboarding.isVisible().catch(() => false)) {
      await page.locator('[data-testid="onboarding-dismiss"]').click()
    }
    await expect(page.locator('[data-testid="unnamed-dot-speakerA"]')).toBeVisible()
    await expect(page.locator('[data-testid="unnamed-dot-speakerB"]')).toBeVisible()

    await page.locator('[data-testid="rename-speakerA"]').click()
    const input = page.locator('[data-testid="rename-input-speakerA"]')
    await input.fill('艾米')
    await input.press('Enter')

    await expect(page.locator('[data-testid="unnamed-dot-speakerA"]')).toHaveCount(0, { timeout: 5000 })
    await expect(page.locator('[data-testid="unnamed-dot-speakerB"]')).toBeVisible()
  })

  test('Persona：重名冲突 409 弹出解决方案弹窗', async ({ page }) => {
    await openDrawer(page)
    const onboarding = page.locator('[data-testid="onboarding-guide"]')
    if (await onboarding.isVisible().catch(() => false)) {
      await page.locator('[data-testid="onboarding-dismiss"]').click()
    }

    await page.locator('[data-testid="rename-speakerA"]').click()
    await page.locator('[data-testid="rename-input-speakerA"]').fill('小明')
    await page.locator('[data-testid="rename-input-speakerA"]').press('Enter')
    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('小明', { timeout: 5000 })

    await page.locator('[data-testid="rename-speakerB"]').click()
    await page.locator('[data-testid="rename-input-speakerB"]').fill('小明')
    await page.locator('[data-testid="rename-input-speakerB"]').press('Enter')

    await expect(page.locator('[data-testid="persona-conflict-modal"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('[data-testid="persona-conflict-force"]')).toBeVisible()
    await expect(page.locator('[data-testid="persona-conflict-merge"]')).toBeVisible()

    await page.locator('[data-testid="persona-conflict-cancel"]').click()
    await expect(page.locator('[data-testid="persona-conflict-modal"]')).toHaveCount(0)
  })

  test('Persona：Apply 预览弹窗展示 summary + 样例变更', async ({ page }) => {
    await openDrawer(page)
    const onboarding = page.locator('[data-testid="onboarding-guide"]')
    if (await onboarding.isVisible().catch(() => false)) {
      await page.locator('[data-testid="onboarding-dismiss"]').click()
    }
    await page.locator('[data-testid="persona-apply-preview-button"]').click()
    await expect(page.locator('[data-testid="apply-diff-preview-modal"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('[data-testid="apply-diff-preview-modal"]')).toContainText('20')
    await page.locator('[data-testid="apply-preview-cancel"]').click()
    await expect(page.locator('[data-testid="apply-diff-preview-modal"]')).toHaveCount(0)
  })

  test('Persona：Cmd+Shift+Z 触发 redo 请求', async ({ page }) => {
    await openDrawer(page)
    const onboarding = page.locator('[data-testid="onboarding-guide"]')
    if (await onboarding.isVisible().catch(() => false)) {
      await page.locator('[data-testid="onboarding-dismiss"]').click()
    }

    const redoWaiter = page.waitForRequest(
      req => req.url().includes('/personas/redo') && req.method() === 'POST',
      { timeout: 5000 },
    )
    const isMac = process.platform === 'darwin'
    await page.keyboard.press(isMac ? 'Meta+Shift+z' : 'Control+Shift+z')
    await redoWaiter
  })

  test('Persona：首次打开显示引导向导', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem('speaker-review-onboarded-v1')
    })
    await openDrawer(page)
    await expect(page.locator('[data-testid="onboarding-guide"]')).toBeVisible({ timeout: 5000 })
    await page.locator('[data-testid="onboarding-dismiss"]').click()
    await expect(page.locator('[data-testid="onboarding-guide"]')).toHaveCount(0)
  })

  test('Persona：voice 编辑按钮触发 PATCH tts_voice_id', async ({ page }) => {
    await openDrawer(page)
    const onboarding = page.locator('[data-testid="onboarding-guide"]')
    if (await onboarding.isVisible().catch(() => false)) {
      await page.locator('[data-testid="onboarding-dismiss"]').click()
    }
    // 先命名 speakerA 以便出现 voice 编辑按钮
    await page.locator('[data-testid="rename-speakerA"]').click()
    await page.locator('[data-testid="rename-input-speakerA"]').fill('艾米')
    await page.locator('[data-testid="rename-input-speakerA"]').press('Enter')
    await expect(page.locator('[data-testid="speaker-display-speakerA"]')).toHaveText('艾米', { timeout: 5000 })

    await page.evaluate(() => {
      const orig = window.prompt
      ;(window as unknown as { __origPrompt?: typeof window.prompt }).__origPrompt = orig
      window.prompt = () => 'voice-test-001'
    })

    const patchWaiter = page.waitForRequest(
      req =>
        req.url().includes('/speaker-review/personas/') &&
        req.method() === 'PATCH' &&
        (req.postData() || '').includes('tts_voice_id'),
      { timeout: 5000 },
    )

    await page.locator('[data-testid="voice-edit-speakerA"]').click()
    await patchWaiter

    await page.evaluate(() => {
      const saved = (window as unknown as { __origPrompt?: typeof window.prompt }).__origPrompt
      if (saved) window.prompt = saved
    })
  })

  test('GlobalPersona：打开角色库 Modal 并列出全局人设', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="global-personas-button"]').click()
    await expect(page.locator('[data-testid="global-persona-modal"]')).toBeVisible()
    await page.locator('[data-testid="global-persona-tab-browse"]').click()
    await expect(page.locator('[data-testid="global-persona-row-旁白老王"]')).toBeVisible()
    await expect(page.locator('[data-testid="global-persona-row-女主小美"]')).toBeVisible()
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, 'global-persona-browse.png'),
      fullPage: true,
    })
  })

  test('GlobalPersona：导出当前任务到全局库', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="global-personas-button"]').click()
    await expect(page.locator('[data-testid="global-persona-modal"]')).toBeVisible()
    await page.locator('[data-testid="global-persona-tab-export"]').click()

    const exportWaiter = page.waitForRequest(
      req =>
        req.url().includes('/speaker-review/global-personas/export-from-task') &&
        req.method() === 'POST',
      { timeout: 5000 },
    )
    await page.locator('[data-testid="global-persona-export-button"]').click()
    await exportWaiter
    await expect(page.locator('[data-testid="global-persona-export-result"]')).toBeVisible()
  })

  test('GlobalPersona：勾选并一键导入到当前任务', async ({ page }) => {
    await openDrawer(page)
    await page.locator('[data-testid="global-personas-button"]').click()
    await page.locator('[data-testid="global-persona-tab-browse"]').click()
    await page.locator('[data-testid="global-persona-check-旁白老王"]').check()

    const importWaiter = page.waitForRequest(
      req =>
        req.url().includes('/speaker-review/personas/import-from-global') &&
        req.method() === 'POST',
      { timeout: 5000 },
    )
    await page.locator('[data-testid="global-persona-import-button"]').click()
    await importWaiter
  })

  test('GlobalPersona：智能匹配 Toast 出现并一键导入', async ({ page }) => {
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem('speaker-review-onboarded-v1', '1')
      } catch {}
    })
    await setupRoutes(page)
    await page.route(
      `**/api/tasks/${TASK_ID}/speaker-review/personas/suggest-from-global`,
      async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            matches: [
              {
                speaker_label: 'speakerA',
                candidates: [
                  {
                    persona_id: 'g-1',
                    name: '旁白老王',
                    score: 0.9,
                    reason: 'role+gender',
                    role: 'narrator',
                    gender: 'male',
                    tts_voice_id: 'voice-abc',
                  },
                ],
              },
            ],
          }),
        })
      },
    )
    await openDrawer(page)
    await expect(page.locator('[data-testid="global-match-toast"]')).toBeVisible({
      timeout: 8000,
    })
    const importWaiter = page.waitForRequest(
      req =>
        req.url().includes('/speaker-review/personas/import-from-global') &&
        req.method() === 'POST',
      { timeout: 5000 },
    )
    await page.locator('[data-testid="global-match-import-all"]').click()
    await importWaiter
    await expect(page.locator('[data-testid="global-match-toast"]')).toHaveCount(0, {
      timeout: 5000,
    })
  })
})
