import { DEFAULT_LOCALE, SUPPORTED_LOCALES, type Locale } from '../i18n/messages'

export interface BlogPost {
  /** Stable id from frontmatter `slug` (falls back to the filename stem). */
  slug: string
  locale: Locale
  title: string
  date: string
  category: string
  tags: string[]
  summary: string
  cover?: string
  author?: string
  /** Minutes; from frontmatter `readingTime`, else estimated from the body. */
  readingTime: number
  /** Markdown body with the frontmatter block stripped. */
  body: string
  /** A short heading list (level-2) for an on-page table of contents. */
  toc: TocItem[]
}

export interface TocItem {
  id: string
  text: string
}

// All posts are authored as `src/content/blog/<slug>.<locale>.md` and bundled
// at build time. Images they reference live under `public/blog/<slug>/...` and
// are addressed with production-absolute paths (`/blog/<slug>/fig.png`).
const rawModules = import.meta.glob('../content/blog/*.md', {
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
    // strip wrapping quotes on scalars
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
    .replace(/```[\s\S]*?```/g, ' ') // drop fenced code
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ') // drop images
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
    const text = m[1].replace(/`/g, '').trim() // inline code renders without backticks
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

function toPost(path: string, raw: string): BlogPost | null {
  const named = parseFilename(path)
  if (!named) return null
  const { data, body } = parseFrontmatter(raw)
  const tags = Array.isArray(data.tags) ? (data.tags as string[]) : []
  const readingTime = Number(data.readingTime) > 0 ? Number(data.readingTime) : estimateReadingTime(body)
  return {
    slug: typeof data.slug === 'string' && data.slug ? data.slug : named.slug,
    locale: named.locale,
    title: String(data.title ?? named.slug),
    date: String(data.date ?? ''),
    category: String(data.category ?? ''),
    tags,
    summary: String(data.summary ?? ''),
    cover: typeof data.cover === 'string' ? data.cover : undefined,
    author: typeof data.author === 'string' ? data.author : undefined,
    readingTime,
    body,
    toc: buildToc(body),
  }
}

// slug -> (locale -> post)
const bySlug: Map<string, Map<Locale, BlogPost>> = (() => {
  const map = new Map<string, Map<Locale, BlogPost>>()
  for (const [path, raw] of Object.entries(rawModules)) {
    const post = toPost(path, raw)
    if (!post) continue
    if (!map.has(post.slug)) map.set(post.slug, new Map())
    map.get(post.slug)!.set(post.locale, post)
  }
  return map
})()

function pickLocale(variants: Map<Locale, BlogPost>, locale: Locale): BlogPost | undefined {
  return variants.get(locale) ?? variants.get(DEFAULT_LOCALE) ?? [...variants.values()][0]
}

/** All posts for a locale (with fallback), newest first. */
export function getAllPosts(locale: Locale): BlogPost[] {
  const posts: BlogPost[] = []
  for (const variants of bySlug.values()) {
    const post = pickLocale(variants, locale)
    if (post) posts.push(post)
  }
  return posts.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
}

export function getPost(slug: string, locale: Locale): BlogPost | undefined {
  const variants = bySlug.get(slug)
  if (!variants) return undefined
  return pickLocale(variants, locale)
}

/** Distinct categories present across posts, in first-seen order. */
export function getCategories(locale: Locale): string[] {
  const out: string[] = []
  for (const post of getAllPosts(locale)) {
    if (post.category && !out.includes(post.category)) out.push(post.category)
  }
  return out
}

/** Previous (newer) and next (older) post relative to a slug, for article footer nav. */
export function getAdjacentPosts(
  slug: string,
  locale: Locale,
): { prev?: BlogPost; next?: BlogPost } {
  const all = getAllPosts(locale)
  const i = all.findIndex(p => p.slug === slug)
  if (i < 0) return {}
  return { prev: all[i - 1], next: all[i + 1] }
}
