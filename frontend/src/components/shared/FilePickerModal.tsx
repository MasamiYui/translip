import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, FileVideo, Folder, Home, Loader2, X } from 'lucide-react'
import { systemApi } from '../../api/config'
import type { FsEntry } from '../../types'

export interface FilePickerLabels {
  title: string
  up: string
  home: string
  currentPath: string
  emptyDir: string
  loadError: string
  noSelection: string
  select: string
  cancel: string
}

interface FilePickerModalProps {
  /** Starting path; a file path is accepted (its parent folder is opened). */
  initialPath?: string
  labels: FilePickerLabels
  onSelect: (path: string) => void
  onClose: () => void
}

function formatSize(bytes: number | null): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`
}

/**
 * Server-side file browser for picking a local input video. translip is
 * local-first, so the backend exposes the user's own filesystem and returns
 * absolute paths — exactly what the pipeline needs (a browser `<input file>`
 * cannot provide an absolute path).
 */
export function FilePickerModal({ initialPath, labels, onSelect, onClose }: FilePickerModalProps) {
  // `cwd === undefined` lets the backend default to the home directory.
  const [cwd, setCwd] = useState<string | undefined>(initialPath || undefined)
  const [selected, setSelected] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['fs-browse', cwd ?? ''],
    queryFn: () => systemApi.browse(cwd),
  })

  const goto = (path: string | undefined) => {
    setSelected(null)
    setCwd(path)
  }

  const onEntryClick = (entry: FsEntry) => {
    if (entry.is_dir) {
      goto(entry.path)
    } else {
      setSelected(entry.path)
    }
  }

  const confirm = () => {
    if (selected) onSelect(selected)
  }

  const entries = data?.entries ?? []

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={event => event.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <span className="text-sm font-semibold text-slate-800">{labels.title}</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={16} />
          </button>
        </div>

        {/* Toolbar: up / home / current path */}
        <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-4 py-2">
          <button
            type="button"
            onClick={() => goto(data?.parent ?? undefined)}
            disabled={!data?.parent}
            title={labels.up}
            className="shrink-0 rounded-md border border-slate-200 bg-white p-1.5 text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40"
          >
            <ArrowUp size={14} />
          </button>
          <button
            type="button"
            onClick={() => goto(data?.home ?? undefined)}
            title={labels.home}
            className="shrink-0 rounded-md border border-slate-200 bg-white p-1.5 text-slate-600 transition-colors hover:bg-slate-100"
          >
            <Home size={14} />
          </button>
          <div className="min-w-0 flex-1 truncate font-mono text-xs text-slate-500" title={data?.path}>
            {data?.path ?? '…'}
          </div>
        </div>

        {/* Entry list */}
        <div className="min-h-[12rem] flex-1 overflow-y-auto">
          {isLoading && (
            <div className="flex h-40 items-center justify-center text-slate-400">
              <Loader2 size={20} className="animate-spin" />
            </div>
          )}
          {isError && (
            <div className="flex h-40 items-center justify-center px-4 text-center text-sm text-rose-500">
              {labels.loadError}
            </div>
          )}
          {!isLoading && !isError && entries.length === 0 && (
            <div className="flex h-40 items-center justify-center px-4 text-center text-sm text-slate-400">
              {labels.emptyDir}
            </div>
          )}
          {!isLoading &&
            !isError &&
            entries.map(entry => {
              const isSelected = !entry.is_dir && entry.path === selected
              return (
                <button
                  key={entry.path}
                  type="button"
                  onClick={() => onEntryClick(entry)}
                  onDoubleClick={() => !entry.is_dir && onSelect(entry.path)}
                  className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                    isSelected ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]' : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {entry.is_dir ? (
                    <Folder size={16} className="shrink-0 text-amber-500" />
                  ) : (
                    <FileVideo size={16} className="shrink-0 text-[#3b5bdb]" />
                  )}
                  <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                  {!entry.is_dir && (
                    <span className="shrink-0 text-xs text-slate-400">{formatSize(entry.size_bytes)}</span>
                  )}
                </button>
              )
            })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-4 py-3">
          <span className="min-w-0 flex-1 truncate text-xs text-slate-500" title={selected ?? undefined}>
            {selected ?? labels.noSelection}
          </span>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-100"
            >
              {labels.cancel}
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={!selected}
              className="rounded-md bg-[#3b5bdb] px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[#3550c8] disabled:opacity-40"
            >
              {labels.select}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
