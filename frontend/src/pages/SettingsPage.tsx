import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { configApi, modelsApi, systemApi } from '../api/config'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { CacheSection } from '../components/settings/CacheSection'
import { AdvancedDefaultsSection } from '../components/settings/AdvancedDefaultsSection'
import { computeChangedAdvancedKeys } from '../components/settings/advancedDefaults'
import { formatBytes } from '../lib/utils'
import {
  CheckCircle,
  XCircle,
  Save,
  Lock,
  Download,
  Loader2,
  AlertTriangle,
  Plug,
  Undo2,
} from 'lucide-react'
import { useI18n } from '../i18n/useI18n'
import { worksApi } from '../api/works'
import type { ModelDownloadEntry } from '../types'
import type { GlobalConfigUpdate } from '../api/config'

type SettingsSection = 'global' | 'advanced'
type GlobalConfigDraft = GlobalConfigUpdate

const defaultGlobalConfig: GlobalConfigDraft = {
  device: 'auto',
  use_cache: true,
  keep_intermediate: false,
  separation_mode: 'dialogue',
  separation_quality: 'balanced',
  music_backend: 'demucs',
  dialogue_backend: 'cdx23',
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
  condense_mode: 'smart',
  deepseek_model: null,
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
  output_sample_rate: 48000,
  preview_format: 'wav',
  subtitle_mode: 'none',
  subtitle_render_source: 'ocr',
  subtitle_font: '',
  subtitle_font_size: 0,
  subtitle_color: '#FFFFFF',
  subtitle_outline_color: '#000000',
  subtitle_outline_width: 2,
  subtitle_position: 'bottom',
  subtitle_margin_v: 0,
  subtitle_bold: false,
  bilingual_chinese_position: 'bottom',
  bilingual_english_position: 'top',
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

export function SettingsPage() {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const [activeSection, setActiveSection] = useState<SettingsSection>('global')
  const [activeGeneralSection, setActiveGeneralSection] = useState('system')
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

  // Sync the server-fetched config into the editable draft when it (re)loads,
  // using the render-time "store previous value" pattern instead of an effect so
  // the reset happens before paint without a second render pass. react-query's
  // structural sharing keeps savedGlobalConfig's reference stable across refetches
  // with identical data, so this never clobbers the user's in-progress edits.
  const [syncedSavedConfig, setSyncedSavedConfig] = useState(savedGlobalConfig)
  if (savedGlobalConfig && savedGlobalConfig !== syncedSavedConfig) {
    setSyncedSavedConfig(savedGlobalConfig)
    setGlobalConfig({ ...defaultGlobalConfig, ...savedGlobalConfig })
  }

  const saveGlobalMutation = useMutation({
    mutationFn: () => configApi.updateGlobal(globalConfig),
    onSuccess: data => {
      setGlobalConfig({ ...defaultGlobalConfig, ...data.config })
      setSaveGlobalStatus('saved')
      queryClient.invalidateQueries({ queryKey: ['global-config'] })
      queryClient.invalidateQueries({ queryKey: ['config-defaults'] })
    },
  })

  // Compare the working draft against the last saved config (falling back to
  // shipped defaults) so we can surface exactly which advanced defaults are unsaved.
  const savedBaseline = useMemo<GlobalConfigDraft>(
    () => ({ ...defaultGlobalConfig, ...(savedGlobalConfig ?? {}) }),
    [savedGlobalConfig],
  )
  const changedKeys = useMemo(
    () => computeChangedAdvancedKeys(globalConfig, savedBaseline),
    [globalConfig, savedBaseline],
  )
  const changedCount = changedKeys.size

  const resetGroupDefaults = (keys: (keyof GlobalConfigDraft)[]) => {
    setSaveGlobalStatus('idle')
    setGlobalConfig(prev => {
      const next = { ...prev } as Record<string, unknown>
      const source = defaultGlobalConfig as Record<string, unknown>
      for (const key of keys) next[key] = source[key]
      return next as GlobalConfigDraft
    })
  }
  const revertGlobalChanges = () => {
    setSaveGlobalStatus('idle')
    setGlobalConfig(savedBaseline)
  }

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

  const [tmdbTestResult, setTmdbTestResult] = useState<{ ok: boolean; message: string } | null>(
    null,
  )
  const testTmdbMutation = useMutation({
    mutationFn: () =>
      worksApi.tmdbTestConfig({
        api_key_v3: apiKeyV3 || undefined,
        api_key_v4: apiKeyV4 || undefined,
      }),
    onSuccess: data => setTmdbTestResult({ ok: data.ok, message: data.message }),
    onError: () => setTmdbTestResult({ ok: false, message: 'request failed' }),
  })

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
  const [hfTestResult, setHfTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const testHfTokenMutation = useMutation({
    mutationFn: () => systemApi.testHfToken(hfToken || undefined),
    onSuccess: data => setHfTestResult({ ok: data.ok, message: data.message }),
    onError: () => setHfTestResult({ ok: false, message: 'request failed' }),
  })

  // ---------- LLM keys (DeepSeek) ----------
  const { data: llmKeys } = useQuery({
    queryKey: ['llm-keys'],
    queryFn: systemApi.getLlmKeys,
  })
  const [llmKeyInputs, setLlmKeyInputs] = useState<Record<string, string>>({
    deepseek: '',
  })
  // Base URL inputs mirror the saved value (account-level, e.g. a compatible
  // proxy); null means "not loaded into the input yet".
  const [llmBaseUrlInputs, setLlmBaseUrlInputs] = useState<Record<string, string | null>>({
    deepseek: null,
  })
  const [llmTestResult, setLlmTestResult] = useState<
    Record<string, { ok: boolean; message: string } | null>
  >({ deepseek: null })
  const saveLlmKeyMutation = useMutation({
    mutationFn: (provider: string) => {
      const update: { api_key?: string; base_url?: string } = {}
      if (llmKeyInputs[provider]) update.api_key = llmKeyInputs[provider]
      const baseUrlInput = llmBaseUrlInputs[provider]
      if (baseUrlInput !== null && baseUrlInput !== (llmKeys?.base_urls?.[provider] ?? '')) {
        update.base_url = baseUrlInput
      }
      return systemApi.saveLlmKey(provider, update)
    },
    onSuccess: (_data, provider) => {
      setLlmKeyInputs(prev => ({ ...prev, [provider]: '' }))
      setLlmBaseUrlInputs(prev => ({ ...prev, [provider]: null }))
      queryClient.invalidateQueries({ queryKey: ['llm-keys'] })
    },
  })
  const testLlmKeyMutation = useMutation({
    mutationFn: (provider: string) =>
      systemApi.testLlmKey(
        provider,
        llmKeyInputs[provider] || undefined,
        llmBaseUrlInputs[provider] || undefined,
      ),
    onSuccess: (data, provider) =>
      setLlmTestResult(prev => ({ ...prev, [provider]: { ok: data.ok, message: data.message } })),
    onError: (_err, provider) =>
      setLlmTestResult(prev => ({ ...prev, [provider]: { ok: false, message: 'request failed' } })),
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

  const generalSections = [
    { id: 'system', title: t.settings.systemInfo },
    { id: 'keys', title: t.settings.keysGroup },
    { id: 'models', title: t.settings.modelStatus },
    { id: 'about', title: t.settings.about },
  ]

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
          <div className="flex flex-col gap-2 md:flex-row md:gap-0">
            <nav
              aria-label={t.settings.navGroups}
              className="flex gap-1 overflow-x-auto px-5 pt-5 md:w-48 md:shrink-0 md:flex-col md:gap-0.5 md:overflow-visible md:border-r md:border-slate-100 md:px-3 md:py-5"
            >
              {generalSections.map(section => {
                const active = activeGeneralSection === section.id
                return (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => setActiveGeneralSection(section.id)}
                    aria-current={active ? 'page' : undefined}
                    className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm transition-colors md:w-full ${
                      active ? 'bg-blue-50 font-medium text-blue-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                    }`}
                  >
                    {section.title}
                  </button>
                )
              })}
            </nav>
            <div className="min-w-0 flex-1">
        {/* System info */}
        <div className={activeGeneralSection === 'system' ? 'px-6 py-5' : 'hidden'}>
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

        {/* Service credentials: TMDb / HuggingFace / DeepSeek */}
        <div className={activeGeneralSection === 'keys' ? 'block' : 'hidden'}>
        <div className="border-b border-slate-100 px-6 py-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">TMDb API</h2>
            {tmdbConfig?.ok && (tmdbConfig.api_key_v3_set || tmdbConfig.api_key_v4_set) ? (
              <div className="flex items-center gap-1.5 text-sm text-emerald-600">
                <CheckCircle size={14} />
                <span>{t.settings.tmdb.configured}</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-sm text-amber-600">
                <XCircle size={14} />
                <span>{t.settings.tmdb.notConfigured}</span>
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm">
              <Lock size={14} className="text-slate-400" />
              <span className="text-slate-500">{t.settings.tmdb.keyHint}</span>
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
                  <p className="mt-1 text-xs text-slate-500">{t.settings.tmdb.savedHint}</p>
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
                  <p className="mt-1 text-xs text-slate-500">{t.settings.tmdb.savedHint}</p>
                )}
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-700">
                {t.settings.tmdb.defaultLanguage}
              </label>
              <select
                value={defaultLanguage}
                onChange={(e) => setDefaultLanguage(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
              >
                <option value="zh-CN">{t.settings.tmdb.langZhCN}</option>
                <option value="zh-TW">{t.settings.tmdb.langZhTW}</option>
                <option value="en-US">{t.settings.tmdb.langEn}</option>
                <option value="ja-JP">{t.settings.tmdb.langJa}</option>
                <option value="ko-KR">{t.settings.tmdb.langKo}</option>
              </select>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={saveMutation.isPending}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Save size={16} />
                {saveMutation.isPending ? t.settings.tmdb.saving : t.settings.tmdb.save}
              </button>
              <button
                onClick={() => testTmdbMutation.mutate()}
                disabled={
                  testTmdbMutation.isPending ||
                  (!apiKeyV3 && !apiKeyV4 && !(tmdbConfig?.api_key_v3_set || tmdbConfig?.api_key_v4_set))
                }
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {testTmdbMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Plug size={16} />
                )}
                {testTmdbMutation.isPending ? t.settings.tmdb.testing : t.settings.tmdb.test}
              </button>
              {tmdbTestResult && (
                <div
                  className={`flex items-center gap-1.5 text-sm ${
                    tmdbTestResult.ok ? 'text-emerald-600' : 'text-red-600'
                  }`}
                >
                  {tmdbTestResult.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
                  <span>{tmdbTestResult.ok ? t.settings.tmdb.testOk : t.settings.tmdb.testFailed}</span>
                </div>
              )}
            </div>
            {tmdbTestResult && !tmdbTestResult.ok && tmdbTestResult.message && (
              <p className="break-words text-xs text-red-500">{tmdbTestResult.message}</p>
            )}
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
              <button
                onClick={() => testHfTokenMutation.mutate()}
                disabled={testHfTokenMutation.isPending || (!hfToken && !hfTokenConfig?.hf_token_set)}
                className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {testHfTokenMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Plug size={16} />
                )}
                {testHfTokenMutation.isPending ? t.settings.hfToken.testing : t.settings.hfToken.test}
              </button>
              {hfTestResult && (
                <div
                  className={`flex items-center gap-1.5 text-sm ${
                    hfTestResult.ok ? 'text-emerald-600' : 'text-red-600'
                  }`}
                >
                  {hfTestResult.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
                  <span>{hfTestResult.ok ? t.settings.hfToken.testOk : t.settings.hfToken.testFailed}</span>
                </div>
              )}
            </div>
            {hfTestResult && !hfTestResult.ok && hfTestResult.message && (
              <p className="break-words text-xs text-red-500">{hfTestResult.message}</p>
            )}
            <p className="text-xs text-amber-600">{t.settings.hfToken.restartHint}</p>
          </div>
        </div>

        {/* Transcript-correction LLM keys */}
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="mb-4 text-[11px] font-semibold uppercase tracking-widest text-slate-400">
            {t.settings.llmKeys.title}
          </h2>
          <div className="mb-5 flex items-start gap-3 text-sm">
            <Lock size={14} className="mt-0.5 shrink-0 text-slate-400" />
            <span className="text-slate-500">{t.settings.llmKeys.description}</span>
          </div>

          <div className="space-y-5">
            {([
              { id: 'deepseek', label: 'DeepSeek' },
            ] as const).map(provider => {
              const isSet = llmKeys?.providers?.[provider.id] ?? false
              const input = llmKeyInputs[provider.id] ?? ''
              const savedBaseUrl = llmKeys?.base_urls?.[provider.id] ?? ''
              const baseUrlInput = llmBaseUrlInputs[provider.id] ?? savedBaseUrl
              const baseUrlChanged =
                llmBaseUrlInputs[provider.id] !== null && baseUrlInput !== savedBaseUrl
              const result = llmTestResult[provider.id]
              const saving =
                saveLlmKeyMutation.isPending && saveLlmKeyMutation.variables === provider.id
              const testing =
                testLlmKeyMutation.isPending && testLlmKeyMutation.variables === provider.id
              return (
                <div key={provider.id} className="rounded-lg border border-slate-100 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-700">{provider.label}</span>
                    {isSet ? (
                      <div className="flex items-center gap-1.5 text-sm text-emerald-600">
                        <CheckCircle size={14} />
                        <span>{t.settings.llmKeys.configured}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-sm text-amber-600">
                        <XCircle size={14} />
                        <span>{t.settings.llmKeys.notConfigured}</span>
                      </div>
                    )}
                  </div>

                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    {t.settings.llmKeys.apiKey}
                  </label>
                  <input
                    type="password"
                    aria-label={`${provider.label} ${t.settings.llmKeys.apiKey}`}
                    value={input}
                    onChange={e =>
                      setLlmKeyInputs(prev => ({ ...prev, [provider.id]: e.target.value }))
                    }
                    placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                  {isSet && !input && (
                    <p className="mt-1 text-xs text-slate-500">{t.settings.llmKeys.savedHint}</p>
                  )}

                  <label className="mb-1.5 mt-3 block text-sm font-medium text-slate-700">
                    {t.settings.llmKeys.baseUrl}
                  </label>
                  <input
                    type="text"
                    aria-label={`${provider.label} ${t.settings.llmKeys.baseUrl}`}
                    value={baseUrlInput}
                    onChange={e =>
                      setLlmBaseUrlInputs(prev => ({ ...prev, [provider.id]: e.target.value }))
                    }
                    placeholder="https://api.deepseek.com"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
                  />
                  <p className="mt-1 text-xs text-slate-500">{t.settings.llmKeys.baseUrlHint}</p>

                  <div className="mt-3 flex items-center gap-3">
                    <button
                      onClick={() => saveLlmKeyMutation.mutate(provider.id)}
                      disabled={saving || (!input && !baseUrlChanged)}
                      className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Save size={16} />
                      {saving ? t.settings.llmKeys.saving : t.settings.llmKeys.save}
                    </button>
                    <button
                      onClick={() => testLlmKeyMutation.mutate(provider.id)}
                      disabled={testing || (!input && !isSet)}
                      className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {testing ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Plug size={16} />
                      )}
                      {testing ? t.settings.llmKeys.testing : t.settings.llmKeys.test}
                    </button>
                    {result && (
                      <div
                        className={`flex items-center gap-1.5 text-sm ${
                          result.ok ? 'text-emerald-600' : 'text-red-600'
                        }`}
                      >
                        {result.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
                        <span>
                          {result.ok ? t.settings.llmKeys.testOk : t.settings.llmKeys.testFailed}
                        </span>
                      </div>
                    )}
                  </div>
                  {result && !result.ok && result.message && (
                    <p className="mt-2 break-words text-xs text-red-500">{result.message}</p>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        </div>
        {/* Model management */}
        <div className={activeGeneralSection === 'models' ? 'px-6 py-5' : 'hidden'}>
        {sysInfo && (
          <div>
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

        </div>
        {/* About */}
        <div className={activeGeneralSection === 'about' ? 'px-6 py-5' : 'hidden'}>
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-slate-400">{t.settings.about}</h2>
          <div className="text-sm text-slate-600 space-y-1">
            <p>{t.settings.aboutTitle}</p>
            <p className="text-slate-400">{t.settings.aboutSubtitle}</p>
          </div>
        </div>
            </div>
          </div>
        ) : (
          <AdvancedDefaultsSection
            config={globalConfig}
            saved={saveGlobalStatus === 'saved'}
            changedKeys={changedKeys}
            defaults={defaultGlobalConfig}
            deepseekKeySet={llmKeys ? Boolean(llmKeys.providers?.deepseek) : undefined}
            onOpenLlmKeys={() => {
              setActiveSection('global')
              setActiveGeneralSection('keys')
            }}
            onPatch={patchGlobalConfig}
            onResetGroup={resetGroupDefaults}
          />
        )}
      </div>

      {activeSection === 'advanced' && changedCount > 0 && (
        <div className="fixed bottom-6 left-1/2 z-40 flex -translate-x-1/2 items-center gap-3 rounded-full border border-slate-200 bg-white/95 px-4 py-2 shadow-lg shadow-slate-900/10 backdrop-blur">
          <span className="text-sm text-slate-600">
            <span className="font-semibold text-slate-900">{changedCount}</span> {t.settings.advanced.unsavedSuffix}
          </span>
          <button
            type="button"
            onClick={revertGlobalChanges}
            disabled={saveGlobalMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Undo2 size={15} />
            {t.settings.advanced.revert}
          </button>
          <button
            type="button"
            onClick={() => saveGlobalMutation.mutate()}
            disabled={saveGlobalMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save size={15} />
            {saveGlobalMutation.isPending ? t.settings.advanced.saving : t.settings.saveDefaults}
          </button>
        </div>
      )}
    </PageContainer>
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
