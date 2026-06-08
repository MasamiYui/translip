import type { GlobalConfigUpdate } from '../../api/config'

export type GlobalConfigDraft = GlobalConfigUpdate

// Static registry of advanced groups and the config keys each owns. Drives both
// the unsaved-change counters/badges and per-group "restore defaults".
export const ADVANCED_GROUPS: { id: string; title: string; keys: (keyof GlobalConfigDraft)[] }[] = [
  { id: 'separation', title: '音频分离', keys: ['separation_mode', 'separation_quality', 'stage1_output_format'] },
  {
    id: 'transcription',
    title: '语音转写',
    keys: [
      'asr_backend',
      'asr_model',
      'enable_diarization',
      'diarizer_backend',
      'generate_srt',
      'transcription_correction',
      'vad_filter',
      'vad_min_silence_duration_ms',
      'beam_size',
      'best_of',
      'temperature',
      'condition_on_previous_text',
    ],
  },
  { id: 'matching', title: '说话人匹配', keys: ['top_k'] },
  { id: 'ocr', title: 'OCR 字幕识别', keys: ['ocr_sample_interval', 'ocr_position_mode', 'ocr_extraction_mode'] },
  {
    id: 'erase',
    title: '字幕擦除',
    keys: [
      'erase_backend',
      'erase_device',
      'erase_mask_dilate_x',
      'erase_mask_dilate_y',
      'erase_event_lead_frames',
      'erase_event_trail_frames',
      'erase_neighbor_stride',
      'erase_reference_length',
      'erase_max_load',
    ],
  },
  {
    id: 'translation',
    title: '翻译',
    keys: ['translation_backend', 'translation_batch_size', 'condense_mode', 'deepseek_model'],
  },
  {
    id: 'dubbing',
    title: '配音',
    keys: [
      'tts_backend',
      'dubbing_workers',
      'dubbing_quality_check',
      'dub_repair_enabled',
      'dub_repair_backend',
      'dub_repair_max_items',
      'dub_repair_attempts_per_item',
      'dub_repair_include_risk',
    ],
  },
  {
    id: 'mixing',
    title: '混音与时间轴',
    keys: ['fit_policy', 'fit_backend', 'mix_profile', 'ducking_mode', 'background_gain_db', 'window_ducking_db', 'max_compress_ratio'],
  },
  {
    id: 'delivery',
    title: '导出与字幕',
    keys: [
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
    ],
  },
]

export const ADVANCED_KEYS: (keyof GlobalConfigDraft)[] = ADVANCED_GROUPS.flatMap(group => group.keys)

export const keysOf = (id: string): (keyof GlobalConfigDraft)[] =>
  ADVANCED_GROUPS.find(group => group.id === id)?.keys ?? []

/** Structural equality good enough for config values (primitives, arrays, plain objects). */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a === null || b === null || a === undefined || b === undefined) return a === b
  if (typeof a !== 'object' || typeof b !== 'object') return false
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false
    return a.every((item, index) => deepEqual(item, b[index]))
  }
  const ao = a as Record<string, unknown>
  const bo = b as Record<string, unknown>
  const aKeys = Object.keys(ao)
  const bKeys = Object.keys(bo)
  if (aKeys.length !== bKeys.length) return false
  return aKeys.every(key => deepEqual(ao[key], bo[key]))
}

/** Keys whose draft value differs from the saved baseline — drives the unsaved-change UI. */
export function computeChangedAdvancedKeys(config: GlobalConfigDraft, baseline: GlobalConfigDraft): Set<string> {
  const changed = new Set<string>()
  for (const key of ADVANCED_KEYS) {
    if (!deepEqual(config[key], baseline[key])) changed.add(key)
  }
  return changed
}
