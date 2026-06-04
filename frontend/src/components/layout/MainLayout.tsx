import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { TopNav } from './TopNav'

const SIDEBAR_STORAGE_KEY = 'translip:sidebar-collapsed'
const LAYOUT_MODE_STORAGE_KEY = 'translip:layout-mode'
const SIDEBAR_EXPANDED_WIDTH = 220
const SIDEBAR_COLLAPSED_WIDTH = 60
const TOP_NAV_HEIGHT = 56

export type LayoutMode = 'left' | 'top'

function readInitialCollapsed() {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

function readInitialLayoutMode(): LayoutMode {
  if (typeof window === 'undefined') return 'left'
  try {
    const v = window.localStorage.getItem(LAYOUT_MODE_STORAGE_KEY)
    return v === 'top' ? 'top' : 'left'
  } catch {
    return 'left'
  }
}

export function MainLayout() {
  const { pathname } = useLocation()
  const isWorkbench =
    /\/tasks\/[^/]+\/dubbing-editor\/?$/.test(pathname) ||
    /\/harness\/speaker-review\//.test(pathname) ||
    /\/tasks\/[^/]+\/speaker-review\/?$/.test(pathname)

  const [collapsed, setCollapsed] = useState<boolean>(readInitialCollapsed)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(readInitialLayoutMode)

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore quota / privacy mode */
    }
  }, [collapsed])

  useEffect(() => {
    try {
      window.localStorage.setItem(LAYOUT_MODE_STORAGE_KEY, layoutMode)
    } catch {
      /* ignore quota / privacy mode */
    }
  }, [layoutMode])

  const toggleSidebar = useCallback(() => setCollapsed((prev) => !prev), [])
  const toggleLayoutMode = useCallback(
    () => setLayoutMode((prev) => (prev === 'left' ? 'top' : 'left')),
    [],
  )

  const isTopMode = layoutMode === 'top'
  const sidebarWidth = isTopMode ? 0 : collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH
  const headerHeight = isWorkbench ? 48 : 60
  const topNavHeight = isWorkbench ? 48 : TOP_NAV_HEIGHT
  const totalTopOffset = isTopMode ? topNavHeight : headerHeight

  const layoutChromeStyle = {
    '--sidebar-offset': `${sidebarWidth}px`,
    '--app-header-height': `${headerHeight}px`,
    '--top-nav-height': `${isTopMode ? topNavHeight : 0}px`,
  } as CSSProperties

  return (
    <div className="min-h-screen bg-[#f4f6fa]">
      {!isTopMode && (
        <div className="hidden md:block print:hidden">
          <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
        </div>
      )}
      {isTopMode ? (
        <div className="hidden md:block print:hidden">
          <TopNav height={topNavHeight} onToggleLayoutMode={toggleLayoutMode} />
        </div>
      ) : (
        <Header
          workbench={isWorkbench}
          sidebarOffset={sidebarWidth}
          topOffset={0}
          layoutMode={layoutMode}
          onToggleLayoutMode={toggleLayoutMode}
        />
      )}
      <main
        style={layoutChromeStyle}
        className={
          isWorkbench
            ? 'ml-0 md:ml-[var(--sidebar-offset)] h-screen overflow-hidden bg-[#f4f6fa] transition-[margin-left] duration-200 ease-out'
            : 'ml-0 md:ml-[var(--sidebar-offset)] min-h-screen transition-[margin-left] duration-200 ease-out'
        }
      >
        {isWorkbench ? (
          <div
            style={{ paddingTop: totalTopOffset, height: `calc(100vh - ${totalTopOffset}px)` }}
            className="animate-[fadeIn_150ms_ease-out]"
          >
            <Outlet />
          </div>
        ) : (
          <div style={{ paddingTop: totalTopOffset + 24 }} className="px-6 pb-6">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
