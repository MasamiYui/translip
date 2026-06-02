import { Link } from 'react-router-dom'
import { Clock } from 'lucide-react'
import type { BlogPost } from '../../lib/blog'
import { useI18n } from '../../i18n/useI18n'

function useCategoryLabel() {
  const { t } = useI18n()
  return (category: string) =>
    (t.blog.categories as Record<string, string>)[category] ?? category
}

interface BlogPostCardProps {
  post: BlogPost
}

export function BlogPostCard({ post }: BlogPostCardProps) {
  const { t } = useI18n()
  const categoryLabel = useCategoryLabel()
  const to = `/blog/${encodeURIComponent(post.slug)}`

  return (
    <Link
      to={to}
      data-testid={`blog-card-${post.slug}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-[#e5e7eb] bg-white shadow-[0_1px_3px_rgba(0,0,0,.04)] transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-gradient-to-br from-[#e0e7ff] to-[#c7d2fe]">
        {post.cover && (
          <img
            src={post.cover}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2.5 p-5">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="rounded-full bg-[#3b5bdb]/10 px-2.5 py-0.5 text-[11px] font-semibold text-[#3b5bdb]">
            {categoryLabel(post.category)}
          </span>
          <span className="text-[11px] text-slate-400">{post.date}</span>
          <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
            <Clock size={11} />
            {t.blog.readingTime(post.readingTime)}
          </span>
        </div>
        <h3 className="line-clamp-2 text-base font-semibold leading-snug tracking-tight text-slate-900 transition-colors group-hover:text-[#3b5bdb]">
          {post.title}
        </h3>
        <p className="line-clamp-3 text-[13px] leading-relaxed text-slate-500">{post.summary}</p>
        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          {post.tags.slice(0, 3).map(tag => (
            <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500">
              #{tag}
            </span>
          ))}
        </div>
      </div>
    </Link>
  )
}
