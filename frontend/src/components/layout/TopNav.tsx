import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  ChevronDown,
  Monitor,
  MoreHorizontal,
  PanelLeft,
  PanelTop,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/utils'
import { useI18n } from '../../i18n/useI18n'
import { systemApi } from '../../api/config'
import { shortDeviceLabel } from './deviceLabel'
import { LanguageToggle } from './LanguageToggle'
import {
  useNavConfig,
  type NavSimpleItem,
  type NavSubItem,
} from './navConfig'
import type { LayoutMode } from './MainLayout'

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

interface TopDropdownProps {
  label: string
  icon: LucideIcon
  active: boolean
  items: NavSubItem[]
  ariaLabel?: string
  renderTrigger?: 'label' | 'icon-only'
}

function TopDropdown({ label, icon: Icon, active, items, ariaLabel, renderTrigger = 'label' }: TopDropdownProps) {
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
        aria-label={ariaLabel}
        title={renderTrigger === 'icon-only' ? (ariaLabel ?? label) : undefined}
        onClick={openNow}
        onFocus={openNow}
        className={topItemClass(active)}
      >
        <Icon size={15} className="shrink-0" />
        {renderTrigger === 'label' && <span>{label}</span>}
        <ChevronDown
          size={13}
          className={cn('shrink-0 transition-transform duration-150', open && 'rotate-180')}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 pt-1 md:left-0 md:right-auto"
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

type NavSlot =
  | { kind: 'link'; key: string; to: string; label: string; icon: LucideIcon; isActive: boolean; testId?: string; external?: boolean }
  | { kind: 'dropdown'; key: string; label: string; icon: LucideIcon; active: boolean; items: NavSubItem[] }

interface MoreMenuProps {
  label: string
  slots: NavSlot[]
}

function MoreMenu({ label, slots }: MoreMenuProps) {
  const [open, setOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement | null>(null)
  const closeTimer = useRef<number | null>(null)

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

  useEffect(() => {
    return () => {
      if (closeTimer.current) window.clearTimeout(closeTimer.current)
    }
  }, [])

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

  const anyActive = slots.some((s) => (s.kind === 'link' ? s.isActive : s.active))

  return (
    <div
      ref={wrapperRef}
      className="relative"
      data-testid="topnav-more"
      onMouseEnter={openNow}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={openNow}
        onFocus={openNow}
        className={topItemClass(anyActive)}
      >
        <MoreHorizontal size={15} className="shrink-0" />
        <span>{label}</span>
        <ChevronDown
          size={13}
          className={cn('shrink-0 transition-transform duration-150', open && 'rotate-180')}
        />
      </button>

      {open && (
        <div
          role="menu"
          aria-label={label}
          className="absolute right-0 top-full z-50 pt-1"
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        >
          <div className="min-w-[220px] max-h-[70vh] overflow-y-auto rounded-lg border border-[#e5e7eb] bg-white p-1 shadow-lg">
            {slots.map((slot) => {
              if (slot.kind === 'link') {
                const { to, label: itemLabel, icon: ItemIcon, isActive, external } = slot
                if (external) {
                  return (
                    <a
                      key={slot.key}
                      href={to}
                      target="_blank"
                      rel="noopener noreferrer"
                      role="menuitem"
                      onClick={() => setOpen(false)}
                      className={cn(
                        'flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] font-medium transition-colors',
                        'text-[#4b5563] hover:bg-[#f3f4f6] hover:text-[#111827]',
                      )}
                    >
                      <ItemIcon size={13} className="shrink-0" />
                      <span className="truncate">{itemLabel}</span>
                    </a>
                  )
                }
                return (
                  <Link
                    key={slot.key}
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
                )
              }
              const { label: groupLabel, icon: GroupIcon, items: groupItems } = slot
              return (
                <div key={slot.key} className="mt-0.5 first:mt-0">
                  <div className="flex items-center gap-2 px-2.5 pt-1.5 pb-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-[#9ca3af]">
                    <GroupIcon size={12} className="shrink-0" />
                    <span className="truncate">{groupLabel}</span>
                  </div>
                  {groupItems.map(({ to, label: itemLabel, icon: ItemIcon, isActive }) => (
                    <Link
                      key={to}
                      to={to}
                      role="menuitem"
                      aria-current={isActive ? 'page' : undefined}
                      onClick={() => setOpen(false)}
                      className={cn(
                        'ml-2 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] font-medium transition-colors',
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
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

interface TopNavProps {
  height?: number
  layoutMode?: LayoutMode
  onToggleLayoutMode?: () => void
}

const TOPNAV_TEST_ID_KEYS = new Set([
  'works-library',
  'character-library',
  'evaluation',
  'blog',
  'api-docs',
  'lab',
])

function resolveTopNavTestId(key: string): string | undefined {
  return TOPNAV_TEST_ID_KEYS.has(key) ? `topnav-link-${key}` : undefined
}

function simpleItemToSlot(item: NavSimpleItem): NavSlot {
  return {
    kind: 'link',
    key: item.key,
    to: item.to,
    label: item.label,
    icon: item.icon,
    isActive: item.isActive,
    testId: resolveTopNavTestId(item.key),
    external: item.external,
  }
}

export function TopNav({ height = 60, layoutMode = 'top', onToggleLayoutMode }: TopNavProps = {}) {
  const { t } = useI18n()
  const nav = useNavConfig()
  const { data: sysInfo } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
    staleTime: 30000,
    retry: 1,
  })

  // Unified ordered nav-slot list driving both inline rendering and overflow.
  const slots: NavSlot[] = useMemo(() => {
    return [
      simpleItemToSlot(nav.dashboard),
      {
        kind: 'dropdown',
        key: 'task-center',
        label: nav.taskCenter.label,
        icon: nav.taskCenter.icon,
        active: nav.taskCenter.isActive,
        items: nav.taskCenter.items,
      },
      {
        kind: 'dropdown',
        key: 'tools',
        label: nav.tools.label,
        icon: nav.tools.icon,
        active: nav.tools.isActive,
        items: nav.tools.items,
      },
      simpleItemToSlot(nav.worksLibrary),
      simpleItemToSlot(nav.characterLibrary),
      simpleItemToSlot(nav.evaluation),
      simpleItemToSlot(nav.blog),
      simpleItemToSlot(nav.apiDocs),
      simpleItemToSlot(nav.lab),
      simpleItemToSlot(nav.settings),
    ]
  }, [nav])

  // Overflow detection: measure inline-slot widths via a hidden mirror row,
  // then compute how many fit in the live container, reserving space for More.
  const itemsContainerRef = useRef<HTMLDivElement | null>(null)
  const measureRowRef = useRef<HTMLDivElement | null>(null)
  const [visibleCount, setVisibleCount] = useState<number>(slots.length)
  const MORE_BUTTON_RESERVE = 100 // approximate px width of the More trigger

  useLayoutEffect(() => {
    const container = itemsContainerRef.current
    const measureRow = measureRowRef.current
    if (!container || !measureRow) return

    const recompute = () => {
      const available = container.clientWidth
      const widths = Array.from(measureRow.children).map((c) => (c as HTMLElement).offsetWidth)
      if (widths.length === 0) return
      let total = 0
      let fit = 0
      for (let i = 0; i < widths.length; i++) {
        total += widths[i] + 2 // gap-0.5 (≈2px)
        if (total <= available) fit = i + 1
        else break
      }
      let next = fit
      if (fit < widths.length) {
        // Reserve room for the More button; trim until everything plus More fits.
        while (next > 0) {
          const widthIfShown = widths.slice(0, next).reduce((s, w) => s + w + 2, 0) + MORE_BUTTON_RESERVE
          if (widthIfShown <= available) break
          next -= 1
        }
      }
      setVisibleCount((prev) => (prev === next ? prev : next))
    }

    recompute()
    const ro = new ResizeObserver(recompute)
    ro.observe(container)
    return () => ro.disconnect()
  }, [slots])

  const overflowSlots = visibleCount < slots.length ? slots.slice(visibleCount) : []
  const inlineSlots = visibleCount < slots.length ? slots.slice(0, visibleCount) : slots

  function renderSlot(slot: NavSlot, keySuffix = '') {
    if (slot.kind === 'link') {
      const { to, label, icon: Icon, isActive, testId, external } = slot
      if (external) {
        return (
          <a
            key={slot.key + keySuffix}
            href={to}
            target="_blank"
            rel="noopener noreferrer"
            data-testid={testId}
            className={topItemClass(false)}
          >
            <Icon size={15} className="shrink-0" />
            <span>{label}</span>
          </a>
        )
      }
      return (
        <Link
          key={slot.key + keySuffix}
          to={to}
          data-testid={testId}
          aria-current={isActive ? 'page' : undefined}
          className={topItemClass(isActive)}
        >
          <Icon size={15} className="shrink-0" />
          <span>{label}</span>
        </Link>
      )
    }
    return (
      <TopDropdown
        key={slot.key + keySuffix}
        label={slot.label}
        icon={slot.icon}
        active={slot.active}
        items={slot.items}
      />
    )
  }

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

      <div
        ref={itemsContainerRef}
        className="relative flex flex-1 items-center gap-0.5 min-w-0 overflow-x-clip overflow-y-visible"
      >
        {/* Live (visible) row */}
        {inlineSlots.map((slot) => renderSlot(slot))}
        {overflowSlots.length > 0 && <MoreMenu label={t.nav.moreMenu} slots={overflowSlots} />}

        {/* Hidden measurement mirror: same items, never visible, never scroll. */}
        <div
          ref={measureRowRef}
          aria-hidden="true"
          className="pointer-events-none invisible absolute left-0 top-0 flex items-center gap-0.5"
          style={{ visibility: 'hidden' }}
        >
          {slots.map((slot) => renderSlot(slot, '__measure'))}
        </div>
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

        <LanguageToggle />

        {onToggleLayoutMode && (() => {
          const isTopMode = layoutMode === 'top'
          const switchTitle = isTopMode ? t.nav.layoutModeLeft : t.nav.layoutModeTop
          return (
            <button
              type="button"
              onClick={onToggleLayoutMode}
              title={switchTitle}
              aria-label={switchTitle}
              data-testid="toggle-layout-mode"
              className="flex h-7 w-7 items-center justify-center rounded-md border border-[#e5e7eb] bg-[#f9fafb] text-[#6b7280] transition-colors hover:bg-white hover:text-[#111827]"
            >
              {isTopMode ? <PanelLeft size={14} /> : <PanelTop size={14} />}
            </button>
          )
        })()}
      </div>
    </nav>
  )
}
