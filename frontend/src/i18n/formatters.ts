import { messages, type Locale, type LocaleMessages } from './messages'

export const STAGE_ORDER = [
  'stage1',
  'ocr-detect',
  'task-a',
  'asr-ocr-correct',
  'task-b',
  'task-c',
  'ocr-translate',
  'task-d',
  'task-e',
  'subtitle-erase',
  'task-g',
] as const
export const LANGUAGE_CODES = ['zh', 'en', 'ja', 'ko', 'de', 'fr', 'es', 'ru'] as const

export type StageKey = keyof LocaleMessages['stages']
export type StageShortKey = keyof LocaleMessages['stageShort']
export type StatusKey = keyof LocaleMessages['status']
export type LanguageCode = (typeof LANGUAGE_CODES)[number]

function getOlderDateOptions(locale: Locale): Intl.DateTimeFormatOptions {
  if (locale === 'zh-CN') {
    return { month: 'short', day: 'numeric' }
  }

  return { month: 'short', day: 'numeric' }
}

function formatEnglishRelative(value: number, unit: 'minute' | 'hour' | 'day') {
  const suffix = value === 1 ? unit : `${unit}s`
  return `${value} ${suffix} ago`
}

export function formatDurationForLocale(seconds: number | undefined, locale: Locale): string {
  if (seconds == null) return messages[locale].common.notAvailable

  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)

  if (locale === 'zh-CN') {
    if (hours > 0) return `${hours}小时 ${minutes}分 ${secs}秒`
    if (minutes > 0) return `${minutes}分 ${secs}秒`
    return `${secs}秒`
  }

  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

export function formatRelativeTimeForLocale(
  dateStr: string,
  locale: Locale,
  now = new Date(),
): string {
  const date = new Date(dateStr)
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 60) {
    return locale === 'zh-CN' ? '刚刚' : 'just now'
  }

  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) {
    return locale === 'zh-CN' ? `${diffMin}分钟前` : formatEnglishRelative(diffMin, 'minute')
  }

  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) {
    return locale === 'zh-CN' ? `${diffHour}小时前` : formatEnglishRelative(diffHour, 'hour')
  }

  const diffDay = Math.floor(diffHour / 24)
  if (diffDay === 1) {
    return locale === 'zh-CN' ? '昨天' : 'yesterday'
  }

  if (diffDay < 7) {
    return locale === 'zh-CN' ? `${diffDay}天前` : formatEnglishRelative(diffDay, 'day')
  }

  return date.toLocaleDateString(locale, getOlderDateOptions(locale))
}

export function formatDateTimeForLocale(dateStr: string | undefined, locale: Locale): string {
  if (!dateStr) return messages[locale].common.notAvailable

  const date = new Date(dateStr)
  return date.toLocaleString(locale, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getStageLabel(stage: StageKey, locale: Locale): string {
  return messages[locale].stages[stage]
}

export function getStageShortLabel(stage: StageShortKey, locale: Locale): string {
  return messages[locale].stageShort[stage]
}

export function getStatusLabel(status: StatusKey, locale: Locale): string {
  return messages[locale].status[status]
}

export function getLanguageLabel(code: LanguageCode | string, locale: Locale): string {
  if (code in messages[locale].languageNames) {
    return messages[locale].languageNames[code as LanguageCode]
  }

  return code
}
