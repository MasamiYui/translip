import { useState, type Dispatch, type SetStateAction } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { atomicToolsApi } from '../api/atomic-tools'
import { FileUploadZone } from '../components/atomic-tools/FileUploadZone'
import { ResultPanel } from '../components/atomic-tools/ResultPanel'
import { ToolProgressBar } from '../components/atomic-tools/ToolProgressBar'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { useAtomicTool } from '../hooks/useAtomicTool'
import { useI18n } from '../i18n/useI18n'
import type { Locale, LocaleMessages } from '../i18n/messages'
import { readAtomicToolPrefill, type AtomicToolPrefill } from '../lib/atomicToolPrefill'
import type { FileUploadResponse } from '../types/atomic-tools'

type FileRefMap = Record<string, FileUploadResponse | null>
type SelectOption = string | { value: string; label: string }

const TRANSCRIPTION_LANGUAGE_CODES = ['auto', 'zh', 'en', 'ja'] as const

export function ToolPage() {
  const { toolId = 'probe' } = useParams()
  const [searchParams] = useSearchParams()
  const prefillParam = searchParams.get('prefill') ?? ''

  return <ToolPageContent key={`${toolId}:${prefillParam}`} toolId={toolId} prefillParam={prefillParam} />
}

function ToolPageContent({ toolId, prefillParam }: { toolId: string; prefillParam: string }) {
  const { locale, t, getLanguageLabel } = useI18n()
  const prefill = readAtomicToolPrefill(prefillParam)
  const { data: tools = [] } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })
  const tool = tools.find(item => item.tool_id === toolId)
  const { uploadFile, job, artifacts, runTool, isRunning, getDownloadUrl, errorMessage, reset } =
    useAtomicTool({ toolId })

  const [fileRefs, setFileRefs] = useState<FileRefMap>(() => buildInitialFileRefs(prefill))
  const [translationInputMode, setTranslationInputMode] = useState<'text' | 'file'>('text')
  const [textInput, setTextInput] = useState(() => prefill?.text ?? '')
  const [params, setParams] = useState<Record<string, string | number | boolean>>(getDefaultParams(toolId))

  if (!tool) {
    return (
      <PageContainer className={APP_CONTENT_MAX_WIDTH}>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
          {t.common.loading}
        </div>
      </PageContainer>
    )
  }

  const title = locale === 'zh-CN' ? tool.name_zh : tool.name_en
  const description = locale === 'zh-CN' ? tool.description_zh : tool.description_en
  const uploadGridClass = toolId === 'mixing' || toolId === 'muxing'
    ? 'grid gap-4 md:grid-cols-2'
    : 'grid gap-4'

  async function handleFileSelected(slot: string, file: File) {
    const uploaded = await uploadFile(file)
    setFileRefs(prev => ({ ...prev, [slot]: uploaded }))
  }

  async function handleRun() {
    const payload = buildRunPayload(toolId, params, fileRefs, textInput, translationInputMode)
    await runTool(payload)
  }

  function handleReset() {
    setFileRefs({})
    setTextInput('')
    setTranslationInputMode('text')
    setParams(getDefaultParams(toolId))
    reset()
  }

  return (
    <PageContainer className={`${APP_CONTENT_MAX_WIDTH} space-y-6`}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/tools" className="mb-2 inline-flex items-center gap-2 text-sm text-slate-500">
            <ArrowLeft size={16} />
            {t.atomicTools.back}
          </Link>
          <h1 className="text-3xl font-semibold text-slate-900">{title}</h1>
          <p className="mt-2 text-sm leading-7 text-slate-600">{description}</p>
        </div>
        <button
          type="button"
          onClick={handleReset}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600"
        >
          <RefreshCw size={16} />
          {t.atomicTools.actions.reset}
        </button>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="space-y-6">
          <div className={uploadGridClass}>
            {renderUploadZones(toolId, fileRefs, handleFileSelected, t.atomicTools.uploadHints)}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5">
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

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void handleRun()}
              disabled={isRunning}
              className="rounded-full bg-blue-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isRunning ? t.atomicTools.actions.running : t.atomicTools.actions.run}
            </button>
            {errorMessage && <span className="text-sm text-rose-600">{errorMessage}</span>}
          </div>

          <ToolProgressBar job={job} />
        </section>

        <ResultPanel toolId={toolId} job={job} artifacts={artifacts} getDownloadUrl={getDownloadUrl} />
      </div>
    </PageContainer>
  )
}

function renderUploadZones(
  toolId: string,
  fileRefs: FileRefMap,
  onFileSelected: (slot: string, file: File) => Promise<void>,
  hints: Record<string, string>,
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
  params: Record<string, string | number | boolean>,
  setParams: Dispatch<SetStateAction<Record<string, string | number | boolean>>>,
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
  const transcriptionLanguageOptions = TRANSCRIPTION_LANGUAGE_CODES.map(code => ({
    value: code,
    label:
      code === 'auto'
        ? locale === 'zh-CN'
          ? '自动检测 (auto)'
          : 'Auto Detect (auto)'
        : `${getLanguageLabel(code)} (${code})`,
  }))

  if (toolId === 'separation') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField label={atomicTools.fields.mode} value={String(params.mode)} options={['auto', 'music', 'dialogue']} onChange={value => setField('mode', value)} />
        <SelectField label={atomicTools.fields.quality} value={String(params.quality)} options={['balanced', 'high']} onChange={value => setField('quality', value)} />
        <SelectField label={atomicTools.fields.outputFormat} value={String(params.output_format)} options={['wav', 'mp3', 'flac']} onChange={value => setField('output_format', value)} />
      </div>
    )
  }

  if (toolId === 'mixing') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <TextField label={atomicTools.fields.backgroundGain} type="number" value={String(params.background_gain_db)} onChange={value => setField('background_gain_db', Number(value))} />
        <SelectField label={atomicTools.fields.duckingMode} value={String(params.ducking_mode)} options={['static', 'sidechain']} onChange={value => setField('ducking_mode', value)} />
        <SelectField label={atomicTools.fields.outputFormat} value={String(params.output_format)} options={['wav', 'mp3']} onChange={value => setField('output_format', value)} />
      </div>
    )
  }

  if (toolId === 'transcription') {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <SelectField label={atomicTools.fields.language} value={String(params.language)} options={transcriptionLanguageOptions} onChange={value => setField('language', value)} />
        <SelectField label={atomicTools.fields.asrModel} value={String(params.asr_model)} options={['tiny', 'base', 'small', 'medium', 'large-v3']} onChange={value => setField('asr_model', value)} />
        <CheckboxField label={atomicTools.fields.enableDiarization} checked={Boolean(params.enable_diarization)} onChange={value => setField('enable_diarization', value)} />
        <CheckboxField label={atomicTools.fields.generateSrt} checked={Boolean(params.generate_srt)} onChange={value => setField('generate_srt', value)} />
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
          <TextField label={atomicTools.fields.sourceLang} value={String(params.source_lang)} onChange={value => setField('source_lang', value)} />
          <TextField label={atomicTools.fields.targetLang} value={String(params.target_lang)} onChange={value => setField('target_lang', value)} />
          <SelectField label={atomicTools.fields.backend} value={String(params.backend)} options={['local-m2m100', 'siliconflow']} onChange={value => setField('backend', value)} />
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

  return null
}

function buildRunPayload(
  toolId: string,
  params: Record<string, string | number | boolean>,
  fileRefs: FileRefMap,
  textInput: string,
  translationInputMode: 'text' | 'file',
) {
  if (toolId === 'separation' || toolId === 'probe' || toolId === 'transcription') {
    return { ...params, file_id: fileRefs.file?.file_id }
  }

  if (toolId === 'mixing') {
    return {
      ...params,
      voice_file_id: fileRefs.voice_file?.file_id,
      background_file_id: fileRefs.background_file?.file_id,
    }
  }

  if (toolId === 'translation') {
    return {
      ...params,
      text: translationInputMode === 'text' ? textInput : undefined,
      file_id: translationInputMode === 'file' ? fileRefs.file?.file_id : undefined,
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

  return params
}

function getDefaultParams(toolId: string): Record<string, string | number | boolean> {
  switch (toolId) {
    case 'separation':
      return { mode: 'auto', quality: 'balanced', output_format: 'wav' }
    case 'mixing':
      return { background_gain_db: -8, ducking_mode: 'static', output_format: 'wav' }
    case 'transcription':
      return { language: 'zh', asr_model: 'small', enable_diarization: false, generate_srt: true }
    case 'translation':
      return { source_lang: 'zh', target_lang: 'en', backend: 'local-m2m100' }
    case 'tts':
      return { language: 'auto' }
    case 'muxing':
      return { video_codec: 'copy', audio_codec: 'aac', audio_bitrate: '192k' }
    default:
      return {}
  }
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
}) {
  return (
    <label className="space-y-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <select value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700">
        {options.map(option => (
          <option key={typeof option === 'string' ? option : option.value} value={typeof option === 'string' ? option : option.value}>
            {typeof option === 'string' ? option : option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function TextField({
  label,
  value,
  onChange,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
}) {
  return (
    <label className="space-y-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <input type={type} value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700" />
    </label>
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
    <label className="space-y-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <textarea rows={6} value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm leading-6 text-slate-700" />
    </label>
  )
}

function CheckboxField({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="inline-flex items-center gap-3 rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700">
      <input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} />
      {label}
    </label>
  )
}
