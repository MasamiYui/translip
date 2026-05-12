import { useState, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, Film, Tv, Download, AlertCircle } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import { worksApi, type TMDbSearchResult } from '../../api/works'
import type { Work } from '../../types'

export interface TMDbSearchPanelProps {
  onImport: (work: Work) => void
  onCancel: () => void
}

const IMAGE_BASE_URL = 'https://image.tmdb.org/t/p'

export function TMDbSearchPanel({ onImport, onCancel }: TMDbSearchPanelProps) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedType, setSelectedType] = useState<'movie' | 'tv' | 'both'>('both')
  const [selectedResult, setSelectedResult] = useState<TMDbSearchResult | null>(null)
  const [isImporting, setIsImporting] = useState(false)

  const { data: tmdbConfig } = useQuery({
    queryKey: ['tmdb-config'],
    queryFn: worksApi.tmdbGetConfig,
  })

  const hasApiKey = useMemo(() => {
    return tmdbConfig?.ok && (tmdbConfig.api_key_v3_set || tmdbConfig.api_key_v4_set)
  }, [tmdbConfig])

  const mediaType = useMemo(() => {
    if (selectedType === 'both') return undefined
    return selectedType
  }, [selectedType])

  const { data: searchResults, isLoading: isSearching } = useQuery({
    queryKey: ['tmdb-search', searchQuery, mediaType],
    queryFn: () => worksApi.tmdbSearch(searchQuery, mediaType),
    enabled: !!searchQuery.trim() && hasApiKey,
    staleTime: 5 * 60 * 1000,
  })

  const { data: selectedDetails } = useQuery({
    queryKey: ['tmdb-details', selectedResult?.tmdb_id, selectedResult?.media_type],
    queryFn: () => worksApi.tmdbDetails(selectedResult!.tmdb_id, selectedResult!.media_type),
    enabled: !!selectedResult,
  })

  const importMutation = useMutation({
    mutationFn: () => {
      if (!selectedResult) throw new Error('No result selected')
      return worksApi.tmdbImport(selectedResult.tmdb_id, selectedResult.media_type)
    },
    onSuccess: (response) => {
      if (response.ok && response.work) {
        onImport(response.work)
        queryClient.invalidateQueries({ queryKey: ['works'] })
      }
      setIsImporting(false)
    },
    onError: () => {
      setIsImporting(false)
    },
  })

  const handleImport = () => {
    if (!selectedResult) return
    setIsImporting(true)
    importMutation.mutate()
  }

  if (!hasApiKey) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{t.worksLibrary.tmdb.search.title}</h2>
          <button
            onClick={onCancel}
            className="text-sm text-slate-500 hover:text-slate-700"
          >
            {t.common.cancel}
          </button>
        </div>
        <div className="border-l-2 border-amber-400 bg-amber-50 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="mt-0.5 shrink-0 text-amber-600" />
            <div>
              <p className="font-medium text-amber-800">{t.worksLibrary.tmdb.apiKeyMissing}</p>
              <p className="mt-1 text-sm text-amber-700">{t.worksLibrary.tmdb.apiKeyHint}</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">{t.worksLibrary.tmdb.search.title}</h2>
        <button
          onClick={onCancel}
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          {t.common.cancel}
        </button>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t.worksLibrary.tmdb.search.placeholder}
            className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
        </div>
        <div className="flex rounded-lg border border-slate-200 overflow-hidden">
          {(['movie', 'tv', 'both'] as const).map((type) => (
            <button
              key={type}
              onClick={() => setSelectedType(type)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm transition-colors ${
                selectedType === type
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              {type === 'movie' && <Film size={16} />}
              {type === 'tv' && <Tv size={16} />}
              {type === 'both' && <Film size={16} />}
              {type === 'movie' && t.worksLibrary.tmdb.search.movie}
              {type === 'tv' && t.worksLibrary.tmdb.search.tv}
              {type === 'both' && t.worksLibrary.tmdb.search.all}
            </button>
          ))}
        </div>
      </div>

      {searchQuery && (
        <div className="flex-1 overflow-auto">
          {isSearching ? (
            <div className="flex items-center justify-center py-8 text-slate-400">
              {t.common.loading}
            </div>
          ) : searchResults?.ok ? (
            <div className="grid gap-2">
              {searchResults.results.length === 0 ? (
                <div className="text-center py-8 text-slate-400">
                  {t.worksLibrary.tmdb.search.noResults}
                </div>
              ) : (
                searchResults.results.map((result) => (
                  <button
                    key={result.tmdb_id}
                    onClick={() => setSelectedResult(result)}
                    className={`flex gap-3 rounded-lg border p-3 text-left transition-colors ${
                      selectedResult?.tmdb_id === result.tmdb_id
                        ? 'border-blue-300 bg-blue-50'
                        : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="h-16 w-11 shrink-0 overflow-hidden rounded">
                      {result.poster_path ? (
                        <img
                          src={`${IMAGE_BASE_URL}/w92${result.poster_path}`}
                          alt={result.title}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-slate-100">
                          {result.media_type === 'movie' ? (
                            <Film size={24} className="text-slate-300" />
                          ) : (
                            <Tv size={24} className="text-slate-300" />
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col justify-center">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-900">{result.title}</span>
                        {result.year && (
                          <span className="text-sm text-slate-500">({result.year})</span>
                        )}
                      </div>
                      <p className="line-clamp-2 text-sm text-slate-500">{result.overview}</p>
                    </div>
                  </button>
                ))
              )}
            </div>
          ) : (
            <div className="border-l-2 border-rose-400 bg-rose-50 p-4 text-sm text-rose-600">
              {searchResults?.error || t.worksLibrary.tmdb.search.error}
            </div>
          )}
        </div>
      )}

      {selectedResult && selectedDetails?.ok && (
        <div className="border-t border-slate-200 pt-4">
          <div className="flex gap-4">
            <div className="h-24 w-16 shrink-0 overflow-hidden rounded-lg">
              {selectedDetails.details?.poster_path ? (
                <img
                  src={`${IMAGE_BASE_URL}/w154${selectedDetails.details.poster_path}`}
                  alt={selectedDetails.details.title}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-slate-100">
                  {selectedDetails.details?.media_type === 'movie' ? (
                    <Film size={32} className="text-slate-300" />
                  ) : (
                    <Tv size={32} className="text-slate-300" />
                  )}
                </div>
              )}
            </div>
            <div className="flex flex-1 flex-col justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">{selectedDetails.details?.title}</h3>
                <div className="mt-1 flex flex-wrap gap-2">
                  {selectedDetails.details?.genres.slice(0, 3).map((genre) => (
                    <span
                      key={genre}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                    >
                      {genre}
                    </span>
                  ))}
                </div>
                <p className="mt-2 line-clamp-2 text-sm text-slate-600">
                  {selectedDetails.details?.overview}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500">
                  {selectedDetails.details?.cast.length} {t.worksLibrary.tmdb.search.castCount}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={handleImport}
            disabled={isImporting}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Download size={18} />
            {isImporting ? t.common.loading : t.worksLibrary.tmdb.search.importButton}
          </button>
        </div>
      )}
    </div>
  )
}
