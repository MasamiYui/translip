import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../i18n/I18nProvider'
import type { GlobalPersona } from '../../types'
import { CharacterLibraryPage } from '../CharacterLibraryPage'

const listGlobalPersonas = vi.fn()
const importGlobalPersonas = vi.fn()
const deleteGlobalPersona = vi.fn()
const listWorks = vi.fn()

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    listGlobalPersonas: (...args: unknown[]) => listGlobalPersonas(...args),
    importGlobalPersonas: (...args: unknown[]) => importGlobalPersonas(...args),
    deleteGlobalPersona: (...args: unknown[]) => deleteGlobalPersona(...args),
  },
}))

vi.mock('../../api/works', () => ({
  worksApi: {
    list: (...args: unknown[]) => listWorks(...args),
    remove: () => Promise.resolve({ ok: true }),
    listTypes: () => Promise.resolve([]),
  },
}))

function buildPersona(overrides: Partial<GlobalPersona> = {}): GlobalPersona {
  return {
    id: 'persona_amy',
    name: '艾米',
    actor_name: 'Anne',
    role: '女主',
    gender: 'female',
    aliases: ['Amy'],
    tags: ['主线'],
    avatar_emoji: '👩',
    color: '#ef4444',
    updated_at: '2026-05-01T10:00:00',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <CharacterLibraryPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  listGlobalPersonas.mockReset()
  importGlobalPersonas.mockReset()
  deleteGlobalPersona.mockReset()
  listWorks.mockReset()
  listWorks.mockResolvedValue({ ok: true, path: '', works: [], unassigned_count: 0, version: 1 })
})

afterEach(() => {
  cleanup()
})

describe('CharacterLibraryPage', () => {
  it('renders empty state with call-to-action when no personas exist', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [],
      version: 1,
    })

    renderPage()

    expect(await screen.findByTestId('character-library-page-empty')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-empty-cta')).toBeInTheDocument()
    expect(screen.getByTestId('character-library-storage')).toHaveTextContent(
      '/tmp/personas.json',
    )
  })

  it('renders the personas table with actor/role/tags columns', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [
        buildPersona({
          avatar_url: 'https://image.tmdb.org/t/p/w185/amy.jpg',
        } as Partial<GlobalPersona> & { avatar_url: string }),
        buildPersona({
          id: 'persona_bob',
          name: '鲍勃',
          actor_name: 'Bob',
          tags: ['配角'],
        }),
      ],
      version: 1,
    })

    renderPage()

    expect(await screen.findByTestId('character-row-persona_amy')).toBeInTheDocument()
    expect(screen.getByTestId('character-row-persona_bob')).toBeInTheDocument()
    expect(screen.getByText('Anne')).toBeInTheDocument()
    expect(screen.getByText('主线')).toBeInTheDocument()
    expect(screen.getByText('配角')).toBeInTheDocument()
    const avatar = screen.getByTestId('character-avatar-image-persona_amy') as HTMLImageElement
    expect(avatar).toHaveAttribute('src', 'https://image.tmdb.org/t/p/w185/amy.jpg')
    expect(avatar).toHaveAttribute('alt', '艾米')
  })

  it('uses a work scope dropdown inside the primary character toolbar', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [buildPersona()],
      version: 1,
    })
    listWorks.mockResolvedValue({
      ok: true,
      path: '/tmp/works.json',
      works: [
        {
          id: 'work_nezha',
          title: '哪吒之魔童闹海',
          cover_emoji: '🎬',
          color: '#ef4444',
          persona_count: 24,
          aliases: [],
          tags: [],
        },
      ],
      unassigned_count: 1,
      version: 1,
    })

    renderPage()

    expect(await screen.findByTestId('character-row-persona_amy')).toBeInTheDocument()
    const worksPanel = screen.getByTestId('works-sidebar')
    const toolbar = screen.getByTestId('character-library-toolbar')
    const searchInput = screen.getByTestId('character-library-search')
    const select = screen.getByTestId('works-sidebar-select') as HTMLSelectElement

    expect(toolbar.firstElementChild).toBe(worksPanel)
    expect(worksPanel.parentElement).toBe(toolbar)
    expect(worksPanel.compareDocumentPosition(searchInput) & Node.DOCUMENT_POSITION_FOLLOWING).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(worksPanel).toHaveAttribute('aria-label', '作品筛选')
    expect(worksPanel).not.toHaveClass('w-[260px]')
    expect(worksPanel).not.toHaveClass('rounded-xl')
    expect(worksPanel).not.toHaveClass('shadow-[0_1px_3px_rgba(0,0,0,.04)]')
    expect(select.value).toBe('__all__')
    expect(screen.getByTestId('works-sidebar-item-work_nezha')).toHaveTextContent(
      '哪吒之魔童闹海 · 24',
    )
  })

  it('filters personas by search keyword', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [
        buildPersona({ id: 'persona_amy', name: '艾米', actor_name: 'Anne', tags: ['主线'] }),
        buildPersona({ id: 'persona_bob', name: '鲍勃', actor_name: 'Bob', tags: ['配角'] }),
      ],
      version: 1,
    })

    renderPage()

    await screen.findByTestId('character-row-persona_amy')
    const search = screen.getByTestId('character-library-search') as HTMLInputElement
    fireEvent.change(search, { target: { value: 'Bob' } })

    await waitFor(() => {
      expect(screen.queryByTestId('character-row-persona_amy')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('character-row-persona_bob')).toBeInTheDocument()
  })

  it('creates a new persona via the editor form', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [],
      version: 1,
    })
    importGlobalPersonas.mockResolvedValue({
      ok: true,
      accepted: 1,
      skipped: 0,
      total: 1,
      personas: [buildPersona({ id: 'persona_new', name: '新角色' })],
    })

    renderPage()

    await screen.findByTestId('character-library-page-empty')
    fireEvent.click(screen.getByTestId('character-library-empty-cta'))
    fireEvent.change(screen.getByTestId('character-field-name'), {
      target: { value: '新角色' },
    })
    fireEvent.change(screen.getByTestId('character-field-actor'), {
      target: { value: '新演员' },
    })
    fireEvent.change(screen.getByTestId('character-field-tags-input'), {
      target: { value: '主线, 测试' },
    })

    await act(async () => {
      fireEvent.click(screen.getByTestId('character-editor-save'))
    })

    await waitFor(() => {
      expect(importGlobalPersonas).toHaveBeenCalledTimes(1)
    })
    const payload = importGlobalPersonas.mock.calls[0][0]
    expect(payload.mode).toBe('merge')
    expect(payload.personas[0]).toMatchObject({
      name: '新角色',
      actor_name: '新演员',
      tags: ['主线', '测试'],
    })
    expect(await screen.findByTestId('character-library-flash-success')).toHaveTextContent(
      '新角色',
    )
  })

  it('deletes a persona after confirm', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [buildPersona()],
      version: 1,
    })
    deleteGlobalPersona.mockResolvedValue({ ok: true, personas: [] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderPage()

    await screen.findByTestId('character-row-persona_amy')
    await act(async () => {
      fireEvent.click(screen.getByTestId('character-delete-persona_amy'))
    })

    await waitFor(() => {
      expect(deleteGlobalPersona).toHaveBeenCalledWith('persona_amy')
    })
    expect(await screen.findByTestId('character-library-flash-success')).toHaveTextContent(
      '艾米',
    )

    confirmSpy.mockRestore()
  })

  it('opens edit dialog with prefilled values', async () => {
    listGlobalPersonas.mockResolvedValue({
      ok: true,
      path: '/tmp/personas.json',
      personas: [buildPersona()],
      version: 1,
    })

    renderPage()

    await screen.findByTestId('character-row-persona_amy')
    fireEvent.click(screen.getByTestId('character-edit-persona_amy'))

    const nameInput = screen.getByTestId('character-field-name') as HTMLInputElement
    expect(nameInput.value).toBe('艾米')
    const actorInput = screen.getByTestId('character-field-actor') as HTMLInputElement
    expect(actorInput.value).toBe('Anne')
    const tagsContainer = screen.getByTestId('character-field-tags')
    expect(tagsContainer).toHaveTextContent('主线')
    expect(screen.getByTestId('character-field-tags-chip-0')).toHaveTextContent('主线')
  })
})
