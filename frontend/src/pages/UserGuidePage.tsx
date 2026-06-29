import { isValidElement, useMemo, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Bot,
  Clapperboard,
  Clock,
  Compass,
  Download,
  Gauge,
  GraduationCap,
  HelpCircle,
  Library,
  ListTree,
  Rocket,
  Settings,
  Sparkles,
  Wrench,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import {
  getAdjacentChapters,
  getAllChapters,
  getFirstChapter,
  getGuideChapter,
  getGuideSections,
  slugifyHeading,
  type GuideChapter,
} from '../lib/guide'
import { useI18n } from '../i18n/useI18n'
import { cn } from '../lib/utils'
import '../components/blog/prose.css'

// ── Markdown rendering (shared shape with the blog reader) ──────────────────

function toText(node: ReactNode): string {
  if (node == null || node === false || node === true) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(toText).join('')
  if (isValidElement(node)) return toText((node.props as { children?: ReactNode }).children)
  return ''
}

const markdownComponents: Components = {
  h2({ children }) {
    return <h2 id={slugifyHeading(toText(children))}>{children}</h2>
  },
  h3({ children }) {
    return <h3 id={slugifyHeading(toText(children))}>{children}</h3>
  },
  a({ href, children }) {
    const url = typeof href === 'string' ? href : ''
    // App-internal links (e.g. cross-chapter `/guide/...`) route client-side;
    // `#anchor` links scroll in place; http(s) links open in a new tab.
    if (url.startsWith('/') && !url.startsWith('//')) {
      return <Link to={url}>{children}</Link>
    }
    const external = /^https?:/i.test(url)
    return (
      <a href={url} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
        {children}
      </a>
    )
  },
  img({ src, alt }) {
    return <img src={typeof src === 'string' ? src : ''} alt={alt ?? ''} loading="lazy" />
  },
  // An image-only paragraph becomes a <figure>; the italic paragraph right after
  // it is styled as the caption (see prose.css).
  p(props) {
    const node = (
      props as {
        node?: { children?: Array<{ type?: string; tagName?: string; value?: string }> }
      }
    ).node
    const kids = (node?.children ?? []).filter(
      child => !(child.type === 'text' && !String(child.value ?? '').trim()),
    )
    const isImageOnly = kids.length === 1 && kids[0].type === 'element' && kids[0].tagName === 'img'
    if (isImageOnly) return <figure className="blog-fig">{props.children}</figure>
    return <p>{props.children}</p>
  },
}

// ── Chapter icons (frontmatter `icon:` resolves to a lucide glyph) ──────────

const CHAPTER_ICONS: Record<string, LucideIcon> = {
  Rocket,
  Compass,
  Workflow,
  Wrench,
  Bot,
  Clapperboard,
  Gauge,
  Library,
  Settings,
  HelpCircle,
  Sparkles,
  BookOpen,
}

function chapterIcon(name?: string): LucideIcon {
  return (name && CHAPTER_ICONS[name]) || GraduationCap
}

// Render a resolved lucide icon through a prop so call sites never bind a
// freshly-called component to a capitalized const during render.
function Glyph({
  icon: Icon,
  size,
  className,
}: {
  icon: LucideIcon
  size?: number
  className?: string
}) {
  return <Icon size={size} className={className} />
}

// ── Page ────────────────────────────────────────────────────────────────────

export function UserGuidePage() {
  const { slug } = useParams()
  const { t, locale } = useI18n()
  const navigate = useNavigate()

  const sections = useMemo(() => getGuideSections(locale), [locale])
  const chapters = useMemo(() => getAllChapters(locale), [locale])
  const first = useMemo(() => getFirstChapter(locale), [locale])
  const chapter = slug ? getGuideChapter(slug, locale) : undefined

  if (slug && !chapter) {
    return (
      <PageContainer className="max-w-[48rem]">
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-20 text-center">
          <div className="text-base font-medium text-slate-700">{t.guide.notFound.title}</div>
          <div className="max-w-md text-sm text-slate-500">{t.guide.notFound.description}</div>
          <Link
            to="/guide"
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-[#3451c7]"
          >
            <ArrowLeft size={14} />
            {t.guide.notFound.back}
          </Link>
        </div>
      </PageContainer>
    )
  }

  const showToc = !!chapter && chapter.toc.length > 0

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      {/* Mobile chapter picker */}
      <div className="mb-4 lg:hidden">
        <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-500">
          <ListTree size={13} />
          {t.guide.mobilePick}
        </label>
        <select
          value={slug ?? ''}
          onChange={e => navigate(e.target.value ? `/guide/${e.target.value}` : '/guide')}
          className="w-full rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-sm text-slate-700 focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
        >
          <option value="">{t.guide.overviewNav}</option>
          {chapters.map(c => (
            <option key={c.slug} value={c.slug}>
              {c.title}
            </option>
          ))}
        </select>
      </div>

      <div
        className={cn(
          'grid gap-x-9 gap-y-6 lg:grid-cols-[14.5rem_minmax(0,1fr)]',
          showToc && 'xl:grid-cols-[14.5rem_minmax(0,1fr)_13rem]',
        )}
      >
        <GuideRail sections={sections} activeSlug={slug} />

        <main className="min-w-0">
          {chapter ? (
            <ChapterView chapter={chapter} />
          ) : (
            <Overview sections={sections} firstSlug={first?.slug} />
          )}
        </main>

        {showToc && (
          <nav className="hidden xl:block print:hidden" aria-label={t.guide.tocTitle}>
            <div className="sticky top-[80px]">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {t.guide.tocTitle}
              </div>
              {chapter!.toc.map(item => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className="block border-l-2 border-[#e5e7eb] py-1.5 pl-3 text-[13px] leading-snug text-slate-500 transition-colors hover:border-[#3b5bdb] hover:text-[#3b5bdb]"
                >
                  {item.text}
                </a>
              ))}
            </div>
          </nav>
        )}
      </div>
    </PageContainer>
  )
}

// ── Left rail ────────────────────────────────────────────────────────────────

function GuideRail({
  sections,
  activeSlug,
}: {
  sections: ReturnType<typeof getGuideSections>
  activeSlug?: string
}) {
  const { t } = useI18n()
  return (
    <aside className="hidden lg:block print:hidden">
      <div className="sticky top-[80px] max-h-[calc(100vh-100px)] overflow-y-auto pb-6 pr-1">
        <Link
          to="/guide"
          className={cn(
            'mb-3 flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition-colors',
            !activeSlug
              ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
          )}
        >
          <Compass size={15} className="shrink-0" />
          {t.guide.overviewNav}
        </Link>
        {sections.map(section => (
          <div key={section.name} className="mb-4">
            {section.name && (
              <div className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {section.name}
              </div>
            )}
            <div className="space-y-0.5">
              {section.chapters.map(c => {
                const active = c.slug === activeSlug
                return (
                  <Link
                    key={c.slug}
                    to={`/guide/${c.slug}`}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px] font-medium transition-colors',
                      active
                        ? 'bg-[#3b5bdb]/10 text-[#3b5bdb]'
                        : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
                    )}
                  >
                    <Glyph icon={chapterIcon(c.icon)} size={14} className="shrink-0" />
                    <span className="truncate">{c.title}</span>
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}

// ── Overview landing ─────────────────────────────────────────────────────────

function Overview({
  sections,
  firstSlug,
}: {
  sections: ReturnType<typeof getGuideSections>
  firstSlug?: string
}) {
  const { t } = useI18n()
  const numberBySlug = useMemo(() => {
    const flat = sections.flatMap(s => s.chapters)
    return new Map(flat.map((c, i) => [c.slug, i + 1]))
  }, [sections])
  return (
    <div>
      <section className="overflow-hidden rounded-2xl border border-[#e5e7eb] bg-gradient-to-br from-[#0f172a] via-[#1e293b] to-[#3b5bdb] px-7 py-9 text-white shadow-sm">
        <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-200">
          <GraduationCap size={13} />
          {t.guide.heroKicker}
        </div>
        <h1 className="text-[30px] font-bold leading-tight tracking-tight">{t.guide.title}</h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-slate-200">
          {t.guide.subtitle}
        </p>
        {firstSlug && (
          <Link
            to={`/guide/${firstSlug}`}
            className="mt-6 inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-[#1e293b] transition-all hover:bg-blue-50"
          >
            <Rocket size={15} />
            {t.guide.startReading}
          </Link>
        )}
      </section>

      <figure className="blog-fig mt-7 overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)]">
        <img src="/guide/flow-choose-path.svg" alt={t.guide.pathDiagramAlt} className="block w-full" />
      </figure>
      <p className="mt-2 px-1 text-[12.5px] leading-relaxed text-slate-500">
        {t.guide.pathDiagramCaption}
      </p>

      {sections.map(section => (
        <section key={section.name} className="mt-9">
          {section.name && (
            <h2 className="mb-3 text-[15px] font-semibold tracking-tight text-slate-900">
              {section.name}
            </h2>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {section.chapters.map(c => {
              const n = numberBySlug.get(c.slug) ?? 0
              return (
                <Link
                  key={c.slug}
                  to={`/guide/${c.slug}`}
                  className="group flex flex-col gap-2 rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:border-[#3b5bdb]/40 hover:shadow-md"
                >
                  <div className="flex items-center gap-2.5">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#3b5bdb]/10 text-[#3b5bdb]">
                      <Glyph icon={chapterIcon(c.icon)} size={16} />
                    </span>
                    <span className="text-[11px] font-semibold text-slate-400">
                      {String(n).padStart(2, '0')}
                    </span>
                    <span className="text-[15px] font-semibold text-slate-800 transition-colors group-hover:text-[#3b5bdb]">
                      {c.title}
                    </span>
                  </div>
                  <p className="line-clamp-2 text-[13px] leading-relaxed text-slate-500">
                    {c.summary}
                  </p>
                  <span className="mt-auto inline-flex items-center gap-1 text-[12.5px] font-medium text-[#3b5bdb] opacity-0 transition-opacity group-hover:opacity-100">
                    {t.guide.cardCta}
                    <ArrowRight size={13} />
                  </span>
                </Link>
              )
            })}
          </div>
        </section>
      ))}
    </div>
  )
}

// ── Chapter reader ───────────────────────────────────────────────────────────

function ChapterView({ chapter }: { chapter: GuideChapter }) {
  const { t, locale } = useI18n()
  const { prev, next } = getAdjacentChapters(chapter.slug, locale)

  return (
    <article className="min-w-0">
      <div className="flex items-center gap-1.5 text-[12.5px] text-slate-400 print:hidden">
        <Link to="/guide" className="transition-colors hover:text-[#3b5bdb]">
          {t.guide.title}
        </Link>
        {chapter.section && (
          <>
            <span>/</span>
            <span className="text-slate-500">{chapter.section}</span>
          </>
        )}
      </div>

      <header className="mt-3">
        <div className="flex items-start gap-3">
          <span className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#3b5bdb]/10 text-[#3b5bdb]">
            <Glyph icon={chapterIcon(chapter.icon)} size={19} />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="text-[30px] font-bold leading-tight tracking-tight text-slate-900">
              {chapter.title}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1">
                <Clock size={12} />
                {t.guide.readingTime(chapter.readingTime)}
              </span>
              <button
                type="button"
                onClick={() => window.print()}
                className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-[12px] font-medium text-slate-600 transition-colors hover:border-[#3b5bdb] hover:text-[#3b5bdb] print:hidden"
              >
                <Download size={13} />
                {t.guide.exportPdf}
              </button>
            </div>
          </div>
        </div>
      </header>

      <hr className="my-6 border-[#e5e7eb]" />

      <div className="blog-prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {chapter.body}
        </ReactMarkdown>
      </div>

      <hr className="my-8 border-[#e5e7eb] print:hidden" />
      <div className="grid gap-4 sm:grid-cols-2 print:hidden">
        <AdjacentLink chapter={prev} label={t.guide.prev} direction="prev" />
        <AdjacentLink chapter={next} label={t.guide.next} direction="next" />
      </div>
    </article>
  )
}

function AdjacentLink({
  chapter,
  label,
  direction,
}: {
  chapter?: GuideChapter
  label: string
  direction: 'prev' | 'next'
}) {
  if (!chapter) return <div className="hidden sm:block" />
  const alignRight = direction === 'next'
  return (
    <Link
      to={`/guide/${chapter.slug}`}
      className={cn(
        'group flex flex-col gap-1 rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:shadow-md',
        alignRight && 'sm:text-right',
      )}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1 text-[11px] font-medium text-slate-400',
          alignRight && 'sm:justify-end',
        )}
      >
        {direction === 'prev' && <ArrowLeft size={12} />}
        {label}
        {direction === 'next' && <ArrowRight size={12} />}
      </span>
      <span className="line-clamp-2 text-sm font-semibold text-slate-800 transition-colors group-hover:text-[#3b5bdb]">
        {chapter.title}
      </span>
    </Link>
  )
}
