import { createContext, useContext, useState } from 'react'
import type { ReactNode } from 'react'
import { ChevronDown, RotateCcw } from 'lucide-react'
import { DUBBING_BACKEND_OPTIONS } from '../../lib/dubbingBackends'
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
  const dirty = useFieldDirty(dirtyKey)
  return (
    <span className="mb-1.5 flex items-center gap-1.5 text-sm font-medium text-slate-700">
      <span>{label}</span>
      {dirty && (
        <span
          aria-hidden
          title="未保存改动"
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
  const [activeStage, setActiveStage] = useState<string>(ADVANCED_GROUPS[0].id)
  const repairBackends = config.dub_repair_backend ?? []
  const asrBackend = config.asr_backend ?? 'faster-whisper'
  const asrModelOptions = asrBackend === 'funasr' ? FUNASR_MODEL_OPTIONS : FASTER_WHISPER_MODEL_OPTIONS
  const asrModelValue = asrModelOptions.some(option => option.value === config.asr_model)
    ? String(config.asr_model)
    : asrModelOptions[0].value
  const subtitleMode = config.subtitle_mode ?? 'none'

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
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-400">节点高级参数</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              这些参数会作为新建任务的默认值，按节点影响分离、转写、翻译、配音、混音和交付结果；新建任务时仍可逐项覆盖。左侧选阶段，深度调参收在每个阶段的「高级选项」里。
            </p>
          </div>
          {saved && <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">已保存</span>}
        </div>

        <div className="flex flex-col gap-4 md:flex-row md:gap-6">
          <nav
            aria-label="参数分组"
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
                  <span className="truncate">{stage.title}</span>
                  {count > 0 && (
                    <span className="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">{count}</span>
                  )}
                </button>
              )
            })}
          </nav>

          <div className="min-w-0 flex-1">
            <StagePanel
              title="音频分离"
              description="Stage 1 从视频中提取人声和背景音，影响后续转写和混音素材。"
              advancedCount={1}
              advanced={
                <SettingsSelect
                  label="Stage 1 输出格式"
                  dirtyKey="stage1_output_format"
                  value={config.stage1_output_format ?? 'mp3'}
                  options={['mp3', 'wav', 'flac', 'aac', 'opus'].map(value => ({ value, label: value }))}
                  onChange={value => onPatch({ stage1_output_format: value })}
                />
              }
              {...stageProps('separation')}
            >
              <SettingsSelect
                label="分离模式"
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
                label="分离质量"
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
              title="语音转写"
              description="Task A 生成带说话人和时间轴的字幕文本。"
              advancedCount={6}
              advanced={
                <>
                  <SettingsField label="VAD" dirtyKey="vad_filter">
                    <SettingsCheckbox
                      label="启用 VAD"
                      checked={config.vad_filter ?? true}
                      onChange={value => onPatch({ vad_filter: value })}
                    />
                  </SettingsField>
                  <SettingsNumber
                    label="VAD 最小静音毫秒"
                    dirtyKey="vad_min_silence_duration_ms"
                    value={config.vad_min_silence_duration_ms ?? 400}
                    min={1}
                    step={50}
                    onChange={value => onPatch({ vad_min_silence_duration_ms: value })}
                  />
                  <SettingsNumber label="Beam Size" dirtyKey="beam_size" value={config.beam_size ?? 5} min={1} step={1} onChange={value => onPatch({ beam_size: value })} />
                  <SettingsNumber label="Best Of" dirtyKey="best_of" value={config.best_of ?? 5} min={1} step={1} onChange={value => onPatch({ best_of: value })} />
                  <SettingsNumber label="Temperature" dirtyKey="temperature" value={config.temperature ?? 0} min={0} step={0.1} onChange={value => onPatch({ temperature: value })} />
                  <SettingsField label="上下文" dirtyKey="condition_on_previous_text">
                    <SettingsCheckbox
                      label="使用前文上下文"
                      checked={config.condition_on_previous_text ?? false}
                      onChange={value => onPatch({ condition_on_previous_text: value })}
                    />
                  </SettingsField>
                </>
              }
              {...stageProps('transcription')}
            >
              <SettingsSelect label="ASR 后端" dirtyKey="asr_backend" value={asrBackend} options={ASR_BACKEND_OPTIONS} onChange={patchAsrBackend} />
              <SettingsSelect label="ASR 模型" dirtyKey="asr_model" value={asrModelValue} options={asrModelOptions} onChange={value => onPatch({ asr_model: value })} />
              <SettingsField label="说话人分离" dirtyKey="enable_diarization">
                <SettingsCheckbox
                  label="启用说话人分离"
                  checked={config.enable_diarization ?? true}
                  onChange={value => onPatch({ enable_diarization: value })}
                />
              </SettingsField>
              <SettingsSelect
                label="说话人后端"
                dirtyKey="diarizer_backend"
                value={config.diarizer_backend ?? 'ecapa'}
                options={DIARIZER_BACKEND_OPTIONS}
                onChange={value => onPatch({ diarizer_backend: value as TaskConfig['diarizer_backend'] })}
              />
              <SettingsField label="生成 SRT" dirtyKey="generate_srt">
                <SettingsCheckbox
                  label="生成 SRT 字幕文件"
                  checked={config.generate_srt ?? true}
                  onChange={value => onPatch({ generate_srt: value })}
                />
              </SettingsField>
            </StagePanel>

            <StagePanel
              title="说话人匹配"
              description="Task B 生成角色/说话人画像并匹配历史声纹。"
              {...stageProps('matching')}
            >
              <SettingsNumber
                label="说话人候选数 Top K"
                dirtyKey="top_k"
                value={config.top_k ?? 3}
                min={1}
                step={1}
                onChange={value => onPatch({ top_k: value })}
              />
            </StagePanel>

            <StagePanel
              title="OCR 字幕识别"
              description="ocr-detect 节点用 PaddleOCR 识别原片硬字幕（仅 +OCR 字幕模板生效），影响字幕翻译与擦除的输入。"
              {...stageProps('ocr')}
            >
              <SettingsNumber
                label="采样间隔 (秒)"
                dirtyKey="ocr_sample_interval"
                value={config.ocr_sample_interval ?? 0.25}
                min={0.1}
                step={0.05}
                onChange={value => onPatch({ ocr_sample_interval: value })}
              />
              <SettingsSelect
                label="字幕位置"
                dirtyKey="ocr_position_mode"
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
                dirtyKey="ocr_extraction_mode"
                value={config.ocr_extraction_mode ?? 'conservative'}
                options={[
                  { value: 'conservative', label: '保守（高精度）' },
                  { value: 'balanced', label: '均衡' },
                  { value: 'variety_recall', label: '高召回' },
                ]}
                onChange={value => onPatch({ ocr_extraction_mode: value as TaskConfig['ocr_extraction_mode'] })}
              />
            </StagePanel>

            <StagePanel
              title="字幕擦除"
              description="subtitle-erase 节点用 OCR 检测框对原片硬字幕做视频修复（仅 +字幕擦除 模板生效）。掩码膨胀越大越能消除残留但易溢出；邻域/参考步长仅 STTN 后端生效。"
              advancedCount={7}
              advanced={
                <>
                  <SettingsNumber label="掩码横向膨胀 (px)" dirtyKey="erase_mask_dilate_x" value={config.erase_mask_dilate_x ?? 12} min={0} step={1} onChange={value => onPatch({ erase_mask_dilate_x: value })} />
                  <SettingsNumber label="掩码纵向膨胀 (px)" dirtyKey="erase_mask_dilate_y" value={config.erase_mask_dilate_y ?? 8} min={0} step={1} onChange={value => onPatch({ erase_mask_dilate_y: value })} />
                  <SettingsNumber label="事件提前帧（淡入）" dirtyKey="erase_event_lead_frames" value={config.erase_event_lead_frames ?? 3} min={0} step={1} onChange={value => onPatch({ erase_event_lead_frames: value })} />
                  <SettingsNumber label="事件延后帧（淡出）" dirtyKey="erase_event_trail_frames" value={config.erase_event_trail_frames ?? 8} min={0} step={1} onChange={value => onPatch({ erase_event_trail_frames: value })} />
                  <SettingsNumber label="STTN 邻域步长" dirtyKey="erase_neighbor_stride" value={config.erase_neighbor_stride ?? 5} min={1} step={1} onChange={value => onPatch({ erase_neighbor_stride: value })} />
                  <SettingsNumber label="STTN 参考帧步长" dirtyKey="erase_reference_length" value={config.erase_reference_length ?? 10} min={1} step={1} onChange={value => onPatch({ erase_reference_length: value })} />
                  <SettingsNumber label="单批最大帧数" dirtyKey="erase_max_load" value={config.erase_max_load ?? 50} min={1} step={1} onChange={value => onPatch({ erase_max_load: value })} />
                </>
              }
              {...stageProps('erase')}
            >
              <SettingsSelect
                label="擦除后端"
                dirtyKey="erase_backend"
                value={config.erase_backend ?? 'sttn'}
                options={[
                  { value: 'sttn', label: 'STTN（时序修复，默认）' },
                  { value: 'lama', label: 'LaMa（单帧最锐，较慢）' },
                ]}
                onChange={value => onPatch({ erase_backend: value as TaskConfig['erase_backend'] })}
              />
              <SettingsSelect
                label="计算设备"
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
              title="翻译"
              description="Task C 翻译配音脚本；OCR 字幕翻译也复用这些后端设置。"
              advancedCount={4}
              advanced={
                <>
                  <SettingsNumber
                    label="翻译批量大小"
                    dirtyKey="translation_batch_size"
                    value={config.translation_batch_size ?? 4}
                    min={1}
                    step={1}
                    onChange={value => onPatch({ translation_batch_size: value })}
                  />
                  <SettingsText
                    label="DeepSeek 模型"
                    dirtyKey="deepseek_model"
                    value={config.deepseek_model ?? ''}
                    placeholder="deepseek-v4-pro"
                    onChange={value => onPatch({ deepseek_model: value || null })}
                  />
                  <SettingsText
                    label="DeepSeek API 地址"
                    dirtyKey="deepseek_base_url"
                    value={config.deepseek_base_url ?? ''}
                    placeholder="https://api.deepseek.com"
                    onChange={value => onPatch({ deepseek_base_url: value || null })}
                  />
                  <SettingsSelect
                    label="文稿校正 LLM 仲裁"
                    dirtyKey="transcription_correction"
                    value={config.transcription_correction?.llm_arbitration ?? 'off'}
                    options={[
                      { value: 'off', label: '关闭' },
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
                label="翻译后端"
                dirtyKey="translation_backend"
                value={config.translation_backend ?? 'local-m2m100'}
                options={[
                  { value: 'local-m2m100', label: 'local-m2m100' },
                  { value: 'deepseek', label: 'DeepSeek API' },
                ]}
                onChange={value => onPatch({ translation_backend: value })}
              />
              <SettingsSelect
                label="译文压缩"
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
              title="配音"
              description="Task D 合成每位说话人的目标语言音频，并可启用修复重试。"
              advancedCount={5}
              advanced={
                <>
                  <SettingsOptionalNumber
                    label="配音并发数"
                    dirtyKey="dubbing_workers"
                    value={config.dubbing_workers}
                    min={1}
                    step={1}
                    onChange={value => onPatch({ dubbing_workers: value })}
                  />
                  <SettingsField label="修复后端" dirtyKey="dub_repair_backend">
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
                  <SettingsNumber label="修复最大条数" dirtyKey="dub_repair_max_items" value={config.dub_repair_max_items ?? 12} min={1} step={1} onChange={value => onPatch({ dub_repair_max_items: value })} />
                  <SettingsNumber label="修复每条尝试次数" dirtyKey="dub_repair_attempts_per_item" value={config.dub_repair_attempts_per_item ?? 3} min={1} step={1} onChange={value => onPatch({ dub_repair_attempts_per_item: value })} />
                  <SettingsField label="风险策略" dirtyKey="dub_repair_include_risk">
                    <SettingsCheckbox
                      label="允许修复风险段落"
                      checked={config.dub_repair_include_risk ?? false}
                      onChange={value => onPatch({ dub_repair_include_risk: value })}
                    />
                  </SettingsField>
                </>
              }
              {...stageProps('dubbing')}
            >
              <SettingsSelect
                label="TTS 后端"
                dirtyKey="tts_backend"
                value={config.tts_backend ?? 'moss-tts-nano-onnx'}
                options={DUBBING_BACKEND_OPTIONS}
                onChange={value => onPatch({ tts_backend: value })}
              />
              <SettingsSelect
                label="配音质检"
                dirtyKey="dubbing_quality_check"
                value={config.dubbing_quality_check ?? 'standard'}
                options={[
                  { value: 'standard', label: '完整质检' },
                  { value: 'duration-only', label: '快速草稿' },
                ]}
                onChange={value => onPatch({ dubbing_quality_check: value as TaskConfig['dubbing_quality_check'] })}
              />
              <SettingsField label="配音修复" dirtyKey="dub_repair_enabled">
                <SettingsCheckbox
                  label="启用配音修复"
                  checked={config.dub_repair_enabled ?? false}
                  onChange={value => onPatch({ dub_repair_enabled: value })}
                />
              </SettingsField>
            </StagePanel>

            <StagePanel
              title="混音与时间轴"
              description="Task E 对齐配音时长、混合背景音并生成预览/成片音轨。"
              advancedCount={5}
              advanced={
                <>
                  <SettingsSelect
                    label="时间伸缩后端"
                    dirtyKey="fit_backend"
                    value={config.fit_backend ?? 'atempo'}
                    options={[
                      { value: 'atempo', label: 'atempo' },
                      { value: 'rubberband', label: 'rubberband' },
                    ]}
                    onChange={value => onPatch({ fit_backend: value })}
                  />
                  <SettingsSelect
                    label="压低背景模式"
                    dirtyKey="ducking_mode"
                    value={config.ducking_mode ?? 'static'}
                    options={[
                      { value: 'static', label: 'static' },
                      { value: 'sidechain', label: 'sidechain' },
                    ]}
                    onChange={value => onPatch({ ducking_mode: value })}
                  />
                  <SettingsNumber label="背景音量 dB" dirtyKey="background_gain_db" value={config.background_gain_db ?? -8} min={-60} step={0.5} onChange={value => onPatch({ background_gain_db: value })} />
                  <SettingsNumber label="窗口压低 dB" dirtyKey="window_ducking_db" value={config.window_ducking_db ?? -3} min={-60} step={0.5} onChange={value => onPatch({ window_ducking_db: value })} />
                  <SettingsNumber label="最大压缩比例" dirtyKey="max_compress_ratio" value={config.max_compress_ratio ?? 1.45} min={0.1} step={0.05} onChange={value => onPatch({ max_compress_ratio: value })} />
                </>
              }
              {...stageProps('mixing')}
            >
              <SettingsSelect
                label="时间伸缩策略"
                dirtyKey="fit_policy"
                value={config.fit_policy ?? 'conservative'}
                options={[
                  { value: 'conservative', label: 'conservative' },
                  { value: 'high_quality', label: 'high_quality' },
                ]}
                onChange={value => onPatch({ fit_policy: value })}
              />
              <SettingsSelect
                label="混音配置"
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
              title="导出与字幕"
              description="Task G 交付视频、字幕叠加和双语字幕布局默认值。字幕模式选「无字幕」以外时显示样式选项。"
              advancedCount={subtitleMode !== 'none' ? 3 : 0}
              advanced={
                subtitleMode !== 'none' ? (
                  <>
                    <SettingsColor
                      label="描边颜色"
                      dirtyKey="subtitle_outline_color"
                      value={config.subtitle_outline_color ?? '#000000'}
                      onChange={value => onPatch({ subtitle_outline_color: value })}
                    />
                    <SettingsNumber
                      label="描边宽度"
                      dirtyKey="subtitle_outline_width"
                      value={config.subtitle_outline_width ?? 2}
                      min={0}
                      step={0.5}
                      onChange={value => onPatch({ subtitle_outline_width: value })}
                    />
                    <SettingsNumber
                      label="垂直边距"
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
                label="成品字幕模式"
                dirtyKey="subtitle_mode"
                value={subtitleMode}
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
                dirtyKey="subtitle_render_source"
                value={config.subtitle_render_source ?? 'ocr'}
                options={[
                  { value: 'ocr', label: 'OCR 字幕' },
                  { value: 'asr', label: 'ASR 字幕' },
                ]}
                onChange={value => onPatch({ subtitle_render_source: value as TaskConfig['subtitle_render_source'] })}
              />
              {subtitleMode !== 'none' && (
                <>
                  <SettingsText
                    label="字幕字体"
                    dirtyKey="subtitle_font"
                    value={config.subtitle_font ?? ''}
                    placeholder="Noto Sans / Source Han Sans"
                    onChange={value => onPatch({ subtitle_font: value || null })}
                  />
                  <SettingsNumber
                    label="字号 (0=自动)"
                    dirtyKey="subtitle_font_size"
                    value={config.subtitle_font_size ?? 0}
                    min={0}
                    step={1}
                    onChange={value => onPatch({ subtitle_font_size: value })}
                  />
                  <SettingsColor
                    label="字幕颜色"
                    dirtyKey="subtitle_color"
                    value={config.subtitle_color ?? '#FFFFFF'}
                    onChange={value => onPatch({ subtitle_color: value })}
                  />
                  <SettingsSelect
                    label="字幕位置"
                    dirtyKey="subtitle_position"
                    value={config.subtitle_position ?? 'bottom'}
                    options={[
                      { value: 'bottom', label: '底部' },
                      { value: 'top', label: '顶部' },
                    ]}
                    onChange={value => onPatch({ subtitle_position: value as TaskConfig['subtitle_position'] })}
                  />
                  <SettingsField label="字幕加粗" dirtyKey="subtitle_bold">
                    <SettingsCheckbox
                      label="加粗"
                      checked={config.subtitle_bold ?? false}
                      onChange={value => onPatch({ subtitle_bold: value })}
                    />
                  </SettingsField>
                </>
              )}
              {subtitleMode === 'bilingual' && (
                <>
                  <SettingsSelect
                    label="双语·中文位置"
                    dirtyKey="bilingual_chinese_position"
                    value={config.bilingual_chinese_position ?? 'bottom'}
                    options={[
                      { value: 'bottom', label: '底部' },
                      { value: 'top', label: '顶部' },
                    ]}
                    onChange={value => onPatch({ bilingual_chinese_position: value as TaskConfig['bilingual_chinese_position'] })}
                  />
                  <SettingsSelect
                    label="双语·英文位置"
                    dirtyKey="bilingual_english_position"
                    value={config.bilingual_english_position ?? 'top'}
                    options={[
                      { value: 'bottom', label: '底部' },
                      { value: 'top', label: '顶部' },
                    ]}
                    onChange={value => onPatch({ bilingual_english_position: value as TaskConfig['bilingual_english_position'] })}
                  />
                </>
              )}
            </StagePanel>
          </div>
        </div>

        <p className="mt-6 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-400">
          改动后下方会出现保存条；保存即作为新建任务默认值。每个阶段可单独「恢复默认」。
        </p>
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
            恢复默认
          </button>
        )}
      </div>
      <div className="grid gap-4 md:grid-cols-2">{children}</div>
      <AdvancedReveal count={advancedCount}>{advanced}</AdvancedReveal>
    </div>
  )
}

function AdvancedReveal({ count, children }: { count: number; children?: ReactNode }) {
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
        {open ? '收起高级选项' : `高级选项（${count}）`}
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
  return (
    <label>
      <FieldLabelText label={label} dirtyKey={dirtyKey} />
      <div className="flex items-center gap-2">
        <input
          type="color"
          aria-label={`${label} 取色器`}
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
