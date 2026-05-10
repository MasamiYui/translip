import { useState } from 'react'
import { Check } from 'lucide-react'
import { useI18n } from '../../../i18n/useI18n'
import { COLOR_SWATCHES, normalizeHex } from './presets'

export interface ColorSwatchPickerProps {
  value: string
  onChange: (value: string) => void
  dataTestId?: string
  allowClear?: boolean
}

export function ColorSwatchPicker({
  value,
  onChange,
  dataTestId,
  allowClear = true,
}: ColorSwatchPickerProps) {
  const { t } = useI18n()
  const normalized = normalizeHex(value)
  const isPreset = normalized
    ? COLOR_SWATCHES.some(s => s.value === normalized)
    : false
  const [customOpen, setCustomOpen] = useState(!!normalized && !isPreset)

  function handlePick(hex: string) {
    setCustomOpen(false)
    onChange(hex === normalized ? '' : hex)
  }

  return (
    <div className="flex flex-col gap-2" data-testid={dataTestId}>
      <div className="flex flex-wrap items-center gap-1.5">
        {COLOR_SWATCHES.map(swatch => {
          const active = !customOpen && normalized === swatch.value
          return (
            <button
              key={swatch.key}
              type="button"
              data-testid={`color-swatch-${swatch.key}`}
              onClick={() => handlePick(swatch.value)}
              title={t.characterLibrary.color.swatchNames[swatch.key]}
              aria-label={t.characterLibrary.color.swatchNames[swatch.key]}
              className={
                active
                  ? 'flex h-7 w-7 items-center justify-center rounded-full ring-2 ring-offset-2 ring-[#3b5bdb] transition'
                  : 'h-7 w-7 rounded-full border border-white shadow-sm transition hover:scale-110'
              }
              style={{ backgroundColor: swatch.value }}
            >
              {active && <Check size={14} className="text-white drop-shadow" />}
            </button>
          )
        })}
        <button
          type="button"
          data-testid="color-swatch-custom"
          onClick={() => setCustomOpen(open => !open)}
          className={
            customOpen
              ? 'inline-flex h-7 items-center gap-1 rounded-full border border-dashed border-[#3b5bdb] bg-[#3b5bdb]/10 px-2.5 text-[11px] font-semibold text-[#3b5bdb]'
              : 'inline-flex h-7 items-center gap-1 rounded-full border border-dashed border-[#e5e7eb] bg-white px-2.5 text-[11px] font-semibold text-[#6b7280] transition-all hover:border-[#3b5bdb]/50 hover:text-[#3b5bdb]'
          }
        >
          ⊕ {t.characterLibrary.color.customToggle}
        </button>
        {allowClear && normalized && (
          <button
            type="button"
            data-testid="color-swatch-clear"
            onClick={() => {
              setCustomOpen(false)
              onChange('')
            }}
            className="inline-flex h-7 items-center rounded-full border border-[#e5e7eb] bg-white px-2.5 text-[11px] font-semibold text-[#6b7280] transition-all hover:border-rose-200 hover:text-rose-600"
          >
            {t.characterLibrary.color.clear}
          </button>
        )}
      </div>
      {customOpen && (
        <div className="flex items-center gap-2">
          <input
            data-testid="color-swatch-custom-input"
            type="color"
            value={normalized || '#94a3b8'}
            onChange={event => onChange(event.target.value)}
            className="h-9 w-14 cursor-pointer rounded-lg border border-[#e5e7eb] bg-white p-0.5"
          />
          <input
            data-testid="color-swatch-custom-hex"
            type="text"
            value={normalized || ''}
            onChange={event => onChange(event.target.value)}
            placeholder="#3b5bdb"
            className="w-32 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
          />
        </div>
      )}
    </div>
  )
}
