export interface AtomicToolPrefillFile {
  file_id: string
  filename: string
}

export interface AtomicToolPrefill {
  files?: Record<string, AtomicToolPrefillFile>
  text?: string
  // Initial parameter overrides merged over the target tool's defaults
  // (e.g. preselecting task=ocr-classify when handing OCR events to video-analyze).
  params?: Record<string, string | number | boolean>
}

const PREFIX = 'translip.atomic-tools.prefill'

export function saveAtomicToolPrefill(payload: AtomicToolPrefill): string {
  const key =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`

  window.sessionStorage.setItem(`${PREFIX}.${key}`, JSON.stringify(payload))
  return key
}

export function readAtomicToolPrefill(key: string | null): AtomicToolPrefill | null {
  if (!key) return null
  const raw = window.sessionStorage.getItem(`${PREFIX}.${key}`)
  if (!raw) return null

  try {
    return JSON.parse(raw) as AtomicToolPrefill
  } catch {
    return null
  }
}
