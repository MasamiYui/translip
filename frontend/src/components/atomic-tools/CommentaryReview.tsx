import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clapperboard, Loader2, RotateCcw, Trash2 } from 'lucide-react'
import { atomicToolsApi } from '../../api/atomic-tools'
import { saveAtomicToolPrefill } from '../../lib/atomicToolPrefill'

export interface CommentaryReviewLabels {
  title: string
  hint: string
  loading: string
  error: string
  empty: string
  ostNarration: string
  ostOriginal: string
  narrationPlaceholder: string
  srcLabel: string
  deleteItem: string
  restore: string
  saveAndRender: string
  saving: string
  saveError: string
  itemsLabel: string
}

interface CommentaryItem {
  id: number
  ost: number
  src: number[]
  narration: string
  picture?: string
  story_role?: string
  [key: string]: unknown
}

interface CommentaryDoc {
  meta?: Record<string, unknown>
  plot_analysis?: string
  items: CommentaryItem[]
  [key: string]: unknown
}

/**
 * In-place review editor for a commentary.json: edit each line's narration,
 * toggle narration↔original-sound (OST), or drop clips, then upload the edited
 * script and hand it to the Commentary Render tool (the source video is uploaded
 * there). This is the human-in-the-loop step between script and render.
 */
export function CommentaryReview({
  commentaryUrl,
  labels,
}: {
  commentaryUrl: string
  labels: CommentaryReviewLabels
}) {
  const navigate = useNavigate()
  const [doc, setDoc] = useState<CommentaryDoc | null>(null)
  const [removed, setRemoved] = useState<Record<number, boolean>>({})
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [saving, setSaving] = useState(false)
  const [saveFailed, setSaveFailed] = useState(false)

  useEffect(() => {
    // Status starts at 'loading' (initial state); the parent remounts this via a
    // key when the artifact changes, so no synchronous reset is needed here.
    let cancelled = false
    fetch(commentaryUrl)
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })
      .then((data: CommentaryDoc) => {
        if (cancelled) return
        setDoc(data && Array.isArray(data.items) ? data : { items: [] })
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [commentaryUrl])

  const updateItem = (index: number, patch: Partial<CommentaryItem>) => {
    setDoc(prev =>
      prev ? { ...prev, items: prev.items.map((item, i) => (i === index ? { ...item, ...patch } : item)) } : prev,
    )
  }

  const remainingCount = doc ? doc.items.filter((_, i) => !removed[i]).length : 0

  async function handleSave() {
    if (!doc) return
    setSaving(true)
    setSaveFailed(false)
    try {
      const items = doc.items.filter((_, i) => !removed[i])
      const edited: CommentaryDoc = { ...doc, items }
      const file = new File([JSON.stringify(edited, null, 2)], 'commentary.edited.json', {
        type: 'application/json',
      })
      const uploaded = await atomicToolsApi.upload(file)
      const key = saveAtomicToolPrefill({
        files: { commentary_file: { file_id: uploaded.file_id, filename: uploaded.filename } },
      })
      navigate(`/tools/commentary-render?prefill=${encodeURIComponent(key)}`)
    } catch {
      setSaveFailed(true)
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-[#111827]">{labels.title}</h3>
        {doc && (
          <span className="text-xs text-[#9ca3af]">
            {remainingCount} {labels.itemsLabel}
          </span>
        )}
      </div>
      <p className="mb-4 text-xs leading-5 text-[#6b7280]">{labels.hint}</p>

      {status === 'loading' && (
        <div className="flex items-center gap-2 py-6 text-sm text-[#6b7280]">
          <Loader2 size={15} className="animate-spin" />
          {labels.loading}
        </div>
      )}
      {status === 'error' && <div className="py-6 text-sm text-red-500">{labels.error}</div>}
      {status === 'ready' && doc && doc.items.length === 0 && (
        <div className="py-6 text-sm text-[#9ca3af]">{labels.empty}</div>
      )}

      {status === 'ready' && doc && doc.items.length > 0 && (
        <>
          <div className="space-y-3">
            {doc.items.map((item, index) => {
              const isRemoved = Boolean(removed[index])
              const isOriginal = Number(item.ost) === 1
              const src = Array.isArray(item.src) ? item.src : [0, 0]
              return (
                <div
                  key={`${item.id}-${index}`}
                  className={`rounded-lg border p-3 transition ${
                    isRemoved ? 'border-dashed border-[#e5e7eb] bg-[#f9fafb] opacity-60' : 'border-[#e5e7eb] bg-white'
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="inline-flex overflow-hidden rounded-lg border border-[#e5e7eb] text-xs">
                        {([0, 1] as const).map(ost => {
                          const active = Number(item.ost) === ost
                          return (
                            <button
                              key={ost}
                              type="button"
                              disabled={isRemoved}
                              onClick={() => updateItem(index, { ost })}
                              className={`px-2.5 py-1 font-medium transition ${
                                active ? 'bg-[#3b5bdb] text-white' : 'bg-white text-[#6b7280] hover:bg-[#f0f3ff]'
                              }`}
                            >
                              {ost === 0 ? labels.ostNarration : labels.ostOriginal}
                            </button>
                          )
                        })}
                      </div>
                      <span className="font-mono text-[11px] text-[#9ca3af]">
                        {labels.srcLabel} {Number(src[0]).toFixed(1)}s – {Number(src[1]).toFixed(1)}s
                      </span>
                      {item.story_role && (
                        <span className="rounded-full bg-[#f3f4f6] px-2 py-0.5 text-[11px] text-[#6b7280]">
                          {String(item.story_role)}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setRemoved(prev => ({ ...prev, [index]: !prev[index] }))}
                      className="inline-flex items-center gap-1 text-xs font-medium text-[#9ca3af] transition hover:text-[#374151]"
                    >
                      {isRemoved ? <RotateCcw size={12} /> : <Trash2 size={12} />}
                      {isRemoved ? labels.restore : labels.deleteItem}
                    </button>
                  </div>
                  <textarea
                    rows={2}
                    disabled={isRemoved || isOriginal}
                    value={isOriginal ? '' : String(item.narration ?? '')}
                    placeholder={isOriginal ? labels.ostOriginal : labels.narrationPlaceholder}
                    onChange={event => updateItem(index, { narration: event.target.value })}
                    className="w-full resize-y rounded-lg border border-[#e5e7eb] px-3 py-2 text-sm leading-6 text-[#374151] disabled:cursor-not-allowed disabled:bg-[#f9fafb] disabled:text-[#9ca3af]"
                  />
                </div>
              )
            })}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-[#f3f4f6] pt-4">
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving || remainingCount === 0}
              className="inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? <Loader2 size={14} className="animate-spin" /> : <Clapperboard size={14} />}
              {saving ? labels.saving : labels.saveAndRender}
            </button>
            {saveFailed && <span className="text-sm font-medium text-red-500">{labels.saveError}</span>}
          </div>
        </>
      )}
    </div>
  )
}
