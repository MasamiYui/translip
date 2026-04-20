import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  AudioWaveform,
  Clapperboard,
  Eraser,
  Pin,
  FileOutput,
  Film,
  Headphones,
  Languages,
  MicVocal,
  ScanText,
  Scissors,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { cn } from '../../lib/utils'
import type { StageShortKey, StatusKey } from '../../i18n/formatters'
import { useI18n } from '../../i18n/useI18n'
import type {
  WorkflowEdgeState,
  WorkflowGraph as WorkflowGraphPayload,
  WorkflowGraphNode,
  WorkflowNodeGroup,
} from '../../types'
import { WorkflowLegend } from './WorkflowLegend'

const NODE_ICON: Record<string, LucideIcon> = {
  stage1: Scissors,
  'ocr-detect': ScanText,
  'task-a': MicVocal,
  'asr-ocr-correct': ScanText,
  'task-b': Users,
  'task-c': Languages,
  'ocr-translate': FileOutput,
  'task-d': Headphones,
  'task-e': Clapperboard,
  'subtitle-erase': Eraser,
  'task-g': Film,
}

const NODE_CODE: Record<string, string> = {
  stage1: 'S1',
  'ocr-detect': 'O1',
  'task-a': 'A1',
  'asr-ocr-correct': 'A2',
  'task-b': 'B1',
  'task-c': 'C1',
  'ocr-translate': 'O2',
  'task-d': 'D1',
  'task-e': 'E1',
  'subtitle-erase': 'V1',
  'task-g': 'G1',
}

const PREVIEW_HINTS: Record<string, { zh: string; en: string }> = {
  stage1: { zh: '拆分人声与背景轨。', en: 'Separate dialogue and background.' },
  'ocr-detect': { zh: '定位画面硬字幕。', en: 'Detect hard subtitles on frame.' },
  'task-a': { zh: '生成时间对齐转写。', en: 'Create aligned transcript segments.' },
  'asr-ocr-correct': { zh: '用 OCR 字幕校正 ASR 文稿。', en: 'Correct ASR transcript text with OCR subtitles.' },
  'task-b': { zh: '补全说话人身份。', en: 'Register and reconcile speakers.' },
  'task-c': { zh: '翻译配音文本。', en: 'Translate dubbing text.' },
  'ocr-translate': { zh: '翻译展示字幕。', en: 'Translate display subtitles.' },
  'task-d': { zh: '合成目标语音轨。', en: 'Synthesize the target voice track.' },
  'task-e': { zh: '回贴时间线并混音。', en: 'Fit the dub back to timeline.' },
  'subtitle-erase': { zh: '清理原字幕画面。', en: 'Remove subtitles from video.' },
  'task-g': { zh: '汇总支线并导出。', en: 'Package branch outputs for delivery.' },
}

const STATUS_STYLES: Record<WorkflowGraphNode['status'], string> = {
  pending: 'border-slate-200/90 bg-white text-slate-700',
  running: 'border-sky-200/90 bg-white text-slate-900',
  succeeded: 'border-emerald-200/90 bg-emerald-50/45 text-slate-900',
  cached: 'border-violet-200/90 bg-violet-50/45 text-slate-900',
  failed: 'border-rose-200/90 bg-rose-50/55 text-slate-900',
  skipped: 'border-slate-200/85 bg-slate-50/85 text-slate-600',
}

const STATUS_ACCENTS: Record<
  WorkflowGraphNode['status'],
  {
    rail: string
    marker: string
    markerInner?: string
    progressTrack?: string
    progressFill?: string
    statusText: string
  }
> = {
  pending: {
    rail: 'bg-slate-200/90',
    marker: 'border border-slate-300 bg-white',
    statusText: 'text-slate-400',
  },
  running: {
    rail: 'bg-gradient-to-r from-sky-300 via-cyan-400 to-sky-300 animate-pulse',
    marker: 'border border-sky-300 bg-white',
    markerInner: 'bg-sky-500 animate-pulse',
    progressTrack: 'bg-sky-100/95',
    progressFill: 'bg-gradient-to-r from-sky-400 via-cyan-400 to-sky-500',
    statusText: 'text-sky-500/90',
  },
  succeeded: {
    rail: 'bg-gradient-to-r from-emerald-300 to-emerald-400',
    marker: 'border border-emerald-300 bg-emerald-100',
    markerInner: 'bg-emerald-500',
    statusText: 'text-emerald-500/90',
  },
  cached: {
    rail: 'bg-gradient-to-r from-violet-300 to-violet-400',
    marker: 'border border-violet-300 bg-violet-100',
    markerInner: 'bg-violet-500',
    statusText: 'text-violet-500/90',
  },
  failed: {
    rail: 'bg-gradient-to-r from-rose-300 to-rose-400',
    marker: 'border border-rose-300 bg-rose-100',
    markerInner: 'bg-rose-500',
    statusText: 'text-rose-500/90',
  },
  skipped: {
    rail: 'bg-slate-200/80',
    marker: 'border border-slate-300 bg-slate-100',
    markerInner: 'bg-slate-400',
    statusText: 'text-slate-400',
  },
}

const EDGE_STYLES: Record<WorkflowEdgeState, Partial<Edge>> = {
  inactive: {
    style: { stroke: '#CBD5E1', strokeWidth: 1.5 },
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#CBD5E1', width: 10, height: 10 },
  },
  active: {
    style: { stroke: '#38BDF8', strokeWidth: 2.2 },
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#38BDF8', width: 12, height: 12 },
  },
  completed: {
    style: { stroke: '#34D399', strokeWidth: 1.9 },
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#34D399', width: 11, height: 11 },
  },
  blocked: {
    style: { stroke: '#FB7185', strokeWidth: 1.8, strokeDasharray: '6 4' },
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#FB7185', width: 11, height: 11 },
  },
}

const PREVIEW_NODE_WIDTH = 160
const PREVIEW_NODE_HEIGHT = 82
const RUNTIME_NODE_WIDTH = 172
const RUNTIME_NODE_HEIGHT = 92
const ANCHOR_WIDTH = 118
const ANCHOR_HEIGHT = 52
const HANDLE_STYLE = { width: 8, height: 8, opacity: 0, pointerEvents: 'none' as const }
const START_NODE_ID = '__dag-start__'
const END_NODE_ID = '__dag-end__'
const MAINLINE_NODE_IDS = ['stage1', 'task-a', 'asr-ocr-correct', 'task-b', 'task-c', 'task-d', 'task-e', 'task-g'] as const

interface CompactNodeChromeProps {
  node: WorkflowGraphNode
  previewOnly: boolean
  shortLabel: string
  statusLabel: string
  focused?: boolean
  pinned?: boolean
  onHoverChange?: (nodeId: string | null) => void
  onPin?: (nodeId: string) => void
}

function CompactNodeChrome({
  node,
  previewOnly,
  shortLabel,
  statusLabel,
  focused = false,
  pinned = false,
  onHoverChange,
  onPin,
}: CompactNodeChromeProps) {
  const Icon = NODE_ICON[node.id] ?? AudioWaveform
  const showProgress = !previewOnly && node.status === 'running'
  const accents = STATUS_ACCENTS[node.status]
  const showStatusMarker = !previewOnly

  return (
    <button
      type="button"
      onClick={() => onPin?.(node.id)}
      onMouseEnter={() => onHoverChange?.(node.id)}
      onMouseLeave={() => onHoverChange?.(null)}
      onFocus={() => onHoverChange?.(node.id)}
      onBlur={() => onHoverChange?.(null)}
      aria-label={`${shortLabel} · ${statusLabel}`}
      data-ui-elevation="flat"
      data-ui-card-size="matched"
      data-ui-node-role={node.group === 'delivery' ? 'terminal' : 'workflow'}
      data-ui-node-status={node.status}
      className={cn(
        'group relative flex h-full w-full overflow-hidden rounded-[22px] border px-3.5 py-3 text-left transition-[border-color,background-color,box-shadow,transform] duration-200',
        STATUS_STYLES[node.status],
        node.required === false && 'border-dashed',
        'cursor-pointer',
        focused && 'ring-2 ring-sky-300/80 ring-offset-2 ring-offset-white',
      )}
    >
      {pinned && !previewOnly && (
        <span className="absolute bottom-3 right-3 inline-flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400">
          <Pin size={11} />
        </span>
      )}

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <span
              data-ui-node-icon="corner"
              className="mt-0.5 inline-flex shrink-0 items-center justify-center text-current/70"
            >
              <Icon size={12.5} strokeWidth={2.05} />
            </span>

            <div className="text-[10.5px] font-medium uppercase tracking-[0.2em] text-current/42">
              {NODE_CODE[node.id] ?? node.id}
            </div>
          </div>

          {showStatusMarker && (
            <span
              data-ui-status-marker=""
              className={cn(
                'mt-0.5 inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full',
                accents.marker,
              )}
            >
              {accents.markerInner ? (
                <span className={cn('h-1.5 w-1.5 rounded-full', accents.markerInner)} />
              ) : null}
            </span>
          )}
        </div>

        <div
          data-ui-title-frame=""
          className={cn(
            'min-w-0 flex-1 flex items-center justify-center',
            showProgress ? 'py-3.5' : 'py-4',
          )}
        >
          <div
            data-ui-title-scale="xl"
            className={cn(
              'whitespace-nowrap text-center font-semibold leading-[1.12] tracking-normal text-current',
              previewOnly ? 'text-[18.5px]' : 'text-[19px]',
            )}
          >
            {shortLabel}
          </div>
        </div>

        {showProgress ? (
          <div className="mt-auto pt-3.5">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-sky-500/80">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400 animate-pulse" />
                <span>{Math.round(node.progress_percent)}%</span>
              </span>
            </div>

            <div
              className={cn(
                'overflow-hidden rounded-full',
                accents.progressTrack ?? 'bg-sky-100/95',
              )}
            >
              <div
                data-ui-progress-bar=""
                className={cn(
                  'h-1 rounded-full transition-[width] duration-500 ease-out',
                  accents.progressFill ?? 'bg-sky-400',
                )}
                style={{ width: `${node.progress_percent}%` }}
              />
            </div>
          </div>
        ) : null}
      </div>
    </button>
  )
}

interface CompactFlowNodeData extends Record<string, unknown> {
  node: WorkflowGraphNode
  previewOnly: boolean
  shortLabel: string
  statusLabel: string
  isFocused: boolean
  isPinned: boolean
  onHoverChange?: (nodeId: string | null) => void
  onPin?: (nodeId: string) => void
}

function CompactFlowNode({ data }: NodeProps) {
  const d = data as CompactFlowNodeData
  const nodeWidth = d.previewOnly ? PREVIEW_NODE_WIDTH : RUNTIME_NODE_WIDTH
  const nodeHeight = d.previewOnly ? PREVIEW_NODE_HEIGHT : RUNTIME_NODE_HEIGHT

  return (
    <div style={{ width: nodeWidth, height: nodeHeight }}>
      <Handle id="left" type="target" position={Position.Left} style={HANDLE_STYLE} />
      <Handle id="right" type="source" position={Position.Right} style={HANDLE_STYLE} />
      <Handle id="top" type="target" position={Position.Top} style={HANDLE_STYLE} />
      <Handle id="bottom" type="source" position={Position.Bottom} style={HANDLE_STYLE} />

      <CompactNodeChrome
        node={d.node}
        previewOnly={d.previewOnly}
        shortLabel={d.shortLabel}
        statusLabel={d.statusLabel}
        focused={d.isFocused}
        pinned={d.isPinned}
        onHoverChange={d.onHoverChange}
        onPin={d.onPin}
      />
    </div>
  )
}

interface AnchorNodeData extends Record<string, unknown> {
  kind: 'start' | 'end'
  label: string
}

function AnchorNode({ data }: NodeProps) {
  const d = data as AnchorNodeData

  return (
    <div
      data-ui-anchor={d.kind}
      className="flex h-full w-full items-center justify-center"
    >
      {d.kind === 'end' && <Handle id="left" type="target" position={Position.Left} style={HANDLE_STYLE} />}
      {d.kind === 'start' && <Handle id="right" type="source" position={Position.Right} style={HANDLE_STYLE} />}

      <div
        data-ui-anchor-size="xl"
        className="inline-flex items-center gap-3 rounded-full border border-slate-200/90 bg-white/92 px-4 py-3 text-[12px] font-semibold uppercase tracking-[0.16em] text-slate-500"
      >
        <span
          className={cn(
            'h-3.5 w-3.5 rounded-full',
            d.kind === 'start' ? 'bg-sky-400' : 'border border-slate-300 bg-white',
          )}
        />
        <span>{d.label}</span>
      </div>
    </div>
  )
}

const NODE_TYPES: NodeTypes = {
  editorialNode: CompactFlowNode as unknown as NodeTypes['editorialNode'],
  dagAnchor: AnchorNode as unknown as NodeTypes['dagAnchor'],
}

function getPreviewHint(node: WorkflowGraphNode, locale: 'zh-CN' | 'en-US') {
  return locale === 'zh-CN'
    ? PREVIEW_HINTS[node.id]?.zh ?? '等待此节点产出。'
    : PREVIEW_HINTS[node.id]?.en ?? 'Waiting for this node.'
}

function resolveNodeHint(node: WorkflowGraphNode, locale: 'zh-CN' | 'en-US', previewOnly: boolean) {
  if (previewOnly) {
    return getPreviewHint(node, locale)
  }
  if (node.error_message) {
    return node.error_message
  }
  if (node.current_step) {
    return node.current_step
  }
  return getPreviewHint(node, locale)
}

interface DagLayoutResult {
  height: number
  positions: Record<string, { x: number; y: number }>
}

function buildCompactDagLayout(graph: WorkflowGraphPayload, previewOnly: boolean): DagLayoutResult {
  const nodeWidth = previewOnly ? PREVIEW_NODE_WIDTH : RUNTIME_NODE_WIDTH
  const nodeHeight = previewOnly ? PREVIEW_NODE_HEIGHT : RUNTIME_NODE_HEIGHT
  const gapX = previewOnly ? 24 : 30
  const mainlineY = previewOnly ? 96 : 104
  const branchY = mainlineY + nodeHeight + (previewOnly ? 34 : 40)
  const hasBranchNodes = ['ocr-detect', 'ocr-translate', 'subtitle-erase'].some(nodeId =>
    graph.nodes.some(node => node.id === nodeId),
  )
  const startX = 28
  const startGap = previewOnly ? 30 : 24
  const firstNodeX = startX + ANCHOR_WIDTH + startGap
  const positions: Record<string, { x: number; y: number }> = {}
  const presentNodeIds = new Set(graph.nodes.map(node => node.id))
  const mainlineNodeIds = hasBranchNodes
    ? MAINLINE_NODE_IDS.filter(nodeId => nodeId !== 'task-g')
    : [...MAINLINE_NODE_IDS]

  let cursorX = firstNodeX
  for (const nodeId of mainlineNodeIds) {
    if (!presentNodeIds.has(nodeId)) {
      continue
    }
    positions[nodeId] = { x: cursorX, y: mainlineY }
    cursorX += nodeWidth + gapX
  }

  if (presentNodeIds.has('ocr-detect')) {
    positions['ocr-detect'] = {
      x:
        positions['stage1']?.x != null
          ? positions['stage1'].x + Math.round((nodeWidth + gapX) * 0.52)
          : positions['task-a']?.x ?? firstNodeX + nodeWidth + gapX,
      y: branchY,
    }
  }

  if (presentNodeIds.has('ocr-translate')) {
    positions['ocr-translate'] = {
      x: positions['task-c']?.x ?? positions['ocr-detect']?.x ?? firstNodeX + (nodeWidth + gapX) * 2,
      y: branchY,
    }
  }

  if (presentNodeIds.has('subtitle-erase')) {
    positions['subtitle-erase'] = {
      x:
        positions['task-e']?.x
        ?? positions['task-d']?.x
        ?? positions['ocr-translate']?.x
        ?? positions['ocr-detect']?.x
        ?? firstNodeX + (nodeWidth + gapX) * 3,
      y: branchY,
    }
  }

  if (presentNodeIds.has('task-g')) {
    if (hasBranchNodes) {
      positions['task-g'] = {
        x: (positions['task-e']?.x ?? cursorX) + nodeWidth + gapX + (previewOnly ? 4 : 8),
        y: mainlineY + Math.round((branchY - mainlineY) * 0.58),
      }
      cursorX = positions['task-g'].x + nodeWidth
    } else if (!positions['task-g']) {
      positions['task-g'] = { x: cursorX, y: mainlineY }
      cursorX += nodeWidth + gapX
    }
  }

  const startAnchorY = mainlineY + nodeHeight / 2 - ANCHOR_HEIGHT / 2
  const endAnchorTargetY = positions['task-g']?.y ?? mainlineY
  const endAnchorY = endAnchorTargetY + nodeHeight / 2 - ANCHOR_HEIGHT / 2
  positions[START_NODE_ID] = { x: startX, y: startAnchorY }
  positions[END_NODE_ID] = { x: cursorX + 20, y: endAnchorY }

  const maxBottom = Object.entries(positions)
    .filter(([id]) => id !== START_NODE_ID && id !== END_NODE_ID)
    .reduce((bottom, [, position]) => Math.max(bottom, position.y + nodeHeight), mainlineY + nodeHeight)

  return {
    positions,
    height: maxBottom + 32,
  }
}

function getLayoutBounds(nodeId: string, previewOnly: boolean, positions: Record<string, { x: number; y: number }>) {
  const isAnchor = nodeId === START_NODE_ID || nodeId === END_NODE_ID
  const width = isAnchor ? ANCHOR_WIDTH : previewOnly ? PREVIEW_NODE_WIDTH : RUNTIME_NODE_WIDTH
  const height = isAnchor ? ANCHOR_HEIGHT : previewOnly ? PREVIEW_NODE_HEIGHT : RUNTIME_NODE_HEIGHT
  const position = positions[nodeId] ?? { x: 0, y: 0 }

  return { ...position, width, height }
}

function resolveHandles(
  sourceNodeId: string,
  targetNodeId: string,
  previewOnly: boolean,
  positions: Record<string, { x: number; y: number }>,
) {
  const source = getLayoutBounds(sourceNodeId, previewOnly, positions)
  const target = getLayoutBounds(targetNodeId, previewOnly, positions)
  const dx = target.x + target.width / 2 - (source.x + source.width / 2)
  const dy = target.y + target.height / 2 - (source.y + source.height / 2)

  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? { sourceHandle: 'right', targetHandle: 'left' }
      : { sourceHandle: 'left', targetHandle: 'right' }
  }

  return dy >= 0
    ? { sourceHandle: 'bottom', targetHandle: 'top' }
    : { sourceHandle: 'top', targetHandle: 'bottom' }
}

function edgeStateFromNodeStatus(status: WorkflowGraphNode['status']): WorkflowEdgeState {
  if (status === 'running') return 'active'
  if (status === 'failed') return 'blocked'
  if (status === 'succeeded' || status === 'cached') return 'completed'
  return 'inactive'
}

function getCompactEdgeStyle(state: WorkflowEdgeState, previewOnly: boolean): Partial<Edge> {
  if (previewOnly) {
    return {
      style: { stroke: '#CBD5E1', strokeWidth: 1.35, opacity: 0.92 },
      animated: false,
    }
  }

  return EDGE_STYLES[state]
}

function getAnchorLabel(kind: 'start' | 'end', locale: 'zh-CN' | 'en-US') {
  if (locale === 'zh-CN') {
    return kind === 'start' ? '输入源' : '最终交付'
  }

  return kind === 'start' ? 'Source' : 'Delivered'
}

function getMetaLabel(group: WorkflowNodeGroup, locale: 'zh-CN' | 'en-US') {
  if (locale === 'zh-CN') {
    switch (group) {
      case 'audio-spine':
        return '音频主干'
      case 'ocr-subtitles':
        return 'OCR 支线'
      case 'video-cleanup':
        return '净化支线'
      case 'delivery':
        return '终态输出'
      default:
        return '处理节点'
    }
  }

  switch (group) {
    case 'audio-spine':
      return 'Audio spine'
    case 'ocr-subtitles':
      return 'OCR branch'
    case 'video-cleanup':
      return 'Cleanup branch'
    case 'delivery':
      return 'Final output'
    default:
      return 'Pipeline node'
  }
}

function getFocusRailInstruction(locale: 'zh-CN' | 'en-US') {
  return locale === 'zh-CN'
    ? '悬停节点可查看说明，点击节点可锁定。'
    : 'Hover a node to inspect it, click to pin it.'
}

function getFocusRailPinnedLabel(locale: 'zh-CN' | 'en-US') {
  return locale === 'zh-CN' ? '已锁定' : 'Pinned'
}

function getFocusRailClearLabel(locale: 'zh-CN' | 'en-US') {
  return locale === 'zh-CN' ? '取消锁定' : 'Clear pin'
}

interface WorkflowCompactCardGraphProps {
  graph: WorkflowGraphPayload
  selectedNodeId?: string
  onNodeSelect?: (nodeId: string) => void
  showLegend?: boolean
}

export function WorkflowCompactCardGraph({
  graph,
  selectedNodeId,
  onNodeSelect,
  showLegend = false,
}: WorkflowCompactCardGraphProps) {
  const { locale, getStageShortLabel, getStatusLabel, t } = useI18n()
  const previewOnly = graph.nodes.every(node => node.status === 'pending')
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [pinnedNodeId, setPinnedNodeId] = useState<string | null>(null)

  const focusedNodeId = hoveredNodeId ?? pinnedNodeId ?? selectedNodeId ?? null
  const focusedNode = graph.nodes.find(node => node.id === focusedNodeId) ?? null
  const pinnedNode = graph.nodes.find(node => node.id === pinnedNodeId) ?? null

  const handlePin = useCallback((nodeId: string) => {
    setPinnedNodeId(current => (current === nodeId ? null : nodeId))
    onNodeSelect?.(nodeId)
  }, [onNodeSelect])

  const flowModel = useMemo(() => {
    const nodesById = new Map(graph.nodes.map(node => [node.id, node]))
    const incoming = new Set(graph.edges.map(edge => edge.to))
    const outgoing = new Set(graph.edges.map(edge => edge.from))
    const previewBranchRoots = new Set<string>()
    const roots = graph.nodes.filter(node => !incoming.has(node.id))
    const terminals = graph.nodes.filter(node => !outgoing.has(node.id))
    const layout = buildCompactDagLayout(graph, previewOnly)

    const anchorNodes: Node[] = [
      {
        id: START_NODE_ID,
        type: 'dagAnchor',
        position: layout.positions[START_NODE_ID],
        data: {
          kind: 'start',
          label: getAnchorLabel('start', locale),
        } satisfies AnchorNodeData,
        width: ANCHOR_WIDTH,
        height: ANCHOR_HEIGHT,
        selectable: false,
        draggable: false,
        focusable: false,
        zIndex: 12,
      },
      {
        id: END_NODE_ID,
        type: 'dagAnchor',
        position: layout.positions[END_NODE_ID],
        data: {
          kind: 'end',
          label: getAnchorLabel('end', locale),
        } satisfies AnchorNodeData,
        width: ANCHOR_WIDTH,
        height: ANCHOR_HEIGHT,
        selectable: false,
        draggable: false,
        focusable: false,
        zIndex: 12,
      },
    ]

    const workflowNodes: Node[] = graph.nodes.map(node => ({
      id: node.id,
      type: 'editorialNode',
      position: layout.positions[node.id] ?? { x: 0, y: 0 },
      data: {
        node,
        previewOnly,
        shortLabel: getStageShortLabel(node.id as StageShortKey),
        statusLabel: getStatusLabel(node.status as StatusKey),
        isFocused: node.id === focusedNodeId,
        isPinned: node.id === pinnedNodeId,
        onHoverChange: setHoveredNodeId,
        onPin: handlePin,
      } satisfies CompactFlowNodeData,
      width: previewOnly ? PREVIEW_NODE_WIDTH : RUNTIME_NODE_WIDTH,
      height: previewOnly ? PREVIEW_NODE_HEIGHT : RUNTIME_NODE_HEIGHT,
      selectable: true,
      draggable: false,
      focusable: true,
      zIndex: 20,
    }))

    const actualEdges: Edge[] = graph.edges
      .filter(edge => nodesById.has(edge.from) && nodesById.has(edge.to))
      .map(edge => {
        const handles = resolveHandles(edge.from, edge.to, previewOnly, layout.positions)

        return {
          id: `${edge.from}--${edge.to}`,
          source: edge.from,
          target: edge.to,
          type: 'default',
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          ...getCompactEdgeStyle(edge.state, previewOnly),
        }
      })

    const syntheticPreviewEdges: Edge[] = []

    if (previewOnly && nodesById.has('stage1') && roots.some(root => root.id === 'ocr-detect')) {
      previewBranchRoots.add('ocr-detect')
      const handles = resolveHandles('stage1', 'ocr-detect', previewOnly, layout.positions)

      syntheticPreviewEdges.push({
        id: 'stage1--ocr-detect--preview',
        source: 'stage1',
        target: 'ocr-detect',
        type: 'default',
        sourceHandle: handles.sourceHandle,
        targetHandle: handles.targetHandle,
        ...getCompactEdgeStyle('inactive', true),
      })
    }

    const rootEdges: Edge[] = roots
      .filter(root => !previewBranchRoots.has(root.id))
      .map(root => {
        const handles = resolveHandles(START_NODE_ID, root.id, previewOnly, layout.positions)

        return {
          id: `${START_NODE_ID}--${root.id}`,
          source: START_NODE_ID,
          target: root.id,
          type: 'default',
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          ...getCompactEdgeStyle(edgeStateFromNodeStatus(root.status), previewOnly),
        }
      })

    const terminalEdges: Edge[] = terminals.map(terminal => {
      const handles = resolveHandles(terminal.id, END_NODE_ID, previewOnly, layout.positions)

      return {
        id: `${terminal.id}--${END_NODE_ID}`,
        source: terminal.id,
        target: END_NODE_ID,
        type: 'default',
        sourceHandle: handles.sourceHandle,
        targetHandle: handles.targetHandle,
        ...getCompactEdgeStyle(edgeStateFromNodeStatus(terminal.status), previewOnly),
      }
    })

    return {
      nodes: [...anchorNodes, ...workflowNodes],
      edges: [...rootEdges, ...syntheticPreviewEdges, ...actualEdges, ...terminalEdges],
      height: layout.height,
    }
  }, [
    getStageShortLabel,
    getStatusLabel,
    focusedNodeId,
    graph,
    handlePin,
    locale,
    pinnedNodeId,
    previewOnly,
  ])

  const focusRailContent = useMemo(() => {
    if (!focusedNode) {
      return null
    }

    return {
      node: focusedNode,
      code: NODE_CODE[focusedNode.id] ?? focusedNode.id,
      shortLabel: getStageShortLabel(focusedNode.id as StageShortKey),
      groupLabel: getMetaLabel(focusedNode.group, locale),
      hint: resolveNodeHint(focusedNode, locale, previewOnly),
      statusLabel: getStatusLabel(focusedNode.status as StatusKey),
      pinned: Boolean(pinnedNode && pinnedNode.id === focusedNode.id),
    }
  }, [
    focusedNode,
    getStageShortLabel,
    getStatusLabel,
    locale,
    pinnedNode,
    previewOnly,
  ])

  const FocusRailIcon = focusRailContent
    ? (NODE_ICON[focusRailContent.node.id] ?? AudioWaveform)
    : AudioWaveform
  const focusStatusAccent = focusRailContent ? STATUS_ACCENTS[focusRailContent.node.status] : null
  const showFocusStatus = Boolean(focusRailContent && !previewOnly && focusStatusAccent)

  return (
    <div className="space-y-3">
      {showLegend && <WorkflowLegend />}

      <div
        data-ui-layout="unified-dag"
        className="overflow-hidden rounded-[30px] border border-slate-200/90 bg-white"
      >
        <div
          className="bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.96),rgba(248,250,252,0.9),rgba(255,255,255,0.95))]"
          style={{ height: flowModel.height }}
        >
          <ReactFlow
            nodes={flowModel.nodes}
            edges={flowModel.edges}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.14 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnDrag
            zoomOnScroll
            zoomOnPinch
            zoomOnDoubleClick={false}
            preventScrolling={false}
            minZoom={0.55}
            maxZoom={1.8}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={26}
              size={1}
              color="#e2e8f0"
            />
          </ReactFlow>
        </div>

        <div className="border-t border-slate-200/80 bg-white px-4 py-3">
          {focusRailContent ? (
            <div
              data-ui-focus-rail="active"
              className="flex items-start justify-between gap-4"
            >
              <div className="flex min-w-0 flex-1 items-start gap-3">
                <span
                  data-ui-focus-icon="inline"
                  className="mt-1 inline-flex shrink-0 items-center justify-center text-slate-500"
                >
                  <FocusRailIcon size={16} />
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                      <div className="text-[17px] font-semibold tracking-tight text-slate-900">
                        {focusRailContent.shortLabel}
                      </div>

                      {showFocusStatus && focusStatusAccent ? (
                        <div
                          data-ui-focus-status=""
                          className="inline-flex items-center gap-2"
                        >
                          <span
                            data-ui-focus-status-rail=""
                            className={cn('h-1 w-7 rounded-full', focusStatusAccent.rail)}
                          />
                          <span
                            data-ui-focus-status-marker=""
                            className={cn(
                              'inline-flex h-3.5 w-3.5 items-center justify-center rounded-full',
                              focusStatusAccent.marker,
                            )}
                          >
                            {focusStatusAccent.markerInner ? (
                              <span className={cn('h-1.5 w-1.5 rounded-full', focusStatusAccent.markerInner)} />
                            ) : null}
                          </span>
                          <span
                            className={cn(
                              'text-[10px] font-semibold uppercase tracking-[0.18em]',
                              focusStatusAccent.statusText,
                            )}
                          >
                            {focusRailContent.statusLabel}
                          </span>
                          {focusRailContent.node.status === 'running' && (
                            <span
                              data-ui-focus-progress-bar=""
                              className="text-[10px] font-semibold uppercase tracking-[0.18em] text-sky-500/75"
                            >
                              {Math.round(focusRailContent.node.progress_percent)}%
                            </span>
                          )}
                        </div>
                      ) : null}
                    </div>

                    {focusRailContent.pinned && (
                      <button
                        type="button"
                        onClick={() => setPinnedNodeId(null)}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-medium text-slate-500 transition-colors hover:bg-slate-50"
                      >
                        <X size={11} />
                        {getFocusRailClearLabel(locale)}
                      </button>
                    )}
                  </div>

                  <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-slate-500">
                    <span className="font-medium uppercase tracking-[0.18em] text-slate-400">
                      {focusRailContent.code}
                    </span>
                    <span className="h-1 w-1 rounded-full bg-slate-300" />
                    <span>{focusRailContent.groupLabel}</span>
                    {focusRailContent.node.required === false && (
                      <>
                        <span className="h-1 w-1 rounded-full bg-slate-300" />
                        <span className="font-medium text-slate-500">{t.workflow.optional}</span>
                      </>
                    )}
                    {focusRailContent.pinned && (
                      <>
                        <span className="h-1 w-1 rounded-full bg-slate-300" />
                        <span className="font-medium text-slate-500">{getFocusRailPinnedLabel(locale)}</span>
                      </>
                    )}
                    <span className="h-1 w-1 rounded-full bg-slate-300" />
                    <span
                      data-ui-focus-inline-detail=""
                      className="min-w-0 flex-1 truncate text-slate-600"
                      title={focusRailContent.hint}
                    >
                      {focusRailContent.hint}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div
              data-ui-focus-rail="idle"
              className="flex items-center gap-2 text-xs text-slate-400"
            >
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-500">
                <AudioWaveform size={13} />
              </span>
              <span>{getFocusRailInstruction(locale)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
