import { useEffect, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { useI18n } from '../../../i18n/useI18n'
import {
  AVATAR_EMOJI_GROUPS,
  type AvatarGroupKey,
  DEFAULT_COLOR,
  firstGlyphOf,
  hexWithAlpha,
  normalizeHex,
} from './presets'

export interface EmojiAvatarPickerProps {
  value: string
  onChange: (value: string) => void
  color: string
  nameForFallback: string
  dataTestId?: string
}

const GROUP_ORDER: AvatarGroupKey[] = ['people', 'character', 'animal', 'symbol']

export function EmojiAvatarPicker({
  value,
  onChange,
  color,
  nameForFallback,
  dataTestId,
}: EmojiAvatarPickerProps) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'emoji' | 'letter'>('emoji')
  const rootRef = useRef<HTMLDivElement>(null)

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

  const resolvedColor = normalizeHex(color) || DEFAULT_COLOR
  const hasEmoji = value.trim().length > 0
  const fallbackGlyph = firstGlyphOf(nameForFallback)
  const displayGlyph = hasEmoji ? value : fallbackGlyph

  function handlePick(emoji: string) {
    onChange(emoji === value ? '' : emoji)
    setOpen(false)
  }

  return (
    <div className="relative" ref={rootRef} data-testid={dataTestId}>
      <button
        type="button"
        data-testid="avatar-picker-trigger"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t.characterLibrary.avatar.triggerAria}
        className={
          open
            ? 'flex w-full items-center gap-2.5 rounded-lg border border-[#3b5bdb] bg-white px-3 py-2 text-left text-sm outline-none ring-2 ring-[#3b5bdb]/20 transition-all'
            : 'flex w-full items-center gap-2.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-left text-sm outline-none transition-all hover:border-slate-300 focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20'
        }
      >
        <span
          className="inline-flex h-6 w-6 flex-none items-center justify-center rounded-full text-sm font-semibold"
          style={{
            backgroundColor: hexWithAlpha(resolvedColor, 0.15),
            color: resolvedColor,
          }}
        >
          {displayGlyph}
        </span>
        <span className="flex-1 truncate text-xs text-slate-500">
          {hasEmoji ? t.characterLibrary.avatar.tabs.emoji : t.characterLibrary.avatar.letterHint}
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
          data-testid="avatar-picker-panel"
          className="absolute left-0 top-full z-30 mt-1 w-[320px] rounded-xl border border-[#e5e7eb] bg-white p-3 shadow-[0_8px_24px_rgba(0,0,0,.12)]"
        >
          <div className="mb-2 flex items-center justify-between">
            <div className="flex gap-1 rounded-lg bg-[#f3f4f6] p-0.5">
              <button
                type="button"
                data-testid="avatar-tab-emoji"
                onClick={() => setTab('emoji')}
                className={
                  tab === 'emoji'
                    ? 'rounded-md bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-800 shadow-sm'
                    : 'rounded-md px-2.5 py-1 text-[11px] font-semibold text-[#6b7280] hover:text-[#374151]'
                }
              >
                {t.characterLibrary.avatar.tabs.emoji}
              </button>
              <button
                type="button"
                data-testid="avatar-tab-letter"
                onClick={() => setTab('letter')}
                className={
                  tab === 'letter'
                    ? 'rounded-md bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-800 shadow-sm'
                    : 'rounded-md px-2.5 py-1 text-[11px] font-semibold text-[#6b7280] hover:text-[#374151]'
                }
              >
                {t.characterLibrary.avatar.tabs.letter}
              </button>
            </div>
            <button
              type="button"
              data-testid="avatar-picker-close"
              onClick={() => setOpen(false)}
              className="rounded-lg p-1 text-slate-400 transition-all hover:bg-[#f3f4f6] hover:text-[#374151]"
            >
              <X size={14} />
            </button>
          </div>

          {tab === 'emoji' ? (
            <div className="max-h-[260px] space-y-3 overflow-y-auto pr-1">
              {GROUP_ORDER.map(groupKey => (
                <div key={groupKey}>
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                    {t.characterLibrary.avatar.groups[groupKey]}
                  </div>
                  <div className="grid grid-cols-7 gap-1">
                    {AVATAR_EMOJI_GROUPS[groupKey].map(emoji => {
                      const active = emoji === value
                      return (
                        <button
                          key={emoji}
                          type="button"
                          data-testid={`avatar-emoji-${emoji}`}
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
          ) : (
            <div className="flex flex-col items-center gap-3 py-4">
              <span
                className="inline-flex h-16 w-16 items-center justify-center rounded-full text-2xl font-semibold"
                style={{
                  backgroundColor: hexWithAlpha(resolvedColor, 0.15),
                  color: resolvedColor,
                }}
              >
                {fallbackGlyph}
              </span>
              <p className="text-center text-[11px] text-slate-500">
                {t.characterLibrary.avatar.letterHint}
              </p>
              <button
                type="button"
                data-testid="avatar-letter-apply"
                onClick={() => {
                  onChange('')
                  setOpen(false)
                }}
                className="rounded-lg bg-[#3b5bdb] px-4 py-1.5 text-xs font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
              >
                {t.characterLibrary.actions.save}
              </button>
            </div>
          )}

          {hasEmoji && (
            <div className="mt-2 flex justify-end border-t border-[#e5e7eb] pt-2">
              <button
                type="button"
                data-testid="avatar-clear"
                onClick={() => handlePick(value)}
                className="text-[11px] font-semibold text-[#6b7280] transition-all hover:text-rose-600"
              >
                {t.characterLibrary.avatar.clear}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
