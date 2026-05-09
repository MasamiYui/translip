import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

const SIDEBAR_STORAGE_KEY = 'translip:sidebar-collapsed'
const SIDEBAR_EXPANDED_WIDTH = 220
const SIDEBAR_COLLAPSED_WIDTH = 60

function readInitialCollapsed() {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function MainLayout() {
  const { pathname } = useLocation()
  const isWorkbench =
    /\/tasks\/[^/]+\/dubbing-editor\/?$/.test(pathname) ||
    /\/harness\/speaker-review\//.test(pathname) ||
    /\/tasks\/[^/]+\/speaker-review\/?$/.test(pathname)

  const [collapsed, setCollapsed] = useState<boolean>(readInitialCollapsed)

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore quota / privacy mode */
    }
  }, [collapsed])

  const toggleSidebar = useCallback(() => setCollapsed((prev) => !prev), [])

  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH
  const headerHeight = isWorkbench ? 48 : 60
  const layoutChromeStyle = {
    '--sidebar-offset': `${sidebarWidth}px`,
    '--app-header-height': `${headerHeight}px`,
  } as CSSProperties

  return (
    <div className="min-h-screen bg-[#f4f6fa]">
      <div className="hidden md:block">
        <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      </div>
      <Header workbench={isWorkbench} sidebarOffset={sidebarWidth} />
      <main
        style={layoutChromeStyle}
        className={
          isWorkbench
            ? 'ml-0 md:ml-[var(--sidebar-offset)] pt-12 h-screen overflow-hidden bg-[#f4f6fa] transition-[margin-left] duration-200 ease-out'
            : 'ml-0 md:ml-[var(--sidebar-offset)] pt-[60px] min-h-screen transition-[margin-left] duration-200 ease-out'
        }
      >
        {isWorkbench ? (
          <div className="h-[calc(100vh-48px)] animate-[fadeIn_150ms_ease-out]">
            <Outlet />
          </div>
        ) : (
          <div className="px-6 py-6">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
