import { useEffect, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { useI18n } from '../../../i18n/useI18n'
import {
  COVER_ICON_GROUPS,
  type CoverGroupKey,
  DEFAULT_COLOR,
  gradientBackground,
  normalizeHex,
} from './presets'

export interface CoverIconPickerProps {
  value: string
  onChange: (value: string) => void
  color: string
  dataTestId?: string
}

const GROUP_ORDER: CoverGroupKey[] = ['media', 'genre', 'object']

export function CoverIconPicker({
  value,
  onChange,
  color,
  dataTestId,
}: CoverIconPickerProps) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const resolved = normalizeHex(color) || DEFAULT_COLOR

  useEffect(() => {
    if (!open) return
    function handleClick(event: MouseEvent) {
      if (!rootRef.current) return
      if (!rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  function handlePick(emoji: string) {
    onChange(emoji === value ? '' : emoji)
    setOpen(false)
  }

  return (
    <div className="relative" ref={rootRef} data-testid={dataTestId}>
      <button
        type="button"
        data-testid="cover-picker-trigger"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t.characterLibrary.cover.triggerAria}
        className={
          open
            ? 'flex w-full items-center gap-2.5 rounded-lg border border-[#3b5bdb] bg-white px-3 py-2 text-left text-sm outline-none ring-2 ring-[#3b5bdb]/20 transition-all'
            : 'flex w-full items-center gap-2.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-left text-sm outline-none transition-all hover:border-slate-300 focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20'
        }
      >
        <span
          className="inline-flex h-6 w-9 flex-none items-center justify-center rounded-md text-sm"
          style={{ background: gradientBackground(resolved) }}
        >
          {value || '🎬'}
        </span>
        <span className="flex-1 truncate text-xs text-slate-500">
          {value
            ? t.characterLibrary.cover.gradientHint
            : t.characterLibrary.cover.label}
        </span>
        <ChevronDown
          size={14}
          className={
            open
              ? 'flex-none text-slate-500 transition-transform rotate-180'
              : 'flex-none text-slate-400 transition-transform'
          }
        />
      </button>

      {open && (
        <div
          data-testid="cover-picker-panel"
          className="absolute left-0 top-full z-30 mt-1 w-[320px] rounded-xl border border-[#e5e7eb] bg-white p-3 shadow-[0_8px_24px_rgba(0,0,0,.12)]"
        >
          <div className="mb-2 flex items-center justify-between">
            <div className="text-xs font-semibold text-slate-700">
              {t.characterLibrary.cover.label}
            </div>
            <button
              type="button"
              data-testid="cover-picker-close"
              onClick={() => setOpen(false)}
              className="rounded-lg p-1 text-slate-400 transition-all hover:bg-[#f3f4f6] hover:text-[#374151]"
            >
              <X size={14} />
            </button>
          </div>

          <div
            data-testid="cover-picker-preview"
            className="mb-3 flex h-20 w-full items-center justify-center rounded-lg text-3xl"
            style={{ background: gradientBackground(resolved) }}
          >
            {value || '🎬'}
          </div>

          <div className="max-h-[240px] space-y-3 overflow-y-auto pr-1">
            {GROUP_ORDER.map(groupKey => (
              <div key={groupKey}>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {t.characterLibrary.cover.groups[groupKey]}
                </div>
                <div className="grid grid-cols-7 gap-1">
                  {COVER_ICON_GROUPS[groupKey].map(emoji => {
                    const active = emoji === value
                    return (
                      <button
                        key={emoji}
                        type="button"
                        data-testid={`cover-icon-${emoji}`}
                        onClick={() => handlePick(emoji)}
                        className={
                          active
                            ? 'flex h-8 w-8 items-center justify-center rounded-md bg-[#3b5bdb]/10 text-lg ring-1 ring-[#3b5bdb]'
                            : 'flex h-8 w-8 items-center justify-center rounded-md text-lg transition hover:bg-slate-100'
                        }
                      >
                        {emoji}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>

          {value && (
            <div className="mt-2 flex justify-end border-t border-[#e5e7eb] pt-2">
              <button
                type="button"
                data-testid="cover-clear"
                onClick={() => handlePick(value)}
                className="text-[11px] font-semibold text-[#6b7280] transition-all hover:text-rose-600"
              >
                {t.characterLibrary.cover.clear}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
