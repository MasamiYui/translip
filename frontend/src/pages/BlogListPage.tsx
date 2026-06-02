import { useMemo, useState, type ReactNode } from 'react'
import { BookOpen, Search } from 'lucide-react'
import { APP_CONTENT_MAX_WIDTH, PageContainer } from '../components/layout/PageContainer'
import { BlogPostCard } from '../components/blog/BlogPostCard'
import { getAllPosts, getCategories } from '../lib/blog'
import { useI18n } from '../i18n/useI18n'
import { cn } from '../lib/utils'

const ALL = '__all__'

export function BlogListPage() {
  const { t, locale } = useI18n()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<string>(ALL)

  const posts = useMemo(() => getAllPosts(locale), [locale])
  const categories = useMemo(() => getCategories(locale), [locale])
  const categoryLabel = (c: string) => (t.blog.categories as Record<string, string>)[c] ?? c

  const noFilter = search.trim() === '' && category === ALL

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return posts.filter(p => {
      if (category !== ALL && p.category !== category) return false
      if (!kw) return true
      return (
        p.title.toLowerCase().includes(kw) ||
        p.summary.toLowerCase().includes(kw) ||
        p.tags.some(tag => tag.toLowerCase().includes(kw))
      )
    })
  }, [posts, search, category])

  const featured = noFilter && filtered.length > 0 ? filtered[0] : null
  const grid = featured ? filtered.slice(1) : filtered

  return (
    <PageContainer className={APP_CONTENT_MAX_WIDTH}>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <BookOpen size={17} className="text-[#3b5bdb]" />
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{t.blog.title}</h1>
        </div>
        {posts.length > 0 && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            {t.blog.countHint(posts.length)}
          </span>
        )}
        <p className="basis-full text-xs text-slate-500">{t.blog.subtitle}</p>
      </div>

      {posts.length === 0 ? (
        <div
          data-testid="blog-empty"
          className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center"
        >
          <BookOpen size={32} className="text-slate-300" />
          <div className="text-base font-medium text-slate-700">{t.blog.empty.title}</div>
          <div className="max-w-md text-sm text-slate-500">{t.blog.empty.description}</div>
        </div>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[240px] flex-1">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                data-testid="blog-search"
                type="search"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder={t.blog.searchPlaceholder}
                className="w-full rounded-lg border border-[#e5e7eb] bg-white py-2 pl-9 pr-3 text-sm text-[#374151] transition-all focus:border-[#3b5bdb] focus:outline-none focus:ring-2 focus:ring-[#3b5bdb]/20"
              />
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <CategoryPill active={category === ALL} onClick={() => setCategory(ALL)}>
                {t.blog.allCategories}
              </CategoryPill>
              {categories.map(c => (
                <CategoryPill key={c} active={category === c} onClick={() => setCategory(c)}>
                  {categoryLabel(c)}
                </CategoryPill>
              ))}
            </div>
          </div>

          {filtered.length === 0 ? (
            <div
              data-testid="blog-empty-filtered"
              className="rounded-xl border border-dashed border-[#e5e7eb] bg-white px-6 py-16 text-center text-sm text-slate-400"
            >
              {t.blog.emptyFiltered}
            </div>
          ) : (
            <div className="space-y-5">
              {featured && <BlogPostCard post={featured} featured />}
              {grid.length > 0 && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {grid.map(post => (
                    <BlogPostCard key={post.slug} post={post} />
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </PageContainer>
  )
}

function CategoryPill({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full px-3 py-1.5 text-xs font-medium transition-all',
        active
          ? 'bg-[#3b5bdb] text-white shadow-[0_1px_3px_rgba(59,91,219,.35)]'
          : 'border border-[#e5e7eb] bg-white text-slate-500 hover:bg-[#f9fafb] hover:text-slate-700',
      )}
    >
      {children}
    </button>
  )
}
