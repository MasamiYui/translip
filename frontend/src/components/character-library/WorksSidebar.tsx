import { useMemo, useState } from 'react'
import { Film, Layers, PlusCircle, Search, UserX, Pencil, Trash2 } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import type { Work } from '../../types'
import { DEFAULT_COLOR, gradientBackground, normalizeHex } from './pickers/presets'

export type WorkSelection = '__all__' | '__unassigned__' | string

interface WorksSidebarProps {
  works: Work[]
  selected: WorkSelection
  onSelect: (value: WorkSelection) => void
  onCreate: () => void
  onEdit: (work: Work) => void
  onDelete: (work: Work) => void
  totalPersonas: number
  unassignedCount: number
  isLoading?: boolean
}

export function WorksSidebar({
  works,
  selected,
  onSelect,
  onCreate,
  onEdit,
  onDelete,
  totalPersonas,
  unassignedCount,
  isLoading,
}: WorksSidebarProps) {
  const { t } = useI18n()
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    if (!kw) return works
    return works.filter(w => {
      const title = (w.title ?? '').toLowerCase()
      const aliases = (w.aliases ?? []).join(' ').toLowerCase()
      const tags = (w.tags ?? []).join(' ').toLowerCase()
      return title.includes(kw) || aliases.includes(kw) || tags.includes(kw)
    })
  }, [works, search])

  return (
    <aside
      data-testid="works-sidebar"
      className="flex h-full w-[260px] shrink-0 flex-col rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]"
    >
      <div className="flex items-center justify-between border-b border-[#e5e7eb] px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
          <Film size={14} className="text-[#3b5bdb]" />
          {t.characterLibrary.works.sidebarTitle}
        </div>
        <button
          type="button"
          data-testid="works-sidebar-create"
          onClick={onCreate}
          className="inline-flex items-center gap-1 rounded-lg bg-[#3b5bdb] px-2.5 py-1 text-[11px] font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
        >
          <PlusCircle size={11} />
          {t.characterLibrary.works.createWork}
        </button>
      </div>

      <div className="border-b border-[#e5e7eb] px-3 py-2">
        <div className="relative">
          <Search
            size={12}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            data-testid="works-sidebar-search"
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder={t.characterLibrary.works.searchPlaceholder}
            className="w-full rounded-lg border border-[#e5e7eb] bg-white py-1.5 pl-7 pr-2 text-xs transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        <button
          type="button"
          data-testid="works-sidebar-item-all"
          onClick={() => onSelect('__all__')}
          className={`mb-1 flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
            selected === '__all__'
              ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
              : 'text-slate-700 hover:bg-[#f9fafb]'
          }`}
        >
          <span className="flex items-center gap-2">
            <Layers size={14} />
            {t.characterLibrary.works.allWorks}
          </span>
          <span className="text-[11px] text-slate-500">{totalPersonas}</span>
        </button>

        <button
          type="button"
          data-testid="works-sidebar-item-unassigned"
          onClick={() => onSelect('__unassigned__')}
          className={`mb-2 flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-all ${
            selected === '__unassigned__'
              ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
              : 'text-slate-700 hover:bg-[#f9fafb]'
          }`}
        >
          <span className="flex items-center gap-2">
            <UserX size={14} />
            {t.characterLibrary.works.unassigned}
          </span>
          <span className="text-[11px] text-slate-500">{unassignedCount}</span>
        </button>

        <div className="my-1 border-t border-[#e5e7eb]" />

        {isLoading ? (
          <div className="px-2 py-3 text-xs text-slate-400">Loading…</div>
        ) : filtered.length === 0 ? (
          <div
            data-testid="works-sidebar-empty"
            className="px-2 py-3 text-xs text-slate-400"
          >
            {t.characterLibrary.works.empty}
          </div>
        ) : (
          filtered.map(work => {
            const isActive = selected === work.id
            const resolvedColor = normalizeHex(work.color) || DEFAULT_COLOR
            return (
              <div
                key={work.id}
                data-testid={`works-sidebar-item-${work.id}`}
                className={`group mb-1 flex items-center justify-between gap-1 rounded-lg px-2 py-1.5 text-sm transition-all ${
                  isActive ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]' : 'text-slate-700 hover:bg-[#f9fafb]'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(work.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <span
                    className="inline-flex h-6 w-8 shrink-0 items-center justify-center rounded-md text-[13px]"
                    style={{ background: gradientBackground(resolvedColor) }}
                  >
                    {work.cover_emoji || '🎬'}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{work.title}</span>
                  <span className="shrink-0 text-[11px] text-slate-500">
                    {work.persona_count ?? 0}
                  </span>
                </button>
                <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-all group-hover:opacity-100">
                  <button
                    type="button"
                    data-testid={`works-sidebar-edit-${work.id}`}
                    onClick={() => onEdit(work)}
                    className="rounded-md p-1 text-[#6b7280] transition-all hover:bg-[#f3f4f6] hover:text-[#374151]"
                    title={t.characterLibrary.works.actions.edit}
                  >
                    <Pencil size={11} />
                  </button>
                  <button
                    type="button"
                    data-testid={`works-sidebar-delete-${work.id}`}
                    onClick={() => onDelete(work)}
                    className="rounded-md p-1 text-rose-500 transition-all hover:bg-rose-50 hover:text-rose-600"
                    title={t.characterLibrary.works.actions.delete}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}
