import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  AudioLines,
  BookOpen,
  BookUser,
  Braces,
  Captions,
  ChevronDown,
  Clapperboard,
  Eraser,
  Gauge,
  Languages,
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  Mic,
  Monitor,
  Music,
  PanelLeft,
  PlusCircle,
  ScanSearch,
  ScanText,
  Settings,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import { atomicToolsApi } from '../../api/atomic-tools'
import { systemApi } from '../../api/config'
import { shortDeviceLabel } from './Header'
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

function TranslipVoiceStemsLogo() {
  return (
    <svg
      role="img"
      aria-label="Translip Voice Stems logo"
      viewBox="0 0 64 64"
      className="h-7 w-7"
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

const topItemBase =
  'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors whitespace-nowrap'

function topItemClass(active: boolean) {
  return cn(
    topItemBase,
    active
      ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
      : 'text-[#4b5563] hover:bg-[#f3f4f6] hover:text-[#111827]',
  )
}

interface DropdownItem {
  to: string
  label: string
  icon: LucideIcon
  isActive: boolean
}

interface TopDropdownProps {
  label: string
  icon: LucideIcon
  active: boolean
  items: DropdownItem[]
}

function TopDropdown({ label, icon: Icon, active, items }: TopDropdownProps) {
  const [open, setOpen] = useState(false)
  const closeTimer = useRef<number | null>(null)
  const wrapperRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    return () => {
      if (closeTimer.current) window.clearTimeout(closeTimer.current)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const onDocPointerDown = (e: PointerEvent) => {
      const node = wrapperRef.current
      if (node && !node.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onDocPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDocPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const scheduleClose = () => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => setOpen(false), 150)
  }
  const cancelClose = () => {
    if (closeTimer.current) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }
  const openNow = () => {
    cancelClose()
    setOpen(true)
  }

  return (
    <div
      ref={wrapperRef}
      className="relative"
      onMouseEnter={openNow}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={openNow}
        onFocus={openNow}
        className={topItemClass(active)}
      >
        <Icon size={15} className="shrink-0" />
        <span>{label}</span>
        <ChevronDown
          size={13}
          className={cn('shrink-0 transition-transform duration-150', open && 'rotate-180')}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full z-50 pt-1"
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        >
          <div className="min-w-[200px] rounded-lg border border-[#e5e7eb] bg-white p-1 shadow-lg">
            {items.map(({ to, label: itemLabel, icon: ItemIcon, isActive }) => (
              <Link
                key={to}
                to={to}
                role="menuitem"
                aria-current={isActive ? 'page' : undefined}
                onClick={() => setOpen(false)}
                className={cn(
                  'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] font-medium transition-colors',
                  isActive
                    ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                    : 'text-[#4b5563] hover:bg-[#f3f4f6] hover:text-[#111827]',
                )}
              >
                <ItemIcon size={13} className="shrink-0" />
                <span className="truncate">{itemLabel}</span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface TopNavProps {
  height?: number
  onToggleLayoutMode?: () => void
}

export function TopNav({ height = 60, onToggleLayoutMode }: TopNavProps = {}) {
  const { t, locale, setLocale } = useI18n()
  const { pathname } = useLocation()
  const currentPath = normalizePathname(pathname)
  const isNewTaskRoute = currentPath === '/tasks/new' || currentPath.startsWith('/tasks/new/')
  const isPipelineTaskRoute =
    currentPath === '/tasks' || (currentPath.startsWith('/tasks/') && !isNewTaskRoute)
  const isAtomicJobsRoute = currentPath === '/tools/jobs' || currentPath.startsWith('/tools/jobs/')
  const isTaskCenterRoute = isPipelineTaskRoute || isNewTaskRoute || isAtomicJobsRoute
  const isToolsRoute =
    currentPath === '/tools' || (currentPath.startsWith('/tools/') && !isAtomicJobsRoute)

  const toolLabels = t.atomicTools.tools as Record<string, string | undefined>
  const { data: tools } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })
  const { data: sysInfo } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
    staleTime: 30000,
    retry: 1,
  })

  const toolNavItems: DropdownItem[] = (tools ?? []).map((tool: ToolInfo) => ({
    to: `/tools/${tool.tool_id}`,
    label: toolLabels[tool.tool_id] ?? (locale === 'zh-CN' ? tool.name_zh : tool.name_en),
    icon: resolveToolIcon(tool.icon),
    isActive: currentPath === `/tools/${tool.tool_id}`,
  }))

  const taskCenterItems: DropdownItem[] = [
    {
      to: '/tasks',
      label: t.nav.pipelineTasks,
      icon: ListChecks,
      isActive: isPipelineTaskRoute,
    },
    {
      to: '/tools/jobs',
      label: t.nav.atomicTasks,
      icon: ListChecks,
      isActive: isAtomicJobsRoute,
    },
    {
      to: '/tasks/new',
      label: t.nav.newPipelineTask,
      icon: PlusCircle,
      isActive: isNewTaskRoute,
    },
  ]

  const toolItems: DropdownItem[] = [
    {
      to: '/tools',
      label: t.atomicJobs.library,
      icon: Wrench,
      isActive: currentPath === '/tools',
    },
    ...toolNavItems,
  ]

  const simpleItems = [
    {
      to: '/',
      label: t.nav.dashboard,
      icon: LayoutDashboard,
      isActive: currentPath === '/',
    },
    {
      to: '/works',
      label: t.nav.worksLibrary,
      icon: Clapperboard,
      isActive: currentPath === '/works',
      testId: 'topnav-link-works-library',
    },
    {
      to: '/character-library',
      label: t.nav.characterLibrary,
      icon: BookUser,
      isActive: currentPath === '/character-library',
      testId: 'topnav-link-character-library',
    },
    {
      to: '/evaluation',
      label: t.nav.evaluation,
      icon: Gauge,
      isActive: currentPath === '/evaluation' || currentPath.startsWith('/evaluation/'),
      testId: 'topnav-link-evaluation',
    },
    {
      to: '/blog',
      label: t.nav.blog,
      icon: BookOpen,
      isActive: currentPath === '/blog' || currentPath.startsWith('/blog/'),
      testId: 'topnav-link-blog',
    },
    {
      to: '/api-docs',
      label: t.nav.apiDocs,
      icon: Braces,
      isActive: currentPath === '/api-docs',
      testId: 'topnav-link-api-docs',
    },
    {
      to: '/settings',
      label: t.nav.settings,
      icon: Settings,
      isActive: currentPath === '/settings',
    },
  ] as const

  return (
    <nav
      data-testid="top-nav"
      style={{ height }}
      className="fixed top-0 left-0 right-0 z-40 flex items-center gap-2 border-b border-[#e5e7eb] bg-white/90 backdrop-blur-md px-5 print:hidden"
    >
      <Link to="/" className="mr-2 flex items-center gap-2 shrink-0">
        <div className="flex h-7 w-7 items-center justify-center overflow-hidden rounded-lg bg-[#d7e7ff]">
          <TranslipVoiceStemsLogo />
        </div>
        <div className="hidden min-w-0 sm:block">
          <div className="truncate text-[13px] font-semibold leading-tight text-[#111827]">
            Translip
          </div>
          <div className="truncate text-[10px] leading-tight text-[#9ca3af]">{t.nav.subtitle}</div>
        </div>
      </Link>

      <div className="flex flex-1 items-center gap-0.5 min-w-0">
        {simpleItems.slice(0, 1).map(({ to, label, icon: Icon, isActive }) => (
          <Link key={to} to={to} aria-current={isActive ? 'page' : undefined} className={topItemClass(isActive)}>
            <Icon size={15} className="shrink-0" />
            <span>{label}</span>
          </Link>
        ))}

        <TopDropdown
          label={t.nav.taskCenter}
          icon={ListChecks}
          active={isTaskCenterRoute}
          items={taskCenterItems}
        />

        <TopDropdown
          label={t.atomicTools.title}
          icon={Wrench}
          active={isToolsRoute}
          items={toolItems}
        />

        {simpleItems.slice(1).map(({ to, label, icon: Icon, isActive, ...rest }) => (
          <Link
            key={to}
            to={to}
            data-testid={'testId' in rest ? rest.testId : undefined}
            aria-current={isActive ? 'page' : undefined}
            className={topItemClass(isActive)}
          >
            <Icon size={15} className="shrink-0" />
            <span>{label}</span>
          </Link>
        ))}
      </div>

      {/* Right utility cluster */}
      <div className="ml-2 flex items-center gap-2.5 shrink-0">
        {sysInfo && (
          <div
            className="hidden items-center gap-1.5 text-xs text-[#6b7280] lg:flex"
            title={sysInfo.device}
          >
            <Monitor size={13} className="text-[#9ca3af]" />
            <span className="font-medium">{shortDeviceLabel(sysInfo.device)}</span>
          </div>
        )}
        {sysInfo ? (
          <div className="hidden items-center gap-1.5 text-xs lg:flex">
            <Zap size={12} className="text-emerald-500" />
            <span className="text-[#6b7280] font-medium">{t.header.ready}</span>
          </div>
        ) : (
          <div className="hidden items-center gap-1.5 text-xs text-[#9ca3af] lg:flex">
            <AlertCircle size={12} />
            <span>{t.header.connecting}</span>
          </div>
        )}

        <div
          className="flex items-center gap-0.5 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] p-0.5"
          aria-label={t.header.languageSwitcherLabel}
        >
          <button
            type="button"
            onClick={() => setLocale('zh-CN')}
            className={cn(
              'rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all',
              locale === 'zh-CN'
                ? 'bg-white text-[#111827] shadow-sm'
                : 'text-[#9ca3af] hover:text-[#374151]',
            )}
          >
            中文
          </button>
          <button
            type="button"
            onClick={() => setLocale('en-US')}
            className={cn(
              'rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all',
              locale === 'en-US'
                ? 'bg-white text-[#111827] shadow-sm'
                : 'text-[#9ca3af] hover:text-[#374151]',
            )}
          >
            EN
          </button>
        </div>

        {onToggleLayoutMode && (
          <button
            type="button"
            onClick={onToggleLayoutMode}
            title={t.nav.layoutModeLeft}
            aria-label={t.nav.layoutModeLeft}
            data-testid="toggle-layout-mode"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-[#e5e7eb] bg-[#f9fafb] text-[#6b7280] transition-colors hover:bg-white hover:text-[#111827]"
          >
            <PanelLeft size={14} />
          </button>
        )}
      </div>
    </nav>
  )
}
