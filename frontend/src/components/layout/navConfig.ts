import { useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AudioLines,
  BookOpen,
  BookUser,
  Bot,
  Braces,
  Captions,
  Clapperboard,
  Eraser,
  FileDown,
  FlaskConical,
  Gauge,
  Globe,
  Languages,
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  Mic,
  Music,
  PlusCircle,
  ScanEye,
  ScanSearch,
  ScanText,
  Settings,
  Stamp,
  Subtitles,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { atomicToolsApi } from '../../api/atomic-tools'
import { collapseSubtitleOutputTools, getToolDisplayName } from '../../lib/atomicToolsDisplay'
import { useI18n } from '../../i18n/useI18n'
import type { ToolInfo } from '../../types/atomic-tools'

export const LAB_URL =
  (import.meta as { env?: Record<string, string | undefined> }).env?.VITE_LAB_URL ||
  'http://localhost:8799'

const TOOL_ICON_MAP: Record<string, LucideIcon> = {
  AudioLines,
  Captions,
  Clapperboard,
  Eraser,
  FileDown,
  Globe,
  Languages,
  MessageSquareText,
  Mic,
  Music,
  ScanEye,
  ScanSearch,
  ScanText,
  Stamp,
  Subtitles,
}

export function resolveToolIcon(name: string): LucideIcon {
  return TOOL_ICON_MAP[name] ?? Wrench
}

export function normalizePathname(pathname: string) {
  if (pathname === '/') return pathname
  return pathname.replace(/\/+$/, '')
}

export interface NavSubItem {
  to: string
  label: string
  icon: LucideIcon
  isActive: boolean
}

export interface NavSimpleItem {
  key: string
  to: string
  label: string
  icon: LucideIcon
  isActive: boolean
  external?: boolean
}

export interface NavConfig {
  dashboard: NavSimpleItem
  taskCenter: {
    label: string
    icon: LucideIcon
    isActive: boolean
    items: NavSubItem[]
  }
  tools: {
    label: string
    icon: LucideIcon
    isActive: boolean
    items: NavSubItem[]
  }
  worksLibrary: NavSimpleItem
  characterLibrary: NavSimpleItem
  evaluation: NavSimpleItem
  blog: NavSimpleItem
  apiDocs: NavSimpleItem
  lab: NavSimpleItem
  settings: NavSimpleItem
  routeFlags: {
    isPipelineTaskRoute: boolean
    isNewTaskRoute: boolean
    isAtomicJobsRoute: boolean
    isAiTaskRoute: boolean
    isTaskCenterRoute: boolean
    isToolsRoute: boolean
  }
}

export function useNavConfig(): NavConfig {
  const { t, locale } = useI18n()
  const { pathname } = useLocation()
  const currentPath = normalizePathname(pathname)

  const isNewTaskRoute = currentPath === '/tasks/new' || currentPath.startsWith('/tasks/new/')
  const isPipelineTaskRoute =
    currentPath === '/tasks' || (currentPath.startsWith('/tasks/') && !isNewTaskRoute)
  const isAtomicJobsRoute =
    currentPath === '/tools/jobs' || currentPath.startsWith('/tools/jobs/')
  const isAiTaskRoute =
    currentPath === '/assistant/tasks' || currentPath.startsWith('/assistant/tasks/')
  const isTaskCenterRoute =
    isPipelineTaskRoute || isNewTaskRoute || isAtomicJobsRoute || isAiTaskRoute
  const isToolsRoute =
    currentPath === '/tools' || (currentPath.startsWith('/tools/') && !isAtomicJobsRoute)

  const toolLabels = t.atomicTools.tools as Record<string, string | undefined>
  const { data: tools } = useQuery({
    queryKey: ['atomic-tools'],
    queryFn: atomicToolsApi.listTools,
    staleTime: 30_000,
  })

  return useMemo<NavConfig>(() => {
    const toolNavItems: NavSubItem[] = collapseSubtitleOutputTools(tools ?? []).map(
      (tool: ToolInfo) => {
        const isSubtitleOutput =
          tool.tool_id === 'subtitle-burn' || tool.tool_id === 'subtitle-embed'
        const label = isSubtitleOutput
          ? getToolDisplayName(tool, locale, t.atomicTools)
          : toolLabels[tool.tool_id] ?? (locale === 'zh-CN' ? tool.name_zh : tool.name_en)
        const isActive = isSubtitleOutput
          ? currentPath === '/tools/subtitle-burn' || currentPath === '/tools/subtitle-embed'
          : currentPath === `/tools/${tool.tool_id}`
        return {
          to: `/tools/${tool.tool_id}`,
          label,
          icon: resolveToolIcon(tool.icon),
          isActive,
        }
      },
    )

    const taskCenterItems: NavSubItem[] = [
      {
        to: '/tasks',
        label: t.nav.pipelineTasks,
        icon: ListChecks,
        isActive: isPipelineTaskRoute,
      },
      {
        to: '/tools/jobs',
        label: t.nav.atomicTasks,
        icon: ListChecks,
        isActive: isAtomicJobsRoute,
      },
      {
        to: '/assistant/tasks',
        label: t.nav.aiTasks,
        icon: Bot,
        isActive: isAiTaskRoute,
      },
      {
        to: '/tasks/new',
        label: t.nav.newPipelineTask,
        icon: PlusCircle,
        isActive: isNewTaskRoute,
      },
    ]

    const toolItems: NavSubItem[] = [
      {
        to: '/tools',
        label: t.atomicJobs.library,
        icon: Wrench,
        isActive: currentPath === '/tools',
      },
      ...toolNavItems,
    ]

    return {
      dashboard: {
        key: 'dashboard',
        to: '/',
        label: t.nav.dashboard,
        icon: LayoutDashboard,
        isActive: currentPath === '/',
      },
      taskCenter: {
        label: t.nav.taskCenter,
        icon: ListChecks,
        isActive: isTaskCenterRoute,
        items: taskCenterItems,
      },
      tools: {
        label: t.atomicTools.title,
        icon: Wrench,
        isActive: isToolsRoute,
        items: toolItems,
      },
      worksLibrary: {
        key: 'works-library',
        to: '/works',
        label: t.nav.worksLibrary,
        icon: Clapperboard,
        isActive: currentPath === '/works',
      },
      characterLibrary: {
        key: 'character-library',
        to: '/character-library',
        label: t.nav.characterLibrary,
        icon: BookUser,
        isActive: currentPath === '/character-library',
      },
      evaluation: {
        key: 'evaluation',
        to: '/evaluation',
        label: t.nav.evaluation,
        icon: Gauge,
        isActive: currentPath === '/evaluation' || currentPath.startsWith('/evaluation/'),
      },
      blog: {
        key: 'blog',
        to: '/blog',
        label: t.nav.blog,
        icon: BookOpen,
        isActive: currentPath === '/blog' || currentPath.startsWith('/blog/'),
      },
      apiDocs: {
        key: 'api-docs',
        to: '/api-docs',
        label: t.nav.apiDocs,
        icon: Braces,
        isActive: currentPath === '/api-docs',
      },
      lab: {
        key: 'lab',
        to: '/lab',
        label: t.nav.lab,
        icon: FlaskConical,
        isActive: currentPath === '/lab' || currentPath.startsWith('/lab/'),
      },
      settings: {
        key: 'settings',
        to: '/settings',
        label: t.nav.settings,
        icon: Settings,
        isActive: currentPath === '/settings',
      },
      routeFlags: {
        isPipelineTaskRoute,
        isNewTaskRoute,
        isAtomicJobsRoute,
        isAiTaskRoute,
        isTaskCenterRoute,
        isToolsRoute,
      },
    }
  }, [
    currentPath,
    locale,
    isAiTaskRoute,
    isAtomicJobsRoute,
    isNewTaskRoute,
    isPipelineTaskRoute,
    isTaskCenterRoute,
    isToolsRoute,
    toolLabels,
    tools,
    t,
  ])
}
