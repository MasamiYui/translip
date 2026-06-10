import { isValidElement, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Clock, Sparkles, Tag } from 'lucide-react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PageContainer } from '../components/layout/PageContainer'
import {
  getAdjacentReleases,
  getRelease,
  slugify,
  type ChangelogRelease,
} from '../lib/changelog'
import { useI18n } from '../i18n/useI18n'
import '../components/blog/prose.css'

function toText(node: ReactNode): string {
  if (node == null || node === false || node === true) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(toText).join('')
  if (isValidElement(node)) return toText((node.props as { children?: ReactNode }).children)
  return ''
}

const markdownComponents: Components = {
  h2({ children }) {
    return <h2 id={slugify(toText(children))}>{children}</h2>
  },
  h3({ children }) {
    return <h3 id={slugify(toText(children))}>{children}</h3>
  },
  a({ href, children }) {
    const external = !!href && /^https?:/i.test(href)
    return (
      <a href={href} {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}>
        {children}
      </a>
    )
  },
  img({ src, alt }) {
    return <img src={typeof src === 'string' ? src : ''} alt={alt ?? ''} loading="lazy" />
  },
  p(props) {
    const node = (props as { node?: { children?: Array<{ type?: string; tagName?: string; value?: string }> } }).node
    const kids = (node?.children ?? []).filter(
      child => !(child.type === 'text' && !String(child.value ?? '').trim()),
    )
    const isImageOnly = kids.length === 1 && kids[0].type === 'element' && kids[0].tagName === 'img'
    if (isImageOnly) return <figure className="blog-fig">{props.children}</figure>
    return <p>{props.children}</p>
  },
}

export function ChangelogDetailPage() {
  const { slug = '' } = useParams()
  const { t, locale } = useI18n()
  const release = getRelease(slug, locale)

  if (!release) {
    return (
      <PageContainer className="max-w-[48rem]">
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-20 text-center">
          <div className="text-base font-medium text-slate-700">
            {t.settings.changelog.notFound.title}
          </div>
          <div className="max-w-md text-sm text-slate-500">
            {t.settings.changelog.notFound.description}
          </div>
          <Link
            to="/settings"
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-[#3451c7]"
          >
            <ArrowLeft size={14} />
            {t.settings.changelog.notFound.back}
          </Link>
        </div>
      </PageContainer>
    )
  }

  const { prev, next } = getAdjacentReleases(release.slug, locale)

  return (
    <PageContainer className="max-w-[64rem]">
      <Link
        to="/settings"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-[#3b5bdb] print:hidden"
      >
        <ArrowLeft size={15} />
        {t.settings.changelog.backToSettings}
      </Link>

      <header className="mt-6">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1 rounded-md bg-[#3b5bdb]/10 px-2 py-0.5 text-[12px] font-semibold text-[#3b5bdb]">
            <Tag size={12} />
            {release.version}
          </span>
          {release.tag && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
              {release.tag}
            </span>
          )}
          {release.date && <span>{release.date}</span>}
          <span className="inline-flex items-center gap-1">
            <Clock size={12} />
            {t.settings.changelog.readingTime(release.readingTime)}
          </span>
        </div>
        <h1 className="mt-3 text-[32px] font-bold leading-tight tracking-tight text-slate-900">
          {release.title}
        </h1>
        {release.summary && (
          <p className="mt-3 text-[15px] leading-relaxed text-slate-600">{release.summary}</p>
        )}
        {release.highlights.length > 0 && (
          <div className="mt-5 rounded-xl border border-[#e5e7eb] bg-gradient-to-br from-[#f5f7ff] to-white p-4">
            <div className="mb-2 inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-[#3b5bdb]">
              <Sparkles size={12} />
              {t.settings.changelog.highlightsTitle}
            </div>
            <ul className="grid gap-1.5 text-sm text-slate-700 sm:grid-cols-2">
              {release.highlights.map(item => (
                <li key={item} className="flex items-start gap-2">
                  <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[#3b5bdb]" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </header>

      <hr className="my-6 border-[#e5e7eb]" />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_13rem] print:block">
        <article className="blog-prose">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {release.body}
          </ReactMarkdown>
        </article>

        {release.toc.length > 0 && (
          <nav className="hidden lg:block print:hidden" aria-label={t.settings.changelog.tocTitle}>
            <div className="sticky top-[80px]">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {t.settings.changelog.tocTitle}
              </div>
              {release.toc.map(item => (
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

      {(prev || next) && (
        <>
          <hr className="my-8 border-[#e5e7eb] print:hidden" />
          <div className="grid gap-4 sm:grid-cols-2 print:hidden">
            <AdjacentLink release={prev} label={t.settings.changelog.prev} direction="prev" />
            <AdjacentLink release={next} label={t.settings.changelog.next} direction="next" />
          </div>
        </>
      )}
    </PageContainer>
  )
}

function AdjacentLink({
  release,
  label,
  direction,
}: {
  release?: ChangelogRelease
  label: string
  direction: 'prev' | 'next'
}) {
  if (!release) return <div className="hidden sm:block" />
  const alignRight = direction === 'next'
  return (
    <Link
      to={`/changelog/${encodeURIComponent(release.slug)}`}
      className={`group flex flex-col gap-1 rounded-xl border border-[#e5e7eb] bg-white p-4 shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:shadow-md ${
        alignRight ? 'sm:text-right' : ''
      }`}
    >
      <span
        className={`inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 ${
          alignRight ? 'sm:justify-end' : ''
        }`}
      >
        {direction === 'prev' && <ArrowLeft size={12} />}
        {label}
        {direction === 'next' && <ArrowRight size={12} />}
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="rounded-md bg-[#3b5bdb]/10 px-1.5 py-0.5 text-[11px] font-semibold text-[#3b5bdb]">
          {release.version}
        </span>
        <span className="line-clamp-1 text-sm font-semibold text-slate-800 transition-colors group-hover:text-[#3b5bdb]">
          {release.title}
        </span>
      </span>
    </Link>
  )
}
