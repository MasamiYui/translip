import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Monitor, CheckCircle, AlertCircle } from 'lucide-react'
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

  const heightClass = workbench ? 'h-12' : 'h-16'
  const pillPad = workbench ? 'px-2 py-0.5' : 'px-2.5 py-1'
  const sidebarOffsetStyle = { '--sidebar-offset': `${sidebarOffset}px` } as CSSProperties

  return (
    <header
      style={sidebarOffsetStyle}
      className={`fixed top-0 right-0 left-0 md:left-[var(--sidebar-offset)] ${heightClass} bg-white border-b border-slate-200 flex items-center justify-between px-4 sm:px-6 z-30 transition-[left] duration-200 ease-out`}
    >
      <div />
      <div className="flex min-w-0 items-center gap-2 sm:gap-4">
        <div
          className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1"
          aria-label={t.header.languageSwitcherLabel}
          title={t.header.languageSwitcherLabel}
        >
          <button
            type="button"
            onClick={() => setLocale('zh-CN')}
            className={`rounded-lg ${pillPad} text-xs font-medium transition-colors ${
              locale === 'zh-CN'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            中文
          </button>
          <button
            type="button"
            onClick={() => setLocale('en-US')}
            className={`rounded-lg ${pillPad} text-xs font-medium transition-colors ${
              locale === 'en-US'
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            EN
          </button>
        </div>
        {sysInfo && (
          <>
            <div className="hidden items-center gap-1.5 text-sm text-slate-600 sm:flex">
              <Monitor size={14} className="text-slate-400" />
              <span>{sysInfo.device}</span>
            </div>
            <div className="hidden items-center gap-1.5 text-sm sm:flex">
              <CheckCircle size={14} className="text-emerald-500" />
              <span className="text-slate-600">{t.header.ready}</span>
            </div>
          </>
        )}
        {!sysInfo && (
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            <AlertCircle size={14} />
            <span>{t.header.connecting}</span>
          </div>
        )}
      </div>
    </header>
  )
}
