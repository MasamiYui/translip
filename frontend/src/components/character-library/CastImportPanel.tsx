import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Users, Check, UserPlus, AlertCircle, ArrowRight } from 'lucide-react'
import { useI18n } from '../../i18n/useI18n'
import { worksApi, type CastPreviewMember } from '../../api/works'

export interface CastImportPanelProps {
  workId: string
  tmdbId: number | null
  mediaType: 'movie' | 'tv'
  onImported: () => void
  onClose: () => void
}

const IMAGE_BASE_URL = 'https://image.tmdb.org/t/p'

export function CastImportPanel({ workId, tmdbId, mediaType, onImported, onClose }: CastImportPanelProps) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [showResult, setShowResult] = useState(false)
  const [importResult, setImportResult] = useState<{ success: boolean; count: number; skipped: number } | null>(null)

  const { data: castData, isLoading } = useQuery({
    queryKey: ['cast-preview', workId, tmdbId, mediaType],
    queryFn: () => {
      if (!tmdbId) return Promise.resolve({ ok: false, cast: [] })
      return worksApi.getCastPreview(workId, tmdbId, mediaType)
    },
    enabled: !!tmdbId && !showResult,
  })

  const importMutation = useMutation({
    mutationFn: () => worksApi.importCast(workId, selectedIds),
    onSuccess: (response) => {
      if (response.ok) {
        setImportResult({
          success: true,
          count: response.imported.length,
          skipped: response.skipped.length,
        })
        queryClient.invalidateQueries({ queryKey: ['personas'] })
        queryClient.invalidateQueries({ queryKey: ['works'] })
      } else {
        setImportResult({ success: false, count: 0, skipped: 0 })
      }
      setShowResult(true)
    },
  })

  const cast: CastPreviewMember[] = castData?.ok ? castData.cast : []

  const toggleSelect = (tmdbId: number) => {
    setSelectedIds(prev =>
      prev.includes(tmdbId) ? prev.filter(id => id !== tmdbId) : [...prev, tmdbId]
    )
  }

  const selectAll = () => {
    setSelectedIds(cast.map(m => m.tmdb_id))
  }

  const deselectAll = () => {
    setSelectedIds([])
  }

  const handleImport = () => {
    if (selectedIds.length === 0) return
    importMutation.mutate()
  }

  const handleRetry = () => {
    setShowResult(false)
    setImportResult(null)
    setSelectedIds([])
  }

  if (showResult && importResult) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{t.worksLibrary.castImport.title}</h2>
          <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700">
            {t.common.close}
          </button>
        </div>

        {importResult.success ? (
          <div className="flex flex-col items-center justify-center py-8">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
              <Check size={32} className="text-emerald-600" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900">
              {t.worksLibrary.castImport.success}
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              {t.worksLibrary.castImport.importedCount(importResult.count)}
              {importResult.skipped > 0 && (
                <span className="ml-2 text-slate-400">
                  {t.worksLibrary.castImport.skippedCount(importResult.skipped)}
                </span>
              )}
            </p>
            <div className="mt-6 flex gap-3">
              <button
                onClick={handleRetry}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
              >
                {t.worksLibrary.castImport.importMore}
              </button>
              <button
                onClick={onImported}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
              >
                {t.worksLibrary.castImport.viewCharacters}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-rose-100">
              <AlertCircle size={32} className="text-rose-600" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900">
              {t.worksLibrary.castImport.failure}
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              {t.worksLibrary.castImport.failureHint}
            </p>
            <button
              onClick={handleRetry}
              className="mt-6 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              {t.common.retry}
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">{t.worksLibrary.castImport.title}</h2>
        <button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-700">
          {t.common.close}
        </button>
      </div>

      {!tmdbId && (
        <div className="border-l-2 border-amber-400 bg-amber-50 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="mt-0.5 shrink-0 text-amber-600" />
            <div>
              <p className="font-medium text-amber-800">{t.worksLibrary.castImport.noTmdb}</p>
              <p className="mt-1 text-sm text-amber-700">{t.worksLibrary.castImport.noTmdbHint}</p>
            </div>
          </div>
        </div>
      )}

      {tmdbId && (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <Users size={16} />
              {t.worksLibrary.castImport.castCount(cast.length)}
            </div>
            <div className="flex gap-2">
              <button
                onClick={selectAll}
                disabled={cast.length === 0}
                className="rounded border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
              >
                {t.worksLibrary.castImport.selectAll}
              </button>
              <button
                onClick={deselectAll}
                disabled={selectedIds.length === 0}
                className="rounded border border-slate-200 px-2 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
              >
                {t.worksLibrary.castImport.deselectAll}
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            {isLoading ? (
              <div className="flex items-center justify-center py-8 text-slate-400">
                {t.common.loading}
              </div>
            ) : cast.length === 0 ? (
              <div className="text-center py-8 text-slate-400">
                {t.worksLibrary.castImport.noCast}
              </div>
            ) : (
              <div className="space-y-2">
                {cast.map((member) => (
                  <div
                    key={member.tmdb_id}
                    className={`flex items-center gap-3 rounded-lg border p-3 transition-colors ${
                      selectedIds.includes(member.tmdb_id)
                        ? 'border-blue-300 bg-blue-50'
                        : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <button
                      onClick={() => toggleSelect(member.tmdb_id)}
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors ${
                        selectedIds.includes(member.tmdb_id)
                          ? 'border-blue-500 bg-blue-500'
                          : 'border-slate-300'
                      }`}
                    >
                      {selectedIds.includes(member.tmdb_id) && (
                        <Check size={12} className="text-white" />
                      )}
                    </button>
                    <div className="h-10 w-10 shrink-0 overflow-hidden rounded">
                      {member.profile_url ? (
                        <img
                          src={member.profile_url}
                          alt={member.actor_name}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-slate-100">
                          <Users size={18} className="text-slate-300" />
                        </div>
                      )}
                    </div>
                    <div className="flex flex-1 flex-col">
                      <span className="font-medium text-slate-900">
                        {member.character_name || member.actor_name}
                      </span>
                      {member.actor_name && member.actor_name !== member.character_name && (
                        <span className="text-xs text-slate-500">{member.actor_name}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={handleImport}
            disabled={selectedIds.length === 0 || importMutation.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 py-2.5 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <UserPlus size={18} />
            {importMutation.isPending ? (
              t.common.loading
            ) : (
              t.worksLibrary.castImport.importButton(selectedIds.length)
            )}
            <ArrowRight size={16} />
          </button>
        </>
      )}
    </div>
  )
}
