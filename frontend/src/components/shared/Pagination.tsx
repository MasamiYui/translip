import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'

interface PaginationProps {
  page: number
  pageCount: number
  onChange: (page: number) => void
  total?: number
  className?: string
  pageSize?: number
  pageSizeOptions?: readonly number[]
  onPageSizeChange?: (pageSize: number) => void
}

const DEFAULT_PAGE_SIZE_OPTIONS: readonly number[] = [10, 20, 50, 100]

function buildPageRange(page: number, pageCount: number): Array<number | 'gap'> {
  if (pageCount <= 7) {
    return Array.from({ length: pageCount }, (_, i) => i + 1)
  }
  const range: Array<number | 'gap'> = [1]
  const start = Math.max(2, page - 1)
  const end = Math.min(pageCount - 1, page + 1)
  if (start > 2) range.push('gap')
  for (let i = start; i <= end; i += 1) range.push(i)
  if (end < pageCount - 1) range.push('gap')
  range.push(pageCount)
  return range
}

export function Pagination({
  page,
  pageCount,
  onChange,
  total,
  className,
  pageSize,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  onPageSizeChange,
}: PaginationProps) {
  const { t } = useI18n()
  const safePageCount = Math.max(1, pageCount)
  const safePage = Math.min(Math.max(1, page), safePageCount)
  const range = buildPageRange(safePage, safePageCount)
  const canPrev = safePage > 1
  const canNext = safePage < safePageCount
  const showSizeSelect = pageSize !== undefined && onPageSizeChange !== undefined

  return (
    <div className={`flex items-center justify-between gap-3 text-sm ${className ?? ''}`}>
      <div className="flex items-center gap-3 text-xs font-semibold text-[#9ca3af]">
        {total !== undefined ? <span>{t.common.totalCount(total)}</span> : null}
        {showSizeSelect ? (
          <label className="flex items-center gap-1">
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="h-8 rounded-lg border border-[#e5e7eb] bg-white px-2 text-xs font-semibold text-[#374151] transition-all hover:border-[#d1d5db] focus:border-[#3b5bdb] focus:outline-none"
              aria-label={t.common.perPage(pageSize)}
            >
              {pageSizeOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {t.common.perPage(opt)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-label={t.common.prevPage}
          disabled={!canPrev}
          onClick={() => canPrev && onChange(safePage - 1)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#e5e7eb] bg-white text-[#6b7280] transition-all enabled:hover:bg-[#f9fafb] enabled:hover:text-[#374151] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft size={14} />
        </button>
        {range.map((entry, index) =>
          entry === 'gap' ? (
            <span
              key={`gap-${index}`}
              className="flex h-8 w-8 items-center justify-center text-xs text-[#9ca3af]"
              aria-hidden="true"
            >
              …
            </span>
          ) : (
            <button
              key={entry}
              type="button"
              onClick={() => onChange(entry)}
              aria-current={entry === safePage ? 'page' : undefined}
              className={`h-8 min-w-8 rounded-lg px-2 text-xs font-semibold transition-all ${
                entry === safePage
                  ? 'bg-[#3b5bdb] text-white shadow-sm'
                  : 'text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#374151]'
              }`}
            >
              {entry}
            </button>
          ),
        )}
        <button
          type="button"
          aria-label={t.common.nextPage}
          disabled={!canNext}
          onClick={() => canNext && onChange(safePage + 1)}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#e5e7eb] bg-white text-[#6b7280] transition-all enabled:hover:bg-[#f9fafb] enabled:hover:text-[#374151] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  )
}
