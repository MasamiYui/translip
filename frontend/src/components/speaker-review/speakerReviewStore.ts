import { create } from 'zustand'

import type {
  PersonaApplyPreviewResponse,
  PersonaNameConflict,
  SuggestFromGlobalMatch,
} from '../../types'

export type ReviewSelectionKind = 'speaker' | 'run' | 'segment'

export interface ReviewSelection {
  kind: ReviewSelectionKind
  id: string
}

export type RiskLevel = 'high' | 'medium' | 'low'

export interface QueueFilters {
  risk: RiskLevel[]
  onlyUndecided: boolean
  sortBy: 'time' | 'risk'
}

export interface PendingConflict {
  conflict: PersonaNameConflict
  attempted: {
    kind: 'create' | 'rename'
    name: string
    personaId?: string
    speaker?: string
  }
}

interface SpeakerReviewUiState {
  selection: ReviewSelection | null
  bulkSelection: Set<string>
  filters: QueueFilters
  showShortcuts: boolean
  showDiffModal: boolean
  pendingMerge: { source: string; target: string } | null
  renamingSpeaker: string | null
  renameDraft: string
  continuousRenaming: boolean
  showPersonaBulk: boolean
  showPersonaSuggest: boolean
  lastUndoAt: number | null
  lastRedoAt: number | null
  pendingConflict: PendingConflict | null
  showApplyPreview: boolean
  applyPreviewData: PersonaApplyPreviewResponse | null
  showOnboarding: boolean
  showGlobalPersonas: boolean
  globalMatchToast: { matches: SuggestFromGlobalMatch[]; dismissedAt: number | null } | null
  setSelection(selection: ReviewSelection | null): void
  toggleBulk(id: string): void
  clearBulk(): void
  setFilters(updater: (current: QueueFilters) => QueueFilters): void
  setShowShortcuts(value: boolean): void
  setShowDiffModal(value: boolean): void
  setPendingMerge(value: { source: string; target: string } | null): void
  startRename(speaker: string, initial: string): void
  updateRenameDraft(value: string): void
  cancelRename(): void
  setContinuousRenaming(value: boolean): void
  setShowPersonaBulk(value: boolean): void
  setShowPersonaSuggest(value: boolean): void
  markUndo(): void
  markRedo(): void
  setPendingConflict(value: PendingConflict | null): void
  setShowApplyPreview(value: boolean): void
  setApplyPreviewData(value: PersonaApplyPreviewResponse | null): void
  setShowOnboarding(value: boolean): void
  setShowGlobalPersonas(value: boolean): void
  setGlobalMatchToast(
    value: { matches: SuggestFromGlobalMatch[]; dismissedAt: number | null } | null,
  ): void
}

export const useSpeakerReviewStore = create<SpeakerReviewUiState>((set, get) => ({
  selection: null,
  bulkSelection: new Set(),
  filters: { risk: ['high', 'medium', 'low'], onlyUndecided: true, sortBy: 'risk' },
  showShortcuts: false,
  showDiffModal: false,
  pendingMerge: null,
  renamingSpeaker: null,
  renameDraft: '',
  continuousRenaming: false,
  showPersonaBulk: false,
  showPersonaSuggest: false,
  lastUndoAt: null,
  lastRedoAt: null,
  pendingConflict: null,
  showApplyPreview: false,
  applyPreviewData: null,
  showOnboarding: false,
  showGlobalPersonas: false,
  globalMatchToast: null,
  setSelection: selection => set({ selection }),
  toggleBulk: id => {
    const next = new Set(get().bulkSelection)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    set({ bulkSelection: next })
  },
  clearBulk: () => set({ bulkSelection: new Set() }),
  setFilters: updater => set({ filters: updater(get().filters) }),
  setShowShortcuts: value => set({ showShortcuts: value }),
  setShowDiffModal: value => set({ showDiffModal: value }),
  setPendingMerge: value => set({ pendingMerge: value }),
  startRename: (speaker, initial) => set({ renamingSpeaker: speaker, renameDraft: initial }),
  updateRenameDraft: value => set({ renameDraft: value }),
  cancelRename: () => set({ renamingSpeaker: null, renameDraft: '' }),
  setContinuousRenaming: value => set({ continuousRenaming: value }),
  setShowPersonaBulk: value => set({ showPersonaBulk: value }),
  setShowPersonaSuggest: value => set({ showPersonaSuggest: value }),
  markUndo: () => set({ lastUndoAt: Date.now() }),
  markRedo: () => set({ lastRedoAt: Date.now() }),
  setPendingConflict: value => set({ pendingConflict: value }),
  setShowApplyPreview: value => set({ showApplyPreview: value }),
  setApplyPreviewData: value => set({ applyPreviewData: value }),
  setShowOnboarding: value => set({ showOnboarding: value }),
  setShowGlobalPersonas: value => set({ showGlobalPersonas: value }),
  setGlobalMatchToast: value => set({ globalMatchToast: value }),
}))

