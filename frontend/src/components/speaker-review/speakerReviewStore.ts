import { create } from 'zustand'

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

interface SpeakerReviewUiState {
  selection: ReviewSelection | null
  bulkSelection: Set<string>
  filters: QueueFilters
  showShortcuts: boolean
  showDiffModal: boolean
  pendingMerge: { source: string; target: string } | null
  setSelection(selection: ReviewSelection | null): void
  toggleBulk(id: string): void
  clearBulk(): void
  setFilters(updater: (current: QueueFilters) => QueueFilters): void
  setShowShortcuts(value: boolean): void
  setShowDiffModal(value: boolean): void
  setPendingMerge(value: { source: string; target: string } | null): void
}

export const useSpeakerReviewStore = create<SpeakerReviewUiState>((set, get) => ({
  selection: null,
  bulkSelection: new Set(),
  filters: { risk: ['high', 'medium', 'low'], onlyUndecided: true, sortBy: 'risk' },
  showShortcuts: false,
  showDiffModal: false,
  pendingMerge: null,
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
}))
