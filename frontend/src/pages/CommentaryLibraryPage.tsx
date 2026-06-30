import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AudioLines,
  Check,
  Copy,
  Loader2,
  Music,
  Pause,
  Play,
  Search,
  UserRound,
} from 'lucide-react'
import {
  bgmPresetPreviewUrl,
  configApi,
  narratorVoicePreviewUrl,
  type BgmPresetInfo,
  type NarratorVoiceInfo,
} from '../api/config'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { useI18n } from '../i18n/useI18n'

type Tab = 'voices' | 'bgm'

const NATIVE_LANGUAGE_LABELS: Record<string, { zh: string; en: string }> = {
  zh: { zh: '中文', en: 'Chinese' },
  en: { zh: '英文', en: 'English' },
  ja: { zh: '日语', en: 'Japanese' },
  ko: { zh: '韩语', en: 'Korean' },
}

const MOOD_TONES: Record<string, { bg: string; text: string }> = {
  suspense: { bg: 'bg-indigo-50', text: 'text-indigo-600' },
  hype: { bg: 'bg-rose-50', text: 'text-rose-600' },
  warm: { bg: 'bg-amber-50', text: 'text-amber-600' },
  documentary: { bg: 'bg-sky-50', text: 'text-sky-600' },
  comedy: { bg: 'bg-emerald-50', text: 'text-emerald-600' },
  action: { bg: 'bg-orange-50', text: 'text-orange-600' },
  'crime-investigation': { bg: 'bg-slate-100', text: 'text-slate-700' },
  'gufeng-mystery': { bg: 'bg-stone-100', text: 'text-stone-700' },
  'epic-trailer': { bg: 'bg-red-50', text: 'text-red-600' },
}

function moodTone(mood: string) {
  return MOOD_TONES[mood] ?? { bg: 'bg-violet-50', text: 'text-violet-600' }
}

export function CommentaryLibraryPage() {
  const { t, locale } = useI18n()
  const isZh = locale === 'zh-CN'
  const c = t.commentaryLibrary

  const [tab, setTab] = useState<Tab>('voices')
  const [search, setSearch] = useState('')
  const [languageFilter, setLanguageFilter] = useState<string>('')
  const [genderFilter, setGenderFilter] = useState<string>('')
  const [moodFilter, setMoodFilter] = useState<string>('')

  const [previewingId, setPreviewingId] = useState<string | null>(null)
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const copyTimerRef = useRef<number | null>(null)

  const voicesQuery = useQuery({
    queryKey: ['narrator-voices'],
    queryFn: configApi.narratorVoices,
    staleTime: 30_000,
  })
  const bgmQuery = useQuery({
    queryKey: ['bgm-presets'],
    queryFn: configApi.bgmPresets,
    staleTime: 30_000,
  })

  const voices = voicesQuery.data ?? []
  const bgmPresets = bgmQuery.data ?? []

  const releaseObjectUrl = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
  }

  const cancelInflight = () => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }

  const stopPreview = () => {
    cancelInflight()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.removeAttribute('src')
      audioRef.current.load()
    }
    releaseObjectUrl()
    setPreviewingId(null)
    setPreviewLoadingId(null)
  }

  useEffect(() => {
    return () => {
      cancelInflight()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.removeAttribute('src')
      }
      releaseObjectUrl()
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    stopPreview()
    setPreviewError(null)
  }, [tab])

  const triggerPreview = async (id: string, url: string) => {
    if (previewingId === id || previewLoadingId === id) {
      stopPreview()
      return
    }
    cancelInflight()
    releaseObjectUrl()
    setPreviewError(null)
    setPreviewLoadingId(id)
    setPreviewingId(null)

    if (!audioRef.current) {
      audioRef.current = new Audio()
      audioRef.current.addEventListener('ended', () => setPreviewingId(null))
    }
    audioRef.current.pause()

    const controller = new AbortController()
    abortRef.current = controller

    let response: Response
    try {
      response = await fetch(url, {
        signal: controller.signal,
        headers: { Accept: 'audio/wav' },
      })
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      setPreviewError(
        isZh
          ? '无法连接到后端服务，请确认服务正在运行'
          : 'Unable to reach backend; please check the server is running',
      )
      setPreviewLoadingId(null)
      return
    }
    if (abortRef.current !== controller) return
    if (!response.ok) {
      let detail = ''
      try {
        const data = (await response.clone().json()) as { detail?: unknown }
        if (typeof data?.detail === 'string') detail = data.detail
      } catch {
        try {
          detail = (await response.text()).slice(0, 240)
        } catch {
          /* noop */
        }
      }
      const fallback = isZh
        ? `试听生成失败（HTTP ${response.status}）`
        : `Preview failed (HTTP ${response.status})`
      setPreviewError(detail ? `${fallback}：${detail}` : fallback)
      setPreviewLoadingId(null)
      return
    }
    let blob: Blob
    try {
      blob = await response.blob()
    } catch {
      setPreviewError(
        isZh ? '试听音频解析失败，请稍后再试' : 'Failed to decode preview audio',
      )
      setPreviewLoadingId(null)
      return
    }
    if (abortRef.current !== controller) return
    const objectUrl = URL.createObjectURL(blob)
    objectUrlRef.current = objectUrl
    audioRef.current.src = objectUrl
    try {
      await audioRef.current.play()
      if (abortRef.current !== controller) return
      setPreviewingId(id)
      setPreviewLoadingId(null)
    } catch (err) {
      if ((err as DOMException)?.name === 'AbortError') return
      setPreviewError(
        isZh
          ? `试听播放失败：${(err as Error).message || 'unknown error'}`
          : `Preview playback failed: ${(err as Error).message || 'unknown error'}`,
      )
      setPreviewingId(null)
      setPreviewLoadingId(null)
    }
  }

  const copyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = id
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      try {
        document.execCommand('copy')
      } catch {
        /* noop */
      }
      document.body.removeChild(textarea)
    }
    setCopiedId(id)
    if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current)
    copyTimerRef.current = window.setTimeout(() => setCopiedId(null), 1500)
  }

  const languageOptions = useMemo(() => {
    const set = new Set<string>()
    voices.forEach(v => {
      if (v.native_language) set.add(v.native_language)
    })
    return Array.from(set)
  }, [voices])

  const genderOptions = useMemo(() => {
    const set = new Set<string>()
    voices.forEach(v => {
      if (v.gender) set.add(v.gender)
    })
    return Array.from(set)
  }, [voices])

  const moodOptions = useMemo(() => {
    const set = new Set<string>()
    bgmPresets.forEach(p => {
      if (p.mood) set.add(p.mood)
    })
    return Array.from(set)
  }, [bgmPresets])

  const filteredVoices = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return voices.filter(v => {
      if (languageFilter && v.native_language !== languageFilter) return false
      if (genderFilter && v.gender !== genderFilter) return false
      if (!kw) return true
      const haystack = [
        v.id,
        v.name_zh,
        v.name_en,
        v.description_zh,
        v.description_en,
        v.native_language,
        v.gender,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return haystack.includes(kw)
    })
  }, [voices, search, languageFilter, genderFilter])

  const filteredBgm = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return bgmPresets.filter(p => {
      if (moodFilter && p.mood !== moodFilter) return false
      if (!kw) return true
      const haystack = [
        p.id,
        p.name_zh,
        p.name_en,
        p.description_zh,
        p.description_en,
        p.mood,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return haystack.includes(kw)
    })
  }, [bgmPresets, search, moodFilter])

  const isVoiceLoading = voicesQuery.isLoading
  const isBgmLoading = bgmQuery.isLoading

  const totalCount = tab === 'voices' ? filteredVoices.length : filteredBgm.length

  const renderVoiceRow = (voice: NarratorVoiceInfo) => {
    const name = isZh ? voice.name_zh : voice.name_en
    const description = isZh ? voice.description_zh : voice.description_en
    const langLabel = voice.native_language
      ? NATIVE_LANGUAGE_LABELS[voice.native_language]?.[isZh ? 'zh' : 'en'] ?? voice.native_language
      : null
    const isViral = voice.id.startsWith('narrator-recap-')
    const isPreviewing = previewingId === voice.id
    const isLoading = previewLoadingId === voice.id
    const isCopied = copiedId === voice.id

    return (
      <tr
        key={voice.id}
        data-testid={`commentary-voice-row-${voice.id}`}
        className="border-t border-[#e5e7eb] text-slate-700 transition-colors hover:bg-[#f9fafb]"
      >
        <td className="px-4 py-3">
          <button
            type="button"
            data-testid={`commentary-voice-preview-${voice.id}`}
            onClick={() => triggerPreview(voice.id, narratorVoicePreviewUrl(voice.id))}
            aria-label={isPreviewing ? c.actions.stop : c.actions.preview}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-full text-white shadow-sm transition-colors ${
              isPreviewing ? 'bg-rose-500 hover:bg-rose-600' : 'bg-[#3b5bdb] hover:bg-[#3046b8]'
            }`}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isPreviewing ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </button>
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#eff6ff] text-[#3b5bdb]">
              <UserRound size={16} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-medium text-slate-800">{name}</span>
                {isViral && (
                  <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                    {c.badges.viral}
                  </span>
                )}
              </div>
              {description && (
                <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{description}</div>
              )}
            </div>
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex flex-wrap items-center gap-1.5">
            {langLabel && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                {langLabel}
              </span>
            )}
            {voice.gender && (
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  voice.gender === 'male'
                    ? 'bg-sky-50 text-sky-600'
                    : 'bg-pink-50 text-pink-600'
                }`}
              >
                {voice.gender === 'male' ? c.filters.male : c.filters.female}
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <code className="font-mono text-[11px] text-slate-500">{voice.id}</code>
        </td>
        <td className="px-4 py-3 align-top text-right">
          <button
            type="button"
            data-testid={`commentary-voice-copy-${voice.id}`}
            onClick={() => copyId(voice.id)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
          >
            {isCopied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
            {isCopied ? c.actions.copied : c.actions.copyId}
          </button>
        </td>
      </tr>
    )
  }

  const renderBgmRow = (preset: BgmPresetInfo) => {
    const name = isZh ? preset.name_zh : preset.name_en
    const description = isZh ? preset.description_zh : preset.description_en
    const tone = moodTone(preset.mood)
    const isPreviewing = previewingId === preset.id
    const isLoading = previewLoadingId === preset.id
    const isCopied = copiedId === preset.id

    return (
      <tr
        key={preset.id}
        data-testid={`commentary-bgm-row-${preset.id}`}
        className="border-t border-[#e5e7eb] text-slate-700 transition-colors hover:bg-[#f9fafb]"
      >
        <td className="px-4 py-3">
          <button
            type="button"
            data-testid={`commentary-bgm-preview-${preset.id}`}
            onClick={() => triggerPreview(preset.id, bgmPresetPreviewUrl(preset.id))}
            aria-label={isPreviewing ? c.actions.stop : c.actions.preview}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-full text-white shadow-sm transition-colors ${
              isPreviewing ? 'bg-rose-500 hover:bg-rose-600' : 'bg-[#7c3aed] hover:bg-[#6d28d9]'
            }`}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isPreviewing ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </button>
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex items-start gap-3">
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${tone.bg} ${tone.text}`}>
              <Music size={16} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-sm font-medium text-slate-800">{name}</span>
              </div>
              {description && (
                <div className="mt-0.5 line-clamp-2 text-xs text-slate-500">{description}</div>
              )}
              {preset.attribution && (
                <div className="mt-1 text-[11px] text-slate-400">
                  {preset.license ? `[${preset.license}] ` : ''}
                  {preset.attribution}
                </div>
              )}
            </div>
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone.bg} ${tone.text}`}>
              {preset.mood}
            </span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
              {isZh ? `增益 ${preset.gain_db}dB` : `Gain ${preset.gain_db}dB`}
            </span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
              {isZh ? `闪避 ${preset.duck_db}dB` : `Duck ${preset.duck_db}dB`}
            </span>
          </div>
        </td>
        <td className="px-4 py-3 align-top">
          <code className="font-mono text-[11px] text-slate-500">{preset.id}</code>
        </td>
        <td className="px-4 py-3 align-top text-right">
          <button
            type="button"
            data-testid={`commentary-bgm-copy-${preset.id}`}
            onClick={() => copyId(preset.id)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-xs font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
          >
            {isCopied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
            {isCopied ? c.actions.copied : c.actions.copyId}
          </button>
        </td>
      </tr>
    )
  }

  const showFiltered =
    (tab === 'voices' && filteredVoices.length === 0 && voices.length > 0) ||
    (tab === 'bgm' && filteredBgm.length === 0 && bgmPresets.length > 0)

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <AudioLines size={17} className="text-[#3b5bdb]" />
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{c.title}</h1>
        </div>
        <span
          data-testid="commentary-library-count"
          className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600"
        >
          {c.countHint(totalCount)}
        </span>
        <p className="basis-full text-xs text-slate-500">{c.subtitle}</p>
      </div>

      <div
        data-testid="commentary-library-toolbar"
        className="mb-4 flex flex-wrap items-center gap-3"
      >
        <div className="relative flex-1 min-w-[240px]">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            data-testid="commentary-library-search"
            type="search"
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder={tab === 'voices' ? c.placeholders.searchVoice : c.placeholders.searchBgm}
            className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
          />
        </div>

        <div
          data-testid="commentary-library-tabs"
          className="inline-flex rounded-lg border border-[#e5e7eb] bg-white p-0.5 shadow-sm"
          role="tablist"
        >
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'voices'}
            data-testid="commentary-tab-voices"
            onClick={() => setTab('voices')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              tab === 'voices'
                ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <UserRound size={13} />
            {c.tabs.voices}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'bgm'}
            data-testid="commentary-tab-bgm"
            onClick={() => setTab('bgm')}
            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              tab === 'bgm'
                ? 'bg-[#7c3aed]/10 text-[#7c3aed]'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Music size={13} />
            {c.tabs.bgm}
          </button>
        </div>

        {tab === 'voices' && (
          <>
            <select
              data-testid="commentary-filter-language"
              value={languageFilter}
              onChange={event => setLanguageFilter(event.target.value)}
              className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
            >
              <option value="">{c.filters.allLanguages}</option>
              {languageOptions.map(lang => (
                <option key={lang} value={lang}>
                  {NATIVE_LANGUAGE_LABELS[lang]?.[isZh ? 'zh' : 'en'] ?? lang}
                </option>
              ))}
            </select>
            <select
              data-testid="commentary-filter-gender"
              value={genderFilter}
              onChange={event => setGenderFilter(event.target.value)}
              className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
            >
              <option value="">{c.filters.allGenders}</option>
              {genderOptions.map(gender => (
                <option key={gender} value={gender}>
                  {gender === 'male' ? c.filters.male : gender === 'female' ? c.filters.female : gender}
                </option>
              ))}
            </select>
          </>
        )}

        {tab === 'bgm' && (
          <select
            data-testid="commentary-filter-mood"
            value={moodFilter}
            onChange={event => setMoodFilter(event.target.value)}
            className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
          >
            <option value="">{c.filters.allMoods}</option>
            {moodOptions.map(mood => (
              <option key={mood} value={mood}>
                {mood}
              </option>
            ))}
          </select>
        )}
      </div>

      {previewError && (
        <div
          data-testid="commentary-library-error"
          className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700"
          role="alert"
        >
          {previewError}
        </div>
      )}

      <div data-testid="commentary-library-main" className="flex flex-col gap-3">
        <div
          data-testid="commentary-library-list"
          className="overflow-x-auto rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]"
        >
          {tab === 'voices' ? (
            isVoiceLoading ? (
              <div className="px-6 py-10 text-center text-sm text-slate-400">
                {t.common.loading}
              </div>
            ) : voices.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <div className="text-sm font-medium text-slate-700">{c.empty.voicesTitle}</div>
                <div className="mt-1 text-xs text-slate-500">{c.empty.voicesDescription}</div>
              </div>
            ) : showFiltered ? (
              <div className="px-6 py-10 text-center text-sm text-slate-400">{c.empty.filtered}</div>
            ) : (
              <table className="w-full min-w-[760px] border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="w-16 px-4 py-2 text-left font-medium">{c.columns.preview}</th>
                    <th className="px-4 py-2 text-left font-medium">{c.columns.name}</th>
                    <th className="px-4 py-2 text-left font-medium">{c.columns.tags}</th>
                    <th className="px-4 py-2 text-left font-medium">{c.columns.id}</th>
                    <th className="px-4 py-2 text-right font-medium">{c.columns.actions}</th>
                  </tr>
                </thead>
                <tbody>{filteredVoices.map(renderVoiceRow)}</tbody>
              </table>
            )
          ) : isBgmLoading ? (
            <div className="px-6 py-10 text-center text-sm text-slate-400">{t.common.loading}</div>
          ) : bgmPresets.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <div className="text-sm font-medium text-slate-700">{c.empty.bgmTitle}</div>
              <div className="mt-1 text-xs text-slate-500">{c.empty.bgmDescription}</div>
            </div>
          ) : showFiltered ? (
            <div className="px-6 py-10 text-center text-sm text-slate-400">{c.empty.filtered}</div>
          ) : (
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <thead>
                <tr className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="w-16 px-4 py-2 text-left font-medium">{c.columns.preview}</th>
                  <th className="px-4 py-2 text-left font-medium">{c.columns.name}</th>
                  <th className="px-4 py-2 text-left font-medium">{c.columns.tags}</th>
                  <th className="px-4 py-2 text-left font-medium">{c.columns.id}</th>
                  <th className="px-4 py-2 text-right font-medium">{c.columns.actions}</th>
                </tr>
              </thead>
              <tbody>{filteredBgm.map(renderBgmRow)}</tbody>
            </table>
          )}
        </div>

        <p className="text-[11px] text-slate-400">
          {tab === 'voices' ? c.previewHint : c.bgmHint}
        </p>
      </div>
    </PageContainer>
  )
}

export default CommentaryLibraryPage
