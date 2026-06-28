import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NarratorVoicePicker } from '../NewTaskPage'

const SAMPLE_VOICES = [
  {
    id: 'narrator-male-calm',
    name_zh: '沉稳男声',
    name_en: 'Calm Male',
    gender: 'male',
    native_language: 'zh',
    description_zh: '沉稳磁性的中文男声',
    description_en: 'Calm Chinese male voice',
  },
  {
    id: 'narrator-female-bright',
    name_zh: '知性女声',
    name_en: 'Bright Female',
    gender: 'female',
    native_language: 'zh',
  },
]

type PlayResolver = (() => void) | null
let playPromiseFactory: () => Promise<void>
let playMock: ReturnType<typeof vi.fn>
let pauseMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  playPromiseFactory = () => Promise.resolve()
  playMock = vi.fn(() => playPromiseFactory())
  pauseMock = vi.fn()
  vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockImplementation(
    playMock as unknown as () => Promise<void>,
  )
  vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(
    pauseMock as unknown as () => void,
  )
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
  cleanup()
})

function mountPicker(initialValue = 'narrator-male-calm') {
  let current = initialValue
  const onChange = vi.fn((next: string) => {
    current = next
  })
  const utils = render(
    <NarratorVoicePicker
      value={current}
      voices={SAMPLE_VOICES}
      locale="zh-CN"
      onChange={onChange}
    />,
  )
  return { ...utils, onChange }
}

describe('NarratorVoicePicker.handlePreview', () => {
  it('plays the audio when fetch returns a valid wav blob', async () => {
    const buffer = new Uint8Array([0x52, 0x49, 0x46, 0x46]).buffer
    const fetchMock = vi.fn(
      async () =>
        new Response(buffer, {
          status: 200,
          headers: { 'Content-Type': 'audio/wav' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    mountPicker()

    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })
    expect((fetchMock.mock.calls as unknown as string[][])[0]?.[0]).toBe(
      '/api/config/narrator-voices/narrator-male-calm/preview',
    )

    await waitFor(() => {
      expect(playMock).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '停止试听' })).toBeInTheDocument()
    })
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('surfaces the backend detail message when the preview endpoint returns 500', async () => {
    const detail = '音色 \'narrator-male-calm\' 试听生成失败：CustomVoice 模型未下载. 提示：模型下载失败，请设置 HF_ENDPOINT=https://hf-mirror.com 或检查网络连接后重试。'
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    mountPicker()

    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('HTTP 500')
    })
    expect(screen.getByRole('alert')).toHaveTextContent('CustomVoice 模型未下载')
    expect(screen.getByRole('alert')).toHaveTextContent('HF_ENDPOINT')
    expect(playMock).not.toHaveBeenCalled()
  })

  it('shows a generic backend error message when 500 body is not JSON', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response('<html>Internal Server Error</html>', {
          status: 500,
          headers: { 'Content-Type': 'text/html' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    mountPicker()

    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('试听生成失败（HTTP 500）')
    })
    expect(playMock).not.toHaveBeenCalled()
  })

  it('shows an autoplay-blocked message only when play() rejects with NotAllowedError', async () => {
    const buffer = new Uint8Array([0x52, 0x49, 0x46, 0x46]).buffer
    const fetchMock = vi.fn(
      async () =>
        new Response(buffer, {
          status: 200,
          headers: { 'Content-Type': 'audio/wav' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const rejectorRef: { current: PlayResolver } = { current: null }
    playPromiseFactory = () =>
      new Promise<void>((_resolve, reject) => {
        rejectorRef.current = () => {
          reject(new DOMException('Autoplay blocked', 'NotAllowedError'))
        }
      })

    mountPicker()
    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])

    await waitFor(() => {
      expect(playMock).toHaveBeenCalledTimes(1)
    })
    rejectorRef.current?.()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('浏览器拒绝了自动播放')
    })
  })

  it('shows a connectivity message when fetch itself throws', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fetchMock)

    mountPicker()
    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('无法连接到后端服务')
    })
    expect(playMock).not.toHaveBeenCalled()
  })

  it('cancels an in-flight request when the user clicks a second voice', async () => {
    let firstRejected = false
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal | undefined
      if (fetchMock.mock.calls.length === 1) {
        return new Promise<Response>((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            firstRejected = true
            reject(new DOMException('Aborted', 'AbortError'))
          })
        })
      }
      return new Response(new Uint8Array([0x52, 0x49, 0x46, 0x46]).buffer, {
        status: 200,
        headers: { 'Content-Type': 'audio/wav' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    mountPicker()
    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[0])
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getAllByRole('button', { name: '试听' })[1])

    await waitFor(() => expect(firstRejected).toBe(true))
    await waitFor(() => expect(playMock).toHaveBeenCalledTimes(1))
  })
})
