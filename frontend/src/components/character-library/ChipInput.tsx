import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from 'react'
import { X } from 'lucide-react'

export interface ChipInputProps {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  dataTestId?: string
  ariaLabel?: string
  removeLabel?: string
  maxLength?: number
}

const SPLIT_RE = /[,，\n\t]+/

function splitDraft(raw: string): string[] {
  return raw
    .split(SPLIT_RE)
    .map(s => s.trim())
    .filter(Boolean)
}

export function ChipInput({
  value,
  onChange,
  placeholder,
  dataTestId,
  ariaLabel,
  removeLabel,
  maxLength,
}: ChipInputProps) {
  const [draft, setDraft] = useState('')
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function commit(parts: string[]) {
    if (!parts.length) return
    const next = [...value]
    for (const p of parts) {
      const clean = maxLength ? p.slice(0, maxLength) : p
      if (clean && !next.includes(clean)) next.push(clean)
    }
    if (next.length !== value.length) onChange(next)
  }

  function flushDraft() {
    const parts = splitDraft(draft)
    if (parts.length) {
      commit(parts)
      setDraft('')
    } else if (draft !== '') {
      setDraft('')
    }
  }

  function removeAt(index: number) {
    const next = value.filter((_, i) => i !== index)
    onChange(next)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault()
      flushDraft()
      return
    }
    if (event.key === 'Tab' && draft.trim()) {
      event.preventDefault()
      flushDraft()
      return
    }
    if (event.key === 'Backspace' && draft === '' && value.length > 0) {
      event.preventDefault()
      removeAt(value.length - 1)
      return
    }
  }

  function handleChange(raw: string) {
    if (SPLIT_RE.test(raw)) {
      const parts = splitDraft(raw)
      commit(parts)
      setDraft('')
      return
    }
    setDraft(raw)
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const text = event.clipboardData.getData('text')
    if (!text) return
    if (SPLIT_RE.test(text)) {
      event.preventDefault()
      commit(splitDraft(text))
      setDraft('')
    }
  }

  function handleContainerMouseDown(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget) {
      event.preventDefault()
      inputRef.current?.focus()
    }
  }

  const showPlaceholder = value.length === 0 && draft === ''
  const containerClass = focused
    ? 'flex w-full flex-wrap items-center gap-1.5 rounded-lg border border-[#3b5bdb] bg-white px-2 py-1.5 text-sm outline-none ring-2 ring-[#3b5bdb]/20 transition-all'
    : 'flex w-full flex-wrap items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-2 py-1.5 text-sm outline-none transition-all hover:border-slate-300'

  return (
    <div
      className={containerClass}
      data-testid={dataTestId}
      onMouseDown={handleContainerMouseDown}
      role="group"
      aria-label={ariaLabel}
    >
      {value.map((chip, index) => (
        <span
          key={`${chip}-${index}`}
          data-testid={dataTestId ? `${dataTestId}-chip-${index}` : undefined}
          className="inline-flex items-center gap-1 rounded-md bg-[#3b5bdb]/10 px-2 py-0.5 text-xs font-medium text-[#3b5bdb]"
        >
          <span className="max-w-[160px] truncate">{chip}</span>
          <button
            type="button"
            data-testid={dataTestId ? `${dataTestId}-chip-remove-${index}` : undefined}
            onClick={() => removeAt(index)}
            aria-label={removeLabel ? `${removeLabel}: ${chip}` : `remove ${chip}`}
            className="inline-flex h-4 w-4 items-center justify-center rounded-sm text-[#3b5bdb]/70 transition-all hover:bg-[#3b5bdb]/20 hover:text-[#3b5bdb]"
          >
            <X size={10} />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        type="text"
        data-testid={dataTestId ? `${dataTestId}-input` : undefined}
        value={draft}
        placeholder={showPlaceholder ? placeholder : ''}
        onChange={event => handleChange(event.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false)
          flushDraft()
        }}
        className="min-w-[80px] flex-1 border-0 bg-transparent px-1 py-0.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-0"
      />
    </div>
  )
}
