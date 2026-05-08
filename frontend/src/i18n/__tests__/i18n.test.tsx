import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  formatDurationForLocale,
  formatRelativeTimeForLocale,
  getStageLabel,
  getStatusLabel,
} from '../formatters'
import { I18nProvider } from '../I18nProvider'
import { useI18n } from '../useI18n'

function wrapper({ children }: { children: React.ReactNode }) {
  return <I18nProvider>{children}</I18nProvider>
}

describe('I18nProvider', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaults to zh-CN when storage is empty', () => {
    const { result } = renderHook(() => useI18n(), { wrapper })

    expect(result.current.locale).toBe('zh-CN')
    expect(result.current.t.nav.dashboard).toBe('仪表盘')
  })

  it('restores the stored locale and persists changes', () => {
    localStorage.setItem('translip.locale', 'en-US')

    const { result } = renderHook(() => useI18n(), { wrapper })

    expect(result.current.locale).toBe('en-US')
    expect(result.current.t.nav.dashboard).toBe('Dashboard')

    act(() => {
      result.current.setLocale('zh-CN')
    })

    expect(localStorage.getItem('translip.locale')).toBe('zh-CN')
  })

  it('formats relative time in both locales', () => {
    const now = new Date('2026-04-15T12:00:00Z')

    expect(formatRelativeTimeForLocale('2026-04-15T11:57:00Z', 'zh-CN', now)).toBe('3分钟前')
    expect(formatRelativeTimeForLocale('2026-04-15T11:57:00Z', 'en-US', now)).toBe('3 minutes ago')
  })

  it('formats durations and localized labels', () => {
    expect(formatDurationForLocale(65, 'zh-CN')).toBe('1分 5秒')
    expect(formatDurationForLocale(65, 'en-US')).toBe('1m 5s')
    expect(getStatusLabel('running', 'zh-CN')).toBe('运行中')
    expect(getStatusLabel('running', 'en-US')).toBe('Running')
    expect(getStageLabel('task-c', 'zh-CN')).toBe('Task C: 翻译')
    expect(getStageLabel('task-c', 'en-US')).toBe('Task C: Translation')
  })

  it('exposes locale-aware helper methods from the hook', () => {
    const { result } = renderHook(() => useI18n(), { wrapper })

    expect(result.current.getLanguageLabel('en')).toBe('英语')
    expect(result.current.getStageLabel('task-d')).toBe('Task D: 语音合成')
    expect(result.current.t.tasks.deleteConfirmOne).toBe('确定删除此任务及其产物？')
    expect(result.current.t.tasks.deleteConfirmMany(2)).toBe('确定删除 2 个任务及其产物？')
    expect(result.current.t.taskDetail.deleteConfirm).toBe('确定删除此任务及其产物？')

    act(() => {
      result.current.setLocale('en-US')
    })

    expect(result.current.formatDuration(65)).toBe('1m 5s')
    expect(result.current.getStatusLabel('succeeded')).toBe('Completed')
    expect(result.current.t.tasks.deleteConfirmOne).toBe('Delete this task and its artifacts?')
    expect(result.current.t.tasks.deleteConfirmMany(2)).toBe('Delete 2 tasks and their artifacts?')
    expect(result.current.t.taskDetail.deleteConfirm).toBe('Delete this task and its artifacts?')
    expect(document.documentElement.lang).toBe('en-US')
  })
})
