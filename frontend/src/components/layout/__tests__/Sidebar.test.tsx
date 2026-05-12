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
  it('groups pipeline and atomic tasks under the task center', () => {
    renderSidebar('/tasks')

    expect(screen.getByRole('button', { name: /任务中心/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '流水线任务' })).toHaveAttribute('href', '/tasks')
    expect(screen.getByRole('link', { name: '原子任务' })).toHaveAttribute('href', '/tools/jobs')
    expect(screen.getByRole('link', { name: '新建流水线任务' })).toHaveAttribute('href', '/tasks/new')
  })

  it('keeps expandable nav rows full width so their chevrons align to the right edge', () => {
    renderSidebar('/tasks')

    expect(screen.getByRole('button', { name: /任务中心/ })).toHaveClass('w-full')
    expect(screen.getByRole('button', { name: /原子工具集/ })).toHaveClass('w-full')
  })

  it('highlights only the new pipeline task entry on the new task page', () => {
    const { container } = renderSidebar('/tasks/new')

    expect(container.firstChild).toHaveClass('bg-white')
    expect(screen.getByRole('link', { name: '流水线任务' })).not.toHaveClass('bg-[#3b5bdb]/10')
    expect(screen.getByRole('link', { name: '新建流水线任务' })).toHaveClass('bg-[#3b5bdb]/10')
    expect(screen.getByRole('link', { name: '新建流水线任务' })).toHaveClass('text-[#3b5bdb]')
    expect(screen.getByRole('link', { name: '流水线任务' })).toHaveClass('text-[#9ca3af]')
    expect(screen.getByText('Pipeline Manager')).toHaveClass('text-[#9ca3af]')
    expect(screen.getByText('v0.1.0')).toHaveClass('text-[11px]')
    expect(container.querySelector('[data-ui-sidebar-brand]')).toHaveClass('h-[60px]')
  })

  it('highlights the pipeline task entry on the task list page', () => {
    renderSidebar('/tasks')

    expect(screen.getByRole('link', { name: '流水线任务' })).toHaveClass('bg-[#3b5bdb]/10')
    expect(screen.getByRole('link', { name: '流水线任务' })).toHaveClass('text-[#3b5bdb]')
    expect(screen.getByRole('link', { name: '新建流水线任务' })).not.toHaveClass('bg-[#3b5bdb]/10')
  })

  it('keeps the pipeline task entry active on task detail pages', () => {
    renderSidebar('/tasks/task-123')

    expect(screen.getByRole('link', { name: '流水线任务' })).toHaveClass('bg-[#3b5bdb]/10')
    expect(screen.getByRole('link', { name: '流水线任务' })).toHaveClass('text-[#3b5bdb]')
    expect(screen.getByRole('link', { name: '新建流水线任务' })).not.toHaveClass('bg-[#3b5bdb]/10')
  })

  it('highlights the atomic task entry on atomic job pages', () => {
    renderSidebar('/tools/jobs/job-123')

    expect(screen.getByRole('button', { name: /任务中心/ })).toHaveClass('bg-[#3b5bdb]/10')
    expect(screen.getByRole('link', { name: '原子任务' })).toHaveClass('bg-[#3b5bdb]/10')
    expect(screen.getByRole('link', { name: '原子任务' })).toHaveClass('text-[#3b5bdb]')
    expect(screen.getByRole('button', { name: /原子工具集/ })).not.toHaveClass('bg-[#3b5bdb]/10')
  })

  it('collapses the atomic tools group when clicked again on the tools page', async () => {
    renderSidebar('/tools')

    expect(await screen.findByRole('link', { name: '人声/背景分离' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '运行记录' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /原子工具集/ }))

    expect(screen.queryByRole('link', { name: '人声/背景分离' })).not.toBeInTheDocument()
  })
})
