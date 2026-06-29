import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NarratorVoicePicker } from '../NewTaskPage'

const BUILTIN_VOICES = [
  {
    id: 'narrator-male-calm',
    name_zh: '沉稳男声',
    name_en: 'Calm Male',
    gender: 'male' as const,
    native_language: 'zh',
  },
  {
    id: 'narrator-en-male-dynamic',
    name_zh: '英文磁性男声',
    name_en: 'Dynamic English Male',
    gender: 'male' as const,
    native_language: 'en',
  },
]

const VIRAL_VOICES = [
  {
    id: 'narrator-recap-classic',
    name_zh: '经典爆款解说',
    name_en: 'Viral Recap Classic',
    gender: 'male' as const,
    native_language: 'zh',
    description_zh: '抖音爆款影视解说同款腔调',
    description_en: 'Douyin viral-recap delivery',
  },
  {
    id: 'narrator-recap-suspense',
    name_zh: '悬疑神秘男声',
    name_en: 'Suspense Whisper',
    gender: 'male' as const,
    native_language: 'zh',
  },
  {
    id: 'narrator-recap-hype',
    name_zh: '热血燃向男声',
    name_en: 'Hype Trailer Male',
    gender: 'male' as const,
    native_language: 'en',
  },
  {
    id: 'narrator-recap-gossip',
    name_zh: '八卦吐槽女声',
    name_en: 'Gossip Roast Female',
    gender: 'female' as const,
    native_language: 'zh',
  },
  {
    id: 'narrator-recap-sichuan-funny',
    name_zh: '川味儿搞笑解说',
    name_en: 'Sichuan Comedy Recap',
    gender: 'male' as const,
    native_language: 'zh',
  },
]

const ALL_VOICES = [...BUILTIN_VOICES, ...VIRAL_VOICES]

afterEach(() => {
  vi.restoreAllMocks()
  cleanup()
})

function mountPicker(locale: 'zh-CN' | 'en-US' = 'zh-CN') {
  return render(
    <NarratorVoicePicker
      value="narrator-male-calm"
      voices={ALL_VOICES}
      locale={locale}
      onChange={vi.fn()}
    />,
  )
}

describe('NarratorVoicePicker grouping', () => {
  it('renders the built-in narrator section with all non-recap voices (zh)', () => {
    mountPicker('zh-CN')
    const builtinSection = screen.getByRole('region', { name: '内置叙述音色' })
    expect(builtinSection).toBeInTheDocument()
    BUILTIN_VOICES.forEach(voice => {
      expect(within(builtinSection).getByText(voice.name_zh)).toBeInTheDocument()
    })
    VIRAL_VOICES.forEach(voice => {
      expect(within(builtinSection).queryByText(voice.name_zh)).toBeNull()
    })
  })

  it('renders the dedicated viral-recap section with NEW badge (zh)', () => {
    mountPicker('zh-CN')
    const viralSection = screen.getByRole('region', { name: '短视频爆款风' })
    expect(viralSection).toBeInTheDocument()
    expect(within(viralSection).getByText('新')).toBeInTheDocument()
    VIRAL_VOICES.forEach(voice => {
      expect(within(viralSection).getByText(voice.name_zh)).toBeInTheDocument()
    })
  })

  it('keeps the "borrow from source" escape hatch outside both groups', () => {
    mountPicker('zh-CN')
    const sourceButton = screen.getByRole('button', { name: '借用源片音色' })
    expect(sourceButton).toBeInTheDocument()
    const builtinSection = screen.getByRole('region', { name: '内置叙述音色' })
    const viralSection = screen.getByRole('region', { name: '短视频爆款风' })
    expect(builtinSection.contains(sourceButton)).toBe(false)
    expect(viralSection.contains(sourceButton)).toBe(false)
  })

  it('localises the section headers in English with NEW badge', () => {
    mountPicker('en-US')
    expect(
      screen.getByRole('region', { name: 'Built-in narrator voices' }),
    ).toBeInTheDocument()
    const viralSection = screen.getByRole('region', {
      name: 'Viral short-video recap',
    })
    expect(viralSection).toBeInTheDocument()
    expect(within(viralSection).getByText('NEW')).toBeInTheDocument()
  })

  it('hides the viral section entirely when no recap voice is provided', () => {
    render(
      <NarratorVoicePicker
        value="narrator-male-calm"
        voices={BUILTIN_VOICES}
        locale="zh-CN"
        onChange={vi.fn()}
      />,
    )
    expect(
      screen.getByRole('region', { name: '内置叙述音色' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: '短视频爆款风' }),
    ).toBeNull()
  })
})
