import { useMemo, useState } from 'react'
import { Film, Layers, PlusCircle, Search, UserX, Pencil, Trash2 } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import type { Work } from '../../types'

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
      className="flex h-full w-[260px] shrink-0 flex-col rounded-xl border border-slate-200 bg-white"
    >
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-700">
          <Film size={14} className="text-[#3b5bdb]" />
          {t.characterLibrary.works.sidebarTitle}
        </div>
        <button
          type="button"
          data-testid="works-sidebar-create"
          onClick={onCreate}
          className="inline-flex h-7 items-center gap-1 rounded-md bg-[#3b5bdb] px-2 text-[11px] font-medium text-white transition hover:bg-[#3451c5]"
        >
          <PlusCircle size={11} />
          {t.characterLibrary.works.createWork}
        </button>
      </div>

      <div className="border-b border-slate-100 px-3 py-2">
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
            className="h-8 w-full rounded-md border border-slate-200 bg-white pl-7 pr-2 text-xs outline-none transition focus:border-[#3b5bdb] focus:ring-2 focus:ring-[#3b5bdb]/20"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        <button
          type="button"
          data-testid="works-sidebar-item-all"
          onClick={() => onSelect('__all__')}
          className={`mb-1 flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-sm transition ${
            selected === '__all__'
              ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
              : 'text-slate-700 hover:bg-slate-50'
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
          className={`mb-2 flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-sm transition ${
            selected === '__unassigned__'
              ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
              : 'text-slate-700 hover:bg-slate-50'
          }`}
        >
          <span className="flex items-center gap-2">
            <UserX size={14} />
            {t.characterLibrary.works.unassigned}
          </span>
          <span className="text-[11px] text-slate-500">{unassignedCount}</span>
        </button>

        <div className="my-1 border-t border-slate-100" />

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
            return (
              <div
                key={work.id}
                data-testid={`works-sidebar-item-${work.id}`}
                className={`group mb-1 flex items-center justify-between gap-1 rounded-md px-2 py-1.5 text-sm transition ${
                  isActive ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]' : 'text-slate-700 hover:bg-slate-50'
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(work.id)}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <span
                    className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-sm"
                    style={{
                      backgroundColor: work.color ? `${work.color}22` : '#f1f5f9',
                      color: work.color ?? '#334155',
                    }}
                  >
                    {work.cover_emoji || '🎬'}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{work.title}</span>
                  <span className="shrink-0 text-[11px] text-slate-500">
                    {work.persona_count ?? 0}
                  </span>
                </button>
                <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition group-hover:opacity-100">
                  <button
                    type="button"
                    data-testid={`works-sidebar-edit-${work.id}`}
                    onClick={() => onEdit(work)}
                    className="rounded p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
                    title={t.characterLibrary.works.actions.edit}
                  >
                    <Pencil size={11} />
                  </button>
                  <button
                    type="button"
                    data-testid={`works-sidebar-delete-${work.id}`}
                    onClick={() => onDelete(work)}
                    className="rounded p-1 text-rose-500 hover:bg-rose-50 hover:text-rose-600"
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
