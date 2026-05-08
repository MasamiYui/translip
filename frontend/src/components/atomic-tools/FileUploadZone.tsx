import { UploadCloud } from 'lucide-react'
import type { FileUploadResponse } from '../../types/atomic-tools'

interface FileUploadZoneProps {
  label: string
  hint: string
  accept: string
  value: FileUploadResponse | null
  onFileSelected: (file: File) => Promise<void> | void
  disabled?: boolean
}

export function FileUploadZone({
  label,
  hint,
  accept,
  value,
  onFileSelected,
  disabled = false,
}: FileUploadZoneProps) {
  const inputId = `upload-${label.replace(/\s+/g, '-').toLowerCase()}`

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="block text-sm font-semibold text-[#374151]">
        {label}
      </label>
      <label
        htmlFor={inputId}
        className="flex min-h-[120px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-[#d1d5db] bg-[#fafafa] px-4 py-6 text-center transition-all hover:border-[#3b5bdb]/50 hover:bg-[#f0f3ff]/60"
      >
        <UploadCloud size={20} className={`mb-2.5 ${value ? 'text-[#3b5bdb]' : 'text-[#9ca3af]'}`} />
        <div className={`text-sm font-semibold ${value ? 'text-[#3b5bdb]' : 'text-[#374151]'}`}>
          {value ? value.filename : label}
        </div>
        <div className="mt-1 text-xs text-[#9ca3af]">{hint}</div>
      </label>
      <input
        id={inputId}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        aria-label={label}
        onChange={event => {
          const file = event.target.files?.[0]
          if (file) {
            void onFileSelected(file)
          }
        }}
      />
    </div>
  )
}
