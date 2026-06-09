import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../../lib/utils'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: ReactNode
  className?: string
  testId?: string
  variant?: 'default' | 'subtle'
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  testId,
  variant = 'default',
}: EmptyStateProps) {
  const isSubtle = variant === 'subtle'
  return (
    <div
      role="status"
      data-testid={testId}
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-dashed bg-white text-center',
        isSubtle
          ? 'border-[#e5e7eb] px-6 py-12'
          : 'border-[#d1d5db] px-6 py-16 sm:py-20',
        className,
      )}
    >
      <div
        className={cn(
          'mb-4 flex items-center justify-center rounded-2xl',
          isSubtle ? 'h-12 w-12 bg-[#f9fafb]' : 'h-14 w-14 bg-[#f3f4f6]',
        )}
      >
        <Icon size={isSubtle ? 22 : 24} className="text-[#9ca3af]" />
      </div>
      <div className="text-base font-semibold text-[#374151]">{title}</div>
      {description && (
        <div className="mt-1 max-w-md text-sm text-[#6b7280]">{description}</div>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
