import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  Clapperboard,
  Download,
  Film,
  Loader2,
  Search,
  Tv,
} from 'lucide-react'
import { worksApi, type TMDbSearchResult } from '../../api/works'
import { useI18n } from '../../i18n/useI18n'
import type { Work } from '../../types'

interface TMDbImportPanelProps {
  onImported: (work: Work) => void
  onError: () => void
}

const IMAGE_BASE_URL = 'https://image.tmdb.org/t/p'

type MediaTypeFilter = 'movie' | 'tv' | 'both'

function mediaTypeLabel(type: 'movie' | 'tv', labels: { movie: string; tv: string }) {
  return type === 'movie' ? labels.movie : labels.tv
}

export function TMDbImportPanel({ onImported, onError }: TMDbImportPanelProps) {
  const { t } = useI18n()
  const [draftQuery, setDraftQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [mediaTypeFilter, setMediaTypeFilter] = useState<MediaTypeFilter>('both')
  const [importingResultId, setImportingResultId] = useState<string | null>(null)

  const { data: tmdbConfig, isLoading: isConfigLoading } = useQuery({
    queryKey: ['tmdb-config'],
    queryFn: worksApi.tmdbGetConfig,
  })

  const hasApiKey = useMemo(
    () => Boolean(tmdbConfig?.ok && (tmdbConfig.api_key_v3_set || tmdbConfig.api_key_v4_set)),
    [tmdbConfig],
  )

  const mediaType = mediaTypeFilter === 'both' ? undefined : mediaTypeFilter
  const canSearch = draftQuery.trim().length > 0 && hasApiKey
  const hasSubmitted = submittedQuery.trim().length > 0

  const {
    data: searchResults,
    isLoading: isSearching,
    isError: isSearchError,
  } = useQuery({
    queryKey: ['tmdb-search', submittedQuery, mediaType],
    queryFn: () => worksApi.tmdbSearch(submittedQuery, mediaType),
    enabled: hasSubmitted && hasApiKey,
    staleTime: 5 * 60 * 1000,
  })

  const importMutation = useMutation({
    mutationFn: (result: TMDbSearchResult) =>
      worksApi.tmdbImport(result.tmdb_id, result.media_type),
    onMutate: result => {
      setImportingResultId(`${result.media_type}-${result.tmdb_id}`)
    },
    onSuccess: response => {
      if (response.ok && response.work) {
        onImported(response.work)
        return
      }
      onError()
    },
    onError,
    onSettled: () => {
      setImportingResultId(null)
    },
  })

  function handleSearch() {
    const nextQuery = draftQuery.trim()
    if (!nextQuery || !hasApiKey) return
    setSubmittedQuery(nextQuery)
  }

  const typeOptions: Array<{
    value: MediaTypeFilter
    label: string
    icon: typeof Film
  }> = [
    { value: 'movie', label: t.worksLibrary.tmdb.search.movie, icon: Film },
    { value: 'tv', label: t.worksLibrary.tmdb.search.tv, icon: Tv },
    { value: 'both', label: t.worksLibrary.tmdb.search.all, icon: Clapperboard },
  ]

  const showNoResults =
    hasSubmitted &&
    !isSearching &&
    searchResults?.ok &&
    searchResults.results.length === 0
  const showSearchError =
    hasSubmitted &&
    !isSearching &&
    (isSearchError || searchResults?.ok === false)

  return (
    <div
      data-testid="works-tmdb-panel"
      className="space-y-4"
    >
      {isConfigLoading ? (
        <div className="flex items-center gap-2 py-3 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin text-[#3b5bdb]" />
          {t.common.loading}
        </div>
      ) : !hasApiKey ? (
        <div
          data-testid="works-tmdb-key-missing"
          className="border-l-2 border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          <div className="flex items-start gap-2.5">
            <AlertCircle size={17} className="mt-0.5 shrink-0" />
            <div>
              <div className="font-medium">{t.worksLibrary.tmdb.apiKeyMissing}</div>
              <div className="mt-0.5 text-xs text-amber-700">
                {t.worksLibrary.tmdb.apiKeyHint}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_auto_auto]">
            <div className="relative min-w-0">
              <Search
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                data-testid="works-tmdb-query"
                type="search"
                value={draftQuery}
                onChange={event => setDraftQuery(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    handleSearch()
                  }
                }}
                placeholder={t.worksLibrary.tmdb.search.placeholder}
                className="h-10 w-full rounded-lg border border-[#dbe3f0] bg-white pl-10 pr-3 text-sm text-slate-800 placeholder:text-slate-400 transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/15"
              />
            </div>

            <div className="grid h-10 grid-cols-3 overflow-hidden rounded-lg border border-[#dbe3f0] bg-[#f8fafc]">
              {typeOptions.map(({ value, label, icon: Icon }) => {
                const selected = mediaTypeFilter === value
                return (
                  <button
                    key={value}
                    type="button"
                    data-testid={`works-tmdb-type-${value}`}
                    onClick={() => setMediaTypeFilter(value)}
                    className={`inline-flex min-w-[72px] items-center justify-center gap-1.5 px-3 text-sm font-medium transition-all ${
                      selected
                        ? 'bg-white text-[#3b5bdb] shadow-[0_1px_2px_rgba(15,23,42,.08)]'
                        : 'text-slate-500 hover:bg-white/70 hover:text-slate-800'
                    }`}
                    aria-pressed={selected}
                  >
                    <Icon size={14} />
                    {label}
                  </button>
                )
              })}
            </div>

            <button
              type="button"
              data-testid="works-tmdb-submit"
              onClick={handleSearch}
              disabled={!canSearch || isSearching}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-[#3b5bdb] px-4 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.3)] transition-all hover:bg-[#3451c7] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSearching ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
              {t.worksLibrary.tmdb.search.searchButton}
            </button>
          </div>

          <div className="mt-4 border-t border-[#edf1f7] pt-4">
            {!hasSubmitted && (
              <div className="flex min-h-[92px] items-center justify-center text-sm text-slate-400">
                {t.worksLibrary.tmdb.search.readyState}
              </div>
            )}

            {isSearching && (
              <div className="flex min-h-[92px] items-center justify-center gap-2 text-sm text-slate-500">
                <Loader2 size={16} className="animate-spin text-[#3b5bdb]" />
                {t.common.loading}
              </div>
            )}

            {showNoResults && (
              <div
                data-testid="works-tmdb-empty"
                className="flex min-h-[92px] items-center justify-center text-sm text-slate-400"
              >
                {t.worksLibrary.tmdb.search.noResults}
              </div>
            )}

            {showSearchError && (
              <div
                data-testid="works-tmdb-error"
                className="border-l-2 border-rose-400 bg-rose-50 px-3 py-2.5 text-sm text-rose-700"
              >
                {searchResults?.error || t.worksLibrary.tmdb.search.error}
              </div>
            )}

            {!isSearching && searchResults?.ok && searchResults.results.length > 0 && (
              <div className="grid gap-3 xl:grid-cols-2">
                {searchResults.results.map(result => {
                  const resultKey = `${result.media_type}-${result.tmdb_id}`
                  const importing = importingResultId === resultKey
                  return (
                    <article
                      key={resultKey}
                      data-testid={`works-tmdb-result-${resultKey}`}
                      className="grid grid-cols-[52px_minmax(0,1fr)] gap-3 rounded-lg border border-[#edf1f7] bg-white p-2.5 transition-all hover:border-[#cdd7e6] hover:bg-[#fbfcff] sm:grid-cols-[52px_minmax(0,1fr)_auto]"
                    >
                      <div className="h-[78px] w-[52px] overflow-hidden rounded-md bg-slate-100">
                        {result.poster_path ? (
                          <img
                            src={`${IMAGE_BASE_URL}/w154${result.poster_path}`}
                            alt={result.title}
                            className="h-full w-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="flex h-full w-full items-center justify-center text-slate-300">
                            {result.media_type === 'movie' ? <Film size={22} /> : <Tv size={22} />}
                          </div>
                        )}
                      </div>
                      <div className="min-w-0 py-0.5">
                        <div className="flex min-w-0 items-center gap-2">
                          <h3 className="truncate text-sm font-semibold text-slate-900">
                            {result.title}
                          </h3>
                          {result.year && (
                            <span className="shrink-0 text-xs text-slate-400">
                              {result.year}
                            </span>
                          )}
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600">
                            {mediaTypeLabel(result.media_type, t.worksLibrary.tmdb.search)}
                          </span>
                          {result.vote_average > 0 && (
                            <span className="tabular-nums">
                              {result.vote_average.toFixed(1)}
                            </span>
                          )}
                        </div>
                        <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-slate-500">
                          {result.overview || t.worksLibrary.card.overviewFallback}
                        </p>
                      </div>
                      <div className="col-span-2 flex items-end justify-end sm:col-span-1">
                        <button
                          type="button"
                          data-testid={`works-tmdb-import-${resultKey}`}
                          onClick={() => importMutation.mutate(result)}
                          disabled={importMutation.isPending}
                          className="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-[#dbe3f0] bg-white px-3 text-xs font-semibold text-[#3b5bdb] transition-all hover:border-[#3b5bdb]/40 hover:bg-[#3b5bdb]/5 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {importing ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Download size={13} />
                          )}
                          {importing ? t.common.loading : t.worksLibrary.tmdb.search.importButton}
                        </button>
                      </div>
                    </article>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
