import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { APP_CONTENT_MAX_WIDTH } from '../../components/layout/PageContainer'
import { I18nProvider } from '../../i18n/I18nProvider'
import { NewTaskPage } from '../NewTaskPage'
import { SettingsPage } from '../SettingsPage'
import { TaskListPage } from '../TaskListPage'
import { ToolListPage } from '../ToolListPage'
import { ToolPage } from '../ToolPage'

vi.mock('../../api/tasks', () => ({
  tasksApi: {
    list: vi.fn(() => Promise.resolve({ items: [], total: 0 })),
    delete: vi.fn(),
    create: vi.fn(),
  },
}))

vi.mock('../../api/config', () => ({
  configApi: {
    getDefaults: vi.fn(),
    getPresets: vi.fn(() => Promise.resolve([])),
    createPreset: vi.fn(),
    deletePreset: vi.fn(),
  },
  systemApi: {
    getInfo: vi.fn(() =>
      Promise.resolve({
        python_version: '3.11',
        platform: 'macOS',
        device: 'mps',
        cache_dir: '/tmp/cache',
        cache_size_bytes: 0,
        models: [],
      }),
    ),
    probe: vi.fn(),
  },
  cacheApi: {
    getBreakdown: vi.fn(() =>
      Promise.resolve({
        cache_dir: '/tmp/cache',
        huggingface_hub_dir: '/tmp/hf',
        total_bytes: 0,
        items: [],
      }),
    ),
    setDir: vi.fn(),
    resetDefault: vi.fn(),
    removeItem: vi.fn(),
    cleanup: vi.fn(),
    startMigrate: vi.fn(),
    pollMigrate: vi.fn(),
    cancelMigrate: vi.fn(),
  },
}))

vi.mock('../../api/atomic-tools', () => ({
  atomicToolsApi: {
    listTools: vi.fn(() =>
      Promise.resolve([
        {
          tool_id: 'probe',
          category: 'video',
          name_zh: '探测',
          name_en: 'Probe',
          description_zh: '探测素材',
          description_en: 'Inspect media',
        },
      ]),
    ),
  },
}))

vi.mock('../../hooks/useAtomicTool', () => ({
  useAtomicTool: vi.fn(() => ({
    uploadFile: vi.fn(),
    job: null,
    artifacts: [],
    runTool: vi.fn(),
    isRunning: false,
    getDownloadUrl: vi.fn(),
    errorMessage: '',
    reset: vi.fn(),
  })),
}))

function createWrapper(initialEntries = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
        </I18nProvider>
      </QueryClientProvider>
    )
  }
}

describe('page content widths', () => {
  it('keeps task list aligned with the dashboard content width', () => {
    const { container } = render(<TaskListPage />, { wrapper: createWrapper() })
    const taskListPanel = container.querySelector('.overflow-hidden.rounded-xl.border.border-slate-200.bg-white')

    expect(screen.getByRole('heading', { name: '任务列表' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
    expect((taskListPanel as HTMLElement).className).not.toContain('shadow')
  })

  it('keeps new task aligned with the dashboard content width', () => {
    const { container } = render(<NewTaskPage />, { wrapper: createWrapper() })
    const sectionCards = container.querySelectorAll('section.overflow-hidden.rounded-xl.border.border-slate-200.bg-white')

    expect(screen.getByRole('heading', { name: '新建任务' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
    sectionCards.forEach(section => {
      expect((section as HTMLElement).className).not.toContain('shadow')
    })
  })

  it('keeps settings aligned with the dashboard content width', () => {
    const { container } = render(<SettingsPage />, { wrapper: createWrapper() })
    const settingsPanel = container.querySelector('.overflow-hidden.rounded-xl.border.border-slate-200.bg-white')

    expect(screen.getByRole('heading', { name: '全局设置' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
    expect((settingsPanel as HTMLElement).className).not.toContain('shadow')
  })

  it('keeps tool list aligned with the dashboard content width', async () => {
    const { container } = render(<ToolListPage />, { wrapper: createWrapper() })

    expect(await screen.findByRole('heading', { name: '原子工具集' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
  })

  it('keeps tool detail aligned with the dashboard content width', async () => {
    const { container } = render(
      <Routes>
        <Route path="/tools/:toolId" element={<ToolPage />} />
      </Routes>,
      { wrapper: createWrapper(['/tools/probe']) },
    )

    expect(await screen.findByRole('heading', { name: '探测' })).toBeInTheDocument()
    expect(container.firstChild).toHaveClass(APP_CONTENT_MAX_WIDTH)
  })
})
