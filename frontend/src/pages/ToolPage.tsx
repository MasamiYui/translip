import { useEffect, useId, useState, type Dispatch, type SetStateAction } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Info, RefreshCw } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { atomicToolsApi } from '../api/atomic-tools'
import { configApi } from '../api/config'
import { FileUploadZone } from '../components/atomic-tools/FileUploadZone'
import { ResultPanel } from '../components/atomic-tools/ResultPanel'
import { ToolProgressBar } from '../components/atomic-tools/ToolProgressBar'
import { WatermarkPreview } from '../components/atomic-tools/WatermarkPreview'
import { PageContainer } from '../components/layout/PageContainer'
import { useAtomicTool } from '../hooks/useAtomicTool'
import { useI18n } from '../i18n/useI18n'
import type { Locale, LocaleMessages } from '../i18n/messages'
import { readAtomicToolPrefill, type AtomicToolPrefill } from '../lib/atomicToolPrefill'
import { getToolDisplayDescription, getToolDisplayName } from '../lib/atomicToolsDisplay'
import type { TaskConfig } from '../types'
import type { FileUploadResponse } from '../types/atomic-tools'
import { DUBBING_BACKEND_OPTIONS } from '../lib/dubbingBackends'

type FileRefMap = Record<string, FileUploadResponse | null>
type ToolParams = Record<string, string | number | boolean>
type SelectOption = string | { value: string; label: string }

// Atomic tool pages render as a focused, centered single column rather than the app's full content width.
export const TOOL_PAGE_MAX_WIDTH = 'max-w-3xl'

const SOURCE_LANGUAGE_CODES = ['auto', 'zh', 'en', 'ja'] as const
const TARGET_LANGUAGE_CODES = ['zh', 'en', 'ja'] as const

const FASTER_WHISPER_MODEL_OPTIONS: SelectOption[] = ['tiny', 'base', 'small', 'medium', 'large-v3']
const FUNASR_MODEL_OPTIONS: SelectOption[] = [
  { value: 'paraformer-zh', label: 'Paraformer-zh' },
  { value: 'iic/SenseVoiceSmall', label: 'SenseVoiceSmall' },
]
const ASR_BACKEND_OPTIONS: SelectOption[] = [
  { value: 'faster-whisper', label: 'faster-whisper' },
  { value: 'funasr', label: 'FunASR' },
]

function selectOptionValue(option: SelectOption): string {
  return typeof option === 'string' ? option : option.value
}

export function ToolPage() {
  const { toolId = 'probe' } = useParams()
  const [searchParams] = useSearchParams()
  const prefillParam = searchParams.get('prefill') ?? ''

  return <ToolPageContent key={`${toolId}:${prefillParam}`} toolId={toolId} prefillParam={prefillParam} />
}

function ToolPageContent({ toolId, prefillParam }: { toolId: string; prefillParam: string }) {
  const { locale, t, getLanguageLabel } = useI18n()
  const navigate = useNavigate()
  const isSubtitleOutputTool = toolId === 'subtitle-burn' || toolId === 'subtitle-embed'
  const subtitleOutputCopy = t.atomicTools.subtitleOutput
  const prefill = readAtomicToolPrefill(prefillParam)
  const { data: tools = [] } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })
  const { data: globalDefaults } = useQuery<Partial<TaskConfig>>({
    queryKey: ['config-defaults'],
    queryFn: configApi.getDefaults,
    staleTime: 30_000,
  })
  const tool = tools.find(item => item.tool_id === toolId)
  const { uploadFile, job, artifacts, runTool, isRunning, getDownloadUrl, errorMessage, reset } =
    useAtomicTool({ toolId })

  const [fileRefs, setFileRefs] = useState<FileRefMap>(() => buildInitialFileRefs(prefill))
  const [translationInputMode, setTranslationInputMode] = useState<'text' | 'file'>('text')
  const [textInput, setTextInput] = useState(() => prefill?.text ?? '')
  const [params, setParams] = useState<ToolParams>(() => ({
    ...getDefaultParams(toolId),
    ...(prefill?.params ?? {}),
  }))
  const [originalVideoUrl, setOriginalVideoUrl] = useState<string | null>(null)
  const [watermarkVideoUrl, setWatermarkVideoUrl] = useState<string | null>(null)
  const [watermarkImageUrl, setWatermarkImageUrl] = useState<string | null>(null)

  // Fold saved transcription defaults into the params when they load. Tracked by
  // reference (react-query keeps it stable across identical refetches) and applied
  // during render instead of in an effect, which would be a set-state-in-effect.
  const [appliedDefaults, setAppliedDefaults] = useState<Partial<TaskConfig> | undefined>(undefined)
  if (toolId === 'transcription' && globalDefaults && globalDefaults !== appliedDefaults) {
    setAppliedDefaults(globalDefaults)
    setParams(prev => applyTranscriptionGlobalDefaults(prev, globalDefaults))
  }

  useEffect(() => {
    return () => {
      if (originalVideoUrl) URL.revokeObjectURL(originalVideoUrl)
    }
  }, [originalVideoUrl])

  useEffect(() => {
    return () => {
      if (watermarkVideoUrl) URL.revokeObjectURL(watermarkVideoUrl)
    }
  }, [watermarkVideoUrl])

  useEffect(() => {
    return () => {
      if (watermarkImageUrl) URL.revokeObjectURL(watermarkImageUrl)
    }
  }, [watermarkImageUrl])

  if (!tool) {
    return (
      <PageContainer className={TOOL_PAGE_MAX_WIDTH}>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
          {t.common.loading}
        </div>
      </PageContainer>
    )
  }

  const title = getToolDisplayName(tool, locale, t.atomicTools)
  const description = getToolDisplayDescription(tool, locale, t.atomicTools)
  const uploadGridClass =
    toolId === 'mixing' ||
    toolId === 'muxing' ||
    toolId === 'transcript-correction' ||
    toolId === 'subtitle-burn' ||
    toolId === 'subtitle-embed' ||
    toolId === 'dub-render' ||
    (toolId === 'watermark' && String(params.mode ?? 'image') === 'image')
      ? 'grid gap-4 md:grid-cols-2'
      : 'grid gap-4'

  async function handleFileSelected(slot: string, file: File) {
    if (toolId === 'subtitle-erase' && slot === 'file' && file.type.startsWith('video/')) {
      setOriginalVideoUrl(prev => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(file)
      })
    }
    if (toolId === 'watermark' && slot === 'video_file' && file.type.startsWith('video/')) {
      setWatermarkVideoUrl(prev => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(file)
      })
    }
    if (toolId === 'watermark' && slot === 'image_file' && file.type.startsWith('image/')) {
      setWatermarkImageUrl(prev => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(file)
      })
    }
    const uploaded = await uploadFile(file)
    setFileRefs(prev => ({ ...prev, [slot]: uploaded }))
    if (toolId === 'translation' && slot === 'file') {
      setTranslationInputMode('file')
    }
  }

  async function handleRun() {
    const payload = buildRunPayload(toolId, params, fileRefs, textInput, translationInputMode)
    await runTool(payload)
  }

  // Clone-only TTS backends (moss/voxcpm) cannot run without a reference upload.
  const ttsNeedsReference =
    toolId === 'tts' &&
    (params.backend === 'moss-tts-nano-onnx' || params.backend === 'voxcpm2') &&
    !fileRefs.reference_audio_file?.file_id

  // m3u8 needs exactly one source: a URL (url mode) or an uploaded playlist (file mode).
  const m3u8NeedsSource =
    toolId === 'm3u8-to-mp4' &&
    (String(params.source_type ?? 'url') === 'file'
      ? !fileRefs.playlist_file?.file_id
      : !String(params.url ?? '').trim())

  function handleReset() {
    setFileRefs({})
    setTextInput('')
    setTranslationInputMode('text')
    setParams(getDefaultParams(toolId, globalDefaults))
    setOriginalVideoUrl(prev => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setWatermarkVideoUrl(prev => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setWatermarkImageUrl(prev => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    reset()
  }

  return (
    <PageContainer className={`${TOOL_PAGE_MAX_WIDTH} space-y-5`}>
      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/tools" className="mb-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-[#9ca3af] hover:text-[#374151] transition-colors">
            <ArrowLeft size={13} />
            {t.atomicTools.back}
          </Link>
          <h1 className="text-xl font-bold text-[#111827]">{title}</h1>
          <p className="mt-1 text-sm text-[#6b7280] leading-relaxed max-w-xl">{description}</p>
        </div>
        <button
          type="button"
          onClick={handleReset}
          className="inline-flex items-center gap-2 rounded-lg border border-[#e5e7eb] bg-white px-3.5 py-2 text-xs font-semibold text-[#6b7280] transition-all hover:bg-[#f9fafb] hover:text-[#374151]"
        >
          <RefreshCw size={13} />
          {t.atomicTools.actions.reset}
        </button>
      </div>

      {/* Inputs + controls — single centered column */}
      <section className="space-y-4">
        <div className={uploadGridClass}>
          {renderUploadZones(toolId, fileRefs, handleFileSelected, t.atomicTools.uploadHints, params)}
        </div>

        {isSubtitleOutputTool && (
          <div className="rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#6b7280]">
              {subtitleOutputCopy.modeLabel}
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              {(['burn', 'embed'] as const).map(mode => {
                const targetToolId = mode === 'burn' ? 'subtitle-burn' : 'subtitle-embed'
                const active = toolId === targetToolId
                return (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => {
                      if (!active) navigate(`/tools/${targetToolId}`)
                    }}
                    className={`rounded-lg border p-3 text-left transition ${
                      active
                        ? 'border-[#3b5bdb] bg-[#f0f3ff]'
                        : 'border-[#e5e7eb] bg-white hover:border-[#3b5bdb]/40'
                    }`}
                  >
                    <div className={`text-sm font-semibold ${active ? 'text-[#3b5bdb]' : 'text-[#111827]'}`}>
                      {subtitleOutputCopy.modes[mode]}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-[#6b7280]">
                      {subtitleOutputCopy.modeHints[mode]}
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <div className="rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)]">
          {toolId === 'watermark' && (
            <div className="mb-4">
              <WatermarkPreview
                videoUrl={watermarkVideoUrl}
                imageUrl={watermarkImageUrl}
                mode={(String(params.mode ?? 'image') === 'text' ? 'text' : 'image') as 'image' | 'text'}
                position={(String(params.position ?? 'bottom-right')) as
                  | 'top-left'
                  | 'top-right'
                  | 'bottom-left'
                  | 'bottom-right'
                  | 'center'}
                margin={Number(params.margin ?? 24)}
                opacity={Number(params.opacity ?? 0.8)}
                scale={Number(params.scale ?? 0.15)}
                text={String(params.text ?? '')}
                fontSize={Number(params.font_size ?? 36)}
                fontColor={String(params.font_color ?? 'white')}
                strokeColor={String(params.stroke_color ?? 'black')}
                strokeOpacity={Number(params.stroke_opacity ?? 0.6)}
                strokeWidth={Number(params.stroke_width ?? 2)}
                copy={{
                  title: t.atomicTools.watermarkPreview.title,
                  uploadVideoFirst: t.atomicTools.watermarkPreview.uploadVideoFirst,
                  imagePlaceholder: t.atomicTools.watermarkPreview.imagePlaceholder,
                  textPlaceholder: t.atomicTools.watermarkPreview.textPlaceholder,
                  unsupportedVideo: t.atomicTools.watermarkPreview.unsupportedVideo,
                  fontHint: t.atomicTools.watermarkPreview.fontHint,
                  resolutionLabel: t.atomicTools.watermarkPreview.resolutionLabel,
                }}
              />
            </div>
          )}
          {renderControls(
            toolId,
            params,
            setParams,
            textInput,
            setTextInput,
            translationInputMode,
            setTranslationInputMode,
            t.atomicTools,
            getLanguageLabel,
            locale,
          )}
        </div>

        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => void handleRun()}
            disabled={isRunning || ttsNeedsReference || m3u8NeedsSource}
            className="rounded-lg bg-[#3b5bdb] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_1px_3px_rgba(59,91,219,.35)] transition-all hover:bg-[#3451c7] hover:shadow-[0_4px_12px_rgba(59,91,219,.3)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRunning ? t.atomicTools.actions.running : t.atomicTools.actions.run}
          </button>
          {ttsNeedsReference && (
            <span className="text-sm font-medium text-amber-600">{t.atomicTools.fields.ttsReferenceRequiredHint}</span>
          )}
          {m3u8NeedsSource && (
            <span className="text-sm font-medium text-amber-600">{t.atomicTools.fields.m3u8SourceRequiredHint}</span>
          )}
          {errorMessage && <span className="text-sm font-medium text-red-500">{errorMessage}</span>}
        </div>

        <ToolProgressBar job={job} />
      </section>

      {/* Results render below the controls */}
      <ResultPanel
        toolId={toolId}
        job={job}
        artifacts={artifacts}
        getDownloadUrl={getDownloadUrl}
        originalVideoUrl={originalVideoUrl}
      />
    </PageContainer>
  )
}

function renderUploadZones(
  toolId: string,
  fileRefs: FileRefMap,
  onFileSelected: (slot: string, file: File) => Promise<void>,
  hints: Record<string, string>,
  params: ToolParams,
) {
  if (toolId === 'mixing') {
    return (
      <>
        <FileUploadZone
          label={hints.voiceLabel}
          hint={hints.voiceHint}
          accept=".wav,.mp3,.flac,.m4a,.ogg"
          value={fileRefs.voice_file ?? null}
          onFileSelected={file => onFileSelected('voice_file', file)}
        />
        <FileUploadZone
          label={hints.backgroundLabel}
          hint={hints.backgroundHint}
          accept=".wav,.mp3,.flac,.m4a,.ogg"
          value={fileRefs.background_file ?? null}
          onFileSelected={file => onFileSelected('background_file', file)}
        />
      </>
    )
  }

  if (toolId === 'muxing') {
    return (
      <>
        <FileUploadZone
          label={hints.videoLabel}
          hint={hints.videoHint}
          accept=".mp4,.mov,.mkv"
          value={fileRefs.video_file ?? null}
          onFileSelected={file => onFileSelected('video_file', file)}
        />
        <FileUploadZone
          label={hints.audioLabel}
          hint={hints.audioHint}
          accept=".wav,.mp3,.aac,.m4a"
          value={fileRefs.audio_file ?? null}
          onFileSelected={file => onFileSelected('audio_file', file)}
        />
      </>
    )
  }

  if (toolId === 'tts') {
    return (
      <FileUploadZone
        label={hints.referenceLabel}
        hint={hints.referenceHint}
        accept=".wav,.mp3,.flac,.m4a,.ogg"
        value={fileRefs.reference_audio_file ?? null}
        onFileSelected={file => onFileSelected('reference_audio_file', file)}
      />
    )
  }

  if (toolId === 'translation') {
    return (
      <FileUploadZone
        label={hints.fileLabel}
        hint={hints.fileHint}
        accept=".txt,.srt,.json"
        value={fileRefs.file ?? null}
        onFileSelected={file => onFileSelected('file', file)}
      />
    )
  }

  if (toolId === 'subtitle-detect') {
    return (
      <FileUploadZone
        label={hints.videoLabel}
        hint={hints.videoHint}
        accept=".mp4,.mkv,.mov,.avi"
        value={fileRefs.file ?? null}
        onFileSelected={file => onFileSelected('file', file)}
      />
    )
  }

  if (toolId === 'subtitle-erase') {
    return (
      <>
        <FileUploadZone
          label={hints.videoLabel}
          hint={hints.videoHint}
          accept=".mp4,.mkv,.mov,.avi"
          value={fileRefs.file ?? null}
          onFileSelected={file => onFileSelected('file', file)}
        />
        <FileUploadZone
          label={hints.detectionLabel}
          hint={hints.detectionHint}
          accept=".json"
          value={fileRefs.detection_file ?? null}
          onFileSelected={file => onFileSelected('detection_file', file)}
          optional
          optionalLabel={hints.optionalBadge}
        />
      </>
    )
  }

  if (toolId === 'dub-render') {
    return (
      <>
        <FileUploadZone
          label={hints.translationLabel}
          hint={hints.translationHint}
          accept=".json"
          value={fileRefs.translation_file ?? null}
          onFileSelected={file => onFileSelected('translation_file', file)}
        />
        <FileUploadZone
          label={hints.backgroundLabel}
          hint={hints.backgroundHint}
          accept=".wav,.mp3,.flac,.m4a,.ogg"
          value={fileRefs.background_file ?? null}
          onFileSelected={file => onFileSelected('background_file', file)}
        />
        <FileUploadZone
          label={hints.referenceLabel}
          hint={hints.referenceHint}
          accept=".wav,.mp3,.flac,.m4a,.ogg"
          value={fileRefs.reference_audio_file ?? null}
          onFileSelected={file => onFileSelected('reference_audio_file', file)}
          optional
          optionalLabel={hints.optionalBadge}
        />
        <FileUploadZone
          label={hints.dubVideoLabel}
          hint={hints.dubVideoHint}
          accept=".mp4,.mkv,.mov,.avi"
          value={fileRefs.video_file ?? null}
          onFileSelected={file => onFileSelected('video_file', file)}
          optional
          optionalLabel={hints.optionalBadge}
        />
      </>
    )
  }

  if (toolId === 'subtitle-burn' || toolId === 'subtitle-embed') {
    return (
      <>
        <FileUploadZone
          label={hints.videoLabel}
          hint={hints.videoHint}
          accept=".mp4,.mkv,.mov,.avi"
          value={fileRefs.video_file ?? null}
          onFileSelected={file => onFileSelected('video_file', file)}
        />
        <FileUploadZone
          label={hints.subtitleLabel}
          hint={hints.subtitleHint}
          accept=".srt,.ass"
          value={fileRefs.subtitle_file ?? null}
          onFileSelected={file => onFileSelected('subtitle_file', file)}
        />
      </>
    )
  }

  if (toolId === 'watermark') {
    const isImageMode = String(params.mode ?? 'image') === 'image'
    return (
      <>
        <FileUploadZone
          label={hints.videoLabel}
          hint={hints.videoHint}
          accept=".mp4,.mkv,.mov,.avi"
          value={fileRefs.video_file ?? null}
          onFileSelected={file => onFileSelected('video_file', file)}
        />
        {isImageMode && (
          <FileUploadZone
            label={hints.watermarkImageLabel}
            hint={hints.watermarkImageHint}
            accept=".png,.jpg,.jpeg,.webp"
            value={fileRefs.image_file ?? null}
            onFileSelected={file => onFileSelected('image_file', file)}
          />
        )}
      </>
    )
  }

  if (toolId === 'video-analyze') {
    return (
      <>
        <FileUploadZone
          label={hints.videoLabel}
          hint={hints.videoHint}
          accept=".mp4,.mkv,.mov,.avi"
          value={fileRefs.file ?? null}
          onFileSelected={file => onFileSelected('file', file)}
        />
        <FileUploadZone
          label={hints.visionDetectionLabel}
          hint={hints.visionDetectionHint}
          accept=".json"
          value={fileRefs.detection_file ?? null}
          onFileSelected={file => onFileSelected('detection_file', file)}
          optional
          optionalLabel={hints.optionalBadge}
        />
      </>
    )
  }

  if (toolId === 'transcript-correction') {
    return (
      <>
        <FileUploadZone
          label={hints.segmentsLabel}
          hint={hints.segmentsHint}
          accept=".json,.srt,.vtt"
          value={fileRefs.segments_file ?? null}
          onFileSelected={file => onFileSelected('segments_file', file)}
        />
        <FileUploadZone
          label={hints.ocrEventsLabel}
          hint={hints.ocrEventsHint}
          accept=".json,.srt,.vtt"
          value={fileRefs.ocr_events_file ?? null}
          onFileSelected={file => onFileSelected('ocr_events_file', file)}
        />
      </>
    )
  }

  if (toolId === 'm3u8-to-mp4') {
    // URL is the primary input (rendered in the controls); the upload zone only
    // appears when the user switches the source toggle to a local file.
    if (String(params.source_type ?? 'url') !== 'file') return null
    return (
      <FileUploadZone
        label={hints.m3u8FileLabel}
        hint={hints.m3u8FileHint}
        accept=".m3u8"
        value={fileRefs.playlist_file ?? null}
        onFileSelected={file => onFileSelected('playlist_file', file)}
      />
    )
  }

  return (
    <FileUploadZone
      label={hints.fileLabel}
      hint={hints.fileHint}
      accept=".mp4,.mkv,.mov,.wav,.mp3,.flac,.m4a,.ogg"
      value={fileRefs.file ?? null}
      onFileSelected={file => onFileSelected('file', file)}
    />
  )
}

function buildInitialFileRefs(prefill: AtomicToolPrefill | null): FileRefMap {
  const next: FileRefMap = {}

  for (const [key, value] of Object.entries(prefill?.files ?? {})) {
    next[key] = {
      file_id: value.file_id,
      filename: value.filename,
      size_bytes: 0,
      content_type: 'application/octet-stream',
    }
  }

  return next
}

function renderControls(
  toolId: string,
  params: ToolParams,
  setParams: Dispatch<SetStateAction<ToolParams>>,
  textInput: string,
  setTextInput: Dispatch<SetStateAction<string>>,
  translationInputMode: 'text' | 'file',
  setTranslationInputMode: Dispatch<SetStateAction<'text' | 'file'>>,
  atomicTools: LocaleMessages['atomicTools'],
  getLanguageLabel: (code: string) => string,
  locale: Locale,
) {
  const setField = (key: string, value: string | number | boolean) => {
    setParams(prev => ({ ...prev, [key]: value }))
  }
  const sourceLanguageOptions = languageOptions(SOURCE_LANGUAGE_CODES, getLanguageLabel, locale)
  const targetLanguageOptions = languageOptions(TARGET_LANGUAGE_CODES, getLanguageLabel, locale)

  if (toolId === 'separation') {
    const separationMode = String(params.mode)
    const showOverlap = separationMode === 'auto' || separationMode === 'dialogue'
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField
          label={atomicTools.fields.mode}
          value={separationMode}
          options={(['auto', 'music', 'dialogue'] as const).map(value => ({ value, label: atomicTools.options.mode[value] }))}
          onChange={value => setField('mode', value)}
        />
        <SelectField
          label={atomicTools.fields.quality}
          value={String(params.quality)}
          options={(['balanced', 'high'] as const).map(value => ({ value, label: atomicTools.options.quality[value] }))}
          onChange={value => setField('quality', value)}
        />
        <SelectField label={atomicTools.fields.outputFormat} value={String(params.output_format)} options={['wav', 'mp3', 'flac']} onChange={value => setField('output_format', value)} />
        {showOverlap && (
          <SelectField
            label={atomicTools.fields.cdx23Overlap}
            hint={atomicTools.hints.cdx23Overlap}
            hintAriaLabel={atomicTools.hints.termHintAria}
            value={String(params.cdx23_overlap ?? 0.5)}
            options={['0.25', '0.5', '0.75', '0.9']}
            onChange={value => setField('cdx23_overlap', Number(value))}
          />
        )}
      </div>
    )
  }

  if (toolId === 'mixing') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <TextField label={atomicTools.fields.backgroundGain} hint={atomicTools.hints.backgroundGain} hintAriaLabel={atomicTools.hints.termHintAria} type="number" value={String(params.background_gain_db)} onChange={value => setField('background_gain_db', Number(value))} />
        <SelectField label={atomicTools.fields.duckingMode} hint={atomicTools.hints.duckingMode} hintAriaLabel={atomicTools.hints.termHintAria} value={String(params.ducking_mode)} options={['static', 'sidechain']} onChange={value => setField('ducking_mode', value)} />
        <SelectField label={atomicTools.fields.outputFormat} value={String(params.output_format)} options={['wav', 'mp3']} onChange={value => setField('output_format', value)} />
      </div>
    )
  }

  if (toolId === 'transcription') {
    const asrBackend = String(params.asr_backend ?? 'faster-whisper')
    const asrModelOptions = asrBackend === 'funasr' ? FUNASR_MODEL_OPTIONS : FASTER_WHISPER_MODEL_OPTIONS
    const asrModelValue = asrModelOptions.some(option => selectOptionValue(option) === String(params.asr_model))
      ? String(params.asr_model)
      : selectOptionValue(asrModelOptions[0])
    const handleAsrBackendChange = (value: string) => {
      setParams(prev => ({
        ...prev,
        asr_backend: value,
        asr_model: value === 'funasr' ? selectOptionValue(FUNASR_MODEL_OPTIONS[0]) : 'small',
      }))
    }
    return (
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField label={atomicTools.fields.language} value={String(params.language)} options={sourceLanguageOptions} onChange={value => setField('language', value)} />
          <SelectField label={atomicTools.fields.asrBackend} hint={atomicTools.hints.asrBackend} hintAriaLabel={atomicTools.hints.termHintAria} value={asrBackend} options={ASR_BACKEND_OPTIONS} onChange={handleAsrBackendChange} />
          <SelectField label={atomicTools.fields.asrModel} hint={atomicTools.hints.asrModel} hintAriaLabel={atomicTools.hints.termHintAria} value={asrModelValue} options={asrModelOptions} onChange={value => setField('asr_model', value)} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <CheckboxField label={atomicTools.fields.enableDiarization} hint={atomicTools.hints.diarization} hintAriaLabel={atomicTools.hints.termHintAria} checked={Boolean(params.enable_diarization)} onChange={value => setField('enable_diarization', value)} />
          <CheckboxField label={atomicTools.fields.generateSrt} checked={Boolean(params.generate_srt)} onChange={value => setField('generate_srt', value)} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField
            label={atomicTools.fields.asrMaxSegmentSec}
            hint={atomicTools.hints.asrMaxSegmentSec}
            hintAriaLabel={atomicTools.hints.termHintAria}
            type="number"
            value={String(params.vad_max_segment_sec ?? 30)}
            onChange={value => setField('vad_max_segment_sec', Number(value))}
          />
        </div>
      </div>
    )
  }

  if (toolId === 'translation') {
    return (
      <div className="space-y-4">
        <div className="inline-flex rounded-full border border-slate-200 p-1">
          <button type="button" onClick={() => setTranslationInputMode('text')} className={`rounded-full px-3 py-1.5 text-sm ${translationInputMode === 'text' ? 'bg-slate-900 text-white' : 'text-slate-500'}`}>
            {atomicTools.actions.directText}
          </button>
          <button type="button" onClick={() => setTranslationInputMode('file')} className={`rounded-full px-3 py-1.5 text-sm ${translationInputMode === 'file' ? 'bg-slate-900 text-white' : 'text-slate-500'}`}>
            {atomicTools.actions.fileInput}
          </button>
        </div>
        {translationInputMode === 'text' && (
          <TextAreaField label={atomicTools.fields.text} value={textInput} onChange={setTextInput} />
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField label={atomicTools.fields.sourceLang} value={String(params.source_lang)} options={sourceLanguageOptions} onChange={value => setField('source_lang', value)} />
          <SelectField label={atomicTools.fields.targetLang} value={String(params.target_lang)} options={targetLanguageOptions} onChange={value => setField('target_lang', value)} />
          <SelectField label={atomicTools.fields.backend} value={String(params.backend)} options={['local-m2m100', 'deepseek']} onChange={value => setField('backend', value)} />
        </div>
      </div>
    )
  }

  if (toolId === 'tts') {
    return (
      <div className="space-y-4">
        <TextAreaField label={atomicTools.fields.text} value={textInput} onChange={setTextInput} />
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label={atomicTools.fields.language} value={String(params.language)} onChange={value => setField('language', value)} />
          <SelectField label={atomicTools.fields.ttsBackend} hint={atomicTools.hints.ttsBackend} hintAriaLabel={atomicTools.hints.termHintAria} value={String(params.backend ?? 'qwen3tts')} options={DUBBING_BACKEND_OPTIONS} onChange={value => setField('backend', value)} />
        </div>
      </div>
    )
  }

  if (toolId === 'muxing') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField label={atomicTools.fields.videoCodec} value={String(params.video_codec)} options={['copy', 'libx264']} onChange={value => setField('video_codec', value)} />
        <SelectField label={atomicTools.fields.audioCodec} value={String(params.audio_codec)} options={['aac']} onChange={value => setField('audio_codec', value)} />
        <TextField label={atomicTools.fields.audioBitrate} value={String(params.audio_bitrate)} onChange={value => setField('audio_bitrate', value)} />
      </div>
    )
  }

  if (toolId === 'detect-language') {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label={atomicTools.fields.langDetectModel}
          hint={atomicTools.hints.langDetectModel}
          hintAriaLabel={atomicTools.hints.termHintAria}
          value={String(params.model ?? 'medium')}
          options={['tiny', 'base', 'small', 'medium', 'large-v3']}
          onChange={value => setField('model', value)}
        />
        <TextField
          label={atomicTools.fields.langDetectWindows}
          type="number"
          value={String(params.windows ?? 3)}
          onChange={value => setField('windows', Number(value))}
        />
      </div>
    )
  }

  if (toolId === 'dub-render') {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label={atomicTools.fields.ttsBackend}
          hint={atomicTools.hints.ttsBackend}
          hintAriaLabel={atomicTools.hints.termHintAria}
          value={String(params.backend ?? 'qwen3tts')}
          options={['qwen3tts', 'moss-tts-nano-onnx', 'voxcpm2']}
          onChange={value => setField('backend', value)}
        />
        <SelectField
          label={atomicTools.fields.targetLang}
          value={String(params.target_lang ?? 'auto')}
          options={[{ value: 'auto', label: atomicTools.options.subtitleLang.auto }, ...targetLanguageOptions]}
          onChange={value => setField('target_lang', value)}
        />
        <SelectField
          label={atomicTools.fields.duckingMode}
          value={String(params.ducking_mode ?? 'static')}
          options={['static', 'sidechain']}
          onChange={value => setField('ducking_mode', value)}
        />
        <TextField
          label={atomicTools.fields.backgroundGain}
          type="number"
          value={String(params.background_gain_db ?? -8)}
          onChange={value => setField('background_gain_db', Number(value))}
        />
      </div>
    )
  }

  if (toolId === 'subtitle-burn') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField
          label={atomicTools.fields.subtitleLang}
          value={String(params.lang ?? 'auto')}
          options={(['auto', 'cjk', 'latin'] as const).map(value => ({ value, label: atomicTools.options.subtitleLang[value] }))}
          onChange={value => setField('lang', value)}
        />
        <SelectField
          label={atomicTools.fields.subtitlePosition}
          value={String(params.position ?? 'bottom')}
          options={(['bottom', 'top'] as const).map(value => ({ value, label: atomicTools.options.subtitlePosition[value] }))}
          onChange={value => setField('position', value)}
        />
        <SelectField
          label={atomicTools.fields.quality}
          value={String(params.quality ?? 'balanced')}
          options={(['balanced', 'high'] as const).map(value => ({ value, label: atomicTools.options.quality[value] }))}
          onChange={value => setField('quality', value)}
        />
      </div>
    )
  }

  if (toolId === 'subtitle-embed') {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField
          label={atomicTools.fields.container}
          value={String(params.container ?? 'mp4')}
          options={(['mp4', 'mkv'] as const).map(value => ({ value, label: atomicTools.options.container[value] }))}
          onChange={value => setField('container', value)}
        />
        <TextField
          label={atomicTools.fields.subtitleLanguage}
          value={String(params.subtitle_language ?? 'und')}
          onChange={value => setField('subtitle_language', value)}
        />
      </div>
    )
  }

  if (toolId === 'watermark') {
    const mode = String(params.mode ?? 'image')
    const positionOptions = (['bottom-right', 'bottom-left', 'top-right', 'top-left', 'center'] as const).map(value => ({
      value,
      label: atomicTools.options.watermarkPosition[value],
    }))
    return (
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium text-slate-700">{atomicTools.fields.watermarkMode}</div>
          <div className="grid gap-2 md:grid-cols-2">
            {(['image', 'text'] as const).map(option => (
              <button
                key={option}
                type="button"
                onClick={() =>
                  // Image watermarks read best slightly translucent; text
                  // watermarks default to fully opaque. Reset opacity to the
                  // mode default on switch so the control reflects the mode.
                  setParams(prev => ({
                    ...prev,
                    mode: option,
                    opacity: option === 'text' ? 1 : 0.8,
                  }))
                }
                className={`rounded-2xl border p-3 text-left transition ${
                  mode === option
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="text-sm font-semibold text-slate-900">
                  {atomicTools.options.watermarkMode[option]}
                </div>
                <div className="mt-1 text-xs leading-5 text-slate-500">
                  {atomicTools.hints.watermarkMode[option]}
                </div>
              </button>
            ))}
          </div>
        </div>
        {mode === 'text' && (
          <TextField
            label={atomicTools.fields.watermarkText}
            value={String(params.text ?? '')}
            onChange={value => setField('text', value)}
          />
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <SelectField
            label={atomicTools.fields.watermarkPosition}
            value={String(params.position ?? 'bottom-right')}
            options={positionOptions}
            onChange={value => setField('position', value)}
          />
          <TextField
            label={atomicTools.fields.watermarkMargin}
            hint={atomicTools.hints.watermarkMargin}
            hintAriaLabel={atomicTools.hints.termHintAria}
            type="number"
            value={String(params.margin ?? 24)}
            onChange={value => setField('margin', value === '' ? 0 : Number(value))}
          />
          <TextField
            label={atomicTools.fields.watermarkOpacity}
            hint={atomicTools.hints.watermarkOpacity}
            hintAriaLabel={atomicTools.hints.termHintAria}
            type="number"
            value={String(params.opacity ?? 0.8)}
            onChange={value => setField('opacity', value === '' ? 0 : Number(value))}
          />
          {mode === 'image' && (
            <TextField
              label={atomicTools.fields.watermarkScale}
              hint={atomicTools.hints.watermarkScale}
              hintAriaLabel={atomicTools.hints.termHintAria}
              type="number"
              value={String(params.scale ?? 0.15)}
              onChange={value => setField('scale', value === '' ? 0 : Number(value))}
            />
          )}
          {mode === 'text' && (
            <>
              <TextField
                label={atomicTools.fields.watermarkFontSize}
                type="number"
                value={String(params.font_size ?? 36)}
                onChange={value => setField('font_size', value === '' ? 0 : Number(value))}
              />
              <SelectField
                label={atomicTools.fields.watermarkFontColor}
                hint={atomicTools.hints.watermarkFontColor}
                hintAriaLabel={atomicTools.hints.termHintAria}
                value={String(params.font_color ?? 'white')}
                options={(
                  ['white', 'black', 'yellow', 'red', 'green', 'blue', 'gray', '#ff6600'] as const
                ).map(value => ({ value, label: atomicTools.options.watermarkColor[value] }))}
                onChange={value => setField('font_color', value)}
              />
              <SelectField
                label={atomicTools.fields.watermarkStrokeColor}
                hint={atomicTools.hints.watermarkStrokeColor}
                hintAriaLabel={atomicTools.hints.termHintAria}
                value={String(params.stroke_color ?? 'black')}
                options={(
                  ['white', 'black', 'yellow', 'red', 'green', 'blue', 'gray', '#ff6600'] as const
                ).map(value => ({ value, label: atomicTools.options.watermarkColor[value] }))}
                onChange={value => setField('stroke_color', value)}
              />
              <TextField
                label={atomicTools.fields.watermarkStrokeOpacity}
                type="number"
                value={String(params.stroke_opacity ?? 0.6)}
                onChange={value => setField('stroke_opacity', value === '' ? 0 : Number(value))}
              />
              <TextField
                label={atomicTools.fields.watermarkStrokeWidth}
                type="number"
                value={String(params.stroke_width ?? 2)}
                onChange={value => setField('stroke_width', value === '' ? 0 : Number(value))}
              />
            </>
          )}
          <SelectField
            label={atomicTools.fields.quality}
            value={String(params.quality ?? 'balanced')}
            options={(['balanced', 'high'] as const).map(value => ({ value, label: atomicTools.options.quality[value] }))}
            onChange={value => setField('quality', value)}
          />
        </div>
      </div>
    )
  }

  if (toolId === 'subtitle-detect') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField
          label={atomicTools.fields.language}
          value={String(params.language ?? 'ch')}
          options={['ch', 'en', 'ch_tra', 'japan', 'korean']}
          onChange={value => setField('language', value)}
        />
        <TextField
          label={atomicTools.fields.sampleInterval}
          hint={atomicTools.hints.sampleIntervalSubDetect}
          hintAriaLabel={atomicTools.hints.termHintAria}
          type="number"
          value={String(params.sample_interval ?? 0.4)}
          onChange={value => setField('sample_interval', Number(value))}
        />
        <TextField
          label={atomicTools.fields.previewFrames}
          hint={atomicTools.hints.previewFrames}
          hintAriaLabel={atomicTools.hints.termHintAria}
          type="number"
          value={String(params.preview_frames ?? 3)}
          onChange={value => setField('preview_frames', Number(value))}
        />
        <SelectField
          label={atomicTools.fields.positionMode}
          hint={atomicTools.hints.positionMode}
          hintAriaLabel={atomicTools.hints.termHintAria}
          value={String(params.position_mode ?? 'auto')}
          options={['auto', 'bottom', 'middle', 'top']}
          onChange={value => setField('position_mode', value)}
        />
        <SelectField
          label={atomicTools.fields.extractionMode}
          hint={atomicTools.hints.extractionMode}
          hintAriaLabel={atomicTools.hints.termHintAria}
          value={String(params.extraction_mode ?? 'conservative')}
          options={['conservative', 'balanced', 'variety_recall']}
          onChange={value => setField('extraction_mode', value)}
        />
      </div>
    )
  }

  if (toolId === 'video-analyze') {
    const visionTask = String(params.task ?? 'scene-context')
    const visionTaskKeys = ['scene-context', 'erase-qc', 'ocr-classify', 'freeform'] as const
    return (
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium text-slate-700">{atomicTools.fields.visionTask}</div>
          <div className="grid gap-2 md:grid-cols-2">
            {visionTaskKeys.map(option => (
              <button
                key={option}
                type="button"
                onClick={() => setField('task', option)}
                className={`rounded-2xl border p-3 text-left transition ${
                  visionTask === option
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="text-sm font-semibold text-slate-900">
                  {atomicTools.visionTasks[option]}
                </div>
                <div className="mt-1 text-xs leading-5 text-slate-500">
                  {atomicTools.visionTaskHints[option]}
                </div>
              </button>
            ))}
          </div>
        </div>
        {visionTask === 'freeform' && (
          <TextAreaField
            label={atomicTools.fields.visionQuestion}
            value={String(params.question ?? '')}
            onChange={value => setField('question', value)}
          />
        )}
        <div className="grid gap-4 md:grid-cols-3">
          <TextField
            label={atomicTools.fields.sampleInterval}
            hint={atomicTools.hints.sampleIntervalVision}
            hintAriaLabel={atomicTools.hints.termHintAria}
            type="number"
            value={String(params.sample_interval ?? 10)}
            onChange={value => setField('sample_interval', Number(value))}
          />
          <TextField
            label={atomicTools.fields.framesPerUnit}
            hint={atomicTools.hints.framesPerUnit}
            hintAriaLabel={atomicTools.hints.termHintAria}
            type="number"
            value={String(params.frames_per_unit ?? 4)}
            onChange={value => setField('frames_per_unit', Number(value))}
          />
          <TextField
            label={atomicTools.fields.maxUnits}
            hint={atomicTools.hints.maxUnits}
            hintAriaLabel={atomicTools.hints.termHintAria}
            type="number"
            value={String(params.max_units ?? '')}
            onChange={value => setField('max_units', value === '' ? '' : Number(value))}
          />
          <SelectField
            label={atomicTools.fields.outputLang}
            value={String(params.lang ?? 'zh')}
            options={['zh', 'en']}
            onChange={value => setField('lang', value)}
          />
          <SelectField
            label={atomicTools.fields.visionBackend}
            value={String(params.backend ?? 'auto')}
            options={['auto', 'mlx', 'ollama']}
            onChange={value => setField('backend', value)}
          />
        </div>
      </div>
    )
  }

  if (toolId === 'subtitle-erase') {
    const preset = String(params.preset ?? 'balanced')
    const backendRaw = String(params.backend ?? '')
    const effectiveBackend = backendRaw || (preset === 'quality' ? 'lama' : 'sttn')
    const showNeighborStride = effectiveBackend !== 'lama'
    return (
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium text-slate-700">{atomicTools.fields.preset}</div>
          <div className="grid gap-2 md:grid-cols-2">
            {(['balanced', 'quality'] as const).map(option => (
              <button
                key={option}
                type="button"
                onClick={() => setField('preset', option)}
                className={`rounded-2xl border p-3 text-left transition ${
                  preset === option
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="text-sm font-semibold text-slate-900">
                  {atomicTools.presetLabels[option]}
                </div>
                <div className="mt-1 text-xs leading-5 text-slate-500">
                  {atomicTools.presetHints[option]}
                </div>
              </button>
            ))}
          </div>
        </div>

        <details className="group rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-1 py-0.5 text-sm font-medium text-slate-700 transition-colors hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300">
            <span className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-flex h-4 w-4 items-center justify-center text-slate-400 transition-transform group-open:rotate-90"
              >
                ▶
              </span>
              {atomicTools.fields.advanced}
            </span>
            <span className="hidden text-xs font-normal text-slate-400 sm:inline">
              {atomicTools.fields.advancedHint}
            </span>
          </summary>
          <div className="mt-3 grid gap-4 md:grid-cols-3">
            <SelectField
              label={atomicTools.fields.backend}
              hint={atomicTools.hints.backendInpaint}
              hintAriaLabel={atomicTools.hints.termHintAria}
              value={backendRaw}
              options={[
                { value: '', label: atomicTools.fields.backendFollowPreset },
                'sttn',
                'lama',
              ]}
              onChange={value => setField('backend', value)}
            />
            <SelectField
              label={atomicTools.fields.device}
              hint={atomicTools.hints.device}
              hintAriaLabel={atomicTools.hints.termHintAria}
              value={String(params.device ?? 'auto')}
              options={['auto', 'mps', 'cuda', 'cpu']}
              onChange={value => setField('device', value)}
            />
            <TextField
              label={atomicTools.fields.maxLoad}
              hint={atomicTools.hints.maxLoad}
              hintAriaLabel={atomicTools.hints.termHintAria}
              type="number"
              value={String(params.max_load ?? '')}
              onChange={value => setField('max_load', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.maskDilateX}
              hint={atomicTools.hints.maskDilateX}
              hintAriaLabel={atomicTools.hints.termHintAria}
              type="number"
              value={String(params.mask_dilate_x ?? '')}
              onChange={value => setField('mask_dilate_x', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.maskDilateY}
              hint={atomicTools.hints.maskDilateY}
              hintAriaLabel={atomicTools.hints.termHintAria}
              type="number"
              value={String(params.mask_dilate_y ?? '')}
              onChange={value => setField('mask_dilate_y', value === '' ? '' : Number(value))}
            />
            {showNeighborStride && (
              <TextField
                label={atomicTools.fields.neighborStride}
                hint={atomicTools.hints.neighborStride}
                hintAriaLabel={atomicTools.hints.termHintAria}
                type="number"
                value={String(params.neighbor_stride ?? '')}
                onChange={value => setField('neighbor_stride', value === '' ? '' : Number(value))}
              />
            )}
            <TextField
              label={atomicTools.fields.referenceLength}
              hint={atomicTools.hints.referenceLength}
              hintAriaLabel={atomicTools.hints.termHintAria}
              type="number"
              value={String(params.reference_length ?? '')}
              onChange={value => setField('reference_length', value === '' ? '' : Number(value))}
            />
          </div>
        </details>
      </div>
    )
  }

  if (toolId === 'transcript-correction') {
    const preset = String(params.preset ?? 'standard')
    const arbitration = String(params.llm_arbitration ?? 'off')
    return (
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium text-slate-700">{atomicTools.fields.preset}</div>
          <div className="grid gap-2 md:grid-cols-3">
            {(['conservative', 'standard', 'aggressive'] as const).map(option => (
              <button
                key={option}
                type="button"
                onClick={() => setField('preset', option)}
                className={`rounded-2xl border p-3 text-left transition ${
                  preset === option
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="text-sm font-semibold text-slate-900">
                  {atomicTools.correctionPresetLabels[option]}
                </div>
                <div className="mt-1 text-xs leading-5 text-slate-500">
                  {atomicTools.correctionPresetHints[option]}
                </div>
              </button>
            ))}
          </div>
        </div>
        <div>
          <SelectField
            label={atomicTools.fields.llmArbitration}
            value={arbitration}
            options={(['off', 'deepseek'] as const).map(value => ({
              value,
              label: atomicTools.arbitrationOptions[value],
            }))}
            onChange={value => setField('llm_arbitration', value)}
          />
          <p className="mt-1.5 text-xs leading-5 text-slate-500">{atomicTools.arbitrationHint}</p>
        </div>
      </div>
    )
  }

  if (toolId === 'm3u8-to-mp4') {
    const sourceType = String(params.source_type ?? 'url')
    const mode = String(params.mode ?? 'copy')
    return (
      <div className="space-y-4">
        <div className="inline-flex rounded-full border border-slate-200 p-1">
          {(['url', 'file'] as const).map(option => (
            <button
              key={option}
              type="button"
              onClick={() => setField('source_type', option)}
              className={`rounded-full px-3 py-1.5 text-sm ${sourceType === option ? 'bg-slate-900 text-white' : 'text-slate-500'}`}
            >
              {atomicTools.options.m3u8Source[option]}
            </button>
          ))}
        </div>

        {sourceType === 'url' && (
          <TextField
            label={atomicTools.fields.m3u8Url}
            hint={atomicTools.hints.m3u8Url}
            hintAriaLabel={atomicTools.hints.termHintAria}
            value={String(params.url ?? '')}
            onChange={value => setField('url', value)}
          />
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <SelectField
            label={atomicTools.fields.m3u8Mode}
            hint={atomicTools.hints.m3u8Mode}
            hintAriaLabel={atomicTools.hints.termHintAria}
            value={mode}
            options={(['copy', 'transcode'] as const).map(value => ({ value, label: atomicTools.options.m3u8Mode[value] }))}
            onChange={value => setField('mode', value)}
          />
          <SelectField
            label={atomicTools.fields.outputFormat}
            value={String(params.output_format ?? 'mp4')}
            options={['mp4', 'mkv']}
            onChange={value => setField('output_format', value)}
          />
        </div>

        <p className="text-xs leading-5 text-slate-500">{atomicTools.hints.m3u8Live}</p>

        <details className="group rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-1 py-0.5 text-sm font-medium text-slate-700 transition-colors hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300">
            <span className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="inline-flex h-4 w-4 items-center justify-center text-slate-400 transition-transform group-open:rotate-90"
              >
                ▶
              </span>
              {atomicTools.fields.advanced}
            </span>
            <span className="hidden text-xs font-normal text-slate-400 sm:inline">
              {atomicTools.fields.advancedHint}
            </span>
          </summary>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <TextField
              label={atomicTools.fields.durationLimit}
              type="number"
              value={String(params.duration_limit_sec ?? '')}
              onChange={value => setField('duration_limit_sec', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.startOffset}
              type="number"
              value={String(params.start_sec ?? '')}
              onChange={value => setField('start_sec', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.userAgent}
              value={String(params.user_agent ?? '')}
              onChange={value => setField('user_agent', value)}
            />
            <TextField
              label={atomicTools.fields.referer}
              value={String(params.referer ?? '')}
              onChange={value => setField('referer', value)}
            />
            <TextField
              label={atomicTools.fields.outputName}
              value={String(params.output_name ?? '')}
              onChange={value => setField('output_name', value)}
            />
          </div>
          <div className="mt-4">
            <TextAreaField
              label={atomicTools.fields.httpHeaders}
              value={String(params.headers ?? '')}
              onChange={value => setField('headers', value)}
            />
            <p className="mt-1.5 text-xs leading-5 text-slate-500">{atomicTools.hints.m3u8Headers}</p>
          </div>
          {mode === 'transcode' && (
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <TextField
                label={atomicTools.fields.crf}
                type="number"
                value={String(params.crf ?? 20)}
                onChange={value => setField('crf', value === '' ? '' : Number(value))}
              />
              <SelectField
                label={atomicTools.fields.x264Preset}
                value={String(params.preset ?? 'veryfast')}
                options={['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow']}
                onChange={value => setField('preset', value)}
              />
              <TextField
                label={atomicTools.fields.audioBitrate}
                value={String(params.audio_bitrate ?? '192k')}
                onChange={value => setField('audio_bitrate', value)}
              />
            </div>
          )}
        </details>
      </div>
    )
  }

  return null
}

function buildRunPayload(
  toolId: string,
  params: ToolParams,
  fileRefs: FileRefMap,
  textInput: string,
  translationInputMode: 'text' | 'file',
) {
  if (
    toolId === 'separation' ||
    toolId === 'probe' ||
    toolId === 'transcription' ||
    toolId === 'detect-language'
  ) {
    return { ...params, file_id: fileRefs.file?.file_id }
  }

  if (toolId === 'subtitle-detect') {
    return { ...params, file_id: fileRefs.file?.file_id }
  }

  if (toolId === 'video-analyze') {
    const cleaned: Record<string, unknown> = {
      file_id: fileRefs.file?.file_id,
    }
    if (fileRefs.detection_file?.file_id) {
      cleaned.detection_file_id = fileRefs.detection_file.file_id
    }
    for (const [key, value] of Object.entries(params)) {
      if (value === '' || value === undefined) continue
      if (key === 'max_units' && !value) continue
      cleaned[key] = value
    }
    return cleaned
  }

  if (toolId === 'subtitle-erase') {
    const cleaned: Record<string, unknown> = {
      file_id: fileRefs.file?.file_id,
    }
    if (fileRefs.detection_file?.file_id) {
      cleaned.detection_file_id = fileRefs.detection_file.file_id
    }
    for (const [key, value] of Object.entries(params)) {
      if (value === '' || value === undefined) continue
      if (key === 'backend' && value === '') continue
      cleaned[key] = value
    }
    return cleaned
  }

  if (toolId === 'mixing') {
    return {
      ...params,
      voice_file_id: fileRefs.voice_file?.file_id,
      background_file_id: fileRefs.background_file?.file_id,
    }
  }

  if (toolId === 'translation') {
    const trimmedText = textInput.trim()
    const uploadedFileId = fileRefs.file?.file_id
    const useFile = translationInputMode === 'file' ? Boolean(uploadedFileId) : !trimmedText && Boolean(uploadedFileId)
    return {
      ...params,
      text: useFile ? undefined : trimmedText || undefined,
      file_id: useFile ? uploadedFileId : undefined,
    }
  }

  if (toolId === 'tts') {
    return {
      ...params,
      text: textInput,
      reference_audio_file_id: fileRefs.reference_audio_file?.file_id,
    }
  }

  if (toolId === 'muxing') {
    return {
      ...params,
      video_file_id: fileRefs.video_file?.file_id,
      audio_file_id: fileRefs.audio_file?.file_id,
    }
  }

  if (toolId === 'subtitle-burn' || toolId === 'subtitle-embed') {
    return {
      ...params,
      video_file_id: fileRefs.video_file?.file_id,
      subtitle_file_id: fileRefs.subtitle_file?.file_id,
    }
  }

  if (toolId === 'watermark') {
    const mode = String(params.mode ?? 'image')
    const cleaned: Record<string, unknown> = {
      video_file_id: fileRefs.video_file?.file_id,
      mode,
      position: params.position ?? 'bottom-right',
      margin: params.margin,
      opacity: params.opacity,
      quality: params.quality ?? 'balanced',
    }
    if (mode === 'image') {
      cleaned.image_file_id = fileRefs.image_file?.file_id
      cleaned.scale = params.scale
    } else {
      const text = String(params.text ?? '').trim()
      if (text) cleaned.text = text
      cleaned.font_size = params.font_size
      cleaned.font_color = params.font_color
      const strokeColorRaw = String(params.stroke_color ?? 'black')
      const strokeOpacity = Number(params.stroke_opacity ?? 0.6)
      cleaned.stroke_color =
        Number.isFinite(strokeOpacity) && strokeOpacity < 1
          ? `${strokeColorRaw}@${strokeOpacity}`
          : strokeColorRaw
      cleaned.stroke_width = params.stroke_width
    }
    return cleaned
  }

  if (toolId === 'dub-render') {
    return {
      ...params,
      translation_file_id: fileRefs.translation_file?.file_id,
      background_file_id: fileRefs.background_file?.file_id,
      reference_audio_file_id: fileRefs.reference_audio_file?.file_id,
      video_file_id: fileRefs.video_file?.file_id,
    }
  }

  if (toolId === 'transcript-correction') {
    return {
      ...params,
      segments_file_id: fileRefs.segments_file?.file_id,
      ocr_events_file_id: fileRefs.ocr_events_file?.file_id,
    }
  }

  if (toolId === 'm3u8-to-mp4') {
    const sourceType = String(params.source_type ?? 'url')
    const cleaned: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(params)) {
      // source_type is a UI-only toggle; url is re-added below per source mode.
      if (key === 'source_type' || key === 'url') continue
      if (value === '' || value === undefined || value === null) continue
      cleaned[key] = value
    }
    if (sourceType === 'file') {
      cleaned.playlist_file_id = fileRefs.playlist_file?.file_id
    } else {
      const url = String(params.url ?? '').trim()
      if (url) cleaned.url = url
    }
    return cleaned
  }

  return params
}

const transcriptionGlobalDefaultKeys = [
  'asr_backend',
  'asr_model',
  'generate_srt',
  'vad_filter',
  'vad_min_silence_duration_ms',
  'beam_size',
  'best_of',
  'temperature',
  'condition_on_previous_text',
] as const satisfies readonly (keyof TaskConfig)[]

function applyTranscriptionGlobalDefaults(current: ToolParams, globalDefaults: Partial<TaskConfig>): ToolParams {
  const base = getDefaultParams('transcription')
  const next = { ...current }

  for (const key of transcriptionGlobalDefaultKeys) {
    const value = globalDefaults[key]
    if (value === undefined || value === null) continue
    if (current[key] === undefined || current[key] === base[key]) {
      next[key] = value as ToolParams[string]
    }
  }

  return next
}

function getDefaultParams(toolId: string, globalDefaults?: Partial<TaskConfig>): ToolParams {
  let params: ToolParams

  switch (toolId) {
    case 'separation':
      params = { mode: 'auto', quality: 'balanced', output_format: 'wav', cdx23_overlap: 0.5 }
      break
    case 'mixing':
      params = { background_gain_db: -8, ducking_mode: 'static', output_format: 'wav' }
      break
    case 'transcription':
      params = {
        language: 'zh',
        asr_backend: 'funasr',
        asr_model: 'paraformer-zh',
        enable_diarization: true,
        generate_srt: true,
        vad_filter: true,
        vad_min_silence_duration_ms: 400,
        vad_max_segment_sec: 30,
        beam_size: 5,
        best_of: 5,
        temperature: 0,
        condition_on_previous_text: false,
      }
      break
    case 'translation':
      params = { source_lang: 'zh', target_lang: 'en', backend: 'local-m2m100' }
      break
    case 'tts':
      params = { language: 'auto', backend: 'qwen3tts' }
      break
    case 'muxing':
      params = { video_codec: 'copy', audio_codec: 'aac', audio_bitrate: '192k' }
      break
    case 'detect-language':
      params = { model: 'medium', windows: 3 }
      break
    case 'dub-render':
      params = { backend: 'qwen3tts', target_lang: 'auto', ducking_mode: 'static', background_gain_db: -8 }
      break
    case 'subtitle-detect':
      params = {
        language: 'ch',
        sample_interval: 0.4,
        preview_frames: 3,
        position_mode: 'auto',
        extraction_mode: 'conservative',
      }
      break
    case 'subtitle-erase':
      params = { preset: 'balanced', backend: '', device: 'auto' }
      break
    case 'subtitle-burn':
      params = { lang: 'auto', position: 'bottom', quality: 'balanced' }
      break
    case 'subtitle-embed':
      params = { container: 'mp4', subtitle_language: 'und' }
      break
    case 'watermark':
      params = {
        mode: 'image',
        position: 'bottom-right',
        margin: 24,
        opacity: 0.8,
        scale: 0.15,
        quality: 'balanced',
        text: '',
        font_size: 36,
        font_color: 'white',
        stroke_color: 'black',
        stroke_opacity: 0.6,
        stroke_width: 2,
      }
      break
    case 'video-analyze':
      params = {
        task: 'scene-context',
        sample_interval: 10,
        frames_per_unit: 4,
        lang: 'zh',
        backend: 'auto',
      }
      break
    case 'transcript-correction':
      params = { preset: 'standard', llm_arbitration: 'off' }
      break
    case 'm3u8-to-mp4':
      params = {
        source_type: 'url',
        url: '',
        mode: 'copy',
        output_format: 'mp4',
        crf: 20,
        preset: 'veryfast',
        audio_bitrate: '192k',
      }
      break
    default:
      params = {}
  }

  return toolId === 'transcription' && globalDefaults
    ? applyTranscriptionGlobalDefaults(params, globalDefaults)
    : params
}

function languageOptions(
  codes: readonly string[],
  getLanguageLabel: (code: string) => string,
  locale: Locale,
): SelectOption[] {
  return codes.map(code => ({
    value: code,
    label:
      code === 'auto'
        ? locale === 'zh-CN'
          ? '自动检测 (auto)'
          : 'Auto Detect (auto)'
        : `${getLanguageLabel(code)} (${code})`,
  }))
}

function TermHint({ hint, ariaLabel }: { hint: string; ariaLabel: string }) {
  const [open, setOpen] = useState(false)
  const tooltipId = useStableId('term-hint')
  const show = () => setOpen(true)
  const hide = () => setOpen(false)
  return (
    <span className="relative inline-flex">
      <span
        role="button"
        aria-label={ariaLabel}
        aria-describedby={open ? tooltipId : undefined}
        tabIndex={0}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onKeyDown={event => {
          if (event.key === 'Escape') hide()
        }}
        className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full text-slate-400 transition-colors hover:text-slate-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        <Info size={14} aria-hidden="true" />
      </span>
      {open && (
        <span
          id={tooltipId}
          role="tooltip"
          className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 w-64 -translate-x-1/2 rounded-lg bg-slate-900 px-3 py-2 text-xs leading-5 text-white shadow-lg"
        >
          {hint}
        </span>
      )}
    </span>
  )
}

function FieldLabelRow({
  label,
  htmlFor,
  hint,
  hintAriaLabel,
}: {
  label: string
  htmlFor?: string
  hint?: string
  hintAriaLabel?: string
}) {
  return (
    <span className="flex items-center gap-1.5 text-sm font-medium text-slate-700">
      <label htmlFor={htmlFor} className="cursor-pointer">
        {label}
      </label>
      {hint && <TermHint hint={hint} ariaLabel={hintAriaLabel ?? label} />}
    </span>
  )
}

const useStableId = (prefix: string) => {
  const reactId = useId()
  return `${prefix}-${reactId.replace(/[^a-zA-Z0-9_-]/g, '')}`
}

function SelectField({
  label,
  value,
  options,
  onChange,
  hint,
  hintAriaLabel,
}: {
  label: string
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  hint?: string
  hintAriaLabel?: string
}) {
  const id = useStableId('select-field')
  return (
    <div className="block space-y-2 text-sm">
      <FieldLabelRow label={label} htmlFor={id} hint={hint} hintAriaLabel={hintAriaLabel} />
      <select id={id} value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700">
        {options.map(option => (
          <option key={typeof option === 'string' ? option : option.value} value={typeof option === 'string' ? option : option.value}>
            {typeof option === 'string' ? option : option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

function TextField({
  label,
  value,
  onChange,
  type = 'text',
  hint,
  hintAriaLabel,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  hint?: string
  hintAriaLabel?: string
}) {
  const id = useStableId('text-field')
  return (
    <div className="block space-y-2 text-sm">
      <FieldLabelRow label={label} htmlFor={id} hint={hint} hintAriaLabel={hintAriaLabel} />
      <input id={id} type={type} value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700" />
    </div>
  )
}

function TextAreaField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="block space-y-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <textarea rows={6} value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm leading-6 text-slate-700" />
    </label>
  )
}

function CheckboxField({
  label,
  checked,
  onChange,
  hint,
  hintAriaLabel,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  hint?: string
  hintAriaLabel?: string
}) {
  return (
    <div className="inline-flex items-center gap-3 rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700">
      <label className="inline-flex cursor-pointer items-center gap-3">
        <input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} />
        <span>{label}</span>
      </label>
      {hint && <TermHint hint={hint} ariaLabel={hintAriaLabel ?? label} />}
    </div>
  )
}
