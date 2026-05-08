import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'
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
import { readAtomicToolPrefill } from '../lib/atomicToolPrefill'
import type { FileUploadResponse } from '../types/atomic-tools'

type FileRefMap = Record<string, FileUploadResponse | null>

export function ToolPage() {
  const { toolId = 'probe' } = useParams()
  const { locale, t } = useI18n()
  const [searchParams] = useSearchParams()
  const { data: tools = [] } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })
  const tool = tools.find(item => item.tool_id === toolId)
  const { uploadFile, job, artifacts, runTool, isRunning, getDownloadUrl, errorMessage, reset } =
    useAtomicTool({ toolId })

  const [fileRefs, setFileRefs] = useState<FileRefMap>({})
  const [translationInputMode, setTranslationInputMode] = useState<'text' | 'file'>('text')
  const [textInput, setTextInput] = useState('')
  const [params, setParams] = useState<Record<string, string | number | boolean>>(getDefaultParams(toolId))

  useEffect(() => {
    setFileRefs({})
    setTextInput('')
    setTranslationInputMode('text')
    setParams(getDefaultParams(toolId))
    reset()
  }, [toolId])

  useEffect(() => {
    const prefill = readAtomicToolPrefill(searchParams.get('prefill'))
    if (!prefill) return

    if (prefill.text) {
      setTextInput(prefill.text)
      if (toolId === 'translation' || toolId === 'tts') {
        setTranslationInputMode('text')
      }
    }

    if (prefill.files) {
      setFileRefs(prev => {
        const next = { ...prev }
        for (const [key, value] of Object.entries(prefill.files ?? {})) {
          next[key] = {
            file_id: value.file_id,
            filename: value.filename,
            size_bytes: 0,
            content_type: 'application/octet-stream',
          }
        }
        return next
      })
    }
  }, [searchParams, toolId])

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

  async function handleFileSelected(slot: string, file: File) {
    const uploaded = await uploadFile(file)
    setFileRefs(prev => ({ ...prev, [slot]: uploaded }))
  }

  async function handleRun() {
    const payload = buildRunPayload(toolId, params, fileRefs, textInput, translationInputMode)
    await runTool(payload)
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
          onClick={reset}
          className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600"
        >
          <RefreshCw size={16} />
          {t.atomicTools.actions.reset}
        </button>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            {renderUploadZones(toolId, fileRefs, handleFileSelected, t.atomicTools.uploadHints)}
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5">
            {renderControls(
              toolId,
              params,
              setParams,
              textInput,
              setTextInput,
              translationInputMode,
              setTranslationInputMode,
              t.atomicTools,
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
        />
      </>
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

function renderControls(
  toolId: string,
  params: Record<string, string | number | boolean>,
  setParams: Dispatch<SetStateAction<Record<string, string | number | boolean>>>,
  textInput: string,
  setTextInput: Dispatch<SetStateAction<string>>,
  translationInputMode: 'text' | 'file',
  setTranslationInputMode: Dispatch<SetStateAction<'text' | 'file'>>,
  atomicTools: any,
) {
  const setField = (key: string, value: string | number | boolean) => {
    setParams(prev => ({ ...prev, [key]: value }))
  }

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
        <TextField label={atomicTools.fields.language} value={String(params.language)} onChange={value => setField('language', value)} />
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

  if (toolId === 'subtitle-detect') {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField
          label={atomicTools.fields.language}
          value={String(params.language ?? 'ch')}
          options={['ch', 'en', 'ch_tra', 'japan', 'korean']}
          onChange={value => setField('language', value)}
        />
        <SelectField
          label={atomicTools.fields.positionMode}
          value={String(params.position_mode ?? 'bottom')}
          options={['auto', 'bottom', 'top', 'full']}
          onChange={value => setField('position_mode', value)}
        />
        <TextField
          label={atomicTools.fields.roiBottomRatio}
          type="number"
          value={String(params.roi_bottom_ratio ?? 0.34)}
          onChange={value => setField('roi_bottom_ratio', Number(value))}
        />
        <TextField
          label={atomicTools.fields.sampleInterval}
          type="number"
          value={String(params.sample_interval ?? 0.4)}
          onChange={value => setField('sample_interval', Number(value))}
        />
        <TextField
          label={atomicTools.fields.mergeThreshold}
          type="number"
          value={String(params.merge_threshold ?? 0.78)}
          onChange={value => setField('merge_threshold', Number(value))}
        />
        <TextField
          label={atomicTools.fields.previewFrames}
          type="number"
          value={String(params.preview_frames ?? 3)}
          onChange={value => setField('preview_frames', Number(value))}
        />
      </div>
    )
  }

  if (toolId === 'subtitle-erase') {
    const preset = String(params.preset ?? 'fast')
    return (
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium text-slate-700">{atomicTools.fields.preset}</div>
          <div className="grid gap-2 md:grid-cols-3">
            {(['fast', 'balanced', 'quality'] as const).map(option => (
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

        <details className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">
            {atomicTools.fields.advanced}
          </summary>
          <div className="mt-3 grid gap-4 md:grid-cols-3">
            <SelectField
              label={atomicTools.fields.mode}
              value={String(params.mode ?? 'auto')}
              options={['auto', 'manual']}
              onChange={value => setField('mode', value)}
            />
            <SelectField
              label={atomicTools.fields.backend}
              value={String(params.backend ?? '')}
              options={['', 'telea', 'flow-guided', 'lama']}
              onChange={value => setField('backend', value)}
            />
            <CheckboxField
              label={atomicTools.fields.autoTune}
              checked={Boolean(params.auto_tune)}
              onChange={value => setField('auto_tune', value)}
            />
            <TextField
              label={atomicTools.fields.maskDilateX}
              type="number"
              value={String(params.mask_dilate_x ?? '')}
              onChange={value => setField('mask_dilate_x', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.maskDilateY}
              type="number"
              value={String(params.mask_dilate_y ?? '')}
              onChange={value => setField('mask_dilate_y', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.temporalRadius}
              type="number"
              value={String(params.mask_temporal_radius ?? '')}
              onChange={value => setField('mask_temporal_radius', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.cleanupCoverage}
              type="number"
              value={String(params.cleanup_max_coverage ?? '')}
              onChange={value => setField('cleanup_max_coverage', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.temporalConsensus}
              type="number"
              value={String(params.temporal_consensus ?? '')}
              onChange={value => setField('temporal_consensus', value === '' ? '' : Number(value))}
            />
            <TextField
              label={atomicTools.fields.temporalStd}
              type="number"
              value={String(params.temporal_std_threshold ?? '')}
              onChange={value => setField('temporal_std_threshold', value === '' ? '' : Number(value))}
            />
          </div>
        </details>
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

  if (toolId === 'subtitle-detect') {
    return { ...params, file_id: fileRefs.file?.file_id }
  }

  if (toolId === 'subtitle-erase') {
    const cleaned: Record<string, unknown> = {
      file_id: fileRefs.file?.file_id,
      detection_file_id: fileRefs.detection_file?.file_id,
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
    case 'subtitle-detect':
      return {
        language: 'ch',
        position_mode: 'bottom',
        roi_bottom_ratio: 0.34,
        sample_interval: 0.4,
        merge_threshold: 0.78,
        preview_frames: 3,
      }
    case 'subtitle-erase':
      return { preset: 'fast', mode: 'auto', backend: '', auto_tune: false }
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
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <label className="space-y-2 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <select value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-2xl border border-slate-200 px-3 py-2.5 text-sm text-slate-700">
        {options.map(option => (
          <option key={option} value={option}>
            {option}
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
