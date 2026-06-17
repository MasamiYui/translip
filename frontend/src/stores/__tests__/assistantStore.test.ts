import { beforeEach, describe, expect, it } from 'vitest'
import { useAssistantStore } from '../assistantStore'

function resetStore() {
  useAssistantStore.setState({ isOpen: false, messages: [], attachments: [], availableFiles: [] })
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

  it('stamps createdAt and supports clarification messages', () => {
    const id = useAssistantStore.getState().addMessage({
      role: 'assistant',
      kind: 'clarification',
      clarification: { question: '翻译成哪种语言？', options: ['中文', '英文'] },
      sourceText: '翻译这个视频',
    })
    const msg = useAssistantStore.getState().messages.find(m => m.id === id)
    expect(msg?.kind).toBe('clarification')
    expect(msg?.clarification?.options).toEqual(['中文', '英文'])
    expect(typeof msg?.createdAt).toBe('number')
    expect(msg?.createdAt).toBeGreaterThan(0)
  })

  it('accumulates available files and dedupes by file_id', () => {
    const { addAvailableFiles } = useAssistantStore.getState()
    addAvailableFiles([{ file_id: 'u1', filename: 'in.mp4', origin: 'upload' }])
    addAvailableFiles([
      { file_id: 'u1', filename: 'in.mp4', origin: 'upload' },
      { file_id: 'o1', filename: 'voice.wav', origin: 'output' },
    ])
    const files = useAssistantStore.getState().availableFiles
    expect(files.map(f => f.file_id)).toEqual(['u1', 'o1'])
    expect(files[1].origin).toBe('output')
  })

  it('resetConversation clears pool/messages and rotates the conversation id', () => {
    const before = useAssistantStore.getState().conversationId
    useAssistantStore.getState().addMessage({ role: 'user', kind: 'text', text: 'hi' })
    useAssistantStore.getState().addAvailableFiles([{ file_id: 'o1', filename: 'voice.wav', origin: 'output' }])
    useAssistantStore.getState().resetConversation()
    const state = useAssistantStore.getState()
    expect(state.messages).toHaveLength(0)
    expect(state.availableFiles).toHaveLength(0)
    expect(state.conversationId).not.toBe(before)
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
