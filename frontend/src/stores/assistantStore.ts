import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AssistantPlan, Clarification, RunState } from '../types/assistant'

export type ChatRole = 'user' | 'assistant'
export type MessageKind = 'text' | 'plan' | 'error' | 'clarification'

export interface AttachedFile {
  file_id: string
  filename: string
}

/** A file the assistant can use as input: an upload or a prior run's artifact. */
export interface AvailableFile {
  file_id: string
  filename: string
  origin: 'upload' | 'output'
}

export interface ChatMessage {
  id: string
  role: ChatRole
  kind: MessageKind
  text?: string
  plan?: AssistantPlan
  // file_ids snapshot (the conversation pool order) used when this plan executes
  fileIds?: string[]
  attachments?: AttachedFile[]
  runId?: string
  run?: RunState
  // clarification message: the question + the original request to merge on answer
  clarification?: Clarification
  sourceText?: string
  sourceFileIds?: string[]
  answered?: boolean
  createdAt: number
}

function genId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

interface AssistantState {
  isOpen: boolean
  conversationId: string
  messages: ChatMessage[]
  attachments: AttachedFile[]
  availableFiles: AvailableFile[]
  open: () => void
  close: () => void
  toggle: () => void
  addMessage: (message: Omit<ChatMessage, 'id' | 'createdAt'> & { id?: string; createdAt?: number }) => string
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void
  addAttachment: (file: AttachedFile) => void
  removeAttachment: (fileId: string) => void
  clearAttachments: () => void
  addAvailableFiles: (files: AvailableFile[]) => void
  resetConversation: () => void
  reset: () => void
}

function mergeFiles(existing: AvailableFile[], incoming: AvailableFile[]): AvailableFile[] {
  const seen = new Set(existing.map(f => f.file_id))
  const merged = [...existing]
  for (const file of incoming) {
    if (!seen.has(file.file_id)) {
      seen.add(file.file_id)
      merged.push(file)
    }
  }
  return merged
}

export const useAssistantStore = create<AssistantState>()(
  persist(
    set => ({
      isOpen: false,
      conversationId: genId(),
      messages: [],
      attachments: [],
      availableFiles: [],
      open: () => set({ isOpen: true }),
      close: () => set({ isOpen: false }),
      toggle: () => set(state => ({ isOpen: !state.isOpen })),
      addMessage: message => {
        const id = message.id ?? genId()
        const createdAt = message.createdAt ?? Date.now()
        set(state => ({ messages: [...state.messages, { ...message, id, createdAt }] }))
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
      addAvailableFiles: files =>
        set(state => ({ availableFiles: mergeFiles(state.availableFiles, files) })),
      resetConversation: () =>
        set({ messages: [], attachments: [], availableFiles: [], conversationId: genId() }),
      reset: () =>
        set({ messages: [], attachments: [], availableFiles: [], conversationId: genId() }),
    }),
    {
      name: 'translip:assistant-conversation',
      partialize: state => ({
        conversationId: state.conversationId,
        messages: state.messages,
        availableFiles: state.availableFiles,
      }),
    },
  ),
)
