import { beforeEach, describe, expect, it } from 'vitest'
import { useAssistantStore } from '../assistantStore'

function resetStore() {
  useAssistantStore.setState({ isOpen: false, messages: [], attachments: [] })
}

describe('assistantStore', () => {
  beforeEach(resetStore)

  it('toggles open state', () => {
    expect(useAssistantStore.getState().isOpen).toBe(false)
    useAssistantStore.getState().toggle()
    expect(useAssistantStore.getState().isOpen).toBe(true)
    useAssistantStore.getState().close()
    expect(useAssistantStore.getState().isOpen).toBe(false)
  })

  it('adds and updates messages, returning a stable id', () => {
    const id = useAssistantStore.getState().addMessage({ role: 'user', kind: 'text', text: 'hi' })
    expect(typeof id).toBe('string')
    expect(useAssistantStore.getState().messages).toHaveLength(1)
    useAssistantStore.getState().updateMessage(id, { text: 'updated' })
    expect(useAssistantStore.getState().messages[0].text).toBe('updated')
  })

  it('dedupes attachments by file_id and removes them', () => {
    const { addAttachment, removeAttachment } = useAssistantStore.getState()
    addAttachment({ file_id: 'a', filename: 'a.mp4' })
    addAttachment({ file_id: 'a', filename: 'a.mp4' })
    expect(useAssistantStore.getState().attachments).toHaveLength(1)
    addAttachment({ file_id: 'b', filename: 'b.wav' })
    expect(useAssistantStore.getState().attachments).toHaveLength(2)
    removeAttachment('a')
    expect(useAssistantStore.getState().attachments.map(f => f.file_id)).toEqual(['b'])
  })

  it('reset clears messages and attachments', () => {
    const s = useAssistantStore.getState()
    s.addMessage({ role: 'user', kind: 'text', text: 'x' })
    s.addAttachment({ file_id: 'a', filename: 'a.mp4' })
    s.reset()
    expect(useAssistantStore.getState().messages).toHaveLength(0)
    expect(useAssistantStore.getState().attachments).toHaveLength(0)
  })
})
