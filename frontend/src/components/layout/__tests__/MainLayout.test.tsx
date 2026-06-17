import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { MainLayout } from '../MainLayout'

vi.mock('../Sidebar', () => ({
  Sidebar: () => <aside>Sidebar</aside>,
}))

vi.mock('../Header', () => ({
  Header: () => <header>Header</header>,
}))

// The floating assistant uses React Query; stub it here since this is a
// layout-only test that intentionally avoids a QueryClientProvider.
vi.mock('../../assistant/AssistantWidget', () => ({
  AssistantWidget: () => null,
}))

// Layout-only test: stub the app-wide task watcher so MainLayout doesn't need a
// QueryClientProvider here (its behaviour is covered in useTaskNotifications.test).
vi.mock('../../../hooks/useTaskNotifications', () => ({
  useTaskNotifications: () => undefined,
}))

describe('MainLayout', () => {
  it('uses the soft-gray application canvas behind the routed content', () => {
    const { container } = render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<MainLayout />}>
              <Route index element={<div>Content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    )

    expect(screen.getByText('Content')).toBeInTheDocument()
    // The redesign (6270c48) moved the canvas to a soft gray so white cards read
    // as raised surfaces; cards are bg-white on top of this.
    expect(container.firstChild).toHaveClass('bg-[#f4f6fa]')
  })

  it('does not reserve sidebar width on mobile viewports', () => {
    const { container } = render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/tools/transcription']}>
          <Routes>
            <Route path="/tools/transcription" element={<MainLayout />}>
              <Route index element={<div>Content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    )

    const sidebarWrapper = container.querySelector('aside')?.parentElement
    const main = container.querySelector('main')

    expect(sidebarWrapper).toHaveClass('hidden', 'md:block')
    expect(main).toHaveClass('ml-0', 'md:ml-[var(--sidebar-offset)]')
    expect(main).not.toHaveAttribute('style', expect.stringContaining('margin-left'))
  })
})
