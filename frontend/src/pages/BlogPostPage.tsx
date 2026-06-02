import { isValidElement, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Clock } from 'lucide-react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { PageContainer } from '../components/layout/PageContainer'
import { getAdjacentPosts, getPost, slugify, type BlogPost } from '../lib/blog'
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
  // Render an image-only paragraph as a <figure>; the italic paragraph that
  // follows is styled as its caption (see prose.css).
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

export function BlogPostPage() {
  const { slug = '' } = useParams()
  const { t, locale } = useI18n()
  const post = getPost(slug, locale)

  if (!post) {
    return (
      <PageContainer className="max-w-[48rem]">
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-20 text-center">
          <div className="text-base font-medium text-slate-700">{t.blog.notFound.title}</div>
          <div className="max-w-md text-sm text-slate-500">{t.blog.notFound.description}</div>
          <Link
            to="/blog"
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-[#3b5bdb] px-4 py-2 text-sm font-semibold text-white transition-all hover:bg-[#3451c7]"
          >
            <ArrowLeft size={14} />
            {t.blog.notFound.back}
          </Link>
        </div>
      </PageContainer>
    )
  }

  const { prev, next } = getAdjacentPosts(post.slug, locale)
  const categoryLabel = (t.blog.categories as Record<string, string>)[post.category] ?? post.category

  return (
    <PageContainer className="max-w-[64rem]">
      <Link
        to="/blog"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 transition-colors hover:text-[#3b5bdb]"
      >
        <ArrowLeft size={15} />
        {t.blog.backToList}
      </Link>

      <header className="mt-6">
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span className="rounded-full bg-[#3b5bdb]/10 px-2.5 py-0.5 text-[12px] font-semibold text-[#3b5bdb]">
            {categoryLabel}
          </span>
          {post.date && <span>{post.date}</span>}
          <span className="inline-flex items-center gap-1">
            <Clock size={12} />
            {t.blog.readingTime(post.readingTime)}
          </span>
        </div>
        <h1 className="mt-3 text-[32px] font-bold leading-tight tracking-tight text-slate-900">
          {post.title}
        </h1>
        {post.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {post.tags.map(tag => (
              <span key={tag} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">
                #{tag}
              </span>
            ))}
          </div>
        )}
      </header>

      <hr className="my-6 border-[#e5e7eb]" />

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_13rem]">
        <article className="blog-prose">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {post.body}
          </ReactMarkdown>
        </article>

        {post.toc.length > 0 && (
          <nav className="hidden lg:block" aria-label={t.blog.tocTitle}>
            <div className="sticky top-[80px]">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {t.blog.tocTitle}
              </div>
              {post.toc.map(item => (
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
          <hr className="my-8 border-[#e5e7eb]" />
          <div className="grid gap-4 sm:grid-cols-2">
            <AdjacentLink post={prev} label={t.blog.prev} direction="prev" />
            <AdjacentLink post={next} label={t.blog.next} direction="next" />
          </div>
        </>
      )}
    </PageContainer>
  )
}

function AdjacentLink({
  post,
  label,
  direction,
}: {
  post?: BlogPost
  label: string
  direction: 'prev' | 'next'
}) {
  if (!post) return <div className="hidden sm:block" />
  const alignRight = direction === 'next'
  return (
    <Link
      to={`/blog/${encodeURIComponent(post.slug)}`}
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
      <span className="line-clamp-2 text-sm font-semibold text-slate-800 transition-colors group-hover:text-[#3b5bdb]">
        {post.title}
      </span>
    </Link>
  )
}
