import { useState } from 'react'
import { useI18n } from '../../../i18n/useI18n'
import { AGE_BANDS, ageBandKeyFromValue } from './presets'

export interface AgeBandSelectorProps {
  value: string
  onChange: (value: string) => void
  dataTestId?: string
}

export function AgeBandSelector({ value, onChange, dataTestId }: AgeBandSelectorProps) {
  const { t } = useI18n()
  const presetKey = ageBandKeyFromValue(value)
  const isCustom = value.trim().length > 0 && presetKey === null
  const [customMode, setCustomMode] = useState(isCustom)

  function handlePick(newValue: string) {
    setCustomMode(false)
    onChange(newValue === value ? '' : newValue)
  }

  function handleCustomClick() {
    setCustomMode(true)
    if (ageBandKeyFromValue(value)) {
      onChange('')
    }
  }

  const bands = t.characterLibrary.ageBands

  return (
    <div className="flex flex-col gap-2" data-testid={dataTestId}>
      <div className="flex flex-wrap gap-1.5">
        {AGE_BANDS.map(band => {
          const active = !customMode && value === band.value
          return (
            <button
              key={band.key}
              type="button"
              data-testid={`age-band-${band.key}`}
              onClick={() => handlePick(band.value)}
              title={bands.hint[band.key]}
              className={
                active
                  ? 'h-8 rounded-full border border-[#3b5bdb] bg-[#3b5bdb] px-3 text-xs font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)]'
                  : 'h-8 rounded-full border border-[#e5e7eb] bg-white px-3 text-xs font-semibold text-[#6b7280] transition-all hover:border-[#3b5bdb]/40 hover:text-[#3b5bdb]'
              }
            >
              {bands[band.key]}
              <span className="ml-1 text-[10px] opacity-70">
                {bands.hint[band.key]}
              </span>
            </button>
          )
        })}
        <button
          type="button"
          data-testid="age-band-custom"
          onClick={handleCustomClick}
          className={
            customMode
              ? 'h-8 rounded-full border border-dashed border-[#3b5bdb] bg-[#3b5bdb]/10 px-3 text-xs font-semibold text-[#3b5bdb]'
              : 'h-8 rounded-full border border-dashed border-[#e5e7eb] bg-white px-3 text-xs font-semibold text-[#6b7280] transition-all hover:border-[#3b5bdb]/50 hover:text-[#3b5bdb]'
          }
        >
          {bands.custom}
        </button>
      </div>
      {customMode && (
        <input
          data-testid="age-band-custom-input"
          type="text"
          value={value}
          onChange={event => onChange(event.target.value)}
          placeholder={bands.customPlaceholder}
          className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
        />
      )}
    </div>
  )
}
