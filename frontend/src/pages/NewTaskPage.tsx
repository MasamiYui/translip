import { useId, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Cpu, FolderOpen, Loader2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { worksApi } from '../api/works'
import { configApi, systemApi } from '../api/config'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { buildTemplatePreviewGraph } from '../lib/workflowPreview'
import { DUBBING_BACKEND_OPTIONS } from '../lib/dubbingBackends'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { getOutputIntentLabel, getQualityPresetLabel } from '../lib/taskPresentation'
import type {
  CreateTaskRequest,
  TaskConfig,
  TaskOutputIntent,
  TaskQualityPreset,
  TranscriptionCorrectionConfig,
  TranscriptionCorrectionPreset,
} from '../types'
import { LANGUAGE_CODES, STAGE_ORDER } from '../i18n/formatters'
import { useI18n } from '../i18n/useI18n'

const defaultConfig: Partial<TaskConfig> = {
  device: 'auto',
  output_intent: 'dub_final',
  quality_preset: 'standard',
  template: 'asr-dub-basic',
  run_from_stage: 'separation',
  run_to_stage: 'delivery',
  use_cache: true,
  keep_intermediate: false,
  video_source: 'original',
  audio_source: 'both',
  subtitle_source: 'asr',
  separation_mode: 'dialogue',
  separation_quality: 'balanced',
  music_backend: 'demucs',
  dialogue_backend: 'cdx23',
  stage1_output_format: 'mp3',
  audio_stream_index: 0,
  asr_model: 'paraformer-zh',
  asr_backend: 'funasr',
  diarizer_backend: 'ecapa',
  enable_diarization: true,
  generate_srt: true,
  vad_filter: true,
  vad_min_silence_duration_ms: 400,
  beam_size: 5,
  best_of: 5,
  temperature: 0.0,
  condition_on_previous_text: false,
  transcription_correction: {
    enabled: true,
    preset: 'standard',
    ocr_only_policy: 'report_only',
    llm_arbitration: 'off',
  },
  top_k: 3,
  ocr_sample_interval: 0.25,
  ocr_position_mode: 'auto',
  ocr_extraction_mode: 'conservative',
  translation_backend: 'local-m2m100',
  translation_batch_size: 4,
  condense_mode: 'smart',
  tts_backend: 'moss-tts-nano-onnx',
  dubbing_quality_check: 'standard',
  dub_repair_enabled: false,
  dub_repair_max_items: 12,
  dub_repair_attempts_per_item: 3,
  dub_repair_include_risk: false,
  fit_policy: 'conservative',
  fit_backend: 'atempo',
  mix_profile: 'preview',
  ducking_mode: 'static',
  background_gain_db: -8.0,
  window_ducking_db: -3.0,
  max_compress_ratio: 1.45,
  output_sample_rate: 48000,
  preview_format: 'wav',
  subtitle_mode: 'none',
  subtitle_render_source: 'ocr',
  erase_backend: 'sttn',
  erase_device: 'auto',
  erase_mask_dilate_x: 12,
  erase_mask_dilate_y: 8,
  erase_event_lead_frames: 3,
  erase_event_trail_frames: 8,
  erase_neighbor_stride: 5,
  erase_reference_length: 10,
  erase_max_load: 50,
}

const FASTER_WHISPER_MODEL_OPTIONS = ['tiny', 'base', 'small', 'medium', 'large-v3'].map(value => ({
  value,
  label: value,
}))

const FUNASR_MODEL_OPTIONS = [
  { value: 'paraformer-zh', label: 'Paraformer-zh' },
  { value: 'iic/SenseVoiceSmall', label: 'SenseVoiceSmall' },
]

const ASR_BACKEND_OPTIONS = [
  { value: 'faster-whisper', label: 'faster-whisper' },
  { value: 'funasr', label: 'FunASR' },
]

const DIARIZER_BACKEND_OPTIONS = [
  { value: 'ecapa', label: 'ECAPA' },
  { value: 'pyannote', label: 'pyannote' },
]

const globalDefaultKeys: Array<keyof TaskConfig> = [
  'device',
  'use_cache',
  'keep_intermediate',
  'separation_mode',
  'separation_quality',
  'music_backend',
  'dialogue_backend',
  'stage1_output_format',
  'audio_stream_index',
  'asr_model',
  'asr_backend',
  'diarizer_backend',
  'enable_diarization',
  'generate_srt',
  'vad_filter',
  'vad_min_silence_duration_ms',
  'beam_size',
  'best_of',
  'temperature',
  'condition_on_previous_text',
  'top_k',
  'ocr_sample_interval',
  'ocr_position_mode',
  'ocr_extraction_mode',
  'translation_backend',
  'translation_batch_size',
  'deepseek_model',
  'condense_mode',
  'tts_backend',
  'dubbing_workers',
  'dubbing_quality_check',
  'dub_repair_enabled',
  'dub_repair_backend',
  'dub_repair_max_items',
  'dub_repair_attempts_per_item',
  'dub_repair_include_risk',
  'fit_policy',
  'fit_backend',
  'mix_profile',
  'ducking_mode',
  'background_gain_db',
  'window_ducking_db',
  'max_compress_ratio',
  'output_sample_rate',
  'preview_format',
  'subtitle_mode',
  'subtitle_render_source',
  'subtitle_font',
  'subtitle_font_size',
  'subtitle_color',
  'subtitle_outline_color',
  'subtitle_outline_width',
  'subtitle_position',
  'subtitle_margin_v',
  'subtitle_bold',
  'bilingual_chinese_position',
  'bilingual_english_position',
  'erase_backend',
  'erase_device',
  'erase_mask_dilate_x',
  'erase_mask_dilate_y',
  'erase_event_lead_frames',
  'erase_event_trail_frames',
  'erase_neighbor_stride',
  'erase_reference_length',
  'erase_max_load',
]

function applyGlobalDefaults(
  current: Partial<TaskConfig>,
  defaults: Partial<TaskConfig>,
): Partial<TaskConfig> {
  const next: Partial<TaskConfig> = { ...current }
  for (const key of globalDefaultKeys) {
    if (defaults[key] === undefined) continue
    if (Object.is(current[key], defaultConfig[key])) {
      next[key] = defaults[key] as never
    }
  }
  const globalArbitration = (defaults as Partial<TaskConfig>).transcription_correction?.llm_arbitration
  const currentArbitration = current.transcription_correction?.llm_arbitration ?? 'off'
  if (globalArbitration && globalArbitration !== 'off' && currentArbitration === 'off') {
    const base = current.transcription_correction ??
      defaultConfig.transcription_correction ?? {
        enabled: true,
        preset: 'standard',
        ocr_only_policy: 'report_only',
        llm_arbitration: 'off',
      }
    next.transcription_correction = {
      ...base,
      llm_arbitration: globalArbitration,
    }
  }
  return next
}

function Field({
  label,
  children,
  hint,
  required = false,
  error,
  htmlFor,
  requiredMark,
}: {
  label: string
  children: React.ReactNode
  hint?: string
  required?: boolean
  error?: string
  htmlFor?: string
  requiredMark?: string
}) {
  const hintId = htmlFor && hint ? `${htmlFor}-hint` : undefined
  const errorId = htmlFor && error ? `${htmlFor}-error` : undefined
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1.5 block text-sm font-medium text-slate-700"
      >
        {label}
        {required && (
          <span
            className="ml-0.5 text-rose-500"
            aria-label={requiredMark}
            title={requiredMark}
          >
            *
          </span>
        )}
      </label>
      {children}
      {error ? (
        <p id={errorId} role="alert" className="mt-1 text-xs text-rose-500">
          {error}
        </p>
      ) : (
        hint && (
          <p id={hintId} className="mt-1 text-xs text-slate-400">
            {hint}
          </p>
        )
      )}
    </div>
  )
}

function Select({ value, onChange, options, id, ariaDescribedBy, ariaInvalid }: {
  value: string | number
  onChange: (v: string) => void
  options: { value: string | number; label: string }[]
  id?: string
  ariaDescribedBy?: string
  ariaInvalid?: boolean
}) {
  return (
    <select
      id={id}
      aria-describedby={ariaDescribedBy}
      aria-invalid={ariaInvalid || undefined}
      value={value}
      onChange={event => onChange(event.target.value)}
      className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20 focus:border-[#3b5bdb] transition-all"
    >
      {options.map(option => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

function TextInput({
  value,
  onChange,
  onBlur,
  placeholder = '',
  type = 'text',
  id,
  required = false,
  ariaDescribedBy,
  ariaInvalid,
}: {
  value: string | number
  onChange: (v: string) => void
  onBlur?: () => void
  placeholder?: string
  type?: string
  id?: string
  required?: boolean
  ariaDescribedBy?: string
  ariaInvalid?: boolean
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      onChange={event => onChange(event.target.value)}
      onBlur={onBlur}
      placeholder={placeholder}
      required={required}
      aria-required={required || undefined}
      aria-describedby={ariaDescribedBy}
      aria-invalid={ariaInvalid || undefined}
      className={`w-full rounded-lg border bg-white px-3 py-2 text-sm transition-all focus:outline-none focus:ring-2 ${
        ariaInvalid
          ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-200/40'
          : 'border-[#e5e7eb] focus:border-[#3b5bdb] focus:ring-[#3b5bdb]/20'
      }`}
    />
  )
}

function Checkbox({ checked, onChange, label }: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2">
      <input
        type="checkbox"
        checked={checked}
        onChange={event => onChange(event.target.checked)}
        className="rounded text-blue-600"
      />
      <span className="text-sm text-slate-700">{label}</span>
    </label>
  )
}

function SectionCard({
  title,
  children,
  action,
  minimal = false,
}: {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
  minimal?: boolean
}) {
  return (
    <section className={minimal ? 'space-y-3' : 'overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]'}>
      <div className={minimal ? 'flex items-center justify-between gap-3' : 'flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5'}>
        <span className={minimal ? 'text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400' : 'text-xs font-semibold uppercase tracking-widest text-slate-500'}>
          {title}
        </span>
        {action}
      </div>
      <div className={minimal ? 'space-y-4' : 'space-y-4 p-4'}>{children}</div>
    </section>
  )
}

function ConfirmRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex">
      <span className="w-28 shrink-0 text-slate-500">{label}:</span>
      <span className="font-medium text-slate-900">{value}</span>
    </div>
  )
}

function IntentCard({
  title,
  description,
  badges,
  selected,
  onClick,
}: {
  title: string
  description: string
  badges: string[]
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`rounded-xl border p-4 text-left transition-colors ${
        selected
          ? 'border-blue-500 bg-blue-50 shadow-sm'
          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
      }`}
    >
      <div className="text-sm font-semibold text-slate-900">{title}</div>
      <div className="mt-1.5 text-sm leading-6 text-slate-600">{description}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {badges.map(badge => (
          <span key={badge} className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 shadow-sm ring-1 ring-slate-200">
            {badge}
          </span>
        ))}
      </div>
    </button>
  )
}

function IntentCapabilityCard({
  title,
  capabilities,
  helper,
}: {
  title: string
  capabilities: string[]
  helper: string
}) {
  return (
    <div className="rounded-[20px] border border-slate-200/80 bg-white/80 p-4 backdrop-blur-sm">
      <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">{title}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {capabilities.map(item => (
          <span key={item} className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 shadow-sm ring-1 ring-slate-200">
            {item}
          </span>
        ))}
      </div>
      <div className="mt-3 text-sm text-slate-500">{helper}</div>
    </div>
  )
}

function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1">
      {options.map(option => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
            option.value === value ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

interface SummaryItem {
  label: string
  value: string
}

function SummaryCard({
  title,
  items,
  lines,
  tip,
  warning,
  cta,
  minimal = false,
}: {
  title: string
  items?: SummaryItem[]
  lines: string[]
  tip?: string
  warning?: string
  cta?: React.ReactNode
  minimal?: boolean
}) {
  const minimalItems = minimal
    ? items ?? lines.map((line, index) => ({ label: `item-${index}`, value: line }))
    : []

  return (
    <section className={minimal ? 'space-y-4' : 'space-y-4 rounded-xl border border-slate-200 bg-white p-5'}>
      <div>
        <div className={minimal ? 'text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400' : 'text-xs font-semibold uppercase tracking-widest text-slate-400'}>
          {title}
        </div>
        {minimal ? (
          <div className="mt-3 space-y-3">
            <div className="text-sm font-semibold text-slate-900">本次任务将生成：</div>
            <div
              data-ui-tone="neutral"
              className="overflow-hidden rounded-[20px] border border-slate-200/80 bg-white/80 p-1 backdrop-blur-sm"
            >
              <div className="grid gap-px overflow-hidden rounded-[16px] bg-slate-200/70 md:grid-cols-3">
                {minimalItems.map(item => (
                  <div key={item.label} className="bg-white/90 px-4 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                      {item.label}
                    </div>
                    <div className="mt-1.5 text-sm font-medium leading-6 text-slate-800">
                      {item.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-3 space-y-2 text-sm text-slate-700">
            <div className="font-semibold text-slate-900">本次任务将生成：</div>
            {lines.map(line => (
              <div key={line}>{line}</div>
            ))}
          </div>
        )}
      </div>
      {tip && (
        <div className={minimal ? 'rounded-[18px] border border-sky-100 bg-sky-50/80 px-4 py-3 text-sm text-sky-800' : 'rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700'}>
          {minimal && <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-500">说明</div>}
          {tip}
        </div>
      )}
      {warning && (
        <div className={minimal ? 'rounded-[18px] border border-slate-200/80 bg-white/80 px-4 py-3 text-sm text-slate-700 backdrop-blur-sm' : 'rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'}>
          {minimal && <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">注意</div>}
          {warning}
        </div>
      )}
      {cta}
    </section>
  )
}

export function NewTaskPage() {
  const { locale, t, getLanguageLabel, getStageShortLabel } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [inputPath, setInputPath] = useState('')
  const [inputPathTouched, setInputPathTouched] = useState(false)
  const [sourceLang, setSourceLang] = useState('zh')
  const [targetLang, setTargetLang] = useState('en')
  const [config, setConfig] = useState<Partial<TaskConfig>>(defaultConfig)
  // Commentary (解说) vs dubbing (配音) mode — derived from the template so the
  // toggle, step labels, gated sections, and preview graph stay in sync.
  const isCommentary = normalizeTemplateId(config.template) === 'asr-commentary'
  const [saveAsPreset, setSaveAsPreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [mediaInfo, setMediaInfo] = useState<Record<string, unknown> | null>(null)
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false)
  const [showDeveloperSettings, setShowDeveloperSettings] = useState(false)
  const [showCorrectionExplanation, setShowCorrectionExplanation] = useState(false)
  const [autoBindWork, setAutoBindWork] = useState(true)
  const [globalDefaultsApplied, setGlobalDefaultsApplied] = useState(false)

  const inputPathFieldId = useId()
  const inputPathHasError = inputPathTouched && !inputPath.trim()
  const inputPathErrorMessage = inputPathHasError ? t.newTask.validation.inputVideoPathMissing : undefined

  const steps = locale === 'zh-CN'
    ? isCommentary
      ? ['素材与语言', '解说设置', '高级设置', '确认创建']
      : ['素材与语言', '成品目标', '质量与设置', '确认创建']
    : isCommentary
      ? ['Source', 'Commentary', 'Advanced', 'Review']
      : ['Source', 'Intent', 'Quality', 'Review']

  const languageOptions = LANGUAGE_CODES.map(code => ({
    value: code,
    label: `${getLanguageLabel(code)} (${code})`,
  }))

  const stageOptions = STAGE_ORDER.map(stage => ({
    value: stage,
    label: getStageShortLabel(stage),
  }))

  const previewGraph = buildTemplatePreviewGraph(normalizeTemplateId(config.template))

  const { data: presets } = useQuery({
    queryKey: ['presets'],
    queryFn: configApi.getPresets,
  })

  const { data: globalDefaults } = useQuery({
    queryKey: ['config-defaults'],
    queryFn: configApi.getDefaults,
  })

  const { data: narratorVoices } = useQuery({
    queryKey: ['narrator-voices'],
    queryFn: configApi.narratorVoices,
    staleTime: Infinity,
  })

  // Seed the form with saved global defaults once they load, exactly once.
  // Adjusted during render (guarded by the applied flag so it converges) rather
  // than in an effect, which would be a set-state-in-effect.
  if (globalDefaults && !globalDefaultsApplied) {
    setGlobalDefaultsApplied(true)
    setConfig(prev => applyGlobalDefaults(prev, globalDefaults))
  }

  const probeMutation = useMutation({
    mutationFn: (path: string) => systemApi.probe(path),
    onSuccess: data => setMediaInfo(data),
    onError: () => setMediaInfo(null),
  })

  // Opens a native OS file dialog on the server machine (local-first) and fills
  // in the chosen absolute path, then auto-inspects it.
  const pickFileMutation = useMutation({
    mutationFn: (currentPath: string) =>
      systemApi.pickFile(currentPath || undefined, t.newTask.filePicker.title),
    onSuccess: result => {
      if (!result.path) return // user cancelled the dialog
      setInputPath(result.path)
      setMediaInfo(null)
      probeMutation.mutate(result.path)
    },
  })

  const createMutation = useMutation({
    mutationFn: async (req: CreateTaskRequest) => {
      const task = await tasksApi.create(req)
      if (autoBindWork) {
        try {
          await worksApi.autoBindTask(task.id)
        } catch {
          // Work binding is helpful context, but task creation should still succeed.
        }
      }
      return task
    },
    onSuccess: task => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/tasks/${task.id}`)
    },
  })

  function patchConfig(patch: Partial<TaskConfig>) {
    setConfig(prev => ({ ...prev, ...patch }))
  }

  const asrBackend = config.asr_backend ?? 'funasr'
  const asrModelOptions = useMemo(
    () => (asrBackend === 'funasr' ? FUNASR_MODEL_OPTIONS : FASTER_WHISPER_MODEL_OPTIONS),
    [asrBackend],
  )
  const asrModelValue = asrModelOptions.some(option => option.value === config.asr_model)
    ? String(config.asr_model)
    : asrModelOptions[0].value

  function patchAsrBackend(backend: string) {
    patchConfig({
      asr_backend: backend as TaskConfig['asr_backend'],
      asr_model: backend === 'funasr' ? FUNASR_MODEL_OPTIONS[0].value : 'small',
    })
  }

  function patchTranscriptionCorrection(patch: Partial<TranscriptionCorrectionConfig>) {
    setConfig(prev => ({
      ...prev,
      transcription_correction: {
        enabled: true,
        preset: 'standard',
        ocr_only_policy: 'report_only',
        llm_arbitration: 'off',
        ...(prev.transcription_correction ?? {}),
        ...patch,
      },
    }))
  }

  function applyPreset(presetId: string) {
    const preset = presets?.find(item => String(item.id) === presetId)
    if (!preset) return
    setConfig(prev => ({ ...prev, ...preset.config }))
    setSourceLang(preset.source_lang)
    setTargetLang(preset.target_lang)
  }

  function applyOutputIntent(intent: TaskOutputIntent) {
    patchConfig({
      ...getIntentDefaults(intent),
      output_intent: intent,
    })
  }

  function applyQualityPreset(preset: TaskQualityPreset) {
    patchConfig({
      ...getQualityDefaults(preset),
      quality_preset: preset,
    })
  }

  async function handleSubmit() {
    let defaultsForSubmit = globalDefaults
    if (!defaultsForSubmit && !globalDefaultsApplied) {
      try {
        defaultsForSubmit = await queryClient.fetchQuery({
          queryKey: ['config-defaults'],
          queryFn: configApi.getDefaults,
        })
      } catch {
        defaultsForSubmit = undefined
      }
    }
    const resolvedConfig =
      defaultsForSubmit && !globalDefaultsApplied
        ? applyGlobalDefaults(config, defaultsForSubmit)
        : config
    createMutation.mutate({
      name:
        name ||
        t.newTask.generatedTaskName(
          new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }),
        ),
      input_path: inputPath,
      source_lang: sourceLang,
      target_lang: targetLang,
      config: resolvedConfig,
      save_as_preset: saveAsPreset,
      preset_name: saveAsPreset ? presetName : undefined,
    })
  }

  const outputIntent = (config.output_intent ?? 'dub_final') as TaskOutputIntent
  const qualityPreset = (config.quality_preset ?? 'standard') as TaskQualityPreset
  const supportsCorrection = supportsTranscriptCorrection(normalizeTemplateId(config.template))
  const summary = useMemo(
    () =>
      isCommentary
        ? buildCommentarySummary(config, sourceLang, locale, getLanguageLabel)
        : buildTaskSummary(outputIntent, sourceLang, targetLang, locale, getLanguageLabel),
    [config, getLanguageLabel, isCommentary, locale, outputIntent, sourceLang, targetLang],
  )
  const capabilitySummary = useMemo(
    () => getIntentCapabilityDetails(outputIntent, locale === 'zh-CN' ? 'zh-CN' : 'en-US'),
    [locale, outputIntent],
  )

  const stepOne = (
    <div className="space-y-5">
      <SectionCard title={locale === 'zh-CN' ? '模式' : 'Mode'} minimal>
        <SegmentedControl
          value={isCommentary ? 'commentary' : 'dubbing'}
          options={[
            { value: 'dubbing', label: locale === 'zh-CN' ? '配音（多说话人翻译配音）' : 'Dubbing' },
            { value: 'commentary', label: locale === 'zh-CN' ? '解说（影视解说成片）' : 'Commentary' },
          ]}
          onChange={value => patchConfig({ template: value === 'commentary' ? 'asr-commentary' : 'asr-dub-basic' })}
        />
        <p className="mt-2 text-xs leading-5 text-slate-500">
          {isCommentary
            ? locale === 'zh-CN'
              ? '解说：转写原片 → 生成解说文案 → 配音并剪辑成解说成片（recap）。'
              : 'Commentary: transcribe → write narration → render a recap video.'
            : locale === 'zh-CN'
              ? '配音：多说话人翻译 + 单说话人 TTS + 时间轴重拟合混音。'
              : 'Dubbing: multi-speaker translation + per-speaker TTS + timeline remix.'}
        </p>
      </SectionCard>
      <SectionCard title={locale === 'zh-CN' ? '素材与语言' : 'Source'}>
        <Field label={t.newTask.fields.taskName}>
          <TextInput value={name} onChange={setName} placeholder={t.newTask.placeholders.taskName} />
        </Field>
        <Field
          label={t.newTask.fields.inputVideoPath}
          hint={t.newTask.hints.inputVideoPath}
          required
          requiredMark={t.newTask.validation.requiredMark}
          htmlFor={inputPathFieldId}
          error={inputPathErrorMessage}
        >
          <div className="flex gap-2">
            <TextInput
              id={inputPathFieldId}
              required
              ariaInvalid={inputPathHasError}
              ariaDescribedBy={
                inputPathHasError
                  ? `${inputPathFieldId}-error`
                  : `${inputPathFieldId}-hint`
              }
              value={inputPath}
              onChange={value => {
                setInputPath(value)
                setMediaInfo(null)
              }}
              onBlur={() => {
                setInputPathTouched(true)
                if (inputPath && !mediaInfo) probeMutation.mutate(inputPath)
              }}
              placeholder={t.newTask.placeholders.inputVideoPath}
            />
            <button
              type="button"
              onClick={() => pickFileMutation.mutate(inputPath)}
              disabled={pickFileMutation.isPending}
              className="flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm transition-colors hover:bg-slate-200 disabled:opacity-50"
            >
              {pickFileMutation.isPending || probeMutation.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <FolderOpen size={14} />
              )}
              {t.newTask.actions.browse}
            </button>
          </div>
          {pickFileMutation.isError && (
            <div className="mt-1.5 text-xs text-rose-500">{t.newTask.filePicker.unavailable}</div>
          )}
          {mediaInfo && (
            <div className="mt-2 space-y-1 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
              <div>
                {t.newTask.mediaInfo.duration(
                  typeof mediaInfo.duration_sec === 'number'
                    ? (mediaInfo.duration_sec / 60).toFixed(1)
                    : t.common.notAvailable,
                )}
              </div>
              <div>{t.newTask.mediaInfo.format(String(mediaInfo.format_name ?? t.common.notAvailable))}</div>
              {Boolean(mediaInfo.has_video) && <div>{t.newTask.mediaInfo.hasVideo}</div>}
              {mediaInfo.sample_rate != null && (
                <div>{t.newTask.mediaInfo.sampleRate(String(mediaInfo.sample_rate))}</div>
              )}
            </div>
          )}
        </Field>
        <div className={`grid gap-4 ${isCommentary ? 'grid-cols-1' : 'grid-cols-2'}`}>
          <Field
            label={
              isCommentary
                ? locale === 'zh-CN'
                  ? '视频语言'
                  : 'Video Language'
                : t.newTask.fields.sourceLanguage
            }
          >
            <Select value={sourceLang} onChange={setSourceLang} options={languageOptions} />
          </Field>
          {/* Commentary doesn't translate — no target language. */}
          {!isCommentary && (
            <Field label={t.newTask.fields.targetLanguage}>
              <Select value={targetLang} onChange={setTargetLang} options={languageOptions} />
            </Field>
          )}
        </div>
        {presets && presets.length > 0 && (
          <Field label={t.newTask.fields.applyPreset}>
            <Select
              value=""
              onChange={applyPreset}
              options={[
                { value: '', label: t.newTask.placeholders.selectPreset },
                ...presets.map(item => ({ value: String(item.id), label: item.name })),
              ]}
            />
          </Field>
        )}
      </SectionCard>
    </div>
  )

  const stepTwo = (
    <div className="space-y-6">
      <div className="space-y-5">
        {isCommentary ? (
          <SectionCard title={locale === 'zh-CN' ? '解说设置' : 'Commentary'} minimal>
            <Field label={locale === 'zh-CN' ? '解说类型' : 'Commentary Type'}>
              <SegmentedControl
                value={(config.commentary_style ?? 'plot_recap') as 'plot_recap'}
                // frame_riff is not implemented yet (the backend rejects it).
                options={[{ value: 'plot_recap', label: locale === 'zh-CN' ? '剧情解说' : 'Plot Recap' }]}
                onChange={value => patchConfig({ commentary_style: value })}
              />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label={locale === 'zh-CN' ? '影视类型' : 'Genre'}>
                <Select
                  value={config.commentary_genre ?? '剧情'}
                  options={[
                    { value: '剧情', label: locale === 'zh-CN' ? '剧情' : 'Drama' },
                    { value: '悬疑', label: locale === 'zh-CN' ? '悬疑' : 'Mystery' },
                    { value: '动作', label: locale === 'zh-CN' ? '动作' : 'Action' },
                    { value: '喜剧', label: locale === 'zh-CN' ? '喜剧' : 'Comedy' },
                    { value: '科幻', label: locale === 'zh-CN' ? '科幻' : 'Sci-Fi' },
                    { value: '历史', label: locale === 'zh-CN' ? '历史' : 'History' },
                    { value: '恐怖', label: locale === 'zh-CN' ? '恐怖' : 'Horror' },
                  ]}
                  onChange={value => patchConfig({ commentary_genre: value })}
                />
              </Field>
              <Field label={locale === 'zh-CN' ? '解说语言' : 'Narration Language'}>
                <Select
                  value={config.commentary_narration_language ?? 'zh'}
                  options={[
                    { value: 'zh', label: locale === 'zh-CN' ? '中文' : 'Chinese' },
                    { value: 'en', label: 'English' },
                    { value: 'ja', label: locale === 'zh-CN' ? '日语' : 'Japanese' },
                  ]}
                  onChange={value => patchConfig({ commentary_narration_language: value })}
                />
              </Field>
            </div>
            <Field
              label={locale === 'zh-CN' ? '解说音色' : 'Narrator Voice'}
              hint={locale === 'zh-CN' ? '内置 AI 解说音色；「借用源片音色」用原片人声' : 'Built-in AI narrator voice; "Borrow from source" reuses the cast voice'}
            >
              <Select
                value={config.commentary_narrator_voice ?? 'narrator-male-calm'}
                options={[
                  ...(narratorVoices ?? [
                    { id: 'narrator-male-calm', name_zh: '沉稳男声', name_en: 'Calm Male', gender: 'male' },
                    { id: 'narrator-female-bright', name_zh: '知性女声', name_en: 'Bright Female', gender: 'female' },
                  ]).map(v => ({ value: v.id, label: locale === 'zh-CN' ? v.name_zh : v.name_en })),
                  { value: 'source', label: locale === 'zh-CN' ? '借用源片音色' : 'Borrow from source' },
                ]}
                onChange={value => patchConfig({ commentary_narrator_voice: value })}
              />
            </Field>
            <Field
              label={locale === 'zh-CN' ? '原片占比（%）' : 'Original Sound %'}
              hint={locale === 'zh-CN' ? '保留原声片段的目标时长占比，0 = 全程解说旁白' : 'Target share of kept original-sound clips; 0 = narration only'}
            >
              <TextInput
                type="number"
                value={String(config.commentary_original_sound_ratio ?? 20)}
                onChange={value => patchConfig({ commentary_original_sound_ratio: value === '' ? 0 : Number(value) })}
              />
            </Field>
          </SectionCard>
        ) : (
          <SectionCard title={locale === 'zh-CN' ? '成品目标' : 'Intent'} minimal>
            <div className="grid gap-4 md:grid-cols-2">
              {getIntentOptions(locale).map(option => (
                <IntentCard
                  key={option.value}
                  title={option.title}
                  description={option.description}
                  badges={option.badges}
                  selected={outputIntent === option.value}
                  onClick={() => applyOutputIntent(option.value)}
                />
              ))}
            </div>
            <IntentCapabilityCard
              title={capabilitySummary.title}
              capabilities={capabilitySummary.capabilities}
              helper={capabilitySummary.helper}
            />
          </SectionCard>
        )}

        <SectionCard
          title={locale === 'zh-CN' ? '处理预览' : 'Workflow Preview'}
          minimal
          action={
            <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-500 shadow-sm ring-1 ring-slate-200">
              {normalizeTemplateId(config.template)}
            </span>
          }
        >
          <PipelineGraph graph={previewGraph} templateId={normalizeTemplateId(config.template)} compact />
        </SectionCard>
      </div>
      <SummaryCard
        title={locale === 'zh-CN' ? '任务摘要' : 'Task Summary'}
        items={summary.items}
        lines={summary.lines}
        tip={summary.tip}
        warning={summary.warning}
        minimal
      />
    </div>
  )

  const stepThreeDubbing = (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-5">
        <SectionCard title={locale === 'zh-CN' ? '质量与设置' : 'Quality'}>
          <Field label={locale === 'zh-CN' ? '质量档位' : 'Quality Preset'}>
            <SegmentedControl
              value={qualityPreset}
              options={([
                'fast',
                'standard',
                'high_quality',
              ] as TaskQualityPreset[]).map(value => ({
                value,
                label: getQualityPresetLabel(value, locale),
              }))}
              onChange={applyQualityPreset}
            />
          </Field>
          {supportsCorrection && (
            <Field
              label={locale === 'zh-CN' ? '台词校正' : 'Transcript Correction'}
              hint={locale === 'zh-CN'
                ? '默认使用标准强度：保留 ASR 时间轴，只替换高置信 OCR 台词文本。'
                : 'Standard by default: keep ASR timing and replace only high-confidence OCR dialogue.'}
            >
              <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <div className="grid gap-3 md:grid-cols-[1fr_12rem]">
                  <Checkbox
                    checked={config.transcription_correction?.enabled ?? true}
                    onChange={value => patchTranscriptionCorrection({ enabled: value })}
                    label={locale === 'zh-CN' ? '使用画面字幕校正 ASR 文稿' : 'Use screen subtitles to correct ASR text'}
                  />
                  <Select
                    value={config.transcription_correction?.preset ?? 'standard'}
                    onChange={value => patchTranscriptionCorrection({ preset: value as TranscriptionCorrectionPreset })}
                    options={[
                      { value: 'conservative', label: locale === 'zh-CN' ? '保守' : 'Conservative' },
                      { value: 'standard', label: locale === 'zh-CN' ? '标准' : 'Standard' },
                      { value: 'aggressive', label: locale === 'zh-CN' ? '积极' : 'Aggressive' },
                    ]}
                  />
                </div>
                {(config.transcription_correction?.enabled ?? true) && (
                  <Field
                    label={locale === 'zh-CN' ? 'LLM 仲裁' : 'LLM Arbitration'}
                    hint={locale === 'zh-CN'
                      ? '仅对疑难段（高置信 OCR 但对齐/长度不达标）调用大模型（DeepSeek）在 ASR/OCR 间裁决，受忠实回校约束。需配置 DeepSeek 的 API Key。'
                      : 'Calls an LLM (DeepSeek) to arbitrate ASR vs OCR only on ambiguous segments, bounded by a faithfulness check. Requires a DeepSeek API key.'}
                  >
                    <Select
                      value={config.transcription_correction?.llm_arbitration ?? 'off'}
                      onChange={value =>
                        patchTranscriptionCorrection({ llm_arbitration: value as 'off' | 'deepseek' })
                      }
                      options={[
                        { value: 'off', label: locale === 'zh-CN' ? '关闭' : 'Off' },
                        { value: 'deepseek', label: 'DeepSeek' },
                      ]}
                    />
                    {(config.transcription_correction?.llm_arbitration ?? 'off') !== 'off' && (
                      <button
                        type="button"
                        onClick={() => navigate('/settings')}
                        className="mt-1.5 text-xs font-medium text-blue-600 underline-offset-2 hover:underline"
                      >
                        {locale === 'zh-CN' ? '前往设置配置 API Key →' : 'Configure the API key in Settings →'}
                      </button>
                    )}
                  </Field>
                )}
                <button
                  type="button"
                  onClick={() => setShowCorrectionExplanation(prev => !prev)}
                  className="text-xs font-medium text-slate-500 underline-offset-2 hover:text-slate-700 hover:underline"
                  aria-expanded={showCorrectionExplanation}
                >
                  {locale === 'zh-CN' ? '这个选项会做什么' : 'What does this option do?'}
                </button>
                {showCorrectionExplanation && (
                  <p className="text-xs leading-5 text-slate-500">
                    {locale === 'zh-CN'
                      ? '系统会读取画面硬字幕，与 ASR 时间轴对齐；只在 OCR 置信度和时间匹配足够高时替换 ASR 文本。保留 ASR 时间轴和说话人。不确定的段落会保留 ASR，并写入校正报告。OCR 有但 ASR 没有的字幕只报告，不自动加入配音。'
                      : 'The system aligns screen subtitles with ASR timing, keeps ASR timing and speakers, replaces only high-confidence dialogue text, and reports OCR-only subtitles without adding dubbing segments.'}
                  </p>
                )}
              </div>
            </Field>
          )}
          {supportsCorrection && (
            <Field
              label={locale === 'zh-CN' ? '画面文字分类（视觉模型）' : 'On-screen Text Triage (vision model)'}
              hint={locale === 'zh-CN'
                ? '用本地 Qwen3-VL 给每条 OCR 文字分类：对白字幕 / 场景文字（路牌店招）/ 水印 / 标题。开启后字幕擦除会跳过场景文字、字幕翻译与台词校正只处理对白字幕。需要视觉后端（Apple Silicon 装 vision 扩展或本地 Ollama）。'
                : 'Classifies every OCR text event with a local Qwen3-VL model: dialogue subtitle / scene text (signs) / watermark / title card. When enabled, erase skips scene text, and subtitle translation / transcript correction only consume dialogue. Needs a vision backend (vision extra on Apple Silicon, or a local Ollama).'}
            >
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <Checkbox
                  checked={config.ocr_classify_text ?? false}
                  onChange={value => patchConfig({ ocr_classify_text: value })}
                  label={locale === 'zh-CN' ? '识别后区分字幕与场景文字（不误擦路牌店招）' : 'Triage subtitles vs scene text after detection (avoid erasing signs)'}
                />
              </div>
            </Field>
          )}
          {normalizeTemplateId(config.template) === 'asr-dub+ocr-subs+erase' && (
            <Field
              label={locale === 'zh-CN' ? '擦除质检（视觉模型）' : 'Erase QC (vision model)'}
              hint={locale === 'zh-CN'
                ? '字幕擦除完成后，用本地 Qwen3-VL 抽查原字幕区间是否仍有残留文字或涂抹痕迹，输出问题帧报告。纯报告，不阻断管线；需要视觉后端。'
                : 'After erasure, samples the original subtitle spans on the clean video with a local Qwen3-VL model and reports leftover text or inpainting artifacts. Pure report, never blocks the pipeline; needs a vision backend.'}
            >
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                <Checkbox
                  checked={config.erase_qc_enabled ?? false}
                  onChange={value => patchConfig({ erase_qc_enabled: value })}
                  label={locale === 'zh-CN' ? '擦除后自动抽查残留字幕' : 'Auto-check the erased video for residual subtitles'}
                />
              </div>
            </Field>
          )}
        </SectionCard>

        <SectionCard
          title={locale === 'zh-CN' ? '更多设置' : 'More Settings'}
          action={
            <button
              type="button"
              onClick={() => setShowAdvancedSettings(prev => !prev)}
              className="text-xs font-medium text-slate-500 hover:text-slate-700"
            >
              {showAdvancedSettings ? (locale === 'zh-CN' ? '收起' : 'Collapse') : (locale === 'zh-CN' ? '展开' : 'Expand')}
            </button>
          }
        >
          {showAdvancedSettings ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label={t.newTask.fields.translationBackend}>
                  <Select
                    value={config.translation_backend ?? 'local-m2m100'}
                    onChange={value => patchConfig({ translation_backend: value })}
                    options={[
                      { value: 'local-m2m100', label: 'local-m2m100' },
                      { value: 'deepseek', label: 'DeepSeek API' },
                    ]}
                  />
                </Field>
                <Field label={t.newTask.fields.ttsBackend}>
                  <Select
                    value={config.tts_backend ?? 'moss-tts-nano-onnx'}
                    onChange={value => patchConfig({ tts_backend: value })}
                    options={DUBBING_BACKEND_OPTIONS}
                  />
                </Field>
                <Field
                  label={locale === 'zh-CN' ? '配音并发数' : 'Dubbing Workers'}
                  hint={
                    locale === 'zh-CN'
                      ? '留空使用默认值；MOSS 后端可按机器核心数调到 4-6。'
                      : 'Leave blank for default; 4-6 is a practical starting point for MOSS.'
                  }
                >
                  <TextInput
                    type="number"
                    value={config.dubbing_workers ?? ''}
                    onChange={value => {
                      const parsed = Number(value)
                      patchConfig({
                        dubbing_workers: value.trim() && Number.isFinite(parsed) && parsed > 0 ? parsed : undefined,
                      })
                    }}
                  />
                </Field>
                <Field
                  label={locale === 'zh-CN' ? '配音质检' : 'Dubbing QA'}
                  hint={
                    locale === 'zh-CN'
                      ? '快速草稿会跳过音色和回读检查，只保留时长兜底。'
                      : 'Fast draft skips speaker/backread checks and only keeps duration fallback.'
                  }
                >
                  <Select
                    value={config.dubbing_quality_check ?? 'standard'}
                    onChange={value =>
                      patchConfig({ dubbing_quality_check: value as 'standard' | 'duration-only' })
                    }
                    options={[
                      { value: 'standard', label: locale === 'zh-CN' ? '完整质检' : 'Standard QA' },
                      { value: 'duration-only', label: locale === 'zh-CN' ? '快速草稿' : 'Fast draft' },
                    ]}
                  />
                </Field>
                <Field label={t.newTask.fields.device}>
                  <Select
                    value={config.device ?? 'auto'}
                    onChange={value => patchConfig({ device: value })}
                    options={[
                      { value: 'auto', label: t.newTask.options.device.auto },
                      { value: 'cpu', label: t.newTask.options.device.cpu },
                      { value: 'cuda', label: t.newTask.options.device.cuda },
                      { value: 'mps', label: t.newTask.options.device.mps },
                    ]}
                  />
                </Field>
                <Field label={t.newTask.fields.asrModel}>
                  <Select
                    value={asrModelValue}
                    onChange={value => patchConfig({ asr_model: value })}
                    options={asrModelOptions}
                  />
                </Field>
                <Field label={locale === 'zh-CN' ? 'ASR 后端' : 'ASR Backend'}>
                  <Select
                    value={asrBackend}
                    onChange={patchAsrBackend}
                    options={ASR_BACKEND_OPTIONS}
                  />
                </Field>
                <Field label={locale === 'zh-CN' ? '说话人后端' : 'Diarizer Backend'}>
                  <Select
                    value={config.diarizer_backend ?? 'ecapa'}
                    onChange={value => patchConfig({ diarizer_backend: value as TaskConfig['diarizer_backend'] })}
                    options={DIARIZER_BACKEND_OPTIONS}
                  />
                </Field>
              </div>
              <div className="space-y-3">
                <Checkbox
                  checked={config.enable_diarization ?? true}
                  onChange={value => patchConfig({ enable_diarization: value })}
                  label={locale === 'zh-CN' ? '启用说话人分离' : 'Enable speaker diarization'}
                />
                <Checkbox
                  checked={config.use_cache ?? true}
                  onChange={value => patchConfig({ use_cache: value })}
                  label={t.newTask.hints.cacheReuse}
                />
                <Checkbox
                  checked={config.keep_intermediate ?? false}
                  onChange={value => patchConfig({ keep_intermediate: value })}
                  label={t.newTask.hints.keepIntermediate}
                />
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">
              {locale === 'zh-CN'
                ? '这里用于调整默认执行偏好，不影响你在导出时再选择成品样式。'
                : 'Adjust execution defaults here without changing delivery styling.'}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title={locale === 'zh-CN' ? '开发者设置' : 'Developer Settings'}
          action={
            <button
              type="button"
              onClick={() => setShowDeveloperSettings(prev => !prev)}
              className="text-xs font-medium text-slate-500 hover:text-slate-700"
            >
              {showDeveloperSettings ? (locale === 'zh-CN' ? '收起' : 'Collapse') : (locale === 'zh-CN' ? '展开' : 'Expand')}
            </button>
          }
        >
          {showDeveloperSettings ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label="工作流模板">
                  <Select
                    value={config.template ?? 'asr-dub-basic'}
                    onChange={value => patchConfig({ template: normalizeTemplateId(value) })}
                    options={([
                      'asr-dub-basic',
                      'asr-dub+visual',
                      'asr-dub+ocr-subs',
                      'asr-dub+ocr-subs+erase',
                    ] as TaskConfig['template'][]).map(value => ({ value, label: value }))}
                  />
                </Field>
                <Field label="字幕输入策略">
                  <Select
                    value={config.subtitle_source ?? 'asr'}
                    onChange={value => patchConfig({ subtitle_source: value as TaskConfig['subtitle_source'] })}
                    options={[
                      { value: 'none', label: '不导出' },
                      { value: 'asr', label: 'ASR 字幕' },
                      { value: 'ocr', label: 'OCR 字幕' },
                      { value: 'both', label: '两者都导出' },
                    ]}
                  />
                </Field>
                <Field label="从阶段">
                  <Select value={config.run_from_stage ?? 'separation'} onChange={value => patchConfig({ run_from_stage: value })} options={stageOptions} />
                </Field>
                <Field label="到阶段">
                  <Select value={config.run_to_stage ?? 'delivery'} onChange={value => patchConfig({ run_to_stage: value })} options={stageOptions} />
                </Field>
                <Field label="交付视频底板">
                  <Select
                    value={config.video_source ?? 'original'}
                    onChange={value => patchConfig({ video_source: value as TaskConfig['video_source'] })}
                    options={[
                      { value: 'original', label: '原始视频' },
                      { value: 'clean', label: '擦字幕视频' },
                      { value: 'clean_if_available', label: '优先擦字幕视频' },
                    ]}
                  />
                </Field>
                <Field label="交付音轨">
                  <Select
                    value={config.audio_source ?? 'both'}
                    onChange={value => patchConfig({ audio_source: value as TaskConfig['audio_source'] })}
                    options={[
                      { value: 'dub', label: '仅配音成片' },
                      { value: 'preview', label: '仅预览混音' },
                      { value: 'both', label: '两者都导出' },
                    ]}
                  />
                </Field>
              </div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">
              {locale === 'zh-CN'
                ? '仅在需要控制模板、阶段范围或调试链路时使用。'
                : 'Only use this when you need to control template or stage ranges.'}
            </div>
          )}
        </SectionCard>
      </div>

      <SummaryCard
        title={locale === 'zh-CN' ? '任务摘要' : 'Task Summary'}
        items={summary.items}
        lines={summary.lines}
        tip={`${locale === 'zh-CN' ? '当前成品目标' : 'Current intent'}：${getOutputIntentLabel(outputIntent, locale)}`}
        warning={qualityPreset === 'fast'
          ? (locale === 'zh-CN' ? '快速档位会优先尽快出结果，适合试跑和验证。' : 'Fast favors speed over completeness.')
          : undefined}
      />
    </div>
  )

  const stepThree = isCommentary ? (
    <div className="space-y-5">
      <SectionCard title={locale === 'zh-CN' ? '高级设置' : 'Advanced'}>
        <p className="text-sm leading-6 text-slate-500">
          {locale === 'zh-CN'
            ? '解说模式：转写 → 解说文案 → 解说渲染，无需翻译/配音/混音配置。解说参数已在上一步设置。'
            : 'Commentary runs transcribe → narration → render; no translation/dubbing/mix config. Commentary options are in the previous step.'}
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={locale === 'zh-CN' ? '计算设备' : 'Device'}>
            <Select
              value={config.device ?? 'auto'}
              options={['auto', 'cpu', 'cuda', 'mps'].map(value => ({ value, label: value }))}
              onChange={value => patchConfig({ device: value })}
            />
          </Field>
          <Field label={locale === 'zh-CN' ? '复用缓存' : 'Reuse Cache'}>
            <Checkbox
              checked={config.use_cache ?? true}
              onChange={value => patchConfig({ use_cache: value })}
              label={locale === 'zh-CN' ? '复用各阶段缓存' : 'Reuse per-stage cache'}
            />
          </Field>
        </div>
      </SectionCard>
    </div>
  ) : stepThreeDubbing

  const stepFour = (
    <div className="space-y-6">
      <SectionCard
        title={locale === 'zh-CN' ? '处理预览' : 'Workflow Preview'}
        action={
          <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-500 shadow-sm ring-1 ring-slate-200">
            {normalizeTemplateId(config.template)}
          </span>
        }
      >
        <div className="rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-3">
          <PipelineGraph graph={previewGraph} templateId={normalizeTemplateId(config.template)} compact />
        </div>
        {mediaInfo ? (
          <div className="grid gap-2 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs text-slate-500 md:grid-cols-2">
            <div>
              时长：{
                typeof mediaInfo.duration_sec === 'number'
                  ? `${(mediaInfo.duration_sec / 60).toFixed(1)} 分钟`
                  : t.common.notAvailable
              }
            </div>
            <div>格式：{String(mediaInfo.format_name ?? t.common.notAvailable)}</div>
          </div>
        ) : null}
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <SectionCard title={locale === 'zh-CN' ? '确认创建' : 'Review'}>
          <div className="space-y-2 rounded-xl border border-slate-100 bg-slate-50 p-5 text-sm">
            <ConfirmRow label={t.newTask.summary.taskName} value={name || t.newTask.summary.autoGenerated} />
            <ConfirmRow label={t.newTask.summary.inputVideo} value={inputPath || t.common.notAvailable} />
            {isCommentary ? (
              <ConfirmRow label={locale === 'zh-CN' ? '视频语言' : 'Video Language'} value={getLanguageLabel(sourceLang)} />
            ) : (
              <ConfirmRow label={t.newTask.summary.direction} value={`${getLanguageLabel(sourceLang)} → ${getLanguageLabel(targetLang)}`} />
            )}
            {isCommentary ? (
              <>
                <ConfirmRow label={locale === 'zh-CN' ? '解说类型' : 'Commentary'} value={config.commentary_style ?? 'plot_recap'} />
                <ConfirmRow label={locale === 'zh-CN' ? '影视类型' : 'Genre'} value={config.commentary_genre ?? '剧情'} />
                <ConfirmRow label={locale === 'zh-CN' ? '原片占比' : 'Original Sound %'} value={`${config.commentary_original_sound_ratio ?? 20}%`} />
              </>
            ) : (
              <>
                <ConfirmRow label={locale === 'zh-CN' ? '成品目标' : 'Intent'} value={getOutputIntentLabel(outputIntent, locale)} />
                <ConfirmRow label={locale === 'zh-CN' ? '质量档位' : 'Quality'} value={getQualityPresetLabel(qualityPreset, locale)} />
              </>
            )}
            <ConfirmRow label={t.newTask.summary.device} value={config.device ?? 'auto'} />
            <ConfirmRow label={t.newTask.summary.cacheReuse} value={config.use_cache ? t.common.yes : t.common.no} />
          </div>

          <div className="space-y-3">
            <Checkbox
              checked={autoBindWork}
              onChange={setAutoBindWork}
              label={locale === 'zh-CN' ? '创建后自动识别并绑定作品' : 'Auto-detect and bind work after creation'}
            />
            <Checkbox checked={saveAsPreset} onChange={setSaveAsPreset} label={t.newTask.fields.saveAsPreset} />
            {saveAsPreset && (
              <Field label={t.newTask.fields.presetName}>
                <TextInput value={presetName} onChange={setPresetName} placeholder={t.newTask.placeholders.presetName} />
              </Field>
            )}
          </div>

          {createMutation.isError && (
            <div className="border-l-2 border-rose-400 bg-rose-50 py-2.5 pl-4 pr-4 text-sm text-rose-700">
              {t.newTask.createFailed}
            </div>
          )}
        </SectionCard>

        <SummaryCard
          title={locale === 'zh-CN' ? '任务摘要' : 'Task Summary'}
          items={summary.items}
          lines={summary.lines}
          tip={summary.tip}
        />
      </div>
    </div>
  )

  const stepContent = [stepOne, stepTwo, stepThree, stepFour]

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <h1 className="mb-6 text-2xl font-bold text-slate-900">{t.newTask.title}</h1>

      <ol
        className="mb-8 -mx-1 flex items-center gap-0 overflow-x-auto px-1 pb-2 sm:overflow-visible sm:pb-0"
        aria-label={t.newTask.stepIndicator.ariaLabel}
      >
        {steps.map((label, index) => {
          const isCompleted = index < step
          const isCurrent = index === step
          const statusText = isCompleted
            ? t.newTask.stepIndicator.completed
            : isCurrent
              ? t.newTask.stepIndicator.current
              : t.newTask.stepIndicator.upcoming
          return (
            <li
              key={label}
              className="flex shrink-0 items-center"
              aria-current={isCurrent ? 'step' : undefined}
            >
              <div className="flex items-center gap-2">
                <div
                  aria-label={t.newTask.stepIndicator.stepDescriptor(
                    index + 1,
                    steps.length,
                    label,
                    statusText,
                  )}
                  className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                    isCompleted
                      ? 'bg-emerald-500 text-white'
                      : isCurrent
                        ? 'bg-blue-600 text-white'
                        : 'bg-slate-200 text-slate-500'
                  }`}
                >
                  <span aria-hidden="true">{isCompleted ? '✓' : index + 1}</span>
                </div>
                <span
                  className={`text-sm font-medium ${
                    isCurrent
                      ? 'text-slate-900'
                      : isCompleted
                        ? 'text-slate-500'
                        : 'text-slate-400'
                  } ${isCurrent ? '' : 'hidden sm:inline'}`}
                >
                  {label}
                </span>
              </div>
              {index < steps.length - 1 && (
                <div
                  aria-hidden="true"
                  className={`mx-2 h-px w-8 ${isCompleted ? 'bg-emerald-300' : 'bg-slate-200'}`}
                />
              )}
            </li>
          )
        })}
      </ol>

      <div className="overflow-hidden rounded-xl border border-slate-100 bg-white p-6">
        <h2 className="mb-5 text-base font-semibold text-slate-800">
          {(locale === 'zh-CN' ? '步骤' : 'Step')} {step + 1}: {steps[step]}
        </h2>

        {stepContent[step]}

        <div className="mt-8 flex items-center justify-between border-t border-slate-100 pt-5">
          <button
            type="button"
            onClick={() => setStep(step - 1)}
            disabled={step === 0}
            className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
          >
            <ChevronLeft size={16} />
            {t.newTask.actions.previous}
          </button>

          {step < stepContent.length - 1 ? (
            <button
              type="button"
              onClick={() => {
                if (step === 0 && !inputPath.trim()) {
                  setInputPathTouched(true)
                  return
                }
                setStep(step + 1)
              }}
              disabled={createMutation.isPending}
              title={
                step === 0 && !inputPath.trim()
                  ? t.newTask.validation.nextDisabledHint
                  : undefined
              }
              aria-disabled={step === 0 && !inputPath.trim() ? true : undefined}
              className={`inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 ${
                step === 0 && !inputPath.trim() ? 'cursor-not-allowed opacity-50 hover:bg-blue-600' : ''
              }`}
            >
              {t.newTask.actions.next}
              <ChevronRight size={16} />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={createMutation.isPending || !inputPath}
              aria-busy={createMutation.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Cpu size={16} />}
              {createMutation.isPending ? t.newTask.actions.creatingTask : t.newTask.actions.createTask}
            </button>
          )}
        </div>
      </div>
    </PageContainer>
  )
}

function normalizeTemplateId(value: unknown): TaskConfig['template'] {
  if (
    value === 'asr-dub-basic' ||
    value === 'asr-dub+visual' ||
    value === 'asr-dub+ocr-subs' ||
    value === 'asr-dub+ocr-subs+erase' ||
    value === 'asr-commentary'
  ) {
    return value
  }
  return 'asr-dub-basic'
}

function supportsTranscriptCorrection(template: TaskConfig['template']) {
  return template === 'asr-dub+ocr-subs' || template === 'asr-dub+ocr-subs+erase'
}

function getIntentDefaults(intent: TaskOutputIntent): Partial<TaskConfig> {
  switch (intent) {
    case 'english_subtitle':
      return {
        template: 'asr-dub+ocr-subs+erase',
        run_to_stage: 'delivery',
        video_source: 'clean_if_available',
        audio_source: 'both',
        subtitle_source: 'both',
      }
    case 'bilingual_review':
      return {
        template: 'asr-dub+ocr-subs',
        run_to_stage: 'delivery',
        video_source: 'original',
        audio_source: 'both',
        subtitle_source: 'both',
      }
    case 'fast_validation':
      return {
        template: 'asr-dub-basic',
        run_to_stage: 'delivery',
        video_source: 'original',
        audio_source: 'preview',
        subtitle_source: 'asr',
      }
    default:
      return {
        template: 'asr-dub-basic',
        run_to_stage: 'delivery',
        video_source: 'original',
        audio_source: 'both',
        subtitle_source: 'asr',
      }
  }
}

function getQualityDefaults(preset: TaskQualityPreset): Partial<TaskConfig> {
  switch (preset) {
    case 'fast':
      return {
        fit_policy: 'conservative',
        mix_profile: 'preview',
      }
    case 'high_quality':
      return {
        fit_policy: 'high_quality',
        mix_profile: 'enhanced',
      }
    default:
      return {
        fit_policy: 'conservative',
        mix_profile: 'preview',
      }
  }
}

function getIntentOptions(locale: string): Array<{
  value: TaskOutputIntent
  title: string
  description: string
  badges: string[]
}> {
  if (locale !== 'zh-CN') {
    return [
      {
        value: 'dub_final',
        title: 'English Dub Master',
        description: 'Create a final dubbed video for direct delivery.',
        badges: ['Master Export', 'Dub First', 'No Burned Subs'],
      },
      {
        value: 'bilingual_review',
        title: 'Bilingual Review',
        description: 'Keep original context and add English subtitles for review.',
        badges: ['Bilingual', 'Review', 'OCR First'],
      },
      {
        value: 'english_subtitle',
        title: 'English Subtitle',
        description: 'Prefer a clean plate with burned English subtitles.',
        badges: ['English Subs', 'Clean Plate', 'Preview First'],
      },
      {
        value: 'fast_validation',
        title: 'Fast Validation',
        description: 'Get to a viewable result as quickly as possible.',
        badges: ['Fast', 'Preview First', 'Tryout'],
      },
    ]
  }

  return [
    {
      value: 'dub_final',
      title: '英文配音成片',
      description: '生成可直接交付的英文配音视频。',
      badges: ['正式成片', '优先正式音轨', '默认不烧录英文字幕'],
    },
    {
      value: 'bilingual_review',
      title: '双语审片版',
      description: '适合审片和对照。导出前系统会检测原片是否已带中文字幕，并推荐合适的双语方式。',
      badges: ['适合审片', '英文对照', '导出前检测中字'],
    },
    {
      value: 'english_subtitle',
      title: '英文字幕版',
      description: '优先使用干净画面并烧录英文字幕，适合海外分发。',
      badges: ['英文字幕', '优先干净画面', '可先预览'],
    },
    {
      value: 'fast_validation',
      title: '快速验证版',
      description: '优先尽快出结果，适合先看整体效果。',
      badges: ['快速出结果', '优先 preview', '适合试跑'],
    },
  ]
}

function buildCommentarySummary(
  config: Partial<TaskConfig>,
  sourceLang: string,
  locale: string,
  getLanguageLabel: (code: string) => string,
) {
  const zh = locale === 'zh-CN'
  const genre = config.commentary_genre ?? '剧情'
  const ratio = `${config.commentary_original_sound_ratio ?? 20}%`
  const lang = getLanguageLabel(sourceLang)
  return {
    lines: zh
      ? [`视频语言：${lang}`, `影视类型：${genre}`, `原片占比：${ratio}`]
      : [`Video language: ${lang}`, `Genre: ${genre}`, `Original sound: ${ratio}`],
    items: zh
      ? [
          { label: '视频语言', value: lang },
          { label: '影视类型', value: genre },
          { label: '原片占比', value: ratio },
        ]
      : [
          { label: 'Video language', value: lang },
          { label: 'Genre', value: genre },
          { label: 'Original sound', value: ratio },
        ],
    tip: zh ? '转写 → 解说文案 → 配音剪辑成解说成片（recap）。' : 'Transcribe → narration → recap render.',
    warning: undefined as string | undefined,
  }
}

function buildTaskSummary(
  intent: TaskOutputIntent,
  sourceLang: string,
  targetLang: string,
  locale: string,
  getLanguageLabel: (code: string) => string,
) {
  const direction = `${getLanguageLabel(sourceLang)} → ${getLanguageLabel(targetLang)}`

  if (locale !== 'zh-CN') {
    const detail = getIntentSummaryDetails(intent, 'en-US')
    return {
      lines: [
        `Language: ${direction}`,
        detail.primary,
        detail.secondary,
      ],
      items: [
        { label: 'Language', value: direction },
        { label: 'Default Output', value: detail.primary },
        { label: 'Strategy', value: detail.secondary },
      ],
      tip: getIntentTip(intent, 'en-US'),
      warning: undefined,
    }
  }

  const detail = getIntentSummaryDetails(intent, 'zh-CN')
  return {
    lines: [
      `语言：${direction}`,
      detail.primary,
      detail.secondary,
    ],
    items: [
      { label: '语言方向', value: direction },
      { label: '默认导出', value: detail.primary },
      { label: '处理策略', value: detail.secondary },
    ],
    tip: getIntentTip(intent, 'zh-CN'),
    warning: intent === 'english_subtitle' ? '如无干净画面，后续会提示你补跑擦字幕。' : undefined,
  }
}

function getIntentSummaryDetails(intent: TaskOutputIntent, locale: 'zh-CN' | 'en-US') {
  if (locale === 'en-US') {
    switch (intent) {
      case 'english_subtitle':
        return {
          primary: 'Default export: clean plate + English subtitles',
          secondary: 'OCR subtitle chain and preview will be prepared',
        }
      case 'bilingual_review':
        return {
          primary: 'Default export: original video + bilingual subtitles',
          secondary: 'OCR subtitle chain will be prepared',
        }
      case 'fast_validation':
        return {
          primary: 'Default export: preview-first validation output',
          secondary: 'The system will prioritize speed',
        }
      default:
        return {
          primary: 'Default export: dubbed master video',
          secondary: 'The system will prioritize a formal dubbed output',
        }
    }
  }

  switch (intent) {
    case 'english_subtitle':
      return {
        primary: '优先干净画面 + 英文字幕',
        secondary: 'OCR 字幕链路、导出预览能力',
      }
    case 'bilingual_review':
      return {
        primary: '原视频 + 英文对照 + 配音音轨',
        secondary: 'OCR 字幕链路、导出前双语策略确认',
      }
    case 'fast_validation':
      return {
        primary: '优先 preview 可看片段',
        secondary: '系统会优先选择更快的默认方案',
      }
    default:
      return {
        primary: '正式配音版导出',
        secondary: '系统会优先准备正式配音成片',
      }
  }
}

function getIntentTip(intent: TaskOutputIntent, locale: 'zh-CN' | 'en-US'): string {
  if (locale === 'en-US') {
    switch (intent) {
      case 'english_subtitle':
        return 'The system will prefer a clean plate and English subtitle delivery.'
      case 'bilingual_review':
        return 'The system will keep the original frame and prepare bilingual delivery.'
      case 'fast_validation':
        return 'The system will prioritize speed so you can validate the result quickly.'
      default:
        return 'The system will prioritize a formal dubbed delivery output.'
    }
  }

  switch (intent) {
    case 'english_subtitle':
      return '系统会优先尝试生成干净画面和英文字幕。'
    case 'bilingual_review':
      return '系统会优先保留原画面，并在导出前根据中文字幕检测结果推荐合适的双语方式。'
    case 'fast_validation':
      return '系统会优先选择更快的默认方案，帮助你尽早看到结果。'
    default:
      return '系统会优先准备正式配音成片所需的默认链路。'
  }
}

function getIntentCapabilityDetails(intent: TaskOutputIntent, locale: 'zh-CN' | 'en-US') {
  if (locale === 'en-US') {
    switch (intent) {
      case 'english_subtitle':
        return {
          title: 'Auto-enabled capabilities',
          capabilities: ['OCR subtitle chain', 'Dub synthesis', 'Subtitle erase'],
          helper: 'This workflow is generated from the selected delivery goal.',
        }
      case 'bilingual_review':
        return {
          title: 'Auto-enabled capabilities',
          capabilities: ['OCR subtitle chain', 'Dub synthesis', 'Bilingual burn-in'],
          helper: 'The system keeps the original frame and prepares review-friendly bilingual output.',
        }
      case 'fast_validation':
        return {
          title: 'Auto-enabled capabilities',
          capabilities: ['ASR subtitles', 'Preview mix', 'Fast delivery compose'],
          helper: 'The workflow will prefer speed-first processing for quicker validation.',
        }
      default:
        return {
          title: 'Auto-enabled capabilities',
          capabilities: ['Dub synthesis', 'Formal mixdown', 'Master export'],
          helper: 'The workflow is generated from the selected delivery goal.',
        }
    }
  }

  switch (intent) {
    case 'english_subtitle':
      return {
        title: '系统将自动启用',
        capabilities: ['OCR 字幕链路', '配音合成', '字幕擦除'],
        helper: '该处理链路由成品目标自动生成。',
      }
    case 'bilingual_review':
      return {
        title: '系统将自动启用',
        capabilities: ['OCR 字幕链路', '配音合成', '审片导出决策'],
        helper: '系统会保留原视频画面，并在导出时根据中文字幕检测结果推荐合适的双语方式。',
      }
    case 'fast_validation':
      return {
        title: '系统将自动启用',
        capabilities: ['ASR 字幕链路', 'Preview 混音', '快速导出'],
        helper: '系统会优先生成尽快可看的结果，帮助你先验证整体效果。',
      }
    default:
      return {
        title: '系统将自动启用',
        capabilities: ['配音合成', '正式混音', '正式成片导出'],
        helper: '该处理链路由成品目标自动生成。',
      }
  }
}
