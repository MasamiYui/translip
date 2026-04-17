import type {
  TaskExportProfile,
  TaskExportReadinessStatus,
  TaskOutputIntent,
  TaskQualityPreset,
} from '../types'
import type { Locale } from '../i18n/messages'

const outputIntentLabels = {
  'zh-CN': {
    dub_final: '英文配音成片',
    bilingual_review: '中英双语审片版',
    english_subtitle: '英文字幕版',
    fast_validation: '快速验证版',
  },
  'en-US': {
    dub_final: 'English Dub Master',
    bilingual_review: 'Bilingual Review',
    english_subtitle: 'English Subtitle',
    fast_validation: 'Fast Validation',
  },
} as const

const qualityLabels = {
  'zh-CN': {
    fast: '快速',
    standard: '标准',
    high_quality: '高质量',
  },
  'en-US': {
    fast: 'Fast',
    standard: 'Standard',
    high_quality: 'High Quality',
  },
} as const

const exportProfileLabels = {
  'zh-CN': {
    dub_no_subtitles: '无字幕配音版',
    bilingual_review: '中英双语版',
    english_subtitle_burned: '英文字幕版',
    preview_only: '预览版',
  },
  'en-US': {
    dub_no_subtitles: 'Dub Only',
    bilingual_review: 'Bilingual Review',
    english_subtitle_burned: 'English Subtitle',
    preview_only: 'Preview Only',
  },
} as const

const exportReadinessLabels = {
  'zh-CN': {
    not_ready: '待补齐素材',
    ready: '可导出',
    exported: '已导出',
    blocked: '受阻',
    exporting: '导出中',
  },
  'en-US': {
    not_ready: 'Needs Assets',
    ready: 'Ready',
    exported: 'Exported',
    blocked: 'Blocked',
    exporting: 'Exporting',
  },
} as const

export function getOutputIntentLabel(intent: TaskOutputIntent, locale: Locale): string {
  return outputIntentLabels[locale][intent]
}

export function getQualityPresetLabel(preset: TaskQualityPreset, locale: Locale): string {
  return qualityLabels[locale][preset]
}

export function getExportProfileLabel(profile: TaskExportProfile, locale: Locale): string {
  return exportProfileLabels[locale][profile]
}

export function getExportReadinessLabel(
  status: TaskExportReadinessStatus,
  locale: Locale,
): string {
  return exportReadinessLabels[locale][status]
}
