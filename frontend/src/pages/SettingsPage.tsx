import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { configApi, modelsApi, systemApi } from '../api/config'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { CacheSection } from '../components/settings/CacheSection'
import { DUBBING_BACKEND_OPTIONS } from '../lib/dubbingBackends'
import { formatBytes } from '../lib/utils'
import {
  CheckCircle,
  XCircle,
  Save,
  Lock,
  Download,
  Loader2,
  AlertTriangle,
} from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import { worksApi } from '../api/works'
import type { ModelDownloadEntry, TaskConfig } from '../types'
import type { GlobalConfigUpdate } from '../api/config'

type SettingsSection = 'global' | 'advanced'
type GlobalConfigDraft = GlobalConfigUpdate

const defaultGlobalConfig: GlobalConfigDraft = {
  device: 'auto',
  use_cache: true,
  keep_intermediate: false,
  separation_mode: 'auto',
  separation_quality: 'balanced',
  stage1_output_format: 'mp3',
  audio_stream_index: 0,
  asr_model: 'small',
  asr_backend: 'faster-whisper',
  diarizer_backend: 'ecapa',
  enable_diarization: true,
  generate_srt: true,
  vad_filter: true,
  vad_min_silence_duration_ms: 400,
  beam_size: 5,
  best_of: 5,
  temperature: 0,
  condition_on_previous_text: false,
  top_k: 3,
  ocr_sample_interval: 0.25,
  ocr_position_mode: 'auto',
  ocr_extraction_mode: 'conservative',
  translation_backend: 'local-m2m100',
  translation_batch_size: 4,
  condense_mode: 'off',
  transcription_correction: { enabled: true, preset: 'standard', ocr_only_policy: 'report_only', llm_arbitration: 'off' },
  tts_backend: 'moss-tts-nano-onnx',
  dubbing_quality_check: 'standard',
  dub_repair_enabled: false,
  dub_repair_backend: [],
  dub_repair_max_items: 12,
  dub_repair_attempts_per_item: 3,
  dub_repair_include_risk: false,
  fit_policy: 'conservative',
  fit_backend: 'atempo',
  mix_profile: 'preview',
  ducking_mode: 'static',
  background_gain_db: -8,
  window_ducking_db: -3,
  max_compress_ratio: 1.45,
  output_sample_rate: 24000,
  preview_format: 'wav',
  subtitle_mode: 'none',
  subtitle_render_source: 'ocr',
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

export function SettingsPage() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [activeSection, setActiveSection] = useState<SettingsSection>('global')
  const { data: sysInfo, isLoading } = useQuery({
    queryKey: ['system-info'],
    queryFn: systemApi.getInfo,
  })

  const { data: tmdbConfig } = useQuery({
    queryKey: ['tmdb-config'],
    queryFn: worksApi.tmdbGetConfig,
  })

  const { data: savedGlobalConfig } = useQuery({
    queryKey: ['global-config'],
    queryFn: configApi.getGlobal,
  })

  const [globalConfig, setGlobalConfig] = useState<GlobalConfigDraft>(defaultGlobalConfig)
  const [saveGlobalStatus, setSaveGlobalStatus] = useState<'idle' | 'saved'>('idle')

  useEffect(() => {
    if (!savedGlobalConfig) return
    setGlobalConfig({ ...defaultGlobalConfig, ...savedGlobalConfig })
  }, [savedGlobalConfig])

  const saveGlobalMutation = useMutation({
    mutationFn: () => configApi.updateGlobal(globalConfig),
    onSuccess: data => {
      setGlobalConfig({ ...defaultGlobalConfig, ...data.config })
      setSaveGlobalStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      queryClient.invalidateQueries({ queryKey: ['config-defaults'] })
    },
  })

  const [apiKeyV3, setApiKeyV3] = useState('')
  const [apiKeyV4, setApiKeyV4] = useState('')
  const [defaultLanguage, setDefaultLanguage] = useState('zh-CN')

  const saveMutation = useMutation({
    mutationFn: () =>
      worksApi.tmdbSaveConfig({
        api_key_v3: apiKeyV3 || undefined,
        api_key_v4: apiKeyV4 || undefined,
        default_language: defaultLanguage || undefined,
      }),
    onSuccess: () => {
      // Refresh config
    },
  })

  const handleSave = () => {
    saveMutation.mutate()
  }

  // ---------- HuggingFace token ----------
  const { data: hfTokenConfig } = useQuery({
    queryKey: ['hf-token'],
    queryFn: systemApi.getHfToken,
  })
  const [hfToken, setHfToken] = useState('')
  const saveHfTokenMutation = useMutation({
    mutationFn: () => systemApi.saveHfToken(hfToken),
    onSuccess: () => {
      setHfToken('')
      queryClient.invalidateQueries({ queryKey: ['hf-token'] })
    },
  })

  const patchGlobalConfig = (patch: GlobalConfigDraft) => {
    setSaveGlobalStatus('idle')
    setGlobalConfig(prev => ({ ...prev, ...patch }))
  }

  // ---------- Model download state ----------
  const [downloadJobId, setDownloadJobId] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)

  // Only count 'missing' (downloadable) models on the button — 'needs_extra'
  // rows can't be resolved by the downloader and are surfaced as a hint instead.
  const missingModelCount =
    sysInfo?.models.filter(m => m.status === 'missing').length ?? 0

  const downloadMutation = useMutation({
    mutationFn: () => modelsApi.downloadMissing(),
    onSuccess: job => {
      setStartError(null)
      setDownloadJobId(job.job_id)
      if (job.state === 'succeeded' || job.state === 'failed' || job.state === 'partial') {
        queryClient.invalidateQueries({ queryKey: ['system-info'] })
      }
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail ||
        (err as { message?: string })?.message ||
        'unknown_error'
      setStartError(msg)
    },
  })

  const jobQuery = useQuery({
    queryKey: ['model-download', downloadJobId],
    queryFn: () => modelsApi.getJob(downloadJobId as string),
    enabled: !!downloadJobId,
    refetchInterval: query => {
      const data = query.state.data
      if (!data) return 1500
      const finished = ['succeeded', 'failed', 'partial', 'cancelled']
      return finished.includes(data.state) ? false : 1500
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => modelsApi.cancelJob(jobId),
  })

  const job = jobQuery.data
  const jobIsRunning = !!job && (job.state === 'pending' || job.state === 'running')

  // When the job finishes, refresh system info so "not downloaded" turns green.
  useEffect(() => {
    if (!job) return
    if (
      job.state === 'succeeded' ||
      job.state === 'partial' ||
      job.state === 'failed' ||
      job.state === 'cancelled'
    ) {
      queryClient.invalidateQueries({ queryKey: ['system-info'] })
    }
  }, [job?.state, queryClient])

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">{t.settings.title}</h1>

      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-white p-1">
        {([
          ['global', t.settings.tabGeneral],
          ['advanced', t.settings.tabDefaults],
        ] as const).map(([section, label]) => (
          <button
            key={section}
            type="button"
            onClick={() => setActiveSection(section)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeSection === section
                ? 'bg-blue-600 text-white'
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        {activeSection === 'global' ? (
          <>
        {/* System info */}
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.systemInfo}</h2>
          {isLoading ? (
            <div className="text-sm text-slate-400">{t.common.loading}</div>
          ) : sysInfo ? (
            <div className="divide-y divide-slate-100 text-sm">
              <InfoRow label={t.settings.fields.python} value={sysInfo.python_version} />
              <InfoRow label={t.settings.fields.platform} value={sysInfo.platform} />
              <InfoRow label={t.settings.fields.device} value={sysInfo.device} />
              <InfoRow label={t.settings.fields.cacheDir} value={sysInfo.cache_dir} mono />
              <CacheSection cacheSize={formatBytes(sysInfo.cache_size_bytes)} />
            </div>
          ) : (
            <div className="border-l-2 border-rose-400 bg-rose-50 py-2 pl-3 text-sm text-rose-600">{t.settings.connectionError}</div>
          )}
        </div>

        {/* TMDb Configuration */}
        <div className="border-b border-slate-100 px-6 py-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">TMDb API</h2>
            {tmdbConfig?.ok && (tmdbConfig.api_key_v3_set || tmdbConfig.api_key_v4_set) ? (
              <div className="flex items-center gap-1.5 text-sm text-emerald-600">
                <CheckCircle size={14} />
                <span>已配置</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-sm text-amber-600">
                <XCircle size={14} />
                <span>未配置</span>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm">
              <Lock size={14} className="text-slate-400" />
              <span className="text-slate-500">API 密钥会保存在本地配置文件中，不会上传到服务器。</span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  API Key (v3)
                </label>
                <input
                  type="password"
                  value={apiKeyV3}
                  onChange={(e) => setApiKeyV3(e.target.value)}
                  placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
                {tmdbConfig?.api_key_v3_set && !apiKeyV3 && (
                  <p className="mt-1 text-xs text-slate-500">已保存（点击输入框可修改）</p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Bearer Token (v4)
                </label>
                <input
                  type="password"
                  value={apiKeyV4}
                  onChange={(e) => setApiKeyV4(e.target.value)}
                  placeholder="eyJhbGciOiJIUzI1NiJ9..."
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                />
                {tmdbConfig?.api_key_v4_set && !apiKeyV4 && (
                  <p className="mt-1 text-xs text-slate-500">已保存（点击输入框可修改）</p>
                )}
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                默认语言
              </label>
              <select
                value={defaultLanguage}
                onChange={(e) => setDefaultLanguage(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="zh-CN">中文 (简体)</option>
                <option value="zh-TW">中文 (繁體)</option>
                <option value="en-US">English</option>
                <option value="ja-JP">日本語</option>
                <option value="ko-KR">한국어</option>
              </select>
            </div>

            <button
              onClick={handleSave}
              disabled={saveMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save size={16} />
              {saveMutation.isPending ? '保存中...' : '保存配置'}
            </button>
          </div>
        </div>

        {/* HuggingFace token */}
        <div className="border-b border-slate-100 px-6 py-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">
              {t.settings.hfToken.title}
            </h2>
            {hfTokenConfig?.hf_token_set ? (
              <div className="flex items-center gap-1.5 text-sm text-emerald-600">
                <CheckCircle size={14} />
                <span>{t.settings.hfToken.configured}</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-sm text-amber-600">
                <XCircle size={14} />
                <span>{t.settings.hfToken.notConfigured}</span>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-start gap-3 text-sm">
              <Lock size={14} className="mt-0.5 shrink-0 text-slate-400" />
              <span className="text-slate-500">{t.settings.hfToken.description}</span>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                {t.settings.hfToken.title}
              </label>
              <input
                type="password"
                value={hfToken}
                onChange={e => setHfToken(e.target.value)}
                placeholder="hf_xxxxxxxxxxxxxxxxxxxxxxxx"
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />
              {hfTokenConfig?.hf_token_set && !hfToken && (
                <p className="mt-1 text-xs text-slate-500">{t.settings.hfToken.savedHint}</p>
              )}
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => saveHfTokenMutation.mutate()}
                disabled={saveHfTokenMutation.isPending || !hfToken}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Save size={16} />
                {saveHfTokenMutation.isPending ? t.settings.hfToken.saving : t.settings.hfToken.save}
              </button>
              <span className="text-xs text-amber-600">{t.settings.hfToken.restartHint}</span>
            </div>
          </div>
        </div>

        {/* Model status */}
        {sysInfo && (
          <div className="border-b border-slate-100 px-6 py-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.modelStatus}</h2>
              {missingModelCount > 0 ? (
                <button
                  type="button"
                  onClick={() => downloadMutation.mutate()}
                  disabled={downloadMutation.isPending || jobIsRunning}
                  className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {downloadMutation.isPending || jobIsRunning ? (
                    <>
                      <Loader2 size={14} className="animate-spin" />
                      <span>{t.settings.models.downloading}</span>
                    </>
                  ) : (
                    <>
                      <Download size={14} />
                      <span>{t.settings.models.downloadAllMissing} ({missingModelCount})</span>
                    </>
                  )}
                </button>
              ) : (
                <span className="flex items-center gap-1.5 text-xs text-emerald-600">
                  <CheckCircle size={14} />
                  {t.settings.models.allDownloaded}
                </span>
              )}
            </div>

            {startError && (
              <div className="mb-3 flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <div>
                  <div className="font-medium">{t.settings.models.downloadStartFailed}</div>
                  <div className="break-all">{startError}</div>
                </div>
              </div>
            )}

            {job && (
              <ModelDownloadJobBanner
                job={job}
                jobIsRunning={jobIsRunning}
                onCancel={() => cancelMutation.mutate(job.job_id)}
                onRetry={() => downloadMutation.mutate()}
                cancelling={cancelMutation.isPending}
                t={t}
              />
            )}

            <div className="divide-y divide-slate-100">
              {sysInfo.models.map(m => {
                const itemKey = m.name
                const liveEntry: ModelDownloadEntry | undefined = job?.items.find(it => it.label === m.name)
                return (
                  <div key={itemKey} className="flex items-center justify-between py-2.5">
                    <span className="text-sm text-slate-700">{m.name}</span>
                    <div className="flex items-center gap-1.5 text-sm">
                      {liveEntry ? (
                        <ModelDownloadEntryStatus entry={liveEntry} t={t} />
                      ) : m.status === 'available' ? (
                        <>
                          <CheckCircle size={14} className="text-emerald-500" />
                          <span className="text-emerald-700">{t.settings.models.downloaded}</span>
                        </>
                      ) : m.status === 'needs_extra' ? (
                        <span
                          className="flex items-center gap-1.5 text-amber-600"
                          title={t.settings.models.needsExtraHint}
                        >
                          <AlertTriangle size={14} />
                          <span>{t.settings.models.needsExtra}</span>
                        </span>
                      ) : (
                        <>
                          <XCircle size={14} className="text-slate-400" />
                          <span className="text-slate-400">{t.settings.models.missing}</span>
                        </>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* About */}
        <div className="px-6 py-5">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.about}</h2>
          <div className="text-sm text-slate-600 space-y-1">
            <p>{t.settings.aboutTitle}</p>
            <p className="text-slate-400">{t.settings.aboutSubtitle}</p>
          </div>
        </div>
          </>
        ) : (
          <AdvancedSettingsSection
            config={globalConfig}
            saving={saveGlobalMutation.isPending}
            saved={saveGlobalStatus === 'saved'}
            onPatch={patchGlobalConfig}
            onSave={() => saveGlobalMutation.mutate()}
          />
        )}
      </div>
    </PageContainer>
  )
}

function AdvancedSettingsSection({
  config,
  saving,
  saved,
  onPatch,
  onSave,
}: {
  config: GlobalConfigDraft
  saving: boolean
  saved: boolean
  onPatch: (patch: GlobalConfigDraft) => void
  onSave: () => void
}) {
  const { t } = useI18n()
  const repairBackends = config.dub_repair_backend ?? config.dub_repair_backends ?? []
  const asrBackend = config.asr_backend ?? 'faster-whisper'
  const asrModelOptions = asrBackend === 'funasr' ? FUNASR_MODEL_OPTIONS : FASTER_WHISPER_MODEL_OPTIONS
  const asrModelValue = asrModelOptions.some(option => option.value === config.asr_model)
    ? String(config.asr_model)
    : asrModelOptions[0].value
  const patchRepairBackend = (backend: string, enabled: boolean) => {
    const next = enabled
      ? Array.from(new Set([...repairBackends, backend]))
      : repairBackends.filter(item => item !== backend)
    onPatch({ dub_repair_backend: next, dub_repair_backends: next })
  }
  const patchAsrBackend = (backend: string) => {
    onPatch({
      asr_backend: backend as TaskConfig['asr_backend'],
      asr_model: backend === 'funasr' ? FUNASR_MODEL_OPTIONS[0].value : 'small',
    })
  }

  return (
    <div className="px-6 py-5">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">节点高级参数</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            这些参数会作为新建任务默认值，按节点影响分离、转写、翻译、配音、混音和交付结果。
          </p>
        </div>
        {saved && <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">已保存</span>}
      </div>

      <div className="space-y-6">
        <AdvancedSettingsGroup title="音频分离" description="Stage 1 从视频中提取人声和背景音，影响后续转写和混音素材。">
          <SettingsSelect
            label="分离模式"
            value={config.separation_mode ?? 'auto'}
            options={[
              { value: 'auto', label: 'auto' },
              { value: 'dialogue', label: 'dialogue' },
              { value: 'music', label: 'music' },
            ]}
            onChange={value => onPatch({ separation_mode: value })}
          />
          <SettingsSelect
            label="分离质量"
            value={config.separation_quality ?? 'balanced'}
            options={[
              { value: 'balanced', label: 'balanced' },
              { value: 'high', label: 'high' },
            ]}
            onChange={value => onPatch({ separation_quality: value })}
          />
          <SettingsSelect
            label="Stage 1 输出格式"
            value={config.stage1_output_format ?? 'mp3'}
            options={['mp3', 'wav', 'flac', 'aac', 'opus'].map(value => ({ value, label: value }))}
            onChange={value => onPatch({ stage1_output_format: value })}
          />
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="语音转写" description="Task A 生成带说话人和时间轴的字幕文本。">
          <SettingsSelect
            label="ASR 后端"
            value={asrBackend}
            options={ASR_BACKEND_OPTIONS}
            onChange={patchAsrBackend}
          />
          <SettingsSelect
            label="ASR 模型"
            value={asrModelValue}
            options={asrModelOptions}
            onChange={value => onPatch({ asr_model: value })}
          />
          <SettingsField label="说话人分离">
            <SettingsCheckbox
              label="启用说话人分离"
              checked={config.enable_diarization ?? true}
              onChange={value => onPatch({ enable_diarization: value })}
            />
          </SettingsField>
          <SettingsSelect
            label="说话人后端"
            value={config.diarizer_backend ?? 'ecapa'}
            options={DIARIZER_BACKEND_OPTIONS}
            onChange={value => onPatch({ diarizer_backend: value as TaskConfig['diarizer_backend'] })}
          />
          <SettingsField label="生成 SRT">
            <SettingsCheckbox
              label="生成 SRT 字幕文件"
              checked={config.generate_srt ?? true}
              onChange={value => onPatch({ generate_srt: value })}
            />
          </SettingsField>
          <SettingsField label="VAD">
            <SettingsCheckbox
              label="启用 VAD"
              checked={config.vad_filter ?? true}
              onChange={value => onPatch({ vad_filter: value })}
            />
          </SettingsField>
          <SettingsNumber
            label="VAD 最小静音毫秒"
            value={config.vad_min_silence_duration_ms ?? 400}
            min={1}
            step={50}
            onChange={value => onPatch({ vad_min_silence_duration_ms: value })}
          />
          <SettingsNumber label="Beam Size" value={config.beam_size ?? 5} min={1} step={1} onChange={value => onPatch({ beam_size: value })} />
          <SettingsNumber label="Best Of" value={config.best_of ?? 5} min={1} step={1} onChange={value => onPatch({ best_of: value })} />
          <SettingsNumber label="Temperature" value={config.temperature ?? 0} min={0} step={0.1} onChange={value => onPatch({ temperature: value })} />
          <SettingsField label="上下文">
            <SettingsCheckbox
              label="使用前文上下文"
              checked={config.condition_on_previous_text ?? false}
              onChange={value => onPatch({ condition_on_previous_text: value })}
            />
          </SettingsField>
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="说话人匹配" description="Task B 生成角色/说话人画像并匹配历史声纹。">
          <SettingsNumber
            label="说话人候选数 Top K"
            value={config.top_k ?? 3}
            min={1}
            step={1}
            onChange={value => onPatch({ top_k: value })}
          />
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="OCR 字幕识别" description="ocr-detect 节点用 PaddleOCR 识别原片硬字幕（仅 +OCR 字幕模板生效），影响字幕翻译与擦除的输入。">
          <SettingsNumber
            label="采样间隔 (秒)"
            value={config.ocr_sample_interval ?? 0.25}
            min={0.1}
            step={0.05}
            onChange={value => onPatch({ ocr_sample_interval: value })}
          />
          <SettingsSelect
            label="字幕位置"
            value={config.ocr_position_mode ?? 'auto'}
            options={[
              { value: 'auto', label: '自动检测' },
              { value: 'bottom', label: '底部' },
              { value: 'middle', label: '中间' },
              { value: 'top', label: '顶部' },
            ]}
            onChange={value => onPatch({ ocr_position_mode: value as TaskConfig['ocr_position_mode'] })}
          />
          <SettingsSelect
            label="提取策略"
            value={config.ocr_extraction_mode ?? 'conservative'}
            options={[
              { value: 'conservative', label: '保守（高精度）' },
              { value: 'balanced', label: '均衡' },
              { value: 'variety_recall', label: '高召回' },
            ]}
            onChange={value => onPatch({ ocr_extraction_mode: value as TaskConfig['ocr_extraction_mode'] })}
          />
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="翻译" description="Task C 翻译配音脚本；OCR 字幕翻译也复用这些后端设置。">
          <SettingsSelect
            label="翻译后端"
            value={config.translation_backend ?? 'local-m2m100'}
            options={[
              { value: 'local-m2m100', label: 'local-m2m100' },
              { value: 'siliconflow', label: 'SiliconFlow API' },
            ]}
            onChange={value => onPatch({ translation_backend: value })}
          />
          <SettingsNumber
            label="翻译批量大小"
            value={config.translation_batch_size ?? 4}
            min={1}
            step={1}
            onChange={value => onPatch({ translation_batch_size: value })}
          />
          <SettingsSelect
            label="译文压缩"
            value={config.condense_mode ?? 'off'}
            options={[
              { value: 'off', label: 'off' },
              { value: 'smart', label: 'smart' },
              { value: 'aggressive', label: 'aggressive' },
            ]}
            onChange={value => onPatch({ condense_mode: value })}
          />
          <SettingsText
            label="SiliconFlow 模型"
            value={config.siliconflow_model ?? ''}
            placeholder="deepseek-ai/DeepSeek-V3"
            onChange={value => onPatch({ siliconflow_model: value || null })}
          />
          <SettingsSelect
            label="文稿校正 LLM 仲裁"
            value={config.transcription_correction?.llm_arbitration ?? 'off'}
            options={[
              { value: 'off', label: '关闭' },
              { value: 'deepseek', label: 'DeepSeek' },
              { value: 'siliconflow', label: 'SiliconFlow' },
            ]}
            onChange={value =>
              onPatch({
                transcription_correction: {
                  ...(config.transcription_correction ?? {
                    enabled: true,
                    preset: 'standard',
                    ocr_only_policy: 'report_only',
                    llm_arbitration: 'off',
                  }),
                  llm_arbitration: value as 'off' | 'deepseek' | 'siliconflow',
                },
              })
            }
          />
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="配音" description="Task D 合成每位说话人的目标语言音频，并可启用修复重试。">
          <SettingsSelect
            label="TTS 后端"
            value={config.tts_backend ?? 'moss-tts-nano-onnx'}
            options={DUBBING_BACKEND_OPTIONS}
            onChange={value => onPatch({ tts_backend: value })}
          />
          <SettingsOptionalNumber
            label="配音并发数"
            value={config.dubbing_workers}
            min={1}
            step={1}
            onChange={value => onPatch({ dubbing_workers: value })}
          />
          <SettingsSelect
            label="配音质检"
            value={config.dubbing_quality_check ?? 'standard'}
            options={[
              { value: 'standard', label: '完整质检' },
              { value: 'duration-only', label: '快速草稿' },
            ]}
            onChange={value => onPatch({ dubbing_quality_check: value as TaskConfig['dubbing_quality_check'] })}
          />
          <SettingsField label="配音修复">
            <SettingsCheckbox
              label="启用配音修复"
              checked={config.dub_repair_enabled ?? false}
              onChange={value => onPatch({ dub_repair_enabled: value })}
            />
          </SettingsField>
          <SettingsField label="修复后端">
            <div className="grid gap-2 sm:grid-cols-2">
              {DUBBING_BACKEND_OPTIONS.map(backend => (
                <SettingsCheckbox
                  key={backend.value}
                  label={backend.label}
                  checked={repairBackends.includes(backend.value)}
                  onChange={value => patchRepairBackend(backend.value, value)}
                />
              ))}
            </div>
          </SettingsField>
          <SettingsNumber label="修复最大条数" value={config.dub_repair_max_items ?? 12} min={1} step={1} onChange={value => onPatch({ dub_repair_max_items: value })} />
          <SettingsNumber label="修复每条尝试次数" value={config.dub_repair_attempts_per_item ?? 3} min={1} step={1} onChange={value => onPatch({ dub_repair_attempts_per_item: value })} />
          <SettingsField label="风险策略">
            <SettingsCheckbox
              label="允许修复风险段落"
              checked={config.dub_repair_include_risk ?? false}
              onChange={value => onPatch({ dub_repair_include_risk: value })}
            />
          </SettingsField>
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="混音与时间轴" description="Task E 对齐配音时长、混合背景音并生成预览/成片音轨。">
          <SettingsSelect
            label="时间伸缩策略"
            value={config.fit_policy ?? 'conservative'}
            options={[
              { value: 'conservative', label: 'conservative' },
              { value: 'high_quality', label: 'high_quality' },
            ]}
            onChange={value => onPatch({ fit_policy: value })}
          />
          <SettingsSelect
            label="时间伸缩后端"
            value={config.fit_backend ?? 'atempo'}
            options={[
              { value: 'atempo', label: 'atempo' },
              { value: 'rubberband', label: 'rubberband' },
            ]}
            onChange={value => onPatch({ fit_backend: value })}
          />
          <SettingsSelect
            label="混音配置"
            value={config.mix_profile ?? 'preview'}
            options={[
              { value: 'preview', label: 'preview' },
              { value: 'enhanced', label: 'enhanced' },
            ]}
            onChange={value => onPatch({ mix_profile: value })}
          />
          <SettingsSelect
            label="压低背景模式"
            value={config.ducking_mode ?? 'static'}
            options={[
              { value: 'static', label: 'static' },
              { value: 'sidechain', label: 'sidechain' },
            ]}
            onChange={value => onPatch({ ducking_mode: value })}
          />
          <SettingsNumber label="背景音量 dB" value={config.background_gain_db ?? -8} min={-60} step={0.5} onChange={value => onPatch({ background_gain_db: value })} />
          <SettingsNumber label="窗口压低 dB" value={config.window_ducking_db ?? -3} min={-60} step={0.5} onChange={value => onPatch({ window_ducking_db: value })} />
          <SettingsNumber label="最大压缩比例" value={config.max_compress_ratio ?? 1.45} min={0.1} step={0.05} onChange={value => onPatch({ max_compress_ratio: value })} />
        </AdvancedSettingsGroup>

        <AdvancedSettingsGroup title="导出与字幕" description="Task G 交付视频、字幕叠加和双语字幕布局默认值。">
          <SettingsSelect
            label="成品字幕模式"
            value={config.subtitle_mode ?? 'none'}
            options={[
              { value: 'none', label: '无字幕' },
              { value: 'chinese_only', label: '仅中文' },
              { value: 'english_only', label: '仅英文' },
              { value: 'bilingual', label: '双语' },
            ]}
            onChange={value => onPatch({ subtitle_mode: value as TaskConfig['subtitle_mode'] })}
          />
          <SettingsSelect
            label="字幕渲染来源"
            value={config.subtitle_render_source ?? 'ocr'}
            options={[
              { value: 'ocr', label: 'OCR 字幕' },
              { value: 'asr', label: 'ASR 字幕' },
            ]}
            onChange={value => onPatch({ subtitle_render_source: value as TaskConfig['subtitle_render_source'] })}
          />
        </AdvancedSettingsGroup>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Save size={16} />
          {saving ? '保存中...' : t.settings.saveDefaults}
        </button>
        <span className="text-xs text-slate-400">保存后会作为新建任务的默认参数。</span>
      </div>
    </div>
  )
}

function AdvancedSettingsGroup({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <section className="border-t border-slate-100 pt-5 first:border-t-0 first:pt-0">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
    </section>
  )
}

function SettingsField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium text-slate-700">{label}</div>
      {children}
    </div>
  )
}

function SettingsSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
}) {
  return (
    <label>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <select
        aria-label={label}
        value={value}
        onChange={event => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
      >
        {options.map(option => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  )
}

function SettingsText({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string
  value: string
  placeholder?: string
  onChange: (value: string) => void
}) {
  return (
    <label>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <input
        aria-label={label}
        value={value}
        placeholder={placeholder}
        onChange={event => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
      />
    </label>
  )
}

function SettingsCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="flex min-h-10 cursor-pointer items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
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

function SettingsNumber({
  label,
  value,
  min,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <input
        type="number"
        aria-label={label}
        value={value}
        min={min}
        step={step}
        onChange={event => {
          const next = Number(event.target.value)
          if (Number.isFinite(next)) onChange(next)
        }}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
      />
    </label>
  )
}

function SettingsOptionalNumber({
  label,
  value,
  min,
  step,
  onChange,
}: {
  label: string
  value?: number | null
  min: number
  step: number
  onChange: (value: number | null) => void
}) {
  return (
    <label>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <input
        type="number"
        aria-label={label}
        value={value ?? ''}
        min={min}
        step={step}
        onChange={event => {
          if (event.target.value === '') {
            onChange(null)
            return
          }
          const next = Number(event.target.value)
          if (Number.isFinite(next)) onChange(next)
        }}
        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
      />
    </label>
  )
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex gap-4 py-2.5">
      <span className="w-24 shrink-0 text-slate-400">{label}</span>
      <span className={`text-slate-700 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}

type I18nT = ReturnType<typeof useI18n>['t']

function ModelDownloadJobBanner({
  job,
  jobIsRunning,
  onCancel,
  onRetry,
  cancelling,
  t,
}: {
  job: import('../types').ModelDownloadJob
  jobIsRunning: boolean
  onCancel: () => void
  onRetry: () => void
  cancelling: boolean
  t: I18nT
}) {
  const summary = job.summary
  if (job.state === 'succeeded') {
    return (
      <div className="mb-3 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
        <CheckCircle size={14} />
        <span>{t.settings.models.downloadDone} ({summary.succeeded}/{summary.total})</span>
      </div>
    )
  }
  if (job.state === 'partial') {
    return (
      <div className="mb-3 flex items-start justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
        <div className="flex items-start gap-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>
            {t.settings.models.downloadPartial} ({summary.succeeded}/{summary.total})
          </span>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-amber-300 px-2 py-0.5 text-[11px] font-medium text-amber-800 hover:bg-amber-100"
        >
          {t.settings.models.retry}
        </button>
      </div>
    )
  }
  if (job.state === 'failed') {
    return (
      <div className="mb-3 flex items-start justify-between gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
        <div className="flex items-start gap-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span>{t.settings.models.downloadFailed}</span>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-rose-300 px-2 py-0.5 text-[11px] font-medium text-rose-800 hover:bg-rose-100"
        >
          {t.settings.models.retry}
        </button>
      </div>
    )
  }
  if (job.state === 'cancelled') {
    return (
      <div className="mb-3 flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <XCircle size={14} />
        <span>{t.settings.models.cancel}</span>
      </div>
    )
  }
  // pending / running
  const currentEntry = job.items.find(it => it.key === job.current_key)
  return (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
      <div className="flex items-center gap-2">
        <Loader2 size={14} className="animate-spin" />
        <span>
          {currentEntry
            ? t.settings.models.downloadingCurrent(currentEntry.label)
            : t.settings.models.downloading}{' '}
          ({summary.succeeded}/{summary.total})
        </span>
      </div>
      {jobIsRunning && (
        <button
          type="button"
          onClick={onCancel}
          disabled={cancelling}
          className="rounded border border-blue-300 px-2 py-0.5 text-[11px] font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60"
        >
          {cancelling ? t.settings.models.cancelling : t.settings.models.cancel}
        </button>
      )}
    </div>
  )
}

function ModelDownloadEntryStatus({
  entry,
  t,
}: {
  entry: ModelDownloadEntry
  t: I18nT
}) {
  if (entry.state === 'running') {
    return (
      <>
        <Loader2 size={14} className="animate-spin text-blue-500" />
        <span className="text-blue-700">{t.settings.models.itemRunning}</span>
      </>
    )
  }
  if (entry.state === 'succeeded') {
    return (
      <>
        <CheckCircle size={14} className="text-emerald-500" />
        <span className="text-emerald-700">{t.settings.models.itemSucceeded}</span>
      </>
    )
  }
  if (entry.state === 'failed') {
    return (
      <>
        <AlertTriangle size={14} className="text-rose-500" />
        <span className="text-rose-700" title={entry.error ?? undefined}>
          {t.settings.models.itemFailed}
        </span>
      </>
    )
  }
  if (entry.state === 'skipped') {
    return (
      <>
        <XCircle size={14} className="text-slate-400" />
        <span className="text-slate-500">{t.settings.models.itemSkipped}</span>
      </>
    )
  }
  return (
    <>
      <Loader2 size={14} className="text-slate-400" />
      <span className="text-slate-500">{t.settings.models.itemPending}</span>
    </>
  )
}
