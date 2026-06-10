import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { TopNav } from './TopNav'
import { useTaskNotifications } from '../../hooks/useTaskNotifications'
import { useI18n } from '../../i18n/useI18n'

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
  const { t } = useI18n()
  // App-wide watcher: notify when a long pipeline run finishes while tabbed away.
  useTaskNotifications()
  const isWorkbench =
    /\/tasks\/[^/]+\/dubbing-editor\/?$/.test(pathname) ||
    /\/harness\/speaker-review\//.test(pathname) ||
    /\/tasks\/[^/]+\/speaker-review\/?$/.test(pathname)

  const [collapsed, setCollapsed] = useState<boolean>(readInitialCollapsed)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(readInitialLayoutMode)
  const [mobileNavOpen, setMobileNavOpen] = useState<boolean>(false)

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
  const openMobileNav = useCallback(() => setMobileNavOpen(true), [])
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), [])

  // Auto-close mobile drawer on route change. Safety net in case a navigation
  // bypasses the in-drawer click delegation. Rule disabled: this synchronization
  // is intentional and unavoidable — closing must follow router pathname updates.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMobileNavOpen((prev) => (prev ? false : prev))
  }, [pathname])

  // ESC closes mobile drawer + lock body scroll while open.
  useEffect(() => {
    if (!mobileNavOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMobileNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [mobileNavOpen])

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

      {/* Mobile hamburger trigger (visible <md only) */}
      <button
        type="button"
        onClick={openMobileNav}
        aria-label={t.nav.openMobileMenu}
        aria-controls="mobile-nav-drawer"
        aria-expanded={mobileNavOpen}
        title={t.nav.openMobileMenu}
        className="md:hidden print:hidden fixed left-3 top-3 z-[60] flex h-9 w-9 items-center justify-center rounded-lg border border-[#e5e7eb] bg-white text-[#374151] shadow-sm transition-colors hover:bg-[#f3f4f6]"
      >
        <Menu size={18} />
      </button>

      {/* Mobile drawer + backdrop (rendered only when open, visible <md only) */}
      {mobileNavOpen && (
        <div className="md:hidden print:hidden" id="mobile-nav-drawer" role="dialog" aria-modal="true" aria-label={t.nav.openMobileMenu}>
          <div
            onClick={closeMobileNav}
            className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-sm animate-[fadeIn_150ms_ease-out]"
          />
          <div className="fixed left-0 top-0 z-[80] h-full animate-[slideInLeft_200ms_ease-out]">
            <Sidebar mobileDrawer onCloseMobile={closeMobileNav} />
          </div>
        </div>
      )}

      {isTopMode ? (
        <div className="hidden md:block print:hidden">
          <TopNav height={topNavHeight} layoutMode={layoutMode} onToggleLayoutMode={toggleLayoutMode} />
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
