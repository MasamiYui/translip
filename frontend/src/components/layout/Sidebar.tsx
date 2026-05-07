import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  AudioLines,
  ChevronDown,
  Clapperboard,
  Cpu,
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
  Settings,
  Wrench,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'

function normalizePathname(pathname: string) {
  if (pathname === '/') return pathname
  return pathname.replace(/\/+$/, '')
}

interface SidebarProps {
  collapsed?: boolean
  onToggle?: () => void
}

export function Sidebar({ collapsed = false, onToggle }: SidebarProps = {}) {
  const { t } = useI18n()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const currentPath = normalizePathname(pathname)
  const isNewTaskRoute = currentPath === '/tasks/new' || currentPath.startsWith('/tasks/new/')
  const isToolsRoute = currentPath === '/tools' || currentPath.startsWith('/tools/')
  const [toolsExpanded, setToolsExpanded] = useState(isToolsRoute)

  const navItems = [
    {
      to: '/',
      label: t.nav.dashboard,
      icon: LayoutDashboard,
      isActive: currentPath === '/',
    },
    {
      to: '/tasks',
      label: t.nav.tasks,
      icon: ListChecks,
      isActive:
        currentPath === '/tasks' || (currentPath.startsWith('/tasks/') && !isNewTaskRoute),
    },
    {
      to: '/tasks/new',
      label: t.nav.newTask,
      icon: PlusCircle,
      isActive: isNewTaskRoute,
    },
    {
      to: '/settings',
      label: t.nav.settings,
      icon: Settings,
      isActive: currentPath === '/settings',
    },
  ]

  const toolNavItems = [
    { to: '/tools/separation', label: t.atomicTools.tools.separation, icon: AudioLines },
    { to: '/tools/mixing', label: t.atomicTools.tools.mixing, icon: Music },
    { to: '/tools/transcription', label: t.atomicTools.tools.transcription, icon: MessageSquareText },
    { to: '/tools/translation', label: t.atomicTools.tools.translation, icon: Languages },
    { to: '/tools/tts', label: t.atomicTools.tools.tts, icon: Mic },
    { to: '/tools/probe', label: t.atomicTools.tools.probe, icon: ScanSearch },
    { to: '/tools/muxing', label: t.atomicTools.tools.muxing, icon: Clapperboard },
  ]
  const activeNavClass =
    'bg-white text-blue-700 ring-1 ring-blue-100 shadow-[0_10px_24px_-20px_rgba(37,99,235,0.55)]'

  const asideWidth = collapsed ? 'w-[56px]' : 'w-[220px]'

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 flex h-full flex-col border-r border-slate-200/80 bg-[#F5F7FB] transition-[width] duration-200 ease-out',
        asideWidth,
      )}
    >
      {/* Logo area */}
      <div
        data-ui-sidebar-brand=""
        className={cn(
          'flex h-16 items-center gap-3 border-b border-slate-200/80',
          collapsed ? 'justify-center px-0' : 'px-5',
        )}
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-[0_12px_24px_-18px_rgba(37,99,235,0.85)]">
          <Cpu size={16} className="text-white" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold leading-tight text-slate-900">
              Translip
            </div>
            <div className="truncate text-xs leading-tight text-slate-500">{t.nav.subtitle}</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav
        className={cn('flex-1 space-y-1 py-4', collapsed ? 'px-2' : 'px-3')}
      >
        {navItems.map(({ to, label, icon: Icon, isActive }) => (
          <Link
            key={to}
            to={to}
            aria-current={isActive ? 'page' : undefined}
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            className={cn(
              'flex items-center rounded-xl text-sm font-medium transition-colors',
              collapsed
                ? 'h-10 w-10 justify-center'
                : 'gap-3 px-3 py-2.5',
              isActive ? activeNavClass : 'text-slate-600 hover:bg-white hover:text-slate-900',
            )}
          >
            <Icon size={16} />
            {!collapsed && label}
          </Link>
        ))}

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
            if (!isToolsRoute) {
              navigate('/tools')
            }
          }}
          className={cn(
            'flex items-center rounded-xl text-sm font-medium transition-colors',
            collapsed
              ? 'h-10 w-10 justify-center'
              : 'w-full gap-3 px-3 py-2.5',
            isToolsRoute ? activeNavClass : 'text-slate-600 hover:bg-white hover:text-slate-900',
          )}
        >
          <Wrench size={16} />
          {!collapsed && (
            <>
              {t.atomicTools.title}
              <ChevronDown
                size={14}
                className={cn('ml-auto transition-transform', toolsExpanded && 'rotate-180')}
              />
            </>
          )}
        </button>

        {!collapsed && (
          <div
            aria-hidden={!toolsExpanded}
            className={cn(
              'grid transition-[grid-template-rows,opacity,margin] duration-200 ease-out',
              toolsExpanded ? 'mt-1 grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0',
            )}
          >
            <div className="overflow-hidden">
              <div className="ml-4 space-y-1 border-l border-slate-200 pl-3 pb-1">
                {toolNavItems.map(({ to, label, icon: Icon }) => {
                  const isActive = currentPath === to
                  return (
                    <Link
                      key={to}
                      to={to}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(
                        'flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-colors',
                        isActive
                          ? 'bg-white text-blue-700 ring-1 ring-blue-100 shadow-sm'
                          : 'text-slate-500 hover:bg-white hover:text-slate-900',
                      )}
                    >
                      <Icon size={14} />
                      {label}
                    </Link>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </nav>

      {/* Footer */}
      <div
        className={cn(
          'flex items-center border-t border-slate-200/80 py-3',
          collapsed ? 'justify-center px-2' : 'justify-between px-5',
        )}
      >
        {!collapsed && <div className="text-xs text-slate-400">v0.1.0</div>}
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            title={collapsed ? t.nav.expandSidebar : t.nav.collapseSidebar}
            aria-label={collapsed ? t.nav.expandSidebar : t.nav.collapseSidebar}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-white hover:text-slate-700"
          >
            {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
        )}
      </div>
    </aside>
  )
}
