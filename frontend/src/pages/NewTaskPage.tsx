import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Cpu, Loader2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { configApi, systemApi } from '../api/config'
import { PageContainer } from '../components/layout/PageContainer'
import { buildTemplatePreviewGraph } from '../lib/workflowPreview'
import { PipelineGraph } from '../components/pipeline/PipelineGraph'
import { getOutputIntentLabel, getQualityPresetLabel } from '../lib/taskPresentation'
import type { CreateTaskRequest, TaskConfig, TaskOutputIntent, TaskQualityPreset } from '../types'
import { LANGUAGE_CODES, STAGE_ORDER } from '../i18n/formatters'
import { useI18n } from '../i18n/useI18n'

const defaultConfig: Partial<TaskConfig> = {
  device: 'auto',
  output_intent: 'dub_final',
  quality_preset: 'standard',
  template: 'asr-dub-basic',
  run_from_stage: 'stage1',
  run_to_stage: 'task-g',
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
  condense_mode: 'off',
  tts_backend: 'qwen3tts',
  fit_policy: 'conservative',
  fit_backend: 'atempo',
  mix_profile: 'preview',
  ducking_mode: 'static',
  background_gain_db: -8.0,
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-slate-700">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  )
}

function Select({ value, onChange, options }: {
  value: string | number
  onChange: (v: string) => void
  options: { value: string | number; label: string }[]
}) {
  return (
    <select
      value={value}
      onChange={event => onChange(event.target.value)}
      className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-slate-300"
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
      onChange={event => onChange(event.target.value)}
      placeholder={placeholder}
      className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-slate-300"
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

function SectionCard({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">{title}</span>
        {action}
      </div>
      <div className="space-y-4 p-4">{children}</div>
    </div>
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

function SummaryCard({
  title,
  lines,
  tip,
  warning,
  cta,
}: {
  title: string
  lines: string[]
  tip?: string
  warning?: string
  cta?: React.ReactNode
}) {
  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <div className="text-xs font-semibold uppercase tracking-widest text-slate-400">{title}</div>
        <div className="mt-3 space-y-2 text-sm text-slate-700">
          <div className="font-semibold text-slate-900">本次任务将生成：</div>
          {lines.map(line => (
            <div key={line}>{line}</div>
          ))}
        </div>
      </div>
      {tip && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          {tip}
        </div>
      )}
      {warning && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {warning}
        </div>
      )}
      {cta}
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
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false)
  const [showDeveloperSettings, setShowDeveloperSettings] = useState(false)

  const steps = locale === 'zh-CN'
    ? ['素材与语言', '成品目标', '质量与设置', '确认创建']
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

  function patchConfig(patch: Partial<TaskConfig>) {
    setConfig(prev => ({ ...prev, ...patch }))
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

  function handleSubmit() {
    createMutation.mutate({
      name: name || `任务-${new Date().toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`,
      input_path: inputPath,
      source_lang: sourceLang,
      target_lang: targetLang,
      config,
      save_as_preset: saveAsPreset,
      preset_name: saveAsPreset ? presetName : undefined,
    })
  }

  const outputIntent = (config.output_intent ?? 'dub_final') as TaskOutputIntent
  const qualityPreset = (config.quality_preset ?? 'standard') as TaskQualityPreset
  const summary = useMemo(
    () => buildTaskSummary(outputIntent, sourceLang, targetLang, locale, getLanguageLabel),
    [getLanguageLabel, locale, outputIntent, sourceLang, targetLang],
  )

  const stepOne = (
    <div className="space-y-5">
      <SectionCard title={locale === 'zh-CN' ? '素材与语言' : 'Source'}>
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
              type="button"
              onClick={() => inputPath && probeMutation.mutate(inputPath)}
              disabled={!inputPath || probeMutation.isPending}
              className="shrink-0 rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm transition-colors hover:bg-slate-200 disabled:opacity-50"
            >
              {probeMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : t.newTask.actions.probe}
            </button>
          </div>
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
      </SectionCard>
    </div>
  )

  const stepTwo = (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-5">
        <SectionCard title={locale === 'zh-CN' ? '成品目标' : 'Intent'}>
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
        </SectionCard>

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
        </SectionCard>
      </div>
      <SummaryCard
        title={locale === 'zh-CN' ? '任务摘要' : 'Task Summary'}
        lines={summary.lines}
        tip={summary.tip}
        warning={summary.warning}
      />
    </div>
  )

  const stepThree = (
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
                      { value: 'siliconflow', label: 'SiliconFlow API' },
                    ]}
                  />
                </Field>
                <Field label={t.newTask.fields.ttsBackend}>
                  <Select
                    value={config.tts_backend ?? 'qwen3tts'}
                    onChange={value => patchConfig({ tts_backend: value })}
                    options={[{ value: 'qwen3tts', label: 'Qwen3TTS' }]}
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
                    value={config.asr_model ?? 'small'}
                    onChange={value => patchConfig({ asr_model: value })}
                    options={['tiny', 'base', 'small', 'medium', 'large-v3'].map(value => ({ value, label: value }))}
                  />
                </Field>
              </div>
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
                  <Select value={config.run_from_stage ?? 'stage1'} onChange={value => patchConfig({ run_from_stage: value })} options={stageOptions} />
                </Field>
                <Field label="到阶段">
                  <Select value={config.run_to_stage ?? 'task-g'} onChange={value => patchConfig({ run_to_stage: value })} options={stageOptions} />
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
        lines={summary.lines}
        tip={`${locale === 'zh-CN' ? '当前成品目标' : 'Current intent'}：${getOutputIntentLabel(outputIntent, locale)}`}
        warning={qualityPreset === 'fast'
          ? (locale === 'zh-CN' ? '快速档位会优先尽快出结果，适合试跑和验证。' : 'Fast favors speed over completeness.')
          : undefined}
      />
    </div>
  )

  const stepFour = (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-5">
        <SectionCard title={locale === 'zh-CN' ? '确认创建' : 'Review'}>
          <div className="space-y-2 rounded-xl border border-slate-100 bg-slate-50 p-5 text-sm">
            <ConfirmRow label={t.newTask.summary.taskName} value={name || t.newTask.summary.autoGenerated} />
            <ConfirmRow label={t.newTask.summary.inputVideo} value={inputPath || t.common.notAvailable} />
            <ConfirmRow label={t.newTask.summary.direction} value={`${getLanguageLabel(sourceLang)} → ${getLanguageLabel(targetLang)}`} />
            <ConfirmRow label={locale === 'zh-CN' ? '成品目标' : 'Intent'} value={getOutputIntentLabel(outputIntent, locale)} />
            <ConfirmRow label={locale === 'zh-CN' ? '质量档位' : 'Quality'} value={getQualityPresetLabel(qualityPreset, locale)} />
            <ConfirmRow label={t.newTask.summary.device} value={config.device ?? 'auto'} />
            <ConfirmRow label={t.newTask.summary.cacheReuse} value={config.use_cache ? t.common.yes : t.common.no} />
          </div>

          <div className="space-y-3">
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
          ) : (
            <div className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-500">
              {locale === 'zh-CN'
                ? '如需再次确认素材信息，可以回到第一步点击“检测”。'
                : 'Go back to step 1 and probe again if you need media details.'}
            </div>
          )}
        </SectionCard>
      </div>

      <SummaryCard
        title={locale === 'zh-CN' ? '任务摘要' : 'Task Summary'}
        lines={summary.lines}
        tip={summary.tip}
      />
    </div>
  )

  const stepContent = [stepOne, stepTwo, stepThree, stepFour]

  return (
    <PageContainer className="max-w-6xl">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">{t.newTask.title}</h1>

      <div className="mb-8 flex items-center">
        {steps.map((label, index) => (
          <div key={label} className="flex items-center">
            <div className="flex items-center gap-2">
              <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                index < step ? 'bg-emerald-500 text-white' :
                index === step ? 'bg-blue-600 text-white' :
                'bg-slate-200 text-slate-500'
              }`}>
                {index < step ? '✓' : index + 1}
              </div>
              <span className={`hidden text-sm font-medium sm:block ${index === step ? 'text-slate-900' : 'text-slate-400'}`}>
                {label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div className={`mx-2 h-px w-8 ${index < step ? 'bg-emerald-300' : 'bg-slate-200'}`} />
            )}
          </div>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-100 bg-white p-6 shadow-sm">
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
              onClick={() => setStep(step + 1)}
              disabled={(step === 0 && !inputPath) || createMutation.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {t.newTask.actions.next}
              <ChevronRight size={16} />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={createMutation.isPending || !inputPath}
              className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {createMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Cpu size={16} />}
              {locale === 'zh-CN' ? '创建任务' : 'Create Task'}
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
    value === 'asr-dub+ocr-subs' ||
    value === 'asr-dub+ocr-subs+erase'
  ) {
    return value
  }
  return 'asr-dub-basic'
}

function getIntentDefaults(intent: TaskOutputIntent): Partial<TaskConfig> {
  switch (intent) {
    case 'english_subtitle':
      return {
        template: 'asr-dub+ocr-subs+erase',
        run_to_stage: 'task-g',
        video_source: 'clean_if_available',
        audio_source: 'both',
        subtitle_source: 'both',
      }
    case 'bilingual_review':
      return {
        template: 'asr-dub+ocr-subs',
        run_to_stage: 'task-g',
        video_source: 'original',
        audio_source: 'both',
        subtitle_source: 'both',
      }
    case 'fast_validation':
      return {
        template: 'asr-dub-basic',
        run_to_stage: 'task-g',
        video_source: 'original',
        audio_source: 'preview',
        subtitle_source: 'asr',
      }
    default:
      return {
        template: 'asr-dub-basic',
        run_to_stage: 'task-g',
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
        asr_model: 'tiny',
        fit_policy: 'conservative',
        mix_profile: 'preview',
      }
    case 'high_quality':
      return {
        asr_model: 'medium',
        fit_policy: 'high_quality',
        mix_profile: 'enhanced',
      }
    default:
      return {
        asr_model: 'small',
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
      title: '中英双语审片版',
      description: '保留中文信息，并叠加英文字幕，适合审片和对照。',
      badges: ['中英双语', '适合审片', '优先 OCR 字幕'],
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

function buildTaskSummary(
  intent: TaskOutputIntent,
  sourceLang: string,
  targetLang: string,
  locale: string,
  getLanguageLabel: (code: string) => string,
) {
  const direction = `${getLanguageLabel(sourceLang)} → ${getLanguageLabel(targetLang)}`

  if (locale !== 'zh-CN') {
    return {
      lines: [
        `Language: ${direction}`,
        ...getIntentSummaryLines(intent, 'en-US'),
      ],
      tip: getIntentTip(intent, 'en-US'),
      warning: undefined,
    }
  }

  return {
    lines: [
      `语言：${direction}`,
      ...getIntentSummaryLines(intent, 'zh-CN'),
    ],
    tip: getIntentTip(intent, 'zh-CN'),
    warning: intent === 'english_subtitle' ? '如无干净画面，后续会提示你补跑擦字幕。' : undefined,
  }
}

function getIntentSummaryLines(intent: TaskOutputIntent, locale: 'zh-CN' | 'en-US'): string[] {
  if (locale === 'en-US') {
    switch (intent) {
      case 'english_subtitle':
        return ['Default export: clean plate + English subtitles', 'OCR subtitle chain and preview will be prepared']
      case 'bilingual_review':
        return ['Default export: original video + bilingual subtitles', 'OCR subtitle chain will be prepared']
      case 'fast_validation':
        return ['Default export: preview-first validation output', 'The system will prioritize speed']
      default:
        return ['Default export: dubbed master video', 'The system will prioritize a formal dubbed output']
    }
  }

  switch (intent) {
    case 'english_subtitle':
      return ['优先干净画面 + 英文字幕', 'OCR 字幕链路、导出预览能力']
    case 'bilingual_review':
      return ['原视频 + 英文字幕 + 配音音轨', 'OCR 字幕链路、双语导出能力']
    case 'fast_validation':
      return ['优先 preview 可看片段', '系统会优先选择更快的默认方案']
    default:
      return ['正式配音版导出', '系统会优先准备正式配音成片']
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
      return '系统会优先保留原画面，并为你准备双语导出能力。'
    case 'fast_validation':
      return '系统会优先选择更快的默认方案，帮助你尽早看到结果。'
    default:
      return '系统会优先准备正式配音成片所需的默认链路。'
  }
}
