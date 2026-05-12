import { Film, PlusCircle, Pencil, Trash2 } from 'lucide-react'
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
  const selectedWork = works.find(work => work.id === selected) ?? null

  return (
    <section
      data-testid="works-sidebar"
      aria-label="作品筛选"
      className="flex items-center gap-1.5"
    >
      <label
        htmlFor="works-sidebar-select"
        className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-slate-500"
      >
        <Film size={12} className="text-[#3b5bdb]" />
        {t.characterLibrary.works.sidebarTitle}
      </label>

      <select
        id="works-sidebar-select"
        data-testid="works-sidebar-select"
        value={selected}
        onChange={event => onSelect(event.target.value as WorkSelection)}
        className="h-9 max-w-[260px] rounded-lg border border-[#e5e7eb] bg-white px-3 text-sm font-medium text-slate-700 transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
      >
        <option data-testid="works-sidebar-item-all" value="__all__">
          {t.characterLibrary.works.allWorks} · {totalPersonas}
        </option>
        <option data-testid="works-sidebar-item-unassigned" value="__unassigned__">
          {t.characterLibrary.works.unassigned} · {unassignedCount}
        </option>
        {isLoading ? (
          <option disabled>Loading…</option>
        ) : works.length === 0 ? (
          <option data-testid="works-sidebar-empty" disabled>
            {t.characterLibrary.works.empty}
          </option>
        ) : (
          works.map(work => (
            <option
              key={work.id}
              data-testid={`works-sidebar-item-${work.id}`}
              value={work.id}
            >
              {work.cover_emoji ? `${work.cover_emoji} ` : ''}
              {work.title} · {work.persona_count ?? 0}
            </option>
          ))
        )}
      </select>

      {selectedWork && (
        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            data-testid={`works-sidebar-edit-${selectedWork.id}`}
            onClick={() => onEdit(selectedWork)}
            className="rounded-lg border border-[#e5e7eb] bg-white p-2 text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
            title={t.characterLibrary.works.actions.edit}
            aria-label={t.characterLibrary.works.actions.edit}
          >
            <Pencil size={12} />
          </button>
          <button
            type="button"
            data-testid={`works-sidebar-delete-${selectedWork.id}`}
            onClick={() => onDelete(selectedWork)}
            className="rounded-lg border border-rose-200 bg-white p-2 text-rose-500 transition-all hover:bg-rose-50 hover:text-rose-600"
            title={t.characterLibrary.works.actions.delete}
            aria-label={t.characterLibrary.works.actions.delete}
          >
            <Trash2 size={12} />
          </button>
        </div>
      )}

      <div className="h-6 w-px shrink-0 bg-[#e5e7eb]" />

      <button
        type="button"
        data-testid="works-sidebar-create"
        onClick={onCreate}
        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 text-xs font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
      >
        <PlusCircle size={12} />
        {t.characterLibrary.works.createWork}
      </button>
    </section>
  )
}
