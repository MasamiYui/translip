export type AgeBandKey =
  | 'child'
  | 'teen'
  | 'youngAdult'
  | 'middleAged'
  | 'senior'

export const AGE_BANDS: { key: AgeBandKey; value: string }[] = [
  { key: 'child', value: '儿童' },
  { key: 'teen', value: '少年' },
  { key: 'youngAdult', value: '青年' },
  { key: 'middleAged', value: '中年' },
  { key: 'senior', value: '老年' },
]

export function ageBandKeyFromValue(value: string): AgeBandKey | null {
  const trimmed = value.trim()
  const found = AGE_BANDS.find(b => b.value === trimmed)
  return found ? found.key : null
}

export type SwatchKey =
  | 'coral'
  | 'orange'
  | 'amber'
  | 'lime'
  | 'emerald'
  | 'cyan'
  | 'sky'
  | 'blue'
  | 'indigo'
  | 'violet'
  | 'purple'
  | 'pink'
  | 'rose'
  | 'slate'

export const COLOR_SWATCHES: { key: SwatchKey; value: string }[] = [
  { key: 'coral', value: '#ef4444' },
  { key: 'orange', value: '#f97316' },
  { key: 'amber', value: '#f59e0b' },
  { key: 'lime', value: '#84cc16' },
  { key: 'emerald', value: '#10b981' },
  { key: 'cyan', value: '#06b6d4' },
  { key: 'sky', value: '#0ea5e9' },
  { key: 'blue', value: '#3b82f6' },
  { key: 'indigo', value: '#6366f1' },
  { key: 'violet', value: '#7c3aed' },
  { key: 'purple', value: '#8b5cf6' },
  { key: 'pink', value: '#ec4899' },
  { key: 'rose', value: '#e11d48' },
  { key: 'slate', value: '#64748b' },
]

export const DEFAULT_COLOR = '#3b5bdb'

export type AvatarGroupKey = 'people' | 'character' | 'animal' | 'symbol'

export const AVATAR_EMOJI_GROUPS: Record<AvatarGroupKey, string[]> = {
  people: ['👩', '👨', '🧑', '👧', '👦', '🧒', '👵', '👴', '👸', '🤴'],
  character: ['🦸‍♀️', '🦸', '🧙', '🧝‍♀️', '🧝', '🥷', '👮', '🕵️', '👨‍🍳', '👨‍🚀', '🧛', '🧟', '🧚', '🧞'],
  animal: ['🐱', '🐶', '🦊', '🐻', '🐼', '🦁', '🐰', '🐯', '🐨', '🐸', '🦄', '🐺'],
  symbol: ['⭐', '🌙', '🌸', '🔥', '⚡', '🍀', '💎', '🌟', '❤️', '🗡️'],
}

export type CoverGroupKey = 'media' | 'genre' | 'object'

export const COVER_ICON_GROUPS: Record<CoverGroupKey, string[]> = {
  media: ['📺', '🎬', '🎭', '🎤', '🎵', '🎞️', '🎙️', '📽️', '🎧', '📡'],
  genre: ['🦸', '🐉', '⚔️', '🚀', '👻', '🧙', '🕵️', '💘', '🏰', '🧛', '🔮', '🛸'],
  object: ['☕', '📖', '🎮', '💼', '🌊', '🌸', '🍷', '🎂', '🌆', '🌌', '🗝️', '🏆'],
}

export const ROLE_PRESET_KEYS = [
  'leadFemale',
  'leadMale',
  'supportingFemale',
  'supportingMale',
  'villain',
  'narrator',
  'cameo',
] as const
export type RolePresetKey = (typeof ROLE_PRESET_KEYS)[number]

export function normalizeHex(value: string | null | undefined): string | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(trimmed)) return null
  if (trimmed.length === 4) {
    const r = trimmed[1]
    const g = trimmed[2]
    const b = trimmed[3]
    return `#${r}${r}${g}${g}${b}${b}`.toLowerCase()
  }
  return trimmed.toLowerCase()
}

export function hexWithAlpha(hex: string, alpha: number): string {
  const normalized = normalizeHex(hex) ?? '#3b5bdb'
  const a = Math.max(0, Math.min(1, alpha))
  const aHex = Math.round(a * 255)
    .toString(16)
    .padStart(2, '0')
  return `${normalized}${aHex}`
}

export function lightenHex(hex: string, ratio = 0.35): string {
  const base = normalizeHex(hex) ?? '#3b5bdb'
  const r = Number.parseInt(base.slice(1, 3), 16)
  const g = Number.parseInt(base.slice(3, 5), 16)
  const b = Number.parseInt(base.slice(5, 7), 16)
  const blend = (c: number) => Math.round(c + (255 - c) * ratio)
  const toHex = (c: number) => c.toString(16).padStart(2, '0')
  return `#${toHex(blend(r))}${toHex(blend(g))}${toHex(blend(b))}`
}

export function gradientBackground(hex: string): string {
  const base = normalizeHex(hex) ?? DEFAULT_COLOR
  const light = lightenHex(base, 0.45)
  const lighter = lightenHex(base, 0.75)
  return `linear-gradient(135deg, ${light} 0%, ${lighter} 100%)`
}

export function firstGlyphOf(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return '?'
  const chars = Array.from(trimmed)
  return chars[0].toUpperCase()
}
