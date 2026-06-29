import { DEFAULT_LOCALE, SUPPORTED_LOCALES, type Locale } from '../i18n/messages'
import { slugify } from './blog'

// Re-exported so the reader builds heading ids from the same slugifier the TOC
// uses — keeping anchor links and `#hash` targets in lock-step.
export { slugify as slugifyHeading } from './blog'

export interface TocItem {
  id: string
  text: string
}

export interface GuideChapter {
  /** Stable id from frontmatter `slug` (falls back to the filename stem). */
  slug: string
  locale: Locale
  title: string
  /** Section group used to cluster chapters in the navigation rail. */
  section: string
  /** Sort key; lower runs first. */
  order: number
  summary: string
  /** Optional lucide icon name rendered next to the chapter in the rail. */
  icon?: string
  /** Minutes; from frontmatter `readingTime`, else estimated from the body. */
  readingTime: number
  /** Markdown body with the frontmatter block stripped. */
  body: string
  /** Level-2 headings for the on-page table of contents. */
  toc: TocItem[]
}

export interface GuideSection {
  name: string
  chapters: GuideChapter[]
}

// Chapters are authored as `src/content/guide/<slug>.<locale>.md` and bundled at
// build time. Images/diagrams they reference live under `public/guide/...` and
// are addressed with production-absolute paths (`/guide/dashboard.png`).
const rawModules = import.meta.glob('../content/guide/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function parseFrontmatter(raw: string): { data: Record<string, unknown>; body: string } {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/)
  if (!match) return { data: {}, body: raw }
  const data: Record<string, unknown> = {}
  for (const line of match[1].split(/\r?\n/)) {
    const idx = line.indexOf(':')
    if (idx < 0) continue
    const key = line.slice(0, idx).trim()
    if (!key) continue
    let value = line.slice(idx + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    data[key] = value
  }
  return { data, body: raw.slice(match[0].length) }
}

function estimateReadingTime(body: string): number {
  const text = body
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/[#>*_`[\]()!-]/g, ' ')
  const cjk = (text.match(/[一-鿿]/g) ?? []).length
  const words = (text.replace(/[一-鿿]/g, ' ').match(/[A-Za-z0-9]+/g) ?? []).length
  return Math.max(1, Math.round(cjk / 400 + words / 200))
}

function buildToc(body: string): TocItem[] {
  const items: TocItem[] = []
  const seen = new Set<string>()
  const re = /^##\s+(.+?)\s*$/gm // level-2 only
  let m: RegExpExecArray | null
  while ((m = re.exec(body)) !== null) {
    const text = m[1].replace(/`/g, '').trim()
    let id = slugify(text)
    while (seen.has(id)) id = `${id}-2`
    seen.add(id)
    items.push({ id, text })
  }
  return items
}

function parseFilename(path: string): { slug: string; locale: Locale } | null {
  const file = path.split('/').pop() ?? ''
  const stem = file.replace(/\.md$/, '')
  const dot = stem.lastIndexOf('.')
  if (dot < 0) return null
  const maybeLocale = stem.slice(dot + 1)
  if (!(SUPPORTED_LOCALES as readonly string[]).includes(maybeLocale)) return null
  return { slug: stem.slice(0, dot), locale: maybeLocale as Locale }
}

function toChapter(path: string, raw: string): GuideChapter | null {
  const named = parseFilename(path)
  if (!named) return null
  const { data, body } = parseFrontmatter(raw)
  const readingTime =
    Number(data.readingTime) > 0 ? Number(data.readingTime) : estimateReadingTime(body)
  return {
    slug: typeof data.slug === 'string' && data.slug ? data.slug : named.slug,
    locale: named.locale,
    title: String(data.title ?? named.slug),
    section: String(data.section ?? ''),
    order: Number(data.order) || 0,
    summary: String(data.summary ?? ''),
    icon: typeof data.icon === 'string' && data.icon ? data.icon : undefined,
    readingTime,
    body,
    toc: buildToc(body),
  }
}

// slug -> (locale -> chapter)
const bySlug: Map<string, Map<Locale, GuideChapter>> = (() => {
  const map = new Map<string, Map<Locale, GuideChapter>>()
  for (const [path, raw] of Object.entries(rawModules)) {
    const chapter = toChapter(path, raw)
    if (!chapter) continue
    if (!map.has(chapter.slug)) map.set(chapter.slug, new Map())
    map.get(chapter.slug)!.set(chapter.locale, chapter)
  }
  return map
})()

function pickLocale(
  variants: Map<Locale, GuideChapter>,
  locale: Locale,
): GuideChapter | undefined {
  return variants.get(locale) ?? variants.get(DEFAULT_LOCALE) ?? [...variants.values()][0]
}

/** All chapters for a locale (with fallback), ordered by `order`. */
export function getAllChapters(locale: Locale): GuideChapter[] {
  const chapters: GuideChapter[] = []
  for (const variants of bySlug.values()) {
    const chapter = pickLocale(variants, locale)
    if (chapter) chapters.push(chapter)
  }
  return chapters.sort((a, b) => a.order - b.order)
}

/** Chapters grouped into sections, both sections and chapters in `order`. */
export function getGuideSections(locale: Locale): GuideSection[] {
  const sections: GuideSection[] = []
  for (const chapter of getAllChapters(locale)) {
    const name = chapter.section || ''
    let section = sections.find(s => s.name === name)
    if (!section) {
      section = { name, chapters: [] }
      sections.push(section)
    }
    section.chapters.push(chapter)
  }
  return sections
}

export function getGuideChapter(slug: string, locale: Locale): GuideChapter | undefined {
  const variants = bySlug.get(slug)
  if (!variants) return undefined
  return pickLocale(variants, locale)
}

export function getFirstChapter(locale: Locale): GuideChapter | undefined {
  return getAllChapters(locale)[0]
}

/** Previous and next chapter relative to a slug, for footer navigation. */
export function getAdjacentChapters(
  slug: string,
  locale: Locale,
): { prev?: GuideChapter; next?: GuideChapter } {
  const all = getAllChapters(locale)
  const i = all.findIndex(c => c.slug === slug)
  if (i < 0) return {}
  return { prev: all[i - 1], next: all[i + 1] }
}
