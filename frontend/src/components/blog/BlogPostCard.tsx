import { Link } from 'react-router-dom'
import { Clock } from 'lucide-react'
import type { BlogPost } from '../../lib/blog'
import { useI18n } from '../../i18n/useI18n'
import { cn } from '../../lib/utils'

function useCategoryLabel() {
  const { t } = useI18n()
  return (category: string) =>
    (t.blog.categories as Record<string, string>)[category] ?? category
}

interface BlogPostCardProps {
  post: BlogPost
  featured?: boolean
}

export function BlogPostCard({ post, featured = false }: BlogPostCardProps) {
  const { t } = useI18n()
  const categoryLabel = useCategoryLabel()
  const to = `/blog/${encodeURIComponent(post.slug)}`

  const categoryPill = (
    <span className="rounded-full bg-[#3b5bdb]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#3b5bdb]">
      {categoryLabel(post.category)}
    </span>
  )
  const readingTime = (
    <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
      <Clock size={11} />
      {t.blog.readingTime(post.readingTime)}
    </span>
  )

  if (featured) {
    return (
      <Link
        to={to}
        data-testid={`blog-card-${post.slug}`}
        className="group grid overflow-hidden rounded-2xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:shadow-md md:grid-cols-[320px_1fr]"
      >
        <div className="relative aspect-[16/10] overflow-hidden bg-gradient-to-br from-[#e0e7ff] to-[#c7d2fe] md:aspect-auto">
          {post.cover && (
            <img
              src={post.cover}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            />
          )}
          <span className="absolute left-3 top-3 rounded-full bg-white/85 px-2.5 py-0.5 text-[11px] font-semibold text-[#3b5bdb] backdrop-blur">
            {t.blog.featured}
          </span>
        </div>
        <div className="flex flex-col gap-3 p-6">
          <div className="flex items-center gap-3">
            {categoryPill}
            <span className="text-[11px] text-slate-400">{post.date}</span>
            {readingTime}
          </div>
          <h3 className="text-xl font-bold leading-snug tracking-tight text-slate-900 transition-colors group-hover:text-[#3b5bdb]">
            {post.title}
          </h3>
          <p className="line-clamp-3 text-sm leading-relaxed text-slate-500">{post.summary}</p>
          <div className="mt-auto flex flex-wrap gap-2 pt-1">
            {post.tags.slice(0, 4).map(tag => (
              <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
                #{tag}
              </span>
            ))}
          </div>
        </div>
      </Link>
    )
  }

  return (
    <Link
      to={to}
      data-testid={`blog-card-${post.slug}`}
      className="group flex flex-col rounded-xl border border-[#e5e7eb] bg-white p-5 shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-2">
        {categoryPill}
        {readingTime}
      </div>
      <h3 className="mt-3 line-clamp-2 text-[15px] font-semibold leading-snug text-slate-800 transition-colors group-hover:text-[#3b5bdb]">
        {post.title}
      </h3>
      <p className="mt-2 line-clamp-3 flex-1 text-[13px] leading-relaxed text-slate-500">
        {post.summary}
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
        <span>{post.date}</span>
        {post.tags.slice(0, 2).map(tag => (
          <span key={tag} className={cn('rounded-full bg-slate-100 px-2 py-0.5 text-slate-500')}>
            #{tag}
          </span>
        ))}
      </div>
    </Link>
  )
}
