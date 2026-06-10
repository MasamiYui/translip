import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { TopNav } from '../TopNav'

vi.mock('../../../api/atomic-tools', () => ({
  atomicToolsApi: {
    listTools: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('../../../api/config', () => ({
  systemApi: {
    info: vi.fn().mockResolvedValue({ status: 'ok' }),
  },
}))

function renderTopNav(layoutMode: 'left' | 'top') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <TopNav layoutMode={layoutMode} onToggleLayoutMode={() => {}} />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('TopNav layout-mode toggle', () => {
  afterEach(() => cleanup())

  it('announces the destination as left sidebar when currently in top mode', () => {
    renderTopNav('top')

    const button = screen.getByTestId('toggle-layout-mode')
    expect(button).toHaveAttribute('aria-label', '切换到左侧菜单')
    expect(button).toHaveAttribute('title', '切换到左侧菜单')
  })

  it('announces the destination as top menu when currently in left mode', () => {
    renderTopNav('left')

    const button = screen.getByTestId('toggle-layout-mode')
    expect(button).toHaveAttribute('aria-label', '切换到顶部菜单')
    expect(button).toHaveAttribute('title', '切换到顶部菜单')
  })
})
