import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AudioLines,
  BookUser,
  Captions,
  ChevronDown,
  Clapperboard,
  Cpu,
  Eraser,
  Languages,
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  Mic,
  Music,
  PanelLeftClose,
  PanelLeftOpen,
  PlusCircle,
  ScanSearch,
  ScanText,
  Settings,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import { atomicToolsApi } from '../../api/atomic-tools'
import type { ToolInfo } from '../../types/atomic-tools'

const TOOL_ICON_MAP: Record<string, LucideIcon> = {
  AudioLines,
  Captions,
  Clapperboard,
  Eraser,
  Languages,
  MessageSquareText,
  Mic,
  Music,
  ScanSearch,
  ScanText,
}

function resolveToolIcon(name: string): LucideIcon {
  return TOOL_ICON_MAP[name] ?? Wrench
}

function normalizePathname(pathname: string) {
  if (pathname === '/') return pathname
  return pathname.replace(/\/+$/, '')
}

interface SidebarProps {
  collapsed?: boolean
  onToggle?: () => void
}

export function Sidebar({ collapsed = false, onToggle }: SidebarProps = {}) {
  const { t, locale } = useI18n()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const currentPath = normalizePathname(pathname)
  const isNewTaskRoute = currentPath === '/tasks/new' || currentPath.startsWith('/tasks/new/')
  const isPipelineTaskRoute =
    currentPath === '/tasks' || (currentPath.startsWith('/tasks/') && !isNewTaskRoute)
  const isAtomicJobsRoute = currentPath === '/tools/jobs' || currentPath.startsWith('/tools/jobs/')
  const isTaskCenterRoute = isPipelineTaskRoute || isNewTaskRoute || isAtomicJobsRoute
  const isToolsRoute =
    currentPath === '/tools' || (currentPath.startsWith('/tools/') && !isAtomicJobsRoute)
  const [taskCenterExpanded, setTaskCenterExpanded] = useState(isTaskCenterRoute)
  const [toolsExpanded, setToolsExpanded] = useState(isToolsRoute)

  useEffect(() => {
    if (isTaskCenterRoute) setTaskCenterExpanded(true)
  }, [isTaskCenterRoute])

  useEffect(() => {
    if (isToolsRoute) setToolsExpanded(true)
  }, [isToolsRoute])

  const navItems = [
    {
      to: '/',
      label: t.nav.dashboard,
      icon: LayoutDashboard,
      isActive: currentPath === '/',
    },
  ]

  const settingsNavItem = {
    to: '/settings',
    label: t.nav.settings,
    icon: Settings,
    isActive: currentPath === '/settings',
  }

  const characterLibraryNavItem = {
    to: '/character-library',
    label: t.nav.characterLibrary,
    icon: BookUser,
    isActive: currentPath === '/character-library',
  }

  const worksLibraryNavItem = {
    to: '/works',
    label: t.nav.worksLibrary,
    icon: Clapperboard,
    isActive: currentPath === '/works',
  }

  const toolLabels = t.atomicTools.tools as Record<string, string | undefined>
  const { data: tools } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })

  const toolNavItems = (tools ?? []).map((tool: ToolInfo) => ({
    to: `/tools/${tool.tool_id}`,
    label: toolLabels[tool.tool_id] ?? (locale === 'zh-CN' ? tool.name_zh : tool.name_en),
    icon: resolveToolIcon(tool.icon),
  }))

  const asideWidth = collapsed ? 'w-[60px]' : 'w-[220px]'

  function navItemClass(isActive: boolean) {
    if (isActive) {
      return cn(
        'flex items-center rounded-lg text-sm font-medium transition-all',
        collapsed ? 'h-9 w-9 justify-center' : 'gap-3 px-3 py-2',
        'bg-[#3b5bdb]/10 text-[#3b5bdb]',
      )
    }
    return cn(
      'flex items-center rounded-lg text-sm font-medium transition-all',
      collapsed ? 'h-9 w-9 justify-center' : 'gap-3 px-3 py-2',
      'text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#111827]',
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
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#3b5bdb]">
          <Cpu size={14} className="text-white" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-[#111827] leading-tight">
              Translip
            </div>
            <div className="truncate text-[11px] text-[#9ca3af] leading-tight">{t.nav.subtitle}</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav
        className={cn('flex-1 space-y-0.5 py-3 overflow-y-auto', collapsed ? 'px-[10px]' : 'px-3')}
      >
        {navItems.map(({ to, label, icon: Icon, isActive }) => (
          <Link
            key={to}
            to={to}
            aria-current={isActive ? 'page' : undefined}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            className={navItemClass(isActive)}
          >
            <Icon size={15} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </Link>
        ))}

        {/* Task center accordion */}
        <button
          type="button"
          title={collapsed ? t.nav.taskCenter : undefined}
          aria-label={collapsed ? t.nav.taskCenter : undefined}
          onClick={() => {
            if (collapsed) {
              if (!isTaskCenterRoute) navigate('/tasks')
              return
            }
            if (taskCenterExpanded) {
              setTaskCenterExpanded(false)
              return
            }
            setTaskCenterExpanded(true)
            if (!isTaskCenterRoute) navigate('/tasks')
          }}
          className={navItemClass(isTaskCenterRoute)}
        >
          <ListChecks size={15} className="shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1 truncate text-left">{t.nav.taskCenter}</span>
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
                <Link
                  to="/tasks"
                  aria-current={isPipelineTaskRoute ? 'page' : undefined}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-all',
                    isPipelineTaskRoute
                      ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                      : 'text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#374151]',
                  )}
                >
                  <ListChecks size={13} className="shrink-0" />
                  <span className="truncate">{t.nav.pipelineTasks}</span>
                </Link>
                <Link
                  to="/tools/jobs"
                  aria-current={isAtomicJobsRoute ? 'page' : undefined}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-all',
                    isAtomicJobsRoute
                      ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                      : 'text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#374151]',
                  )}
                >
                  <ListChecks size={13} className="shrink-0" />
                  <span className="truncate">{t.nav.atomicTasks}</span>
                </Link>
                <Link
                  to="/tasks/new"
                  aria-current={isNewTaskRoute ? 'page' : undefined}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-all',
                    isNewTaskRoute
                      ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                      : 'text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#374151]',
                  )}
                >
                  <PlusCircle size={13} className="shrink-0" />
                  <span className="truncate">{t.nav.newPipelineTask}</span>
                </Link>
              </div>
            </div>
          </div>
        )}

        {/* Tools accordion */}
        <button
          type="button"
          title={collapsed ? t.atomicTools.title : undefined}
          aria-label={collapsed ? t.atomicTools.title : undefined}
          onClick={() => {
            if (collapsed) {
              if (!isToolsRoute) navigate('/tools')
              return
            }
            if (toolsExpanded) {
              setToolsExpanded(false)
              return
            }
            setToolsExpanded(true)
            if (!isToolsRoute) navigate('/tools')
          }}
          className={navItemClass(isToolsRoute)}
        >
          <Wrench size={15} className="shrink-0" />
          {!collapsed && (
            <>
              <span className="flex-1 truncate text-left">{t.atomicTools.title}</span>
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
                  <Link
                    to="/tools"
                    aria-current={currentPath === '/tools' ? 'page' : undefined}
                    className={cn(
                      'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[12px] font-medium transition-all',
                      currentPath === '/tools'
                        ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                        : 'text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#374151]',
                    )}
                  >
                    <Wrench size={13} className="shrink-0" />
                    <span className="truncate">{t.atomicJobs.library}</span>
                  </Link>
                  {toolNavItems.map(({ to, label, icon: Icon }) => {
                    const isActive = currentPath === to
                  return (
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
                  )
                })}
              </div>
            </div>
          </div>
        )}

        {/* Works library (before Character library to reflect data flow:
            create / curate works first, then characters belong to them). */}
        {(() => {
          const { to, label, icon: Icon, isActive } = worksLibraryNavItem
          return (
            <Link
              key={to}
              to={to}
              data-testid="sidebar-link-works-library"
              aria-current={isActive ? 'page' : undefined}
              title={collapsed ? label : undefined}
              aria-label={collapsed ? label : undefined}
              className={navItemClass(isActive)}
            >
              <Icon size={15} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          )
        })()}

        {/* Character library */}
        {(() => {
          const { to, label, icon: Icon, isActive } = characterLibraryNavItem
          return (
            <Link
              key={to}
              to={to}
              data-testid="sidebar-link-character-library"
              aria-current={isActive ? 'page' : undefined}
              title={collapsed ? label : undefined}
              aria-label={collapsed ? label : undefined}
              className={navItemClass(isActive)}
            >
              <Icon size={15} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          )
        })()}

        {/* Settings */}
        {(() => {
          const { to, label, icon: Icon, isActive } = settingsNavItem
          return (
            <Link
              key={to}
              to={to}
              aria-current={isActive ? 'page' : undefined}
              title={collapsed ? label : undefined}
              aria-label={collapsed ? label : undefined}
              className={navItemClass(isActive)}
            >
              <Icon size={15} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          )
        })()}
      </nav>

      {/* Footer */}
      <div
        className={cn(
          'flex items-center border-t border-[#f3f4f6] py-2.5',
          collapsed ? 'justify-center px-[10px]' : 'justify-between px-4',
        )}
      >
        {!collapsed && <div className="text-[11px] text-[#d1d5db] font-medium">v0.1.0</div>}
        {onToggle && (
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
