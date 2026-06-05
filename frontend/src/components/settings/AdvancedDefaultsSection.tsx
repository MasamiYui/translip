import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown, RotateCcw } from 'lucide-react'
import { DUBBING_BACKEND_OPTIONS } from '../../lib/dubbingBackends'
import { useI18n } from '../../i18n/useI18n'
import type { TaskConfig } from '../../types'
import { ADVANCED_GROUPS, deepEqual, keysOf, type GlobalConfigDraft } from './advancedDefaults'

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

// ---------------------------------------------------------------------------
// Per-field "unsaved change" dot, fed by context so call sites only pass a key.
// ---------------------------------------------------------------------------

const ChangedKeysContext = createContext<Set<string>>(new Set())

function useFieldDirty(dirtyKey?: string): boolean {
  const changed = useContext(ChangedKeysContext)
  return dirtyKey ? changed.has(dirtyKey) : false
}

function FieldLabelText({ label, dirtyKey }: { label: string; dirtyKey?: string }) {
  const { t } = useI18n()
  const dirty = useFieldDirty(dirtyKey)
  return (
    <span className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-slate-700">
      <span>{label}</span>
      {dirty && (
        <span
          aria-hidden
          title={t.settings.advanced.unsaved}
          className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"
        />
      )}
    </span>
  )
}

export function AdvancedDefaultsSection({
  config,
  saved,
  changedKeys,
  defaults,
  onPatch,
  onResetGroup,
}: {
  config: GlobalConfigDraft
  saved: boolean
  changedKeys: Set<string>
  defaults: GlobalConfigDraft
  onPatch: (patch: GlobalConfigDraft) => void
  onResetGroup: (keys: (keyof GlobalConfigDraft)[]) => void
}) {
  const { t } = useI18n()
  const a = t.settings.advanced
  const [activeStage, setActiveStage] = useState<string>(ADVANCED_GROUPS[0].id)
  const repairBackends = config.dub_repair_backend ?? []
  const asrBackend = config.asr_backend ?? 'faster-whisper'
  const asrModelOptions = asrBackend === 'funasr' ? FUNASR_MODEL_OPTIONS : FASTER_WHISPER_MODEL_OPTIONS
  const asrModelValue = asrModelOptions.some(option => option.value === config.asr_model)
    ? String(config.asr_model)
    : asrModelOptions[0].value
  const subtitleMode = config.subtitle_mode ?? 'none'

  // Stage title/description come from i18n; ADVANCED_GROUPS only carries ids + keys.
  const stageTitle: Record<string, string> = {
    separation: a.stages.separationTitle,
    transcription: a.stages.transcriptionTitle,
    matching: a.stages.matchingTitle,
    ocr: a.stages.ocrTitle,
    erase: a.stages.eraseTitle,
    translation: a.stages.translationTitle,
    dubbing: a.stages.dubbingTitle,
    mixing: a.stages.mixingTitle,
    delivery: a.stages.deliveryTitle,
  }

  const patchRepairBackend = (backend: string, enabled: boolean) => {
    const next = enabled
      ? Array.from(new Set([...repairBackends, backend]))
      : repairBackends.filter(item => item !== backend)
    onPatch({ dub_repair_backend: next })
  }
  const patchAsrBackend = (backend: string) => {
    onPatch({
      asr_backend: backend as TaskConfig['asr_backend'],
      asr_model: backend === 'funasr' ? FUNASR_MODEL_OPTIONS[0].value : 'small',
    })
  }

  const countChanged = (keys: (keyof GlobalConfigDraft)[]) =>
    keys.reduce((total, key) => (changedKeys.has(key) ? total + 1 : total), 0)
  const hasNonDefault = (keys: (keyof GlobalConfigDraft)[]) =>
    keys.some(key => !deepEqual(config[key], defaults[key]))
  const stageProps = (id: string) => {
    const keys = keysOf(id)
    return {
      active: activeStage === id,
      canReset: hasNonDefault(keys),
      onReset: () => onResetGroup(keys),
    }
  }

  return (
    <ChangedKeysContext.Provider value={changedKeys}>
      <div className="px-6 py-5">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">{a.title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">{a.intro}</p>
          </div>
          {saved && <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">{a.saved}</span>}
        </div>

        <div className="flex flex-col gap-4 md:flex-row md:gap-6">
          <nav
            aria-label={a.navLabel}
            className="flex gap-1 overflow-x-auto pb-1 md:w-52 md:shrink-0 md:flex-col md:gap-0.5 md:overflow-visible md:border-r md:border-slate-100 md:pb-0 md:pr-3"
          >
            {ADVANCED_GROUPS.map(stage => {
              const count = countChanged(stage.keys)
              const active = activeStage === stage.id
              return (
                <button
                  key={stage.id}
                  type="button"
                  onClick={() => setActiveStage(stage.id)}
                  aria-current={active ? 'page' : undefined}
                  className={`flex shrink-0 items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors md:w-full ${
                    active ? 'bg-blue-50 font-medium text-blue-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                  }`}
                >
                  <span className="truncate">{stageTitle[stage.id]}</span>
                  {count > 0 && (
                    <span className="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">{count}</span>
                  )}
                </button>
              )
            })}
          </nav>

          <div className="min-w-0 flex-1">
            <StagePanel
              title={a.stages.separationTitle}
              description={a.stages.separationDesc}
              advancedCount={1}
              advanced={
                <SettingsSelect
                  label={a.fields.stage1Format}
                  dirtyKey="stage1_output_format"
                  value={config.stage1_output_format ?? 'mp3'}
                  options={['mp3', 'wav', 'flac', 'aac', 'opus'].map(value => ({ value, label: value }))}
                  onChange={value => onPatch({ stage1_output_format: value })}
                />
              }
              {...stageProps('separation')}
            >
              <SettingsSelect
                label={a.fields.separationMode}
                dirtyKey="separation_mode"
                value={config.separation_mode ?? 'auto'}
                options={[
                  { value: 'auto', label: 'auto' },
                  { value: 'dialogue', label: 'dialogue' },
                  { value: 'music', label: 'music' },
                ]}
                onChange={value => onPatch({ separation_mode: value })}
              />
              <SettingsSelect
                label={a.fields.separationQuality}
                dirtyKey="separation_quality"
                value={config.separation_quality ?? 'balanced'}
                options={[
                  { value: 'balanced', label: 'balanced' },
                  { value: 'high', label: 'high' },
                ]}
                onChange={value => onPatch({ separation_quality: value })}
              />
            </StagePanel>

            <StagePanel
              title={a.stages.transcriptionTitle}
              description={a.stages.transcriptionDesc}
              advancedCount={6}
              advanced={
                <>
                  <SettingsField label={a.fields.vad} dirtyKey="vad_filter">
                    <SettingsCheckbox
                      label={a.checks.enableVad}
                      checked={config.vad_filter ?? true}
                      onChange={value => onPatch({ vad_filter: value })}
                    />
                  </SettingsField>
                  <SettingsNumber
                    label={a.fields.vadMinSilence}
                    dirtyKey="vad_min_silence_duration_ms"
                    value={config.vad_min_silence_duration_ms ?? 400}
                    min={1}
                    step={50}
                    onChange={value => onPatch({ vad_min_silence_duration_ms: value })}
                  />
                  <SettingsNumber label="Beam Size" dirtyKey="beam_size" value={config.beam_size ?? 5} min={1} step={1} onChange={value => onPatch({ beam_size: value })} />
                  <SettingsNumber label="Best Of" dirtyKey="best_of" value={config.best_of ?? 5} min={1} step={1} onChange={value => onPatch({ best_of: value })} />
                  <SettingsNumber label="Temperature" dirtyKey="temperature" value={config.temperature ?? 0} min={0} step={0.1} onChange={value => onPatch({ temperature: value })} />
                  <SettingsField label={a.fields.context} dirtyKey="condition_on_previous_text">
                    <SettingsCheckbox
                      label={a.checks.usePrevContext}
                      checked={config.condition_on_previous_text ?? false}
                      onChange={value => onPatch({ condition_on_previous_text: value })}
                    />
                  </SettingsField>
                </>
              }
              {...stageProps('transcription')}
            >
              <SettingsSelect label={a.fields.asrBackend} dirtyKey="asr_backend" value={asrBackend} options={ASR_BACKEND_OPTIONS} onChange={patchAsrBackend} />
              <SettingsSelect label={a.fields.asrModel} dirtyKey="asr_model" value={asrModelValue} options={asrModelOptions} onChange={value => onPatch({ asr_model: value })} />
              <SettingsField label={a.fields.diarization} dirtyKey="enable_diarization">
                <SettingsCheckbox
                  label={a.checks.enableDiarization}
                  checked={config.enable_diarization ?? true}
                  onChange={value => onPatch({ enable_diarization: value })}
                />
              </SettingsField>
              <SettingsSelect
                label={a.fields.diarizerBackend}
                dirtyKey="diarizer_backend"
                value={config.diarizer_backend ?? 'ecapa'}
                options={DIARIZER_BACKEND_OPTIONS}
                onChange={value => onPatch({ diarizer_backend: value as TaskConfig['diarizer_backend'] })}
              />
              <SettingsField label={a.fields.generateSrt} dirtyKey="generate_srt">
                <SettingsCheckbox
                  label={a.checks.generateSrtFile}
                  checked={config.generate_srt ?? true}
                  onChange={value => onPatch({ generate_srt: value })}
                />
              </SettingsField>
            </StagePanel>

            <StagePanel
              title={a.stages.matchingTitle}
              description={a.stages.matchingDesc}
              {...stageProps('matching')}
            >
              <SettingsNumber
                label={a.fields.topK}
                dirtyKey="top_k"
                value={config.top_k ?? 3}
                min={1}
                step={1}
                onChange={value => onPatch({ top_k: value })}
              />
            </StagePanel>

            <StagePanel
              title={a.stages.ocrTitle}
              description={a.stages.ocrDesc}
              {...stageProps('ocr')}
            >
              <SettingsNumber
                label={a.fields.ocrInterval}
                dirtyKey="ocr_sample_interval"
                value={config.ocr_sample_interval ?? 0.25}
                min={0.1}
                step={0.05}
                onChange={value => onPatch({ ocr_sample_interval: value })}
              />
              <SettingsSelect
                label={a.fields.subtitlePosition}
                dirtyKey="ocr_position_mode"
                value={config.ocr_position_mode ?? 'auto'}
                options={[
                  { value: 'auto', label: a.opts.ocrAuto },
                  { value: 'bottom', label: a.opts.posBottom },
                  { value: 'middle', label: a.opts.posMiddle },
                  { value: 'top', label: a.opts.posTop },
                ]}
                onChange={value => onPatch({ ocr_position_mode: value as TaskConfig['ocr_position_mode'] })}
              />
              <SettingsSelect
                label={a.fields.extraction}
                dirtyKey="ocr_extraction_mode"
                value={config.ocr_extraction_mode ?? 'conservative'}
                options={[
                  { value: 'conservative', label: a.opts.extractConservative },
                  { value: 'balanced', label: a.opts.extractBalanced },
                  { value: 'variety_recall', label: a.opts.extractRecall },
                ]}
                onChange={value => onPatch({ ocr_extraction_mode: value as TaskConfig['ocr_extraction_mode'] })}
              />
            </StagePanel>

            <StagePanel
              title={a.stages.eraseTitle}
              description={a.stages.eraseDesc}
              advancedCount={7}
              advanced={
                <>
                  <SettingsNumber label={a.fields.maskDilateX} dirtyKey="erase_mask_dilate_x" value={config.erase_mask_dilate_x ?? 12} min={0} step={1} onChange={value => onPatch({ erase_mask_dilate_x: value })} />
                  <SettingsNumber label={a.fields.maskDilateY} dirtyKey="erase_mask_dilate_y" value={config.erase_mask_dilate_y ?? 8} min={0} step={1} onChange={value => onPatch({ erase_mask_dilate_y: value })} />
                  <SettingsNumber label={a.fields.leadFrames} dirtyKey="erase_event_lead_frames" value={config.erase_event_lead_frames ?? 3} min={0} step={1} onChange={value => onPatch({ erase_event_lead_frames: value })} />
                  <SettingsNumber label={a.fields.trailFrames} dirtyKey="erase_event_trail_frames" value={config.erase_event_trail_frames ?? 8} min={0} step={1} onChange={value => onPatch({ erase_event_trail_frames: value })} />
                  <SettingsNumber label={a.fields.neighborStride} dirtyKey="erase_neighbor_stride" value={config.erase_neighbor_stride ?? 5} min={1} step={1} onChange={value => onPatch({ erase_neighbor_stride: value })} />
                  <SettingsNumber label={a.fields.referenceLength} dirtyKey="erase_reference_length" value={config.erase_reference_length ?? 10} min={1} step={1} onChange={value => onPatch({ erase_reference_length: value })} />
                  <SettingsNumber label={a.fields.maxLoad} dirtyKey="erase_max_load" value={config.erase_max_load ?? 50} min={1} step={1} onChange={value => onPatch({ erase_max_load: value })} />
                </>
              }
              {...stageProps('erase')}
            >
              <SettingsSelect
                label={a.fields.eraseBackend}
                dirtyKey="erase_backend"
                value={config.erase_backend ?? 'sttn'}
                options={[
                  { value: 'sttn', label: a.opts.eraseSttn },
                  { value: 'lama', label: a.opts.eraseLama },
                ]}
                onChange={value => onPatch({ erase_backend: value as TaskConfig['erase_backend'] })}
              />
              <SettingsSelect
                label={a.fields.eraseDevice}
                dirtyKey="erase_device"
                value={config.erase_device ?? 'auto'}
                options={[
                  { value: 'auto', label: 'auto' },
                  { value: 'mps', label: 'mps (Apple)' },
                  { value: 'cuda', label: 'cuda' },
                  { value: 'cpu', label: 'cpu' },
                ]}
                onChange={value => onPatch({ erase_device: value as TaskConfig['erase_device'] })}
              />
            </StagePanel>

            <StagePanel
              title={a.stages.translationTitle}
              description={a.stages.translationDesc}
              advancedCount={4}
              advanced={
                <>
                  <SettingsNumber
                    label={a.fields.translationBatch}
                    dirtyKey="translation_batch_size"
                    value={config.translation_batch_size ?? 4}
                    min={1}
                    step={1}
                    onChange={value => onPatch({ translation_batch_size: value })}
                  />
                  <SettingsText
                    label={a.fields.deepseekModel}
                    dirtyKey="deepseek_model"
                    value={config.deepseek_model ?? ''}
                    placeholder="deepseek-v4-pro"
                    onChange={value => onPatch({ deepseek_model: value || null })}
                  />
                  <SettingsText
                    label={a.fields.deepseekBaseUrl}
                    dirtyKey="deepseek_base_url"
                    value={config.deepseek_base_url ?? ''}
                    placeholder="https://api.deepseek.com"
                    onChange={value => onPatch({ deepseek_base_url: value || null })}
                  />
                  <SettingsSelect
                    label={a.fields.correction}
                    dirtyKey="transcription_correction"
                    value={config.transcription_correction?.llm_arbitration ?? 'off'}
                    options={[
                      { value: 'off', label: a.opts.correctionOff },
                      { value: 'deepseek', label: 'DeepSeek V4 Pro' },
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
                          llm_arbitration: value as 'off' | 'deepseek',
                        },
                      })
                    }
                  />
                </>
              }
              {...stageProps('translation')}
            >
              <SettingsSelect
                label={a.fields.translationBackend}
                dirtyKey="translation_backend"
                value={config.translation_backend ?? 'local-m2m100'}
                options={[
                  { value: 'local-m2m100', label: 'local-m2m100' },
                  { value: 'deepseek', label: 'DeepSeek API' },
                ]}
                onChange={value => onPatch({ translation_backend: value })}
              />
              <SettingsSelect
                label={a.fields.condense}
                dirtyKey="condense_mode"
                value={config.condense_mode ?? 'off'}
                options={[
                  { value: 'off', label: 'off' },
                  { value: 'smart', label: 'smart' },
                  { value: 'aggressive', label: 'aggressive' },
                ]}
                onChange={value => onPatch({ condense_mode: value })}
              />
            </StagePanel>

            <StagePanel
              title={a.stages.dubbingTitle}
              description={a.stages.dubbingDesc}
              advancedCount={5}
              advanced={
                <>
                  <SettingsOptionalNumber
                    label={a.fields.dubbingWorkers}
                    dirtyKey="dubbing_workers"
                    value={config.dubbing_workers}
                    min={1}
                    step={1}
                    onChange={value => onPatch({ dubbing_workers: value })}
                  />
                  <SettingsField label={a.fields.repairBackend} dirtyKey="dub_repair_backend">
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
                  <SettingsNumber label={a.fields.repairMaxItems} dirtyKey="dub_repair_max_items" value={config.dub_repair_max_items ?? 12} min={1} step={1} onChange={value => onPatch({ dub_repair_max_items: value })} />
                  <SettingsNumber label={a.fields.repairAttempts} dirtyKey="dub_repair_attempts_per_item" value={config.dub_repair_attempts_per_item ?? 3} min={1} step={1} onChange={value => onPatch({ dub_repair_attempts_per_item: value })} />
                  <SettingsField label={a.fields.riskPolicy} dirtyKey="dub_repair_include_risk">
                    <SettingsCheckbox
                      label={a.checks.allowRisk}
                      checked={config.dub_repair_include_risk ?? false}
                      onChange={value => onPatch({ dub_repair_include_risk: value })}
                    />
                  </SettingsField>
                </>
              }
              {...stageProps('dubbing')}
            >
              <SettingsSelect
                label={a.fields.ttsBackend}
                dirtyKey="tts_backend"
                value={config.tts_backend ?? 'moss-tts-nano-onnx'}
                options={DUBBING_BACKEND_OPTIONS}
                onChange={value => onPatch({ tts_backend: value })}
              />
              <SettingsSelect
                label={a.fields.qualityCheck}
                dirtyKey="dubbing_quality_check"
                value={config.dubbing_quality_check ?? 'standard'}
                options={[
                  { value: 'standard', label: a.opts.qualityStandard },
                  { value: 'duration-only', label: a.opts.qualityDraft },
                ]}
                onChange={value => onPatch({ dubbing_quality_check: value as TaskConfig['dubbing_quality_check'] })}
              />
              <SettingsField label={a.fields.dubRepair} dirtyKey="dub_repair_enabled">
                <SettingsCheckbox
                  label={a.checks.enableRepair}
                  checked={config.dub_repair_enabled ?? false}
                  onChange={value => onPatch({ dub_repair_enabled: value })}
                />
              </SettingsField>
            </StagePanel>

            <StagePanel
              title={a.stages.mixingTitle}
              description={a.stages.mixingDesc}
              advancedCount={5}
              advanced={
                <>
                  <SettingsSelect
                    label={a.fields.fitBackend}
                    dirtyKey="fit_backend"
                    value={config.fit_backend ?? 'atempo'}
                    options={[
                      { value: 'atempo', label: 'atempo' },
                      { value: 'rubberband', label: 'rubberband' },
                    ]}
                    onChange={value => onPatch({ fit_backend: value })}
                  />
                  <SettingsSelect
                    label={a.fields.duckingMode}
                    dirtyKey="ducking_mode"
                    value={config.ducking_mode ?? 'static'}
                    options={[
                      { value: 'static', label: 'static' },
                      { value: 'sidechain', label: 'sidechain' },
                    ]}
                    onChange={value => onPatch({ ducking_mode: value })}
                  />
                  <SettingsNumber label={a.fields.backgroundGain} dirtyKey="background_gain_db" value={config.background_gain_db ?? -8} min={-60} step={0.5} onChange={value => onPatch({ background_gain_db: value })} />
                  <SettingsNumber label={a.fields.windowDucking} dirtyKey="window_ducking_db" value={config.window_ducking_db ?? -3} min={-60} step={0.5} onChange={value => onPatch({ window_ducking_db: value })} />
                  <SettingsNumber label={a.fields.maxCompress} dirtyKey="max_compress_ratio" value={config.max_compress_ratio ?? 1.45} min={0.1} step={0.05} onChange={value => onPatch({ max_compress_ratio: value })} />
                </>
              }
              {...stageProps('mixing')}
            >
              <SettingsSelect
                label={a.fields.fitPolicy}
                dirtyKey="fit_policy"
                value={config.fit_policy ?? 'conservative'}
                options={[
                  { value: 'conservative', label: 'conservative' },
                  { value: 'high_quality', label: 'high_quality' },
                ]}
                onChange={value => onPatch({ fit_policy: value })}
              />
              <SettingsSelect
                label={a.fields.mixProfile}
                dirtyKey="mix_profile"
                value={config.mix_profile ?? 'preview'}
                options={[
                  { value: 'preview', label: 'preview' },
                  { value: 'enhanced', label: 'enhanced' },
                ]}
                onChange={value => onPatch({ mix_profile: value })}
              />
            </StagePanel>

            <StagePanel
              title={a.stages.deliveryTitle}
              description={a.stages.deliveryDesc}
              advancedCount={subtitleMode !== 'none' ? 3 : 0}
              advanced={
                subtitleMode !== 'none' ? (
                  <>
                    <SettingsColor
                      label={a.fields.outlineColor}
                      dirtyKey="subtitle_outline_color"
                      value={config.subtitle_outline_color ?? '#000000'}
                      onChange={value => onPatch({ subtitle_outline_color: value })}
                    />
                    <SettingsNumber
                      label={a.fields.outlineWidth}
                      dirtyKey="subtitle_outline_width"
                      value={config.subtitle_outline_width ?? 2}
                      min={0}
                      step={0.5}
                      onChange={value => onPatch({ subtitle_outline_width: value })}
                    />
                    <SettingsNumber
                      label={a.fields.marginV}
                      dirtyKey="subtitle_margin_v"
                      value={config.subtitle_margin_v ?? 0}
                      min={0}
                      step={1}
                      onChange={value => onPatch({ subtitle_margin_v: value })}
                    />
                  </>
                ) : null
              }
              {...stageProps('delivery')}
            >
              <SettingsSelect
                label={a.fields.subtitleMode}
                dirtyKey="subtitle_mode"
                value={subtitleMode}
                options={[
                  { value: 'none', label: a.opts.subNone },
                  { value: 'chinese_only', label: a.opts.subZh },
                  { value: 'english_only', label: a.opts.subEn },
                  { value: 'bilingual', label: a.opts.subBi },
                ]}
                onChange={value => onPatch({ subtitle_mode: value as TaskConfig['subtitle_mode'] })}
              />
              <SettingsSelect
                label={a.fields.renderSource}
                dirtyKey="subtitle_render_source"
                value={config.subtitle_render_source ?? 'ocr'}
                options={[
                  { value: 'ocr', label: a.opts.renderOcr },
                  { value: 'asr', label: a.opts.renderAsr },
                ]}
                onChange={value => onPatch({ subtitle_render_source: value as TaskConfig['subtitle_render_source'] })}
              />
              {subtitleMode !== 'none' && (
                <>
                  <SettingsText
                    label={a.fields.subtitleFont}
                    dirtyKey="subtitle_font"
                    value={config.subtitle_font ?? ''}
                    placeholder="Noto Sans / Source Han Sans"
                    onChange={value => onPatch({ subtitle_font: value || null })}
                  />
                  <SettingsNumber
                    label={a.fields.fontSize}
                    dirtyKey="subtitle_font_size"
                    value={config.subtitle_font_size ?? 0}
                    min={0}
                    step={1}
                    onChange={value => onPatch({ subtitle_font_size: value })}
                  />
                  <SettingsColor
                    label={a.fields.subtitleColor}
                    dirtyKey="subtitle_color"
                    value={config.subtitle_color ?? '#FFFFFF'}
                    onChange={value => onPatch({ subtitle_color: value })}
                  />
                  <SettingsSelect
                    label={a.fields.subtitlePosition}
                    dirtyKey="subtitle_position"
                    value={config.subtitle_position ?? 'bottom'}
                    options={[
                      { value: 'bottom', label: a.opts.posBottom },
                      { value: 'top', label: a.opts.posTop },
                    ]}
                    onChange={value => onPatch({ subtitle_position: value as TaskConfig['subtitle_position'] })}
                  />
                  <SettingsField label={a.fields.bold} dirtyKey="subtitle_bold">
                    <SettingsCheckbox
                      label={a.checks.boldText}
                      checked={config.subtitle_bold ?? false}
                      onChange={value => onPatch({ subtitle_bold: value })}
                    />
                  </SettingsField>
                </>
              )}
              {subtitleMode === 'bilingual' && (
                <>
                  <SettingsSelect
                    label={a.fields.biZhPos}
                    dirtyKey="bilingual_chinese_position"
                    value={config.bilingual_chinese_position ?? 'bottom'}
                    options={[
                      { value: 'bottom', label: a.opts.posBottom },
                      { value: 'top', label: a.opts.posTop },
                    ]}
                    onChange={value => onPatch({ bilingual_chinese_position: value as TaskConfig['bilingual_chinese_position'] })}
                  />
                  <SettingsSelect
                    label={a.fields.biEnPos}
                    dirtyKey="bilingual_english_position"
                    value={config.bilingual_english_position ?? 'top'}
                    options={[
                      { value: 'bottom', label: a.opts.posBottom },
                      { value: 'top', label: a.opts.posTop },
                    ]}
                    onChange={value => onPatch({ bilingual_english_position: value as TaskConfig['bilingual_english_position'] })}
                  />
                </>
              )}
            </StagePanel>
          </div>
        </div>

        <p className="mt-6 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-400">{a.footer}</p>
      </div>
    </ChangedKeysContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Stage detail panel (kept mounted; hidden when not the active rail item) +
// per-stage advanced reveal.
// ---------------------------------------------------------------------------

function StagePanel({
  active,
  title,
  description,
  canReset,
  onReset,
  advanced,
  advancedCount = 0,
  children,
}: {
  active: boolean
  title: string
  description: string
  canReset: boolean
  onReset: () => void
  advanced?: ReactNode
  advancedCount?: number
  children: ReactNode
}) {
  const { t } = useI18n()
  return (
    <div className={active ? 'block' : 'hidden'}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
        </div>
        {canReset && (
          <button
            type="button"
            onClick={onReset}
            className="mt-0.5 flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
          >
            <RotateCcw size={13} />
            {t.settings.advanced.restoreDefault}
          </button>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
      <AdvancedReveal count={advancedCount}>{advanced}</AdvancedReveal>
    </div>
  )
}

function AdvancedReveal({ count, children }: { count: number; children?: ReactNode }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  if (count <= 0) return null
  return (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        className="flex items-center gap-1.5 text-xs font-medium text-slate-500 transition-colors hover:text-slate-700"
      >
        <ChevronDown size={14} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        {open ? t.settings.advanced.advancedHide : t.settings.advanced.advancedShow(count)}
      </button>
      <div className={open ? 'mt-3 grid gap-4 md:grid-cols-2' : 'hidden'}>{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Field controls
// ---------------------------------------------------------------------------

function SettingsField({ label, dirtyKey, children }: { label: string; dirtyKey?: string; children: ReactNode }) {
  return (
    <div>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
      {children}
    </div>
  )
}

function SettingsSelect({
  label,
  dirtyKey,
  value,
  options,
  onChange,
}: {
  label: string
  dirtyKey?: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
}) {
  return (
    <label>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
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
  dirtyKey,
  value,
  placeholder,
  onChange,
}: {
  label: string
  dirtyKey?: string
  value: string
  placeholder?: string
  onChange: (value: string) => void
}) {
  return (
    <label>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
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

function SettingsColor({
  label,
  dirtyKey,
  value,
  onChange,
}: {
  label: string
  dirtyKey?: string
  value: string
  onChange: (value: string) => void
}) {
  const { t } = useI18n()
  return (
    <label>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} ${t.settings.advanced.colorPicker}`}
          value={value}
          onChange={event => onChange(event.target.value)}
          className="h-9 w-12 shrink-0 cursor-pointer rounded-lg border border-slate-200 bg-white p-1"
        />
        <input
          type="text"
          aria-label={label}
          value={value}
          onChange={event => onChange(event.target.value)}
          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
        />
      </div>
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
  dirtyKey,
  value,
  min,
  step,
  onChange,
}: {
  label: string
  dirtyKey?: string
  value: number
  min: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
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
  dirtyKey,
  value,
  min,
  step,
  onChange,
}: {
  label: string
  dirtyKey?: string
  value?: number | null
  min: number
  step: number
  onChange: (value: number | null) => void
}) {
  return (
    <label>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
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
