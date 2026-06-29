import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BgmPresetPicker } from '../NewTaskPage'

const BGM_PRESETS = [
  {
    id: 'bgm-suspense-dark',
    name_zh: '悬疑暗流',
    name_en: 'Suspense Dark',
    mood: 'suspense',
    gain_db: -17,
    duck_db: -10,
    description_zh: '低频持续音 + 缓慢心跳脉冲',
    description_en: 'Low drone + slow heartbeat pulse',
  },
  {
    id: 'bgm-epic-hype',
    name_zh: '史诗燃向',
    name_en: 'Epic Hype',
    mood: 'hype',
    gain_db: -14,
    duck_db: -9,
    description_zh: '昂扬上行的合成铺底',
    description_en: 'Rising synth bed',
  },
]

afterEach(() => {
  vi.restoreAllMocks()
  cleanup()
})

function mount({
  value = '',
  locale = 'zh-CN' as 'zh-CN' | 'en-US',
  presets = BGM_PRESETS,
  onChange = vi.fn(),
} = {}) {
  render(
    <BgmPresetPicker value={value} presets={presets} locale={locale} onChange={onChange} />,
  )
  return { onChange }
}

describe('BgmPresetPicker', () => {
  it('renders the built-in BGM section with every preset tile (zh)', () => {
    mount()
    const section = screen.getByRole('region', { name: '内置 BGM 预设' })
    expect(section).toBeInTheDocument()
    BGM_PRESETS.forEach(preset => {
      expect(within(section).getByText(preset.name_zh)).toBeInTheDocument()
    })
    expect(within(section).getByText('新')).toBeInTheDocument()
  })

  it('localises labels for en-US', () => {
    mount({ locale: 'en-US' })
    const section = screen.getByRole('region', { name: 'Built-in BGM presets' })
    expect(within(section).getByText('NEW')).toBeInTheDocument()
    BGM_PRESETS.forEach(preset => {
      expect(within(section).getByText(preset.name_en)).toBeInTheDocument()
    })
  })

  it('keeps the "no BGM" opt-out outside the preset section', () => {
    mount()
    const optOut = screen.getByRole('button', { name: /不加 BGM/ })
    expect(optOut).toBeInTheDocument()
    const section = screen.getByRole('region', { name: '内置 BGM 预设' })
    expect(section.contains(optOut)).toBe(false)
  })

  it('clears the selection when the no-BGM button is clicked', () => {
    const onChange = vi.fn()
    mount({ value: 'bgm-suspense-dark', onChange })
    fireEvent.click(screen.getByRole('button', { name: /不加 BGM/ }))
    expect(onChange).toHaveBeenCalledWith('')
  })

  it('emits the preset id when a tile is clicked', () => {
    const onChange = vi.fn()
    mount({ onChange })
    const section = screen.getByRole('region', { name: '内置 BGM 预设' })
    const tile = within(section).getByText('史诗燃向').closest('[role="button"]')
    expect(tile).not.toBeNull()
    fireEvent.click(tile!)
    expect(onChange).toHaveBeenCalledWith('bgm-epic-hype')
  })

  it('hides the preset section entirely when the registry is empty', () => {
    mount({ presets: [] })
    expect(screen.queryByRole('region', { name: '内置 BGM 预设' })).toBeNull()
    expect(screen.getByRole('button', { name: /不加 BGM/ })).toBeInTheDocument()
  })

  it('survives a non-array payload (cached HTML fallback / 500 body)', () => {
    // Regression: a bad-cached /api/config/bgm-presets response (e.g. HTML
    // string from a Vite SPA fallback or an error envelope object) used to
    // crash with "items.map is not a function". The picker must downgrade to
    // the empty-registry layout instead.
    const garbage = '<html>oops</html>' as unknown as undefined
    mount({ presets: garbage })
    expect(screen.queryByRole('region', { name: '内置 BGM 预设' })).toBeNull()
    expect(screen.getByRole('button', { name: /不加 BGM/ })).toBeInTheDocument()
  })

  it('marks the selected tile via aria-pressed', () => {
    mount({ value: 'bgm-suspense-dark' })
    const section = screen.getByRole('region', { name: '内置 BGM 预设' })
    const tile = within(section).getByText('悬疑暗流').closest('[role="button"]')
    expect(tile).not.toBeNull()
    expect(tile!.getAttribute('aria-pressed')).toBe('true')
  })
})
