import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  ChevronDown,
  ListChecks,
  PanelLeftClose,
  PanelLeftOpen,
  Wrench,
  X,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import { normalizePathname, useNavConfig, type NavSimpleItem } from './navConfig'

function TranslipVoiceStemsLogo() {
  return (
    <svg
      role="img"
      aria-label="Translip Voice Stems logo"
      viewBox="0 0 64 64"
      className="h-8 w-8"
    >
      <rect x="7" y="7" width="50" height="50" rx="14" fill="#ffffff" stroke="#d0d5dd" strokeWidth="2" />
      <path
        d="M17 32h4l4-11 5 25 6-31 5 17h6"
        fill="none"
        stroke="#4285f4"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M17 47h13" stroke="#34a853" strokeWidth="5" strokeLinecap="round" />
      <path d="M36 47h11" stroke="#fbbc04" strokeWidth="5" strokeLinecap="round" />
      <circle cx="47" cy="32" r="4" fill="#ea4335" />
    </svg>
  )
}

interface SidebarProps {
  collapsed?: boolean
  onToggle?: () => void
  mobileDrawer?: boolean
  onCloseMobile?: () => void
}

export function Sidebar({
  collapsed: collapsedProp = false,
  onToggle,
  mobileDrawer = false,
  onCloseMobile,
}: SidebarProps = {}) {
  const { t } = useI18n()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const currentPath = normalizePathname(pathname)

  const nav = useNavConfig()
  const { isTaskCenterRoute, isToolsRoute } = nav.routeFlags

  const [taskCenterCollapsedPath, setTaskCenterCollapsedPath] = useState<string | null>(null)
  const [toolsCollapsedPath, setToolsCollapsedPath] = useState<string | null>(null)
  const taskCenterExpanded = isTaskCenterRoute && taskCenterCollapsedPath !== currentPath
  const toolsExpanded = isToolsRoute && toolsCollapsedPath !== currentPath

  const asideWidth = mobileDrawer ? 'w-[260px]' : collapsedProp ? 'w-[60px]' : 'w-[220px]'
  const collapsed = mobileDrawer ? false : collapsedProp

  function navItemClass(isActive: boolean) {
    if (isActive) {
      return cn(
        'flex items-center rounded-lg text-sm font-medium transition-all',
        collapsed ? 'h-9 w-9 justify-center' : 'w-full gap-3 px-3 py-2',
        'bg-[#3b5bdb]/10 text-[#3b5bdb]',
      )
    }
    return cn(
      'flex items-center rounded-lg text-sm font-medium transition-all',
      collapsed ? 'h-9 w-9 justify-center' : 'w-full gap-3 px-3 py-2',
      'text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#111827]',
    )
  }

  const SIDEBAR_TEST_ID_KEYS = new Set([
    'works-library',
    'character-library',
    'evaluation',
    'user-guide',
    'blog',
    'api-docs',
    'lab',
  ])

  function resolveSidebarTestId(key: string) {
    return SIDEBAR_TEST_ID_KEYS.has(key) ? `sidebar-link-${key}` : undefined
  }

  function renderSimpleItem(item: NavSimpleItem) {
    const { to, label, icon: Icon, isActive, external } = item
    const testId = resolveSidebarTestId(item.key)
    if (external) {
      return (
        <a
          key={item.key}
          href={to}
          target="_blank"
          rel="noopener noreferrer"
          data-testid={testId}
          title={collapsed ? label : undefined}
          aria-label={collapsed ? label : undefined}
          className={navItemClass(false)}
        >
          <Icon size={15} className="shrink-0" />
          {!collapsed && <span className="truncate">{label}</span>}
        </a>
      )
    }
    return (
      <Link
        key={item.key}
        to={to}
        data-testid={testId}
        aria-current={isActive ? 'page' : undefined}
        title={collapsed ? label : undefined}
        aria-label={collapsed ? label : undefined}
        className={navItemClass(isActive)}
      >
        <Icon size={15} className="shrink-0" />
        {!collapsed && <span className="truncate">{label}</span>}
      </Link>
    )
  }

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 flex h-full flex-col bg-white transition-[width] duration-200 ease-out',
        'border-r border-[#e5e7eb]',
        asideWidth,
      )}
    >
      {/* Brand / Logo */}
      <div
        data-ui-sidebar-brand=""
        className={cn(
          'flex h-[60px] items-center gap-3 border-b border-[#f3f4f6]',
          collapsed ? 'justify-center px-0' : 'px-4',
        )}
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-[#d7e7ff]">
          <TranslipVoiceStemsLogo />
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-[#111827] leading-tight">
              Translip
            </div>
            <div className="truncate text-[11px] text-[#9ca3af] leading-tight">{t.nav.subtitle}</div>
          </div>
        )}
        {mobileDrawer && onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label={t.nav.closeMobileMenu}
            title={t.nav.closeMobileMenu}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#9ca3af] transition-colors hover:bg-[#f3f4f6] hover:text-[#374151]"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav
        className={cn('flex-1 space-y-0.5 py-3 overflow-y-auto', collapsed ? 'px-[10px]' : 'px-3')}
        onClick={(e) => {
          if (!mobileDrawer || !onCloseMobile) return
          const target = e.target as HTMLElement | null
          if (target?.closest('a[href]')) onCloseMobile()
        }}
      >
        {renderSimpleItem(nav.dashboard)}

        {/* Task center accordion */}
        <button
          type="button"
          title={collapsed ? nav.taskCenter.label : undefined}
          aria-label={collapsed ? nav.taskCenter.label : undefined}
          onClick={() => {
            if (collapsed) {
              if (!isTaskCenterRoute) navigate('/tasks')
              return
            }
            if (taskCenterExpanded) {
              setTaskCenterCollapsedPath(currentPath)
              return
            }
            setTaskCenterCollapsedPath(null)
            if (!isTaskCenterRoute) navigate('/tasks')
          }}
          className={navItemClass(isTaskCenterRoute)}
        >
          <ListChecks size={15} className="shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1 truncate text-left">{nav.taskCenter.label}</span>
              <ChevronDown
                size={13}
                className={cn(
                  'shrink-0 transition-transform duration-200',
                  taskCenterExpanded && 'rotate-180',
                )}
              />
            </>
          )}
        </button>

        {!collapsed && (
          <div
            aria-hidden={!taskCenterExpanded}
            className={cn(
              'grid transition-[grid-template-rows,opacity] duration-200 ease-out',
              taskCenterExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
            )}
          >
            <div className="overflow-hidden">
              <div className="ml-[22px] mt-0.5 space-y-0.5 border-l border-[#e5e7eb] pl-3 pb-1">
                {nav.taskCenter.items.map(({ to, label, icon: Icon, isActive }) => (
                  <Link
                    key={to}
                    to={to}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-all',
                      isActive
                        ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                        : 'text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#374151]',
                    )}
                  >
                    <Icon size={13} className="shrink-0" />
                    <span className="truncate">{label}</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Tools accordion */}
        <button
          type="button"
          title={collapsed ? nav.tools.label : undefined}
          aria-label={collapsed ? nav.tools.label : undefined}
          onClick={() => {
            if (collapsed) {
              if (!isToolsRoute) navigate('/tools')
              return
            }
            if (toolsExpanded) {
              setToolsCollapsedPath(currentPath)
              return
            }
            setToolsCollapsedPath(null)
            if (!isToolsRoute) navigate('/tools')
          }}
          className={navItemClass(isToolsRoute)}
        >
          <Wrench size={15} className="shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1 truncate text-left">{nav.tools.label}</span>
              <ChevronDown
                size={13}
                className={cn('shrink-0 transition-transform duration-200', toolsExpanded && 'rotate-180')}
              />
            </>
          )}
        </button>

        {!collapsed && (
          <div
            aria-hidden={!toolsExpanded}
            className={cn(
              'grid transition-[grid-template-rows,opacity] duration-200 ease-out',
              toolsExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
            )}
          >
            <div className="overflow-hidden">
              <div className="ml-[22px] mt-0.5 space-y-0.5 border-l border-[#e5e7eb] pl-3 pb-1">
                {nav.tools.items.map(({ to, label, icon: Icon, isActive }) => (
                  <Link
                    key={to}
                    to={to}
                    aria-current={isActive ? 'page' : undefined}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-all',
                      isActive
                        ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                        : 'text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#374151]',
                    )}
                  >
                    <Icon size={13} className="shrink-0" />
                    <span className="truncate">{label}</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>
        )}

        {renderSimpleItem(nav.worksLibrary)}
        {renderSimpleItem(nav.characterLibrary)}
        {renderSimpleItem(nav.evaluation)}
        {renderSimpleItem(nav.userGuide)}
        {renderSimpleItem(nav.blog)}
        {renderSimpleItem(nav.apiDocs)}
        {renderSimpleItem(nav.lab)}
        {renderSimpleItem(nav.settings)}
      </nav>

      {/* Footer */}
      <div
        className={cn(
          'flex items-center border-t border-[#f3f4f6] py-2.5',
          collapsed ? 'justify-center px-[10px]' : 'justify-between px-4',
        )}
      >
        {!collapsed && <div className="text-[11px] text-[#d1d5db] font-medium">v0.1.0</div>}
        {onToggle && !mobileDrawer && (
          <button
            type="button"
            onClick={onToggle}
            title={collapsed ? t.nav.expandSidebar : t.nav.collapseSidebar}
            aria-label={collapsed ? t.nav.expandSidebar : t.nav.collapseSidebar}
            className="flex h-7 w-7 items-center justify-center rounded-md text-[#9ca3af] transition-colors hover:bg-[#f3f4f6] hover:text-[#374151]"
          >
            {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
          </button>
        )}
      </div>
    </aside>
  )
}
