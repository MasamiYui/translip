import { Film } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import type { Work } from '../../types'

export type WorkSelection = '__all__' | '__unassigned__' | string

interface WorksSidebarProps {
  works: Work[]
  selected: WorkSelection
  onSelect: (value: WorkSelection) => void
  totalPersonas: number
  unassignedCount: number
  isLoading?: boolean
}

export function WorksSidebar({
  works,
  selected,
  onSelect,
  totalPersonas,
  unassignedCount,
  isLoading,
}: WorksSidebarProps) {
  const { t } = useI18n()

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
        className="h-9 w-[260px] max-w-full rounded-lg border border-[#e5e7eb] bg-white px-3 text-sm font-medium text-slate-700 transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
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
    </section>
  )
}
