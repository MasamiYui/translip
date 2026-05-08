import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useI18n } from '../../i18n/useI18n'
import type { ToolInfo } from '../../types/atomic-tools'

interface ToolCardProps {
  tool: ToolInfo
  title: string
  description: string
  categoryLabel: string
}

export function ToolCard({ tool, title, description, categoryLabel }: ToolCardProps) {
  const { t } = useI18n()

  return (
    <Link
      to={`/tools/${tool.tool_id}`}
      className="group flex flex-col rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:border-[#3b5bdb]/30 hover:shadow-[0_4px_16px_rgba(0,0,0,.08)]"
    >
      <div className="mb-3 inline-flex self-start rounded-full border border-[#e5e7eb] bg-[#f9fafb] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-[#6b7280]">
        {categoryLabel}
      </div>
      <h3 className="text-sm font-bold text-[#111827]">{title}</h3>
      <p className="mt-1.5 flex-1 text-xs leading-5 text-[#6b7280]">{description}</p>
      <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-[#3b5bdb]">
        {t.atomicTools.actions.useTool}
        <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}
