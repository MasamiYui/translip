import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft, Loader2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { configApi, systemApi } from '../api/config'
import { PageContainer } from '../components/layout/PageContainer'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { buildTemplatePreviewGraph } from '../lib/workflowPreview'
import type { CreateTaskRequest, TaskConfig } from '../types'
import { LANGUAGE_CODES, STAGE_ORDER } from '../i18n/formatters'
import { useI18n } from '../i18n/useI18n'

const defaultConfig: Partial<TaskConfig> = {
  device: 'auto',
  template: 'asr-dub-basic',
  run_from_stage: 'stage1',
  run_to_stage: 'task-e',
  use_cache: true,
  keep_intermediate: false,
  video_source: 'original',
  audio_source: 'both',
  subtitle_source: 'asr',
  separation_mode: 'auto',
  separation_quality: 'balanced',
  music_backend: 'demucs',
  dialogue_backend: 'cdx23',
  asr_model: 'small',
  generate_srt: true,
  top_k: 3,
  translation_backend: 'local-m2m100',
  translation_batch_size: 4,
  tts_backend: 'qwen3tts',
  fit_policy: 'conservative',
  fit_backend: 'atempo',
  mix_profile: 'preview',
  ducking_mode: 'static',
  background_gain_db: -8.0,
  export_preview: true,
  export_dub: true,
  delivery_container: 'mp4',
  delivery_video_codec: 'copy',
  delivery_audio_codec: 'aac',
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  )
}

function Select({ value, onChange, options, className = '' }: {
  value: string | number
  onChange: (v: string) => void
  options: { value: string | number; label: string }[]
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className={`w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 ${className}`}
    >
      {options.map(option => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

function TextInput({ value, onChange, placeholder = '', type = 'text' }: {
  value: string | number
  onChange: (v: string) => void
  placeholder?: string
  type?: string
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400"
    />
  )
}

function Checkbox({ checked, onChange, label }: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        className="rounded text-blue-600"
      />
      <span className="text-sm text-slate-700">{label}</span>
    </label>
  )
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <div className="bg-slate-50 px-4 py-2.5 border-b border-slate-200">
        <span className="text-sm font-semibold text-slate-700">{title}</span>
      </div>
      <div className="p-4 space-y-4">{children}</div>
    </div>
  )
}

function ConfirmRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex">
      <span className="text-slate-500 w-28 shrink-0">{label}:</span>
      <span className="text-slate-900 font-medium">{value}</span>
    </div>
  )
}

export function NewTaskPage() {
  const { locale, t, getLanguageLabel, getStageShortLabel } = useI18n()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [name, setName] = useState('')
  const [inputPath, setInputPath] = useState('')
  const [sourceLang, setSourceLang] = useState('zh')
  const [targetLang, setTargetLang] = useState('en')
  const [config, setConfig] = useState<Partial<TaskConfig>>(defaultConfig)
  const [saveAsPreset, setSaveAsPreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [mediaInfo, setMediaInfo] = useState<Record<string, unknown> | null>(null)

  const steps = t.newTask.steps
  const stageOptions = STAGE_ORDER.map(stage => ({
    value: stage,
    label: getStageShortLabel(stage),
  }))
  const templateOptions = [
    { value: 'asr-dub-basic', label: t.workflow.templates['asr-dub-basic'] },
    { value: 'asr-dub+ocr-subs', label: t.workflow.templates['asr-dub+ocr-subs'] },
    { value: 'asr-dub+ocr-subs+erase', label: t.workflow.templates['asr-dub+ocr-subs+erase'] },
  ]
  const languageOptions = LANGUAGE_CODES.map(code => ({
    value: code,
    label: `${getLanguageLabel(code)} (${code})`,
  }))
  const templateId = normalizeTemplateId(config.template)
  const previewGraph = buildTemplatePreviewGraph(templateId)

  const { data: presets } = useQuery({
    queryKey: ['presets'],
    queryFn: configApi.getPresets,
  })

  const patchConfig = (patch: Partial<TaskConfig>) => {
    setConfig(prev => ({ ...prev, ...patch }))
  }

  const probeMutation = useMutation({
    mutationFn: (path: string) => systemApi.probe(path),
    onSuccess: data => setMediaInfo(data),
    onError: () => setMediaInfo(null),
  })

  const createMutation = useMutation({
    mutationFn: (req: CreateTaskRequest) => tasksApi.create(req),
    onSuccess: task => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      navigate(`/tasks/${task.id}`)
    },
  })

  function handleSubmit() {
    createMutation.mutate({
      name: name || t.newTask.generatedTaskName(
        new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }),
      ),
      input_path: inputPath,
      source_lang: sourceLang,
      target_lang: targetLang,
      config,
      save_as_preset: saveAsPreset,
      preset_name: saveAsPreset ? presetName : undefined,
    })
  }

  function applyPreset(presetId: string) {
    const preset = presets?.find(item => String(item.id) === presetId)
    if (!preset) return

    setConfig(prev => ({ ...prev, ...preset.config }))
    setSourceLang(preset.source_lang)
    setTargetLang(preset.target_lang)
  }

  const step1 = (
    <div className="space-y-5">
      <Field label={t.newTask.fields.taskName}>
        <TextInput value={name} onChange={setName} placeholder={t.newTask.placeholders.taskName} />
      </Field>
      <Field label={t.newTask.fields.inputVideoPath} hint={t.newTask.hints.inputVideoPath}>
        <div className="flex gap-2">
          <TextInput
            value={inputPath}
            onChange={value => {
              setInputPath(value)
              setMediaInfo(null)
            }}
            placeholder={t.newTask.placeholders.inputVideoPath}
          />
          <button
            onClick={() => inputPath && probeMutation.mutate(inputPath)}
            disabled={!inputPath || probeMutation.isPending}
            className="px-3 py-2 text-sm bg-slate-100 border border-slate-200 rounded-xl hover:bg-slate-200 disabled:opacity-50 shrink-0 transition-colors"
          >
            {probeMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : t.newTask.actions.probe}
          </button>
        </div>
        {mediaInfo && (
          <div className="mt-2 p-3 bg-slate-50 rounded-lg text-xs text-slate-600 space-y-1">
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
      <div className="grid grid-cols-2 gap-4">
        <Field label={t.newTask.fields.sourceLanguage}>
          <Select value={sourceLang} onChange={setSourceLang} options={languageOptions} />
        </Field>
        <Field label={t.newTask.fields.targetLanguage}>
          <Select value={targetLang} onChange={setTargetLang} options={languageOptions} />
        </Field>
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
    </div>
  )

  const step2 = (
    <div className="space-y-4">
      <SectionCard title={t.newTask.fields.template}>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t.newTask.fields.template} hint={t.newTask.hints.template}>
            <Select
              value={templateId}
              onChange={value => patchConfig({ template: normalizeTemplateId(value) })}
              options={templateOptions}
            />
          </Field>
          <Field label={t.newTask.fields.subtitleSource}>
            <Select
              value={config.subtitle_source ?? 'asr'}
              onChange={value => patchConfig({ subtitle_source: value as TaskConfig['subtitle_source'] })}
              options={[
                { value: 'none', label: t.newTask.options.subtitleSource.none },
                { value: 'asr', label: t.newTask.options.subtitleSource.asr },
                { value: 'ocr', label: t.newTask.options.subtitleSource.ocr },
                { value: 'both', label: t.newTask.options.subtitleSource.both },
              ]}
            />
          </Field>
          <Field label={t.newTask.fields.videoSource}>
            <Select
              value={config.video_source ?? 'original'}
              onChange={value => patchConfig({ video_source: value as TaskConfig['video_source'] })}
              options={[
                { value: 'original', label: t.newTask.options.videoSource.original },
                { value: 'clean', label: t.newTask.options.videoSource.clean },
                { value: 'clean_if_available', label: t.newTask.options.videoSource.clean_if_available },
              ]}
            />
          </Field>
          <Field label={t.newTask.fields.audioSource}>
            <Select
              value={config.audio_source ?? 'both'}
              onChange={value => patchConfig({ audio_source: value as TaskConfig['audio_source'] })}
              options={[
                { value: 'dub', label: t.newTask.options.audioSource.dub },
                { value: 'preview', label: t.newTask.options.audioSource.preview },
                { value: 'both', label: t.newTask.options.audioSource.both },
              ]}
            />
          </Field>
        </div>

        <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/70 px-3 py-3">
          <div className="mb-2.5 flex items-center justify-between gap-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              {t.workflow.previewTitle}
            </div>
            <div className="flex items-center gap-3 text-[10px] text-slate-400">
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full border border-slate-400 bg-slate-400" />
                {t.workflow.required}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full border border-slate-300 bg-transparent" />
                {t.workflow.optional}
              </span>
            </div>
          </div>
          <PipelineGraph graph={previewGraph} templateId={templateId} compact />
        </div>
      </SectionCard>

      <div className="grid grid-cols-2 gap-4">
        <Field label={t.newTask.fields.fromStage}>
          <Select
            value={config.run_from_stage ?? 'stage1'}
            onChange={value => patchConfig({ run_from_stage: value })}
            options={stageOptions}
          />
        </Field>
        <Field label={t.newTask.fields.toStage}>
          <Select
            value={config.run_to_stage ?? 'task-e'}
            onChange={value => patchConfig({ run_to_stage: value })}
            options={stageOptions}
          />
        </Field>
      </div>

      <SectionCard title={t.newTask.sections.stage1}>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t.newTask.fields.separationMode}>
            <Select
              value={config.separation_mode ?? 'auto'}
              onChange={value => patchConfig({ separation_mode: value })}
              options={[
                { value: 'auto', label: t.newTask.options.separationMode.auto },
                { value: 'music', label: t.newTask.options.separationMode.music },
                { value: 'dialogue', label: t.newTask.options.separationMode.dialogue },
              ]}
            />
          </Field>
          <Field label={t.newTask.fields.quality}>
            <Select
              value={config.separation_quality ?? 'balanced'}
              onChange={value => patchConfig({ separation_quality: value })}
              options={[
                { value: 'balanced', label: t.newTask.options.separationQuality.balanced },
                { value: 'high', label: t.newTask.options.separationQuality.high },
              ]}
            />
          </Field>
        </div>
      </SectionCard>

      <SectionCard title={t.newTask.sections.taskA}>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t.newTask.fields.asrModel}>
            <Select
              value={config.asr_model ?? 'small'}
              onChange={value => patchConfig({ asr_model: value })}
              options={['tiny', 'base', 'small', 'medium', 'large-v3'].map(value => ({ value, label: value }))}
            />
          </Field>
        </div>
        <Checkbox
          checked={config.generate_srt ?? true}
          onChange={value => patchConfig({ generate_srt: value })}
          label={t.newTask.fields.generateSrt}
        />
      </SectionCard>

      <SectionCard title={t.newTask.sections.taskC}>
        <Field label={t.newTask.fields.translationBackend}>
          <Select
            value={config.translation_backend ?? 'local-m2m100'}
            onChange={value => patchConfig({ translation_backend: value })}
            options={[
              { value: 'local-m2m100', label: 'local-m2m100' },
              { value: 'siliconflow', label: 'SiliconFlow API' },
            ]}
          />
        </Field>
        {config.translation_backend === 'siliconflow' && (
          <div className="grid grid-cols-2 gap-4">
            <Field label={t.newTask.fields.apiBaseUrl}>
              <TextInput
                value={config.siliconflow_base_url ?? ''}
                onChange={value => patchConfig({ siliconflow_base_url: value })}
                placeholder="https://api.siliconflow.cn/v1"
              />
            </Field>
            <Field label={t.newTask.fields.apiModel}>
              <TextInput
                value={config.siliconflow_model ?? ''}
                onChange={value => patchConfig({ siliconflow_model: value })}
                placeholder="deepseek-ai/DeepSeek-V3"
              />
            </Field>
          </div>
        )}
      </SectionCard>

      <SectionCard title={t.newTask.sections.taskD}>
        <Field label={t.newTask.fields.ttsBackend}>
          <Select
            value={config.tts_backend ?? 'qwen3tts'}
            onChange={value => patchConfig({ tts_backend: value })}
            options={[{ value: 'qwen3tts', label: 'Qwen3TTS' }]}
          />
        </Field>
      </SectionCard>

      <SectionCard title={t.newTask.sections.taskE}>
        <div className="grid grid-cols-2 gap-4">
          <Field label={t.newTask.fields.fitPolicy}>
            <Select
              value={config.fit_policy ?? 'conservative'}
              onChange={value => patchConfig({ fit_policy: value })}
              options={[
                { value: 'conservative', label: t.newTask.options.fitPolicy.conservative },
                { value: 'high_quality', label: t.newTask.options.fitPolicy.high_quality },
              ]}
            />
          </Field>
          <Field label={t.newTask.fields.mixProfile}>
            <Select
              value={config.mix_profile ?? 'preview'}
              onChange={value => patchConfig({ mix_profile: value })}
              options={[
                { value: 'preview', label: t.newTask.options.mixProfile.preview },
                { value: 'enhanced', label: t.newTask.options.mixProfile.enhanced },
              ]}
            />
          </Field>
          <Field label={t.newTask.fields.backgroundGain}>
            <TextInput
              type="number"
              value={config.background_gain_db ?? -8}
              onChange={value => patchConfig({ background_gain_db: parseFloat(value) })}
            />
          </Field>
        </div>
      </SectionCard>
    </div>
  )

  const step3 = (
    <div className="space-y-5">
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
      <div className="space-y-3">
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
  )

  const step4 = (
    <div className="space-y-5">
      <div className="bg-slate-50 rounded-xl p-5 space-y-2 text-sm">
        <ConfirmRow label={t.newTask.summary.taskName} value={name || t.newTask.summary.autoGenerated} />
        <ConfirmRow label={t.newTask.summary.inputVideo} value={inputPath || t.common.notAvailable} />
        <ConfirmRow
          label={t.newTask.summary.direction}
          value={`${getLanguageLabel(sourceLang)} → ${getLanguageLabel(targetLang)}`}
        />
        <ConfirmRow label={t.newTask.summary.template} value={t.workflow.templates[templateId]} />
        <ConfirmRow
          label={t.newTask.summary.deliveryPolicy}
          value={[config.video_source, config.audio_source, config.subtitle_source].filter(Boolean).join(' · ') || t.common.notAvailable}
        />
        <ConfirmRow
          label={t.newTask.summary.stageRange}
          value={`${getStageShortLabel((config.run_from_stage ?? 'stage1') as typeof STAGE_ORDER[number])} → ${getStageShortLabel((config.run_to_stage ?? 'task-e') as typeof STAGE_ORDER[number])}`}
        />
        <ConfirmRow label={t.newTask.summary.translationBackend} value={config.translation_backend ?? t.common.notAvailable} />
        <ConfirmRow label={t.newTask.summary.ttsBackend} value={config.tts_backend ?? t.common.notAvailable} />
        <ConfirmRow label={t.newTask.summary.device} value={config.device ?? 'auto'} />
        <ConfirmRow label={t.newTask.summary.cacheReuse} value={config.use_cache ? t.common.yes : t.common.no} />
      </div>
      <div className="space-y-3">
        <Checkbox
          checked={saveAsPreset}
          onChange={setSaveAsPreset}
          label={t.newTask.fields.saveAsPreset}
        />
        {saveAsPreset && (
          <Field label={t.newTask.fields.presetName}>
            <TextInput value={presetName} onChange={setPresetName} placeholder={t.newTask.placeholders.presetName} />
          </Field>
        )}
      </div>
      {createMutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
          {t.newTask.createFailed}
        </div>
      )}
    </div>
  )

  const stepContent = [step1, step2, step3, step4]

  return (
    <PageContainer className="max-w-2xl">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">{t.newTask.title}</h1>

      <div className="flex items-center mb-8">
        {steps.map((label, index) => (
          <div key={label} className="flex items-center">
            <div className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                index < step ? 'bg-emerald-500 text-white' :
                index === step ? 'bg-blue-600 text-white' :
                'bg-slate-200 text-slate-500'
              }`}>
                {index < step ? '✓' : index + 1}
              </div>
              <span className={`text-sm font-medium hidden sm:block ${index === step ? 'text-slate-900' : 'text-slate-400'}`}>
                {label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div className={`h-px w-8 mx-2 ${index < step ? 'bg-emerald-300' : 'bg-slate-200'}`} />
            )}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-5">
          {t.newTask.stepTitle(step + 1, steps[step])}
        </h2>
        {stepContent[step]}
      </div>

      <div className="flex justify-between mt-5">
        <button
          onClick={() => setStep(current => current - 1)}
          disabled={step === 0}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 disabled:opacity-40 transition-colors"
        >
          <ChevronLeft size={15} />
          {t.newTask.actions.previous}
        </button>
        {step < steps.length - 1 ? (
          <button
            onClick={() => setStep(current => current + 1)}
            disabled={step === 0 && !inputPath}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {t.newTask.actions.next}
            <ChevronRight size={15} />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={createMutation.isPending || !inputPath}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {createMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : '🚀'}
            {t.newTask.actions.start}
          </button>
        )}
      </div>
    </PageContainer>
  )
}

function normalizeTemplateId(value: unknown): TaskConfig['template'] {
  if (
    value === 'asr-dub-basic' ||
    value === 'asr-dub+ocr-subs' ||
    value === 'asr-dub+ocr-subs+erase'
  ) {
    return value
  }
  return 'asr-dub-basic'
}
