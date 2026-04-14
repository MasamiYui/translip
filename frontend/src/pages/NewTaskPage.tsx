import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft, Folder, Loader2 } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { configApi, systemApi } from '../api/config'
import type { CreateTaskRequest, TaskConfig } from '../types'
import { STAGE_LABELS, LANG_LABELS } from '../lib/utils'

const STEPS = ['基础信息', '节点配置', '高级选项', '确认提交']

const STAGE_OPTIONS = Object.keys(STAGE_LABELS).map(k => ({ value: k, label: STAGE_LABELS[k].split(': ')[0] }))

const defaultConfig: Partial<TaskConfig> = {
  device: 'auto',
  run_from_stage: 'stage1',
  run_to_stage: 'task-e',
  use_cache: true,
  keep_intermediate: false,
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
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
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
  onChange: (v: boolean) => void
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

export function NewTaskPage() {
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

  const { data: presets } = useQuery({
    queryKey: ['presets'],
    queryFn: configApi.getPresets,
  })

  const patchConfig = (patch: Partial<TaskConfig>) =>
    setConfig(prev => ({ ...prev, ...patch }))

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
      name: name || `任务-${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`,
      input_path: inputPath,
      source_lang: sourceLang,
      target_lang: targetLang,
      config,
      save_as_preset: saveAsPreset,
      preset_name: saveAsPreset ? presetName : undefined,
    })
  }

  function applyPreset(presetId: string) {
    const preset = presets?.find(p => String(p.id) === presetId)
    if (preset) {
      setConfig(prev => ({ ...prev, ...preset.config }))
      setSourceLang(preset.source_lang)
      setTargetLang(preset.target_lang)
    }
  }

  const langOptions = Object.entries(LANG_LABELS).map(([v, l]) => ({ value: v, label: `${l} (${v})` }))

  const step1 = (
    <div className="space-y-5">
      <Field label="任务名称">
        <TextInput value={name} onChange={setName} placeholder="例如：产品演示配音" />
      </Field>
      <Field label="输入视频路径" hint="本地视频文件的绝对路径">
        <div className="flex gap-2">
          <TextInput value={inputPath} onChange={v => { setInputPath(v); setMediaInfo(null) }} placeholder="/path/to/video.mp4" />
          <button
            onClick={() => inputPath && probeMutation.mutate(inputPath)}
            disabled={!inputPath || probeMutation.isPending}
            className="px-3 py-2 text-sm bg-slate-100 border border-slate-200 rounded-xl hover:bg-slate-200 disabled:opacity-50 shrink-0 transition-colors"
          >
            {probeMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : '检测'}
          </button>
        </div>
        {mediaInfo && (
          <div className="mt-2 p-3 bg-slate-50 rounded-lg text-xs text-slate-600 space-y-1">
            <div>时长: {typeof mediaInfo.duration_sec === 'number' ? `${(mediaInfo.duration_sec / 60).toFixed(1)}分钟` : '—'}</div>
            <div>格式: {String(mediaInfo.format_name ?? '—')}</div>
            {mediaInfo.has_video && <div>包含视频流</div>}
            {mediaInfo.sample_rate && <div>采样率: {String(mediaInfo.sample_rate)} Hz</div>}
          </div>
        )}
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="源语言">
          <Select value={sourceLang} onChange={setSourceLang} options={langOptions} />
        </Field>
        <Field label="目标语言">
          <Select value={targetLang} onChange={setTargetLang} options={langOptions} />
        </Field>
      </div>
      {presets && presets.length > 0 && (
        <Field label="应用预设">
          <Select
            value=""
            onChange={applyPreset}
            options={[{ value: '', label: '— 选择预设 —' }, ...presets.map(p => ({ value: String(p.id), label: p.name }))]}
          />
        </Field>
      )}
    </div>
  )

  const step2 = (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Field label="从阶段">
          <Select
            value={config.run_from_stage ?? 'stage1'}
            onChange={v => patchConfig({ run_from_stage: v })}
            options={STAGE_OPTIONS}
          />
        </Field>
        <Field label="到阶段">
          <Select
            value={config.run_to_stage ?? 'task-e'}
            onChange={v => patchConfig({ run_to_stage: v })}
            options={STAGE_OPTIONS}
          />
        </Field>
      </div>
      <SectionCard title="Stage 1: 音频分离">
        <div className="grid grid-cols-2 gap-4">
          <Field label="分离模式">
            <Select value={config.separation_mode ?? 'auto'} onChange={v => patchConfig({ separation_mode: v })}
              options={[{ value: 'auto', label: 'auto' }, { value: 'music', label: 'music' }, { value: 'dialogue', label: 'dialogue' }]} />
          </Field>
          <Field label="质量">
            <Select value={config.separation_quality ?? 'balanced'} onChange={v => patchConfig({ separation_quality: v })}
              options={[{ value: 'balanced', label: 'balanced' }, { value: 'high', label: 'high' }]} />
          </Field>
        </div>
      </SectionCard>
      <SectionCard title="Task A: 语音转写">
        <div className="grid grid-cols-2 gap-4">
          <Field label="ASR 模型">
            <Select value={config.asr_model ?? 'small'} onChange={v => patchConfig({ asr_model: v })}
              options={['tiny', 'base', 'small', 'medium', 'large-v3'].map(v => ({ value: v, label: v }))} />
          </Field>
        </div>
        <Checkbox checked={config.generate_srt ?? true} onChange={v => patchConfig({ generate_srt: v })} label="生成 SRT 字幕" />
      </SectionCard>
      <SectionCard title="Task C: 翻译">
        <Field label="翻译后端">
          <Select value={config.translation_backend ?? 'local-m2m100'} onChange={v => patchConfig({ translation_backend: v })}
            options={[{ value: 'local-m2m100', label: 'local-m2m100' }, { value: 'siliconflow', label: 'SiliconFlow API' }]} />
        </Field>
        {config.translation_backend === 'siliconflow' && (
          <div className="grid grid-cols-2 gap-4">
            <Field label="API Base URL">
              <TextInput value={config.siliconflow_base_url ?? ''} onChange={v => patchConfig({ siliconflow_base_url: v })}
                placeholder="https://api.siliconflow.cn/v1" />
            </Field>
            <Field label="API Model">
              <TextInput value={config.siliconflow_model ?? ''} onChange={v => patchConfig({ siliconflow_model: v })}
                placeholder="deepseek-ai/DeepSeek-V3" />
            </Field>
          </div>
        )}
      </SectionCard>
      <SectionCard title="Task D: 语音合成">
        <Field label="TTS 后端">
          <Select value={config.tts_backend ?? 'qwen3tts'} onChange={v => patchConfig({ tts_backend: v })}
            options={[{ value: 'qwen3tts', label: 'Qwen3TTS' }]} />
        </Field>
      </SectionCard>
      <SectionCard title="Task E: 时间线装配">
        <div className="grid grid-cols-2 gap-4">
          <Field label="贴合策略">
            <Select value={config.fit_policy ?? 'conservative'} onChange={v => patchConfig({ fit_policy: v })}
              options={[{ value: 'conservative', label: 'conservative' }, { value: 'high_quality', label: 'high_quality' }]} />
          </Field>
          <Field label="混音配置">
            <Select value={config.mix_profile ?? 'preview'} onChange={v => patchConfig({ mix_profile: v })}
              options={[{ value: 'preview', label: 'preview' }, { value: 'enhanced', label: 'enhanced' }]} />
          </Field>
          <Field label="背景增益 (dB)">
            <TextInput type="number" value={config.background_gain_db ?? -8} onChange={v => patchConfig({ background_gain_db: parseFloat(v) })} />
          </Field>
        </div>
      </SectionCard>
    </div>
  )

  const step3 = (
    <div className="space-y-5">
      <Field label="计算设备">
        <Select value={config.device ?? 'auto'} onChange={v => patchConfig({ device: v })}
          options={[{ value: 'auto', label: 'auto (自动检测)' }, { value: 'cpu', label: 'CPU' }, { value: 'cuda', label: 'CUDA (GPU)' }, { value: 'mps', label: 'MPS (Apple Silicon)' }]} />
      </Field>
      <div className="space-y-3">
        <Checkbox checked={config.use_cache ?? true} onChange={v => patchConfig({ use_cache: v })} label="复用缓存（跳过已成功完成的阶段）" />
        <Checkbox checked={config.keep_intermediate ?? false} onChange={v => patchConfig({ keep_intermediate: v })} label="保留中间文件" />
      </div>
    </div>
  )

  const step4 = (
    <div className="space-y-5">
      <div className="bg-slate-50 rounded-xl p-5 space-y-2 text-sm">
        <ConfirmRow label="任务名称" value={name || '（自动生成）'} />
        <ConfirmRow label="输入视频" value={inputPath || '—'} />
        <ConfirmRow label="语言方向" value={`${sourceLang} → ${targetLang}`} />
        <ConfirmRow label="执行范围" value={`${config.run_from_stage} → ${config.run_to_stage}`} />
        <ConfirmRow label="翻译后端" value={config.translation_backend ?? '—'} />
        <ConfirmRow label="TTS 后端" value={config.tts_backend ?? '—'} />
        <ConfirmRow label="设备" value={config.device ?? 'auto'} />
        <ConfirmRow label="缓存复用" value={config.use_cache ? '是' : '否'} />
      </div>
      <div className="space-y-3">
        <Checkbox checked={saveAsPreset} onChange={setSaveAsPreset} label="保存为预设" />
        {saveAsPreset && (
          <Field label="预设名称">
            <TextInput value={presetName} onChange={setPresetName} placeholder="例如：中英高清配音" />
          </Field>
        )}
      </div>
      {createMutation.isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
          创建失败，请检查参数后重试
        </div>
      )}
    </div>
  )

  const stepContent = [step1, step2, step3, step4]

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">新建任务</h1>

      {/* Stepper */}
      <div className="flex items-center mb-8">
        {STEPS.map((s, i) => (
          <div key={i} className="flex items-center">
            <div className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${
                i < step ? 'bg-emerald-500 text-white' :
                i === step ? 'bg-blue-600 text-white' :
                'bg-slate-200 text-slate-500'
              }`}>
                {i < step ? '✓' : i + 1}
              </div>
              <span className={`text-sm font-medium hidden sm:block ${i === step ? 'text-slate-900' : 'text-slate-400'}`}>
                {s}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-px w-8 mx-2 ${i < step ? 'bg-emerald-300' : 'bg-slate-200'}`} />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
        <h2 className="text-base font-semibold text-slate-800 mb-5">步骤 {step + 1}: {STEPS[step]}</h2>
        {stepContent[step]}
      </div>

      {/* Nav buttons */}
      <div className="flex justify-between mt-5">
        <button
          onClick={() => setStep(s => s - 1)}
          disabled={step === 0}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-600 bg-white border border-slate-200 rounded-xl hover:bg-slate-50 disabled:opacity-40 transition-colors"
        >
          <ChevronLeft size={15} />
          上一步
        </button>
        {step < STEPS.length - 1 ? (
          <button
            onClick={() => setStep(s => s + 1)}
            disabled={step === 0 && !inputPath}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            下一步
            <ChevronRight size={15} />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={createMutation.isPending || !inputPath}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-blue-600 rounded-xl hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            {createMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : '🚀'}
            开始执行
          </button>
        )}
      </div>
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
