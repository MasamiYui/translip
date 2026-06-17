import { create } from 'zustand'
import type { AssistantPlan, RunState } from '../types/assistant'

export type ChatRole = 'user' | 'assistant'
export type MessageKind = 'text' | 'plan' | 'error'

export interface AttachedFile {
  file_id: string
  filename: string
}

export interface ChatMessage {
  id: string
  role: ChatRole
  kind: MessageKind
  text?: string
  plan?: AssistantPlan
  // file_ids snapshot used when this plan executes (for upload bindings)
  fileIds?: string[]
  attachments?: AttachedFile[]
  runId?: string
  run?: RunState
}

function genId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

interface AssistantState {
  isOpen: boolean
  messages: ChatMessage[]
  attachments: AttachedFile[]
  open: () => void
  close: () => void
  toggle: () => void
  addMessage: (message: Omit<ChatMessage, 'id'> & { id?: string }) => string
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void
  addAttachment: (file: AttachedFile) => void
  removeAttachment: (fileId: string) => void
  clearAttachments: () => void
  reset: () => void
}

export const useAssistantStore = create<AssistantState>(set => ({
  isOpen: false,
  messages: [],
  attachments: [],
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  toggle: () => set(state => ({ isOpen: !state.isOpen })),
  addMessage: message => {
    const id = message.id ?? genId()
    set(state => ({ messages: [...state.messages, { ...message, id }] }))
    return id
  },
  updateMessage: (id, patch) =>
    set(state => ({
      messages: state.messages.map(m => (m.id === id ? { ...m, ...patch } : m)),
    })),
  addAttachment: file =>
    set(state =>
      state.attachments.some(f => f.file_id === file.file_id)
        ? state
        : { attachments: [...state.attachments, file] },
    ),
  removeAttachment: fileId =>
    set(state => ({ attachments: state.attachments.filter(f => f.file_id !== fileId) })),
  clearAttachments: () => set({ attachments: [] }),
  reset: () => set({ messages: [], attachments: [] }),
}))
