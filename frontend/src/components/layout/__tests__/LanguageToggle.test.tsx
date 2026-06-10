import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { I18nProvider } from '../../../i18n/I18nProvider'
import { LanguageToggle } from '../LanguageToggle'

function renderToggle() {
  return render(
    <I18nProvider>
      <LanguageToggle />
    </I18nProvider>,
  )
}

describe('LanguageToggle', () => {
  afterEach(() => cleanup())

  it('renders both locale buttons with aria-pressed reflecting the active locale (zh-CN default)', () => {
    renderToggle()
    const zhButton = screen.getByRole('button', { name: '中文' })
    const enButton = screen.getByRole('button', { name: 'EN' })
    expect(zhButton).toHaveAttribute('aria-pressed', 'true')
    expect(enButton).toHaveAttribute('aria-pressed', 'false')
  })

  it('switches active state when the other locale is clicked', () => {
    renderToggle()
    const enButton = screen.getByRole('button', { name: 'EN' })
    fireEvent.click(enButton)
    const zhButton = screen.getByRole('button', { name: '中文' })
    expect(enButton).toHaveAttribute('aria-pressed', 'true')
    expect(zhButton).toHaveAttribute('aria-pressed', 'false')
  })

  it('exposes a labelled group for assistive tech', () => {
    renderToggle()
    const group = screen.getByRole('group')
    expect(group).toHaveAttribute('aria-label')
    expect(group.getAttribute('aria-label')).toBeTruthy()
  })
})
