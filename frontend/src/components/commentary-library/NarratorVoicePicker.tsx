import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Pause, Play } from 'lucide-react'
import { narratorVoicePreviewUrl } from '../../api/config'
import type { NarratorVoiceInfo } from '../../api/config'

const NATIVE_LANGUAGE_LABELS: Record<string, { zh: string; en: string }> = {
  zh: { zh: '中文', en: 'Chinese' },
  en: { zh: '英文', en: 'English' },
  ja: { zh: '日语', en: 'Japanese' },
  ko: { zh: '韩语', en: 'Korean' },
}

export interface NarratorVoicePickerProps {
  value: string
  voices: NarratorVoiceInfo[] | undefined
  locale: 'zh-CN' | 'en-US'
  onChange: (id: string) => void
}

export function NarratorVoicePicker({ value, voices, locale, onChange }: NarratorVoicePickerProps) {
  const isZh = locale === 'zh-CN'
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState<string | null>(null)

  const fallbackVoices: NarratorVoiceInfo[] = useMemo(
    () => [
      { id: 'narrator-male-calm', name_zh: '沉稳男声', name_en: 'Calm Male', gender: 'male', native_language: 'zh' },
      { id: 'narrator-female-bright', name_zh: '知性女声', name_en: 'Bright Female', gender: 'female', native_language: 'zh' },
    ],
    [],
  )

  const items = voices && voices.length > 0 ? voices : fallbackVoices

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
    setPreviewing(null)
    setPreviewLoading(null)
  }

  useEffect(() => {
    return () => {
      cancelInflight()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.removeAttribute('src')
      }
      releaseObjectUrl()
    }
  }, [])

  const handlePreview = async (voiceId: string) => {
    if (previewing === voiceId || previewLoading === voiceId) {
      stopPreview()
      return
    }
    cancelInflight()
    releaseObjectUrl()
    setPreviewError(null)
    setPreviewLoading(voiceId)
    setPreviewing(null)
    if (!audioRef.current) {
      audioRef.current = new Audio()
      audioRef.current.addEventListener('ended', () => setPreviewing(null))
    }
    audioRef.current.pause()

    const controller = new AbortController()
    abortRef.current = controller

    let response: Response
    try {
      response = await fetch(narratorVoicePreviewUrl(voiceId), {
        signal: controller.signal,
        headers: { Accept: 'audio/wav' },
      })
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return
      }
      setPreviewError(
        isZh
          ? '无法连接到后端服务，请确认服务正在运行'
          : 'Unable to reach backend; please check the server is running',
      )
      setPreviewLoading(null)
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
      setPreviewLoading(null)
      return
    }

    let blob: Blob
    try {
      blob = await response.blob()
    } catch {
      setPreviewError(
        isZh ? '试听音频解析失败，请稍后再试' : 'Failed to decode preview audio',
      )
      setPreviewLoading(null)
      return
    }
    if (abortRef.current !== controller) return

    const url = URL.createObjectURL(blob)
    objectUrlRef.current = url
    audioRef.current.src = url
    try {
      await audioRef.current.play()
      if (abortRef.current !== controller) return
      setPreviewing(voiceId)
      setPreviewLoading(null)
    } catch (err) {
      if ((err as DOMException)?.name === 'AbortError') {
        return
      }
      const name = (err as DOMException)?.name
      if (name === 'NotAllowedError') {
        setPreviewError(
          isZh
            ? '浏览器拒绝了自动播放，请再次点击播放按钮以继续。'
            : 'Browser blocked autoplay — click the play button again to continue.',
        )
      } else {
        setPreviewError(
          isZh
            ? `试听播放失败：${(err as Error).message || name || 'unknown error'}`
            : `Preview playback failed: ${(err as Error).message || name || 'unknown error'}`,
        )
      }
      setPreviewing(null)
      setPreviewLoading(null)
    }
  }

  const isViralRecap = (voice: NarratorVoiceInfo) => voice.id.startsWith('narrator-recap-')

  const builtinVoices = items.filter(v => !isViralRecap(v))
  const viralVoices = items.filter(isViralRecap)

  const renderTile = (voice: NarratorVoiceInfo) => {
    const selected = value === voice.id
    const isPreviewing = previewing === voice.id
    const isLoading = previewLoading === voice.id
    const name = isZh ? voice.name_zh : voice.name_en
    const description = isZh ? voice.description_zh : voice.description_en
    const langLabel = voice.native_language
      ? NATIVE_LANGUAGE_LABELS[voice.native_language]?.[isZh ? 'zh' : 'en']
      : undefined
    return (
      <div
        key={voice.id}
        role="button"
        tabIndex={0}
        onClick={() => onChange(voice.id)}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            onChange(voice.id)
          }
        }}
        className={`group flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition-all ${
          selected
            ? 'border-[#3b5bdb] bg-[#3b5bdb]/5 ring-2 ring-[#3b5bdb]/20'
            : 'border-[#e5e7eb] bg-white hover:border-slate-300'
        }`}
        aria-pressed={selected}
      >
        <button
          type="button"
          onClick={event => {
            event.stopPropagation()
            handlePreview(voice.id)
          }}
          aria-label={
            isPreviewing
              ? isZh ? '停止试听' : 'Stop preview'
              : isZh ? '试听' : 'Preview'
          }
          className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white shadow-sm transition-colors ${
            isPreviewing ? 'bg-rose-500 hover:bg-rose-600' : 'bg-[#3b5bdb] hover:bg-[#3046b8]'
          }`}
        >
          {isLoading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : isPreviewing ? (
            <Pause className="h-3.5 w-3.5" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
        </button>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-slate-800">{name}</span>
            {langLabel && (
              <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                {langLabel}
              </span>
            )}
            {voice.gender && (
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                  voice.gender === 'male'
                    ? 'bg-sky-50 text-sky-600'
                    : 'bg-pink-50 text-pink-600'
                }`}
              >
                {voice.gender === 'male' ? (isZh ? '男' : 'M') : (isZh ? '女' : 'F')}
              </span>
            )}
          </span>
          {description && (
            <span className="mt-0.5 block text-xs text-slate-500 line-clamp-2">
              {description}
            </span>
          )}
        </span>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {builtinVoices.length > 0 && (
        <section
          aria-label={isZh ? '内置叙述音色' : 'Built-in narrator voices'}
          className="space-y-2"
        >
          <h4 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <span>{isZh ? '内置叙述音色' : 'Built-in narrators'}</span>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
              {builtinVoices.length}
            </span>
          </h4>
          <p className="text-[11px] text-slate-400">
            {isZh
              ? '中立旁白音色，覆盖中、英、日、韩四语，适合常规影视/纪录片解说。'
              : 'Neutral narrator timbres in zh / en / ja / ko — best for general recap & documentary work.'}
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {builtinVoices.map(renderTile)}
          </div>
        </section>
      )}

      {viralVoices.length > 0 && (
        <section
          aria-label={isZh ? '短视频爆款风' : 'Viral short-video recap'}
          className="space-y-2 rounded-xl border border-amber-200/70 bg-gradient-to-br from-amber-50/60 to-rose-50/40 p-3"
        >
          <h4 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
            <span aria-hidden="true">🔥</span>
            <span>{isZh ? '短视频爆款风' : 'Viral recap packs'}</span>
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700">
              {viralVoices.length}
            </span>
            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-medium text-rose-600">
              {isZh ? '新' : 'NEW'}
            </span>
          </h4>
          <p className="text-[11px] text-amber-700/80">
            {isZh
              ? '复用上方 speaker、改写 instruct 得到的「抖音影视解说」风格变体，按短视频节奏调校。'
              : 'Style variants of the built-in speakers tuned for Douyin / TikTok-style recap cadence.'}
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {viralVoices.map(renderTile)}
          </div>
        </section>
      )}

      <div>
        <button
          type="button"
          onClick={() => onChange('source')}
          className={`flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-all ${
            value === 'source'
              ? 'border-[#3b5bdb] bg-[#3b5bdb]/5 text-[#3b5bdb] ring-2 ring-[#3b5bdb]/20'
              : 'border-dashed border-slate-300 bg-white text-slate-500 hover:border-slate-400 hover:text-slate-700'
          }`}
          aria-pressed={value === 'source'}
        >
          {isZh ? '借用源片音色' : 'Borrow from source'}
        </button>
      </div>

      {previewError && (
        <p className="text-xs text-rose-500" role="alert">
          {previewError}
        </p>
      )}
      <p className="text-[11px] text-slate-400">
        {isZh
          ? '首轮试听会即时生成约 10 秒的样本（基于 Qwen3-TTS CustomVoice），随后会复用本地缓存。'
          : 'The first preview synthesizes ~10s sample via Qwen3-TTS CustomVoice and then reuses the local cache.'}
      </p>
    </div>
  )
}
