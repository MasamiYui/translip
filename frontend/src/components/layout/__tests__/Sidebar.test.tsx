import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '../Sidebar'
import { I18nProvider } from '../../../i18n/I18nProvider'

vi.mock('../../../api/atomic-tools', () => ({
  atomicToolsApi: {
    listTools: vi.fn().mockResolvedValue([
      {
        tool_id: 'separation',
        name_zh: '人声/背景分离',
        name_en: 'Audio Separation',
        description_zh: '',
        description_en: '',
        category: 'audio',
        icon: 'AudioLines',
        accept_formats: [],
        max_file_size_mb: 0,
        max_files: 0,
      },
      {
        tool_id: 'subtitle-erase',
        name_zh: '字幕擦除',
        name_en: 'Subtitle Erase',
        description_zh: '',
        description_en: '',
        category: 'video',
        icon: 'Eraser',
        accept_formats: [],
        max_file_size_mb: 0,
        max_files: 0,
      },
    ]),
  },
}))

function renderSidebar(initialPath: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Sidebar />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  cleanup()
})

describe('Sidebar', () => {
  it('highlights only the new task entry on the new task page', () => {
    const { container } = renderSidebar('/tasks/new')

    expect(container.firstChild).toHaveClass('bg-[#F5F7FB]')
    expect(screen.getByRole('link', { name: '任务列表' })).not.toHaveClass('bg-white')
    expect(screen.getByRole('link', { name: '新建任务' })).toHaveClass('bg-white')
    expect(screen.getByRole('link', { name: '新建任务' })).toHaveClass('text-blue-700')
    expect(screen.getByRole('link', { name: '任务列表' })).toHaveClass('text-slate-600')
    expect(screen.getByText('Pipeline Manager')).toHaveClass('text-slate-500')
    expect(screen.getByText('v0.1.0')).toHaveClass('text-slate-400')
    expect(container.querySelector('[data-ui-sidebar-brand]')).toHaveClass('h-16')
  })

  it('highlights the task list entry on the task list page', () => {
    renderSidebar('/tasks')

    expect(screen.getByRole('link', { name: '任务列表' })).toHaveClass('bg-white')
    expect(screen.getByRole('link', { name: '任务列表' })).toHaveClass('text-blue-700')
    expect(screen.getByRole('link', { name: '新建任务' })).not.toHaveClass('bg-white')
  })

  it('keeps the task list entry active on task detail pages', () => {
    renderSidebar('/tasks/task-123')

    expect(screen.getByRole('link', { name: '任务列表' })).toHaveClass('bg-white')
    expect(screen.getByRole('link', { name: '任务列表' })).toHaveClass('text-blue-700')
    expect(screen.getByRole('link', { name: '新建任务' })).not.toHaveClass('bg-white')
  })

  it('collapses the atomic tools group when clicked again on the tools page', async () => {
    renderSidebar('/tools')

    expect(await screen.findByRole('link', { name: '人声/背景分离' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /原子工具集/ }))

    expect(screen.queryByRole('link', { name: '人声/背景分离' })).not.toBeInTheDocument()
  })
})
