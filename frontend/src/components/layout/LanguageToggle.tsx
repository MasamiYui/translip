import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

interface LanguageToggleProps {
  className?: string
}

export function LanguageToggle({ className }: LanguageToggleProps = {}) {
  const { locale, setLocale, t } = useI18n()
  return (
    <div
      className={cn(
        'flex items-center gap-0.5 rounded-lg border border-[#e5e7eb] bg-[#f9fafb] p-0.5',
        className,
      )}
      role="group"
      aria-label={t.header.languageSwitcherLabel}
    >
      <button
        type="button"
        onClick={() => setLocale('zh-CN')}
        aria-pressed={locale === 'zh-CN'}
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
        aria-pressed={locale === 'en-US'}
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
  )
}
