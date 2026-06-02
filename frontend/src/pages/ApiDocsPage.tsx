import { Fragment, useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  Braces,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  ExternalLink,
  Search,
} from 'lucide-react'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { apiDocsApi } from '../api/api-docs'
import {
  collectOperations,
  collectSchemaRefs,
  DEFAULT_TAG_KEY,
  formatSchemaType,
  groupByTag,
  pickContentSchema,
  schemaFields,
  sortedResponseCodes,
  type ResolvedOperation,
  type SchemaField,
} from '../lib/openapi'
import type {
  OpenApiOperation,
  OpenApiParameter,
  OpenApiResponse,
  OpenApiSpec,
} from '../types/openapi'
import type { LocaleMessages } from '../i18n/messages'
import { useI18n } from '../i18n/useI18n'
import { cn } from '../lib/utils'

const RAW_SPEC_URL = '/api/meta/openapi'

const METHOD_STYLES: Record<string, string> = {
  get: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  post: 'bg-blue-50 text-blue-700 ring-blue-600/20',
  put: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  patch: 'bg-violet-50 text-violet-700 ring-violet-600/20',
  delete: 'bg-rose-50 text-rose-700 ring-rose-600/20',
  options: 'bg-slate-100 text-slate-600 ring-slate-500/20',
  head: 'bg-slate-100 text-slate-600 ring-slate-500/20',
}

export function ApiDocsPage() {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(() => new Set())
  const [openOps, setOpenOps] = useState<Set<string>>(() => new Set())

  const {
    data: spec,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['openapi-spec'],
    queryFn: apiDocsApi.getSpec,
    staleTime: 5 * 60_000,
  })

  const operations = useMemo(() => collectOperations(spec), [spec])
  const groups = useMemo(() => groupByTag(operations), [operations])

  const searching = query.trim().length > 0
  const kw = query.trim().toLowerCase()

  const visibleGroups = useMemo(() => {
    if (!searching) return groups.map(g => ({ tag: g.tag, ops: g.operations }))
    return groups
      .map(g => ({
        tag: g.tag,
        ops: g.operations.filter(
          op =>
            op.path.toLowerCase().includes(kw) ||
            op.summary.toLowerCase().includes(kw) ||
            op.method.includes(kw) ||
            g.tag.toLowerCase().includes(kw),
        ),
      }))
      .filter(g => g.ops.length > 0)
  }, [groups, searching, kw])

  const allCollapsed = groups.length > 0 && collapsedGroups.size >= groups.length

  function toggleGroup(tag: string) {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return next
    })
  }

  function toggleAllGroups() {
    setCollapsedGroups(allCollapsed ? new Set() : new Set(groups.map(g => g.tag)))
  }

  function toggleOp(key: string) {
    setOpenOps(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const groupLabel = (tag: string) => (tag === DEFAULT_TAG_KEY ? t.apiDocs.untagged : tag)

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Braces size={17} className="text-[#3b5bdb]" />
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{t.apiDocs.title}</h1>
        </div>
        {operations.length > 0 && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            {t.apiDocs.countHint(operations.length)}
          </span>
        )}
        {spec?.info && (
          <span className="text-xs text-slate-400">
            {spec.info.title} · v{spec.info.version}
          </span>
        )}
        <p className="basis-full text-xs text-slate-500">{t.apiDocs.subtitle}</p>
      </div>

      {isPending ? (
        <div
          data-testid="api-docs-loading"
          className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center text-sm text-slate-400"
        >
          {t.apiDocs.loading}
        </div>
      ) : isError ? (
        <div
          data-testid="api-docs-error"
          className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-rose-200 bg-rose-50/40 px-6 py-16 text-center"
        >
          <AlertCircle size={28} className="text-rose-400" />
          <div className="text-sm font-medium text-rose-700">{t.apiDocs.error}</div>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-600 transition-colors hover:bg-rose-50"
          >
            {t.apiDocs.retry}
          </button>
        </div>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[240px] flex-1">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                data-testid="api-docs-search"
                type="search"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder={t.apiDocs.searchPlaceholder}
                className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
              />
            </div>
            {!searching && groups.length > 0 && (
              <button
                type="button"
                onClick={toggleAllGroups}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-[#f9fafb] hover:text-slate-700"
              >
                {allCollapsed ? <ChevronsUpDown size={14} /> : <ChevronsDownUp size={14} />}
                {allCollapsed ? t.apiDocs.expandAll : t.apiDocs.collapseAll}
              </button>
            )}
            <a
              href={RAW_SPEC_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-xs font-medium text-slate-500 transition-colors hover:bg-[#f9fafb] hover:text-slate-700"
            >
              <ExternalLink size={14} />
              {t.apiDocs.rawSpec}
            </a>
          </div>

          {visibleGroups.length === 0 ? (
            <div
              data-testid="api-docs-empty"
              className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center text-sm text-slate-400"
            >
              {t.apiDocs.empty}
            </div>
          ) : (
            <div className="space-y-3">
              {visibleGroups.map(group => {
                const open = searching || !collapsedGroups.has(group.tag)
                return (
                  <section
                    key={group.tag}
                    data-testid={`api-docs-group-${group.tag}`}
                    className="overflow-hidden rounded-xl border border-[#e5e7eb] bg-white"
                  >
                    <button
                      type="button"
                      onClick={() => !searching && toggleGroup(group.tag)}
                      className={cn(
                        'flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors',
                        searching ? 'cursor-default' : 'hover:bg-[#fafbfc]',
                      )}
                    >
                      <span className="text-sm font-semibold text-slate-800">
                        {groupLabel(group.tag)}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
                        {t.apiDocs.groupCountHint(group.ops.length)}
                      </span>
                      {!searching && (
                        <ChevronDown
                          size={16}
                          className={cn(
                            'ml-auto shrink-0 text-slate-300 transition-transform duration-200',
                            open && 'rotate-180',
                          )}
                        />
                      )}
                    </button>

                    {open && (
                      <div className="space-y-2 border-t border-[#f1f5f9] bg-[#f8fafc] p-3">
                        {group.ops.map(op => (
                          <OperationCard
                            key={op.key}
                            op={op}
                            spec={spec}
                            t={t}
                            open={openOps.has(op.key)}
                            onToggle={() => toggleOp(op.key)}
                          />
                        ))}
                      </div>
                    )}
                  </section>
                )
              })}
            </div>
          )}
        </>
      )}
    </PageContainer>
  )
}

function MethodBadge({ method }: { method: string }) {
  return (
    <span
      className={cn(
        'inline-flex w-[58px] shrink-0 items-center justify-center rounded-md px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ring-1 ring-inset',
        METHOD_STYLES[method] ?? METHOD_STYLES.head,
      )}
    >
      {method}
    </span>
  )
}

interface OperationCardProps {
  op: ResolvedOperation
  spec: OpenApiSpec | undefined
  t: LocaleMessages
  open: boolean
  onToggle: () => void
}

function OperationCard({ op, spec, t, open, onToggle }: OperationCardProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-[#e9ebef] bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-[#fafbfc]"
      >
        <MethodBadge method={op.method} />
        <code className="shrink-0 font-mono text-[13px] text-slate-800">{op.path}</code>
        {op.summary && (
          <span className="min-w-0 flex-1 truncate text-[12px] text-slate-400">{op.summary}</span>
        )}
        {op.deprecated && (
          <span className="shrink-0 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 ring-1 ring-inset ring-amber-600/20">
            {t.apiDocs.deprecated}
          </span>
        )}
        <ChevronDown
          size={15}
          className={cn(
            'ml-auto shrink-0 text-slate-300 transition-transform duration-200',
            open && 'rotate-180',
          )}
        />
      </button>
      {open && <OperationDetail operation={op.operation} spec={spec} t={t} />}
    </div>
  )
}

function OperationDetail({
  operation,
  spec,
  t,
}: {
  operation: OpenApiOperation
  spec: OpenApiSpec | undefined
  t: LocaleMessages
}) {
  const params = operation.parameters ?? []
  const reqContent = pickContentSchema(operation.requestBody?.content)
  const reqFields = schemaFields(reqContent?.schema, spec)
  const responseCodes = sortedResponseCodes(operation.responses)

  return (
    <div className="space-y-4 border-t border-[#f1f5f9] bg-[#fcfcfd] px-4 py-4">
      {operation.description && (
        <p className="whitespace-pre-line text-[13px] leading-relaxed text-slate-600">
          {operation.description}
        </p>
      )}

      {params.length > 0 && (
        <section>
          <SectionTitle>{t.apiDocs.parameters}</SectionTitle>
          <ParamTable params={params} t={t} />
        </section>
      )}

      {reqContent && (
        <section>
          <SectionTitle>
            {t.apiDocs.requestBody}
            {operation.requestBody?.required && <RequiredMark t={t} />}
          </SectionTitle>
          <div className="mb-1.5 text-[11px] text-slate-400">
            {t.apiDocs.mediaType}: <span className="font-mono text-slate-500">{reqContent.mediaType}</span>
            {reqContent.schema && (
              <>
                {' · '}
                <span className="font-mono text-[#3b5bdb]">{formatSchemaType(reqContent.schema)}</span>
              </>
            )}
          </div>
          <FieldTable
            fields={reqFields}
            spec={spec}
            t={t}
            ancestors={collectSchemaRefs(reqContent.schema)}
          />
        </section>
      )}

      {responseCodes.length > 0 && (
        <section>
          <SectionTitle>{t.apiDocs.responses}</SectionTitle>
          <div className="space-y-2">
            {responseCodes.map(code => (
              <ResponseRow
                key={code}
                code={code}
                response={operation.responses?.[code]}
                spec={spec}
                t={t}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ParamTable({ params, t }: { params: OpenApiParameter[]; t: LocaleMessages }) {
  const locationLabel = (where: OpenApiParameter['in']) => t.apiDocs.location[where] ?? where
  return (
    <div className="overflow-hidden rounded-lg border border-[#e5e7eb]">
      <table className="w-full border-collapse text-left text-[12px]">
        <thead className="bg-[#f9fafb] text-[11px] uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.name}</th>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.in}</th>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.type}</th>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.description}</th>
          </tr>
        </thead>
        <tbody>
          {params.map(param => (
            <tr key={`${param.in}:${param.name}`} className="border-t border-[#f1f5f9] align-top">
              <td className="px-3 py-1.5 font-mono text-slate-800">
                {param.name}
                {param.required && <RequiredMark t={t} />}
              </td>
              <td className="px-3 py-1.5 text-slate-500">{locationLabel(param.in)}</td>
              <td className="px-3 py-1.5 font-mono text-[#3b5bdb]">{formatSchemaType(param.schema)}</td>
              <td className="px-3 py-1.5 text-slate-500">{param.description ?? t.apiDocs.noDescription}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FieldTable({
  fields,
  spec,
  t,
  ancestors = [],
}: {
  fields: SchemaField[]
  spec: OpenApiSpec | undefined
  t: LocaleMessages
  ancestors?: string[]
}) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  if (fields.length === 0) return null

  const toggle = (name: string) =>
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })

  return (
    <div className="overflow-hidden rounded-lg border border-[#e5e7eb]">
      <table className="w-full border-collapse text-left text-[12px]">
        <thead className="bg-[#f9fafb] text-[11px] uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.name}</th>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.type}</th>
            <th className="px-3 py-1.5 font-medium">{t.apiDocs.description}</th>
          </tr>
        </thead>
        <tbody>
          {fields.map(field => {
            // Only models that exist and are not already an ancestor are
            // expandable — this stops self-referential models from looping.
            const expandableRefs = field.refs.filter(
              ref => spec?.components?.schemas?.[ref] && !ancestors.includes(ref),
            )
            const canExpand = expandableRefs.length > 0
            const isOpen = expanded.has(field.name)
            return (
              <Fragment key={field.name}>
                <tr className="border-t border-[#f1f5f9] align-top">
                  <td className="px-3 py-1.5 font-mono text-slate-800">
                    {field.name}
                    {field.required && <RequiredMark t={t} />}
                  </td>
                  <td className="px-3 py-1.5">
                    {canExpand ? (
                      <button
                        type="button"
                        onClick={() => toggle(field.name)}
                        aria-expanded={isOpen}
                        className="inline-flex items-center gap-1 font-mono text-[12px] text-[#3b5bdb] hover:underline"
                      >
                        {field.type}
                        <ChevronRight
                          size={12}
                          className={cn(
                            'shrink-0 transition-transform duration-200',
                            isOpen && 'rotate-90',
                          )}
                        />
                      </button>
                    ) : (
                      <span className="font-mono text-[12px] text-[#3b5bdb]">{field.type}</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-slate-500">
                    {field.description ?? t.apiDocs.noDescription}
                    {field.enumValues && (
                      <span className="mt-0.5 block text-[11px] text-slate-400">
                        {t.apiDocs.enumLabel}: {field.enumValues.join(' · ')}
                      </span>
                    )}
                  </td>
                </tr>
                {canExpand && isOpen && (
                  <tr className="border-t border-[#f1f5f9]">
                    <td colSpan={3} className="px-3 py-2">
                      <div className="space-y-2 border-l-2 border-[#dbe1ea] pl-3">
                        {expandableRefs.map(ref => (
                          <div key={ref}>
                            <div className="mb-1 font-mono text-[11px] text-slate-400">{ref}</div>
                            <FieldTable
                              fields={schemaFields({ $ref: `#/components/schemas/${ref}` }, spec)}
                              spec={spec}
                              t={t}
                              ancestors={[...ancestors, ref]}
                            />
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ResponseRow({
  code,
  response,
  spec,
  t,
}: {
  code: string
  response: OpenApiResponse | undefined
  spec: OpenApiSpec | undefined
  t: LocaleMessages
}) {
  const content = pickContentSchema(response?.content)
  const is2xx = code.startsWith('2')
  const fields = is2xx ? schemaFields(content?.schema, spec) : []
  return (
    <div className="rounded-lg border border-[#eef0f3] bg-white p-2.5">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold ring-1 ring-inset',
            is2xx
              ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20'
              : 'bg-slate-100 text-slate-500 ring-slate-400/20',
          )}
        >
          {code}
        </span>
        {response?.description && (
          <span className="text-[12px] text-slate-600">{response.description}</span>
        )}
        {content?.schema && (
          <span className="ml-auto font-mono text-[11px] text-[#3b5bdb]">
            {formatSchemaType(content.schema)}
          </span>
        )}
      </div>
      {fields.length > 0 && (
        <div className="mt-2">
          <FieldTable
            fields={fields}
            spec={spec}
            t={t}
            ancestors={collectSchemaRefs(content?.schema)}
          />
        </div>
      )}
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
      {children}
    </h4>
  )
}

function RequiredMark({ t }: { t: LocaleMessages }) {
  return (
    <span className="ml-1 text-rose-500" title={t.apiDocs.required}>
      *
    </span>
  )
}
