import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Monitor, Zap, AlertCircle } from 'lucide-react'
import { systemApi } from '../../api/config'
import { useI18n } from '../../i18n/useI18n'

interface HeaderProps {
  workbench?: boolean
  sidebarOffset?: number
}

export function Header({ workbench = false, sidebarOffset = 220 }: HeaderProps) {
  const { locale, setLocale, t } = useI18n()
  const { data: sysInfo } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
    staleTime: 30000,
    retry: 1,
  })

  const heightClass = workbench ? 'h-12' : 'h-[60px]'
  const sidebarOffsetStyle = { '--sidebar-offset': `${sidebarOffset}px` } as CSSProperties

  return (
    <header
      style={sidebarOffsetStyle}
      className={`fixed top-0 right-0 left-0 md:left-[var(--sidebar-offset)] ${heightClass} bg-white/90 backdrop-blur-md border-b border-[#f3f4f6] flex items-center justify-between px-5 z-30 transition-[left] duration-200 ease-out`}
    >
      <div />
      <div className="flex items-center gap-3">
        {sysInfo && (
          <div className="hidden items-center gap-1.5 text-xs text-[#6b7280] sm:flex">
            <Monitor size={13} className="text-[#9ca3af]" />
            <span className="font-medium">{sysInfo.device}</span>
          </div>
        )}
        {sysInfo ? (
          <div className="hidden items-center gap-1.5 text-xs sm:flex">
            <Zap size={12} className="text-emerald-500" />
            <span className="text-[#6b7280] font-medium">{t.header.ready}</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-[#9ca3af]">
            <AlertCircle size={12} />
            <span>{t.header.connecting}</span>
          </div>
        )}

        {/* Language switcher */}
        <div
          className="flex items-center gap-0.5 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] p-0.5"
          aria-label={t.header.languageSwitcherLabel}
        >
          <button
            type="button"
            onClick={() => setLocale('zh-CN')}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all ${
              locale === 'zh-CN'
                ? 'bg-white text-[#111827] shadow-sm'
                : 'text-[#9ca3af] hover:text-[#374151]'
            }`}
          >
            中文
          </button>
          <button
            type="button"
            onClick={() => setLocale('en-US')}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition-all ${
              locale === 'en-US'
                ? 'bg-white text-[#111827] shadow-sm'
                : 'text-[#9ca3af] hover:text-[#374151]'
            }`}
          >
            EN
          </button>
        </div>
      </div>
    </header>
  )
}
