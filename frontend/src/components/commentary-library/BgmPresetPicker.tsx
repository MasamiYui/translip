import { useEffect, useRef, useState } from 'react'
import { Loader2, Pause, Play } from 'lucide-react'
import { bgmPresetPreviewUrl } from '../../api/config'
import type { BgmPresetInfo } from '../../api/config'

const BGM_NONE_SELECTOR = ''

export interface BgmPresetPickerProps {
  value: string
  presets: BgmPresetInfo[] | undefined
  locale: 'zh-CN' | 'en-US'
  onChange: (id: string) => void
}

export function BgmPresetPicker({ value, presets, locale, onChange }: BgmPresetPickerProps) {
  const isZh = locale === 'zh-CN'
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const items = Array.isArray(presets) ? presets : []

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

  const handlePreview = async (presetId: string) => {
    if (previewing === presetId || previewLoading === presetId) {
      stopPreview()
      return
    }
    cancelInflight()
    releaseObjectUrl()
    setPreviewError(null)
    setPreviewLoading(presetId)
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
      response = await fetch(bgmPresetPreviewUrl(presetId), {
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
      setPreviewLoading(null)
      return
    }
    if (abortRef.current !== controller) return
    if (!response.ok) {
      setPreviewError(
        isZh ? `试听加载失败（HTTP ${response.status}）` : `Preview failed (HTTP ${response.status})`,
      )
      setPreviewLoading(null)
      return
    }
    const blob = await response.blob()
    if (abortRef.current !== controller) return
    const url = URL.createObjectURL(blob)
    objectUrlRef.current = url
    audioRef.current.src = url
    try {
      await audioRef.current.play()
      if (abortRef.current !== controller) return
      setPreviewing(presetId)
      setPreviewLoading(null)
    } catch (err) {
      setPreviewError(
        isZh
          ? `试听播放失败：${(err as Error).message || 'unknown error'}`
          : `Preview playback failed: ${(err as Error).message || 'unknown error'}`,
      )
      setPreviewing(null)
      setPreviewLoading(null)
    }
  }

  const renderTile = (preset: BgmPresetInfo) => {
    const selected = value === preset.id
    const isPreviewing = previewing === preset.id
    const isLoading = previewLoading === preset.id
    const name = isZh ? preset.name_zh : preset.name_en
    const description = isZh ? preset.description_zh : preset.description_en
    return (
      <div
        key={preset.id}
        role="button"
        tabIndex={0}
        onClick={() => onChange(preset.id)}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            onChange(preset.id)
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
            handlePreview(preset.id)
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
            <span className="rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-600">
              {preset.mood}
            </span>
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
      <button
        type="button"
        onClick={() => onChange(BGM_NONE_SELECTOR)}
        className={`flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition-all ${
          value === BGM_NONE_SELECTOR
            ? 'border-[#3b5bdb] bg-[#3b5bdb]/5 text-[#3b5bdb] ring-2 ring-[#3b5bdb]/20'
            : 'border-dashed border-slate-300 bg-white text-slate-500 hover:border-slate-400 hover:text-slate-700'
        }`}
        aria-pressed={value === BGM_NONE_SELECTOR}
      >
        {isZh ? '不加 BGM（纯原声 + 解说）' : 'No BGM (voice + original audio only)'}
      </button>

      {items.length > 0 && (
        <section
          aria-label={isZh ? '内置 BGM 预设' : 'Built-in BGM presets'}
          className="space-y-2 rounded-xl border border-violet-200/70 bg-gradient-to-br from-violet-50/60 to-indigo-50/30 p-3"
        >
          <h4 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
            <span aria-hidden="true">🎵</span>
            <span>{isZh ? '内置 BGM 预设' : 'Built-in BGM moods'}</span>
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-medium text-violet-700">
              {items.length}
            </span>
            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-medium text-rose-600">
              {isZh ? '新' : 'NEW'}
            </span>
          </h4>
          <p className="text-[11px] text-violet-700/80">
            {isZh
              ? '算法合成的中性铺底（CC0），仅供本地学习 / 调试使用；正式发布请替换 assets/bgm/ 内的同名 wav 为合规授权曲。'
              : 'Algorithmically synthesised neutral beds (CC0) — for local learning only. For published work, replace the WAVs under assets/bgm/ with licensed tracks.'}
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">{items.map(renderTile)}</div>
        </section>
      )}

      {previewError && (
        <p className="text-xs text-rose-500" role="alert">
          {previewError}
        </p>
      )}
    </div>
  )
}
