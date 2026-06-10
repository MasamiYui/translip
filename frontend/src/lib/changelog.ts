import { DEFAULT_LOCALE, SUPPORTED_LOCALES, type Locale } from '../i18n/messages'

export type ChangelogEntryType = 'feature' | 'improvement' | 'fix' | 'breaking'

export interface ChangelogRelease {
  slug: string
  locale: Locale
  version: string
  title: string
  date: string
  tag?: string
  summary: string
  highlights: string[]
  readingTime: number
  body: string
  toc: TocItem[]
}

export interface TocItem {
  id: string
  text: string
}

const rawModules = import.meta.glob('../content/changelog/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

export function slugify(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^\w一-鿿]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

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
    if (value.startsWith('[') && value.endsWith(']')) {
      data[key] = value
        .slice(1, -1)
        .split(',')
        .map(s => s.trim().replace(/^["']|["']$/g, ''))
        .filter(Boolean)
    } else {
      data[key] = value
    }
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
  const re = /^##\s+(.+?)\s*$/gm
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

function toRelease(path: string, raw: string): ChangelogRelease | null {
  const named = parseFilename(path)
  if (!named) return null
  const { data, body } = parseFrontmatter(raw)
  const highlights = Array.isArray(data.highlights) ? (data.highlights as string[]) : []
  const readingTime =
    Number(data.readingTime) > 0 ? Number(data.readingTime) : estimateReadingTime(body)
  return {
    slug: typeof data.slug === 'string' && data.slug ? data.slug : named.slug,
    locale: named.locale,
    version: String(data.version ?? named.slug),
    title: String(data.title ?? named.slug),
    date: String(data.date ?? ''),
    tag: typeof data.tag === 'string' ? data.tag : undefined,
    summary: String(data.summary ?? ''),
    highlights,
    readingTime,
    body,
    toc: buildToc(body),
  }
}

const bySlug: Map<string, Map<Locale, ChangelogRelease>> = (() => {
  const map = new Map<string, Map<Locale, ChangelogRelease>>()
  for (const [path, raw] of Object.entries(rawModules)) {
    const release = toRelease(path, raw)
    if (!release) continue
    if (!map.has(release.slug)) map.set(release.slug, new Map())
    map.get(release.slug)!.set(release.locale, release)
  }
  return map
})()

function pickLocale(
  variants: Map<Locale, ChangelogRelease>,
  locale: Locale,
): ChangelogRelease | undefined {
  return variants.get(locale) ?? variants.get(DEFAULT_LOCALE) ?? [...variants.values()][0]
}

export function getAllReleases(locale: Locale): ChangelogRelease[] {
  const list: ChangelogRelease[] = []
  for (const variants of bySlug.values()) {
    const release = pickLocale(variants, locale)
    if (release) list.push(release)
  }
  return list.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
}

export function getRelease(slug: string, locale: Locale): ChangelogRelease | undefined {
  const variants = bySlug.get(slug)
  if (!variants) return undefined
  return pickLocale(variants, locale)
}

export function getAdjacentReleases(
  slug: string,
  locale: Locale,
): { prev?: ChangelogRelease; next?: ChangelogRelease } {
  const all = getAllReleases(locale)
  const i = all.findIndex(r => r.slug === slug)
  if (i < 0) return {}
  return { prev: all[i - 1], next: all[i + 1] }
}
