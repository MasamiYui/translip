import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Clapperboard, Download, ExternalLink, Pencil, PlusCircle, RefreshCw, Search, Trash2 } from 'lucide-react'
import { worksApi } from '../api/works'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { WorkEditorDrawer, type WorkCreateMode } from '../components/character-library/WorkEditorDrawer'
import { useI18n } from '../i18n/useI18n'
import { DEFAULT_COLOR, gradientBackground, normalizeHex } from '../components/character-library/pickers/presets'
import type { Work, WorkType } from '../types'

const TYPE_FILTER_ALL = '__all_types__'

function workYearLabel(work: Work, fallback: string): string {
  if (work.year) return String(work.year)
  const meta = work.metadata
  if (meta?.release_date) return String(meta.release_date).slice(0, 4)
  if (meta?.first_air_date) return String(meta.first_air_date).slice(0, 4)
  return fallback
}

function workTypeLabel(types: WorkType[], key: string, locale: string): string {
  const found = types.find(t => t.key === key)
  if (!found) return key
  return locale === 'zh-CN' ? found.label_zh : found.label_en
}

export function WorksPage() {
  const { t, locale } = useI18n()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>(TYPE_FILTER_ALL)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingWork, setEditingWork] = useState<Work | null>(null)
  const [flash, setFlash] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [createMode, setCreateMode] = useState<WorkCreateMode>('manual')

  const { data: worksData, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['works'],
    queryFn: () => worksApi.list(),
  })

  const { data: typesData } = useQuery({
    queryKey: ['work-types'],
    queryFn: () => worksApi.listTypes(),
    staleTime: 60_000,
  })

  const { data: tmdbConfig } = useQuery({
    queryKey: ['tmdb-config'],
    queryFn: worksApi.tmdbGetConfig,
  })

  const hasTmdbKey = tmdbConfig?.ok && (tmdbConfig.api_key_v3_set || tmdbConfig.api_key_v4_set)

  const works: Work[] = useMemo(() => worksData?.works ?? [], [worksData])
  const types: WorkType[] = useMemo(() => typesData?.types ?? [], [typesData])
  const storagePath = worksData?.path ?? ''

  const deleteMutation = useMutation({
    mutationFn: (workId: string) => worksApi.remove(workId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['works'] })
      queryClient.invalidateQueries({ queryKey: ['global-personas'] })
    },
  })

  useEffect(() => {
    if (!flash) return
    const timer = window.setTimeout(() => setFlash(null), 3500)
    return () => window.clearTimeout(timer)
  }, [flash])

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return works.filter(w => {
      if (typeFilter !== TYPE_FILTER_ALL && w.type !== typeFilter) return false
      if (!kw) return true
      const title = (w.title ?? '').toLowerCase()
      const original = (w.metadata?.original_title ?? '').toString().toLowerCase()
      const aliases = (w.aliases ?? []).join(' ').toLowerCase()
      const tags = (w.tags ?? []).join(' ').toLowerCase()
      return (
        title.includes(kw) ||
        original.includes(kw) ||
        aliases.includes(kw) ||
        tags.includes(kw)
      )
    })
  }, [works, search, typeFilter])

  function openCreate(mode: WorkCreateMode = 'manual') {
    setCreateMode(mode)
    setEditingWork(null)
    setDrawerOpen(true)
  }

  function openEdit(work: Work) {
    setCreateMode('manual')
    setEditingWork(work)
    setDrawerOpen(true)
  }

  function handleSaved(work: Work, isCreate: boolean) {
    setFlash({
      type: 'success',
      text: isCreate
        ? t.worksLibrary.flash.created(work.title)
        : t.worksLibrary.flash.updated(work.title),
    })
    setDrawerOpen(false)
    setEditingWork(null)
  }

  async function handleDelete(work: Work) {
    const count = work.persona_count ?? 0
    if (!window.confirm(t.characterLibrary.works.deleteConfirm(work.title, count))) return
    try {
      await deleteMutation.mutateAsync(work.id)
      setFlash({ type: 'success', text: t.worksLibrary.flash.deleted(work.title) })
    } catch (err) {
      console.error(err)
      setFlash({ type: 'error', text: t.worksLibrary.flash.deleteFailed })
    }
  }

  const noKeyword = search.trim().length === 0 && typeFilter === TYPE_FILTER_ALL

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Clapperboard size={18} className="text-[#3b5bdb]" />
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            {t.worksLibrary.title}
          </h1>
        </div>
        <span
          data-testid="works-library-count"
          className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600"
        >
          {t.worksLibrary.countHint(works.length)}
        </span>
        <p className="basis-full text-xs text-slate-500">{t.worksLibrary.subtitle}</p>
        {storagePath && (
          <p data-testid="works-library-storage" className="basis-full text-[11px] text-slate-400">
            {t.worksLibrary.storageHint(storagePath)}
          </p>
        )}
      </div>

      {flash && (
        <div
          data-testid={`works-library-flash-${flash.type}`}
          className={
            flash.type === 'success'
              ? 'mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700'
              : 'mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700'
          }
        >
          {flash.text}
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            data-testid="works-library-search"
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder={t.worksLibrary.filters.searchPlaceholder}
            className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
          />
        </div>
        <select
          data-testid="works-library-type-filter"
          value={typeFilter}
          onChange={event => setTypeFilter(event.target.value)}
          className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#374151] focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
        >
          <option value={TYPE_FILTER_ALL}>{t.worksLibrary.filters.all}</option>
          {types.map(typeRecord => (
            <option key={typeRecord.key} value={typeRecord.key}>
              {locale === 'zh-CN' ? typeRecord.label_zh : typeRecord.label_en}
            </option>
          ))}
        </select>
        <button
          type="button"
          data-testid="works-library-refresh"
          onClick={() => refetch()}
          disabled={isFetching}
          title={t.worksLibrary.actions.refresh}
          aria-label={t.worksLibrary.actions.refresh}
          className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151] disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={14} className={isFetching ? 'animate-spin' : undefined} />
          {t.worksLibrary.actions.refresh}
        </button>
        <button
          type="button"
          data-testid="works-library-create"
          onClick={() => openCreate('manual')}
          className="inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
        >
          <PlusCircle size={14} />
          {t.worksLibrary.actions.create}
        </button>
      </div>

      <div data-testid="works-library-grid">
        {isLoading ? (
          <div className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center text-sm text-slate-400">
            {t.common.loading}
          </div>
        ) : filtered.length === 0 ? (
          noKeyword ? (
            <div
              data-testid="works-library-empty"
              className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center"
            >
              <Clapperboard size={32} className="text-slate-300" />
              <div className="text-base font-medium text-slate-700">
                {t.worksLibrary.empty.title}
              </div>
              <div className="max-w-md text-sm text-slate-500">
                {t.worksLibrary.empty.description}
              </div>
              {hasTmdbKey ? (
                <button
                  type="button"
                  data-testid="works-library-empty-cta"
                  onClick={() => openCreate('tmdb')}
                  className="mt-2 inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
                >
                  <Download size={14} />
                  {t.worksLibrary.actions.importFromTmdb}
                </button>
              ) : (
                <button
                  type="button"
                  data-testid="works-library-empty-cta"
                  onClick={() => openCreate('manual')}
                  className="mt-2 inline-flex items-center gap-2 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7]"
                >
                  <PlusCircle size={14} />
                  {t.worksLibrary.empty.cta}
                </button>
              )}
            </div>
          ) : (
            <div
              data-testid="works-library-empty-filtered"
              className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center text-sm text-slate-400"
            >
              {t.worksLibrary.emptyFiltered}
            </div>
          )
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {filtered.map(work => (
              <WorkCard
                key={work.id}
                work={work}
                typeLabel={workTypeLabel(types, work.type, locale)}
                yearFallback={t.worksLibrary.card.yearFallback}
                overviewFallback={t.worksLibrary.card.overviewFallback}
                personaCountLabel={t.worksLibrary.card.personaCount(work.persona_count ?? 0)}
                posterAlt={t.worksLibrary.card.posterAlt(work.title)}
                tmdbBadge={t.worksLibrary.card.fromTmdb}
                editLabel={t.worksLibrary.actions.edit}
                deleteLabel={t.worksLibrary.actions.delete}
                openCharactersLabel={t.worksLibrary.actions.openCharacters}
                onEdit={() => openEdit(work)}
                onDelete={() => handleDelete(work)}
                onOpenCharacters={() => navigate(`/character-library?work=${encodeURIComponent(work.id)}`)}
              />
            ))}
          </div>
        )}
      </div>

      <WorkEditorDrawer
        open={drawerOpen}
        work={editingWork}
        initialMode={createMode}
        onClose={() => {
          setDrawerOpen(false)
          setEditingWork(null)
        }}
        onSaved={handleSaved}
        onError={text => setFlash({ type: 'error', text })}
      />
    </PageContainer>
  )
}

interface WorkCardProps {
  work: Work
  typeLabel: string
  yearFallback: string
  overviewFallback: string
  personaCountLabel: string
  posterAlt: string
  tmdbBadge: string
  editLabel: string
  deleteLabel: string
  openCharactersLabel: string
  onEdit: () => void
  onDelete: () => void
  onOpenCharacters: () => void
}

function WorkCard({
  work,
  typeLabel,
  yearFallback,
  overviewFallback,
  personaCountLabel,
  posterAlt,
  tmdbBadge,
  editLabel,
  deleteLabel,
  openCharactersLabel,
  onEdit,
  onDelete,
  onOpenCharacters,
}: WorkCardProps) {
  const accent = normalizeHex(work.color) || DEFAULT_COLOR
  const posterUrl = work.metadata?.poster_url || null
  const overview = (work.metadata?.overview ?? '').toString().trim()
  const tmdbId = work.external_refs?.tmdb_id
  const yearLabel = workYearLabel(work, yearFallback)

  return (
    <article
      data-testid={`works-card-${work.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div
        className="relative aspect-[2/3] w-full overflow-hidden"
        style={{ background: gradientBackground(accent) }}
      >
        {posterUrl ? (
          <img
            data-testid={`works-card-poster-${work.id}`}
            src={posterUrl}
            alt={posterAlt}
            loading="lazy"
            className="h-full w-full object-cover"
            onError={event => {
              ;(event.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <span className="text-5xl" aria-hidden>
              {work.cover_emoji?.trim() || '🎬'}
            </span>
          </div>
        )}
        {tmdbId && (
          <span
            data-testid={`works-card-tmdb-badge-${work.id}`}
            className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white backdrop-blur"
            title={tmdbBadge}
          >
            <ExternalLink size={10} />
            TMDb
          </span>
        )}
        <span
          className="absolute right-2 top-2 inline-flex items-center rounded-full bg-white/85 px-2 py-0.5 text-[10px] font-semibold text-slate-700 backdrop-blur"
        >
          {typeLabel}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 px-3 py-3">
        <div className="flex items-start justify-between gap-2">
          <h3
            className="line-clamp-2 text-sm font-semibold text-slate-800"
            title={work.title}
          >
            {work.title}
          </h3>
          <span className="shrink-0 text-[11px] text-slate-400">{yearLabel}</span>
        </div>
        <p className="line-clamp-3 text-[12px] text-slate-500">
          {overview || overviewFallback}
        </p>
        <div className="mt-auto flex flex-wrap items-center gap-2 pt-1 text-[11px] text-slate-500">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
            {personaCountLabel}
          </span>
          {(work.aliases ?? []).slice(0, 2).map(a => (
            <span key={a} className="rounded-full bg-slate-50 px-2 py-0.5 text-slate-500">
              {a}
            </span>
          ))}
        </div>
        <div className="flex items-center justify-end gap-1 pt-1">
          <button
            type="button"
            data-testid={`works-card-open-characters-${work.id}`}
            onClick={onOpenCharacters}
            title={openCharactersLabel}
            aria-label={openCharactersLabel}
            className="rounded-lg p-1.5 text-slate-400 transition-all hover:bg-[#f3f4f6] hover:text-[#3b5bdb]"
          >
            <ExternalLink size={13} />
          </button>
          <button
            type="button"
            data-testid={`works-card-edit-${work.id}`}
            onClick={onEdit}
            title={editLabel}
            aria-label={editLabel}
            className="rounded-lg p-1.5 text-slate-400 transition-all hover:bg-[#f3f4f6] hover:text-[#374151]"
          >
            <Pencil size={13} />
          </button>
          <button
            type="button"
            data-testid={`works-card-delete-${work.id}`}
            onClick={onDelete}
            title={deleteLabel}
            aria-label={deleteLabel}
            className="rounded-lg p-1.5 text-slate-400 transition-all hover:bg-rose-50 hover:text-rose-600"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </article>
  )
}
