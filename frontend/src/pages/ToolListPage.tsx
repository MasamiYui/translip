import { useQuery } from '@tanstack/react-query'
import { atomicToolsApi } from '../api/atomic-tools'
import { ToolCard } from '../components/atomic-tools/ToolCard'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { useI18n } from '../i18n/useI18n'

const CATEGORY_ORDER = ['audio', 'speech', 'video'] as const

export function ToolListPage() {
  const { locale, t } = useI18n()
  const { data: tools = [] } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })

  const toolsByCategory = CATEGORY_ORDER.map(category => ({
    category,
    tools: tools.filter(tool => tool.category === category),
  })).filter(group => group.tools.length > 0)

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-6`}>
      {/* Hero */}
      <div className="rounded-xl border border-[#e5e7eb] bg-white px-6 py-6 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        <div className="max-w-2xl">
          <div className="mb-2 inline-flex rounded-full border border-[#3b5bdb]/20 bg-[#f0f3ff] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-widest text-[#3b5bdb]">
            {t.atomicTools.sectionEyebrow}
          </div>
          <h1 className="text-xl font-bold text-[#111827]">{t.atomicTools.title}</h1>
          <p className="mt-1.5 text-sm text-[#6b7280] leading-relaxed">{t.atomicTools.description}</p>
        </div>
      </div>

      {toolsByCategory.map(group => (
        <section key={group.category} className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-widest text-[#9ca3af]">
              {t.atomicTools.categories[group.category]}
            </h2>
            <div className="text-xs font-semibold tabular-nums text-[#d1d5db]">
              {group.tools.length}
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {group.tools.map(tool => (
              <ToolCard
                key={tool.tool_id}
                tool={tool}
                title={locale === 'zh-CN' ? tool.name_zh : tool.name_en}
                description={locale === 'zh-CN' ? tool.description_zh : tool.description_en}
                categoryLabel={t.atomicTools.categories[tool.category]}
              />
            ))}
          </div>
        </section>
      ))}
    </PageContainer>
  )
}
