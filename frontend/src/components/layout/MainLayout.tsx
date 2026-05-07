import { useCallback, useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

const SIDEBAR_STORAGE_KEY = 'translip:sidebar-collapsed'
const SIDEBAR_EXPANDED_WIDTH = 220
const SIDEBAR_COLLAPSED_WIDTH = 56

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
  const isWorkbench = /\/tasks\/[^/]+\/dubbing-editor\/?$/.test(pathname)

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

  return (
    <div className="min-h-screen bg-white">
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <Header workbench={isWorkbench} sidebarOffset={sidebarWidth} />
      <main
        style={{ marginLeft: sidebarWidth }}
        className={
          isWorkbench
            ? 'pt-12 h-screen overflow-hidden bg-[#F5F7FB] transition-[margin-left] duration-200 ease-out'
            : 'pt-16 min-h-screen transition-[margin-left] duration-200 ease-out'
        }
      >
        {isWorkbench ? (
          <div className="h-[calc(100vh-48px)] animate-[fadeIn_150ms_ease-out]">
            <Outlet />
          </div>
        ) : (
          <div className="p-6">
            <Outlet />
          </div>
        )}
      </main>
    </div>
  )
}
