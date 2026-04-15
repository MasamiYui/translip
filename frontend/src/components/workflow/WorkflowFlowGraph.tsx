import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  type Node,
  type Edge,
  type NodeTypes,
  type NodeProps,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useI18n } from '../../i18n/useI18n'
import { WORKFLOW_LANES, WORKFLOW_NODE_DEFINITIONS } from '../../lib/workflowPreview'
import { cn } from '../../lib/utils'
import type { WorkflowEdgeState, WorkflowGraph as WorkflowGraphPayload } from '../../types'
import { WorkflowFlowNode, type WorkflowFlowNodeData, COMPACT_CIRCLE, FULL_CIRCLE, COMPACT_NODE_WIDTH, FULL_NODE_WIDTH } from './WorkflowFlowNode'
import { WorkflowLegend } from './WorkflowLegend'
import type { StageShortKey } from '../../i18n/formatters'

// ─── layout constants ─────────────────────────────────────────────────────────

const COMPACT = {
  COLUMN_SPACING: 110,   // horizontal distance between column centres
  LANE_HEIGHT:    112,   // total height per lane row
  PADDING_X:       48,   // left padding before col-1 centre  (≥ NODE_WIDTH/2)
  NODE_WIDTH:  COMPACT_NODE_WIDTH,
  NODE_HEIGHT:     88,   // circle + label + spacing
  CIRCLE:      COMPACT_CIRCLE,
}

const FULL = {
  COLUMN_SPACING: 150,
  LANE_HEIGHT:    148,
  PADDING_X:       60,
  NODE_WIDTH:  FULL_NODE_WIDTH,
  NODE_HEIGHT:    108,
  CIRCLE:      FULL_CIRCLE,
}

// ─── lane background node ─────────────────────────────────────────────────────

interface LaneBgData extends Record<string, unknown> {
  label: string
  nodeWidth: number
  nodeHeight: number
}

function LaneBgNode({ data }: NodeProps) {
  const d = data as LaneBgData
  return (
    <div
      className="flex flex-col overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50/50"
      style={{ width: d.nodeWidth, height: d.nodeHeight, pointerEvents: 'none' }}
    >
      {/* Lane label strip */}
      <div className="px-3 pt-2.5 pb-1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
          {d.label}
        </span>
      </div>
    </div>
  )
}

// ─── node types registry ──────────────────────────────────────────────────────

const NODE_TYPES: NodeTypes = {
  workflowCircle: WorkflowFlowNode as unknown as NodeTypes['workflowCircle'],
  laneBg: LaneBgNode as unknown as NodeTypes['laneBg'],
}

// ─── edge helpers ─────────────────────────────────────────────────────────────

function edgeProps(state: WorkflowEdgeState, prefersReducedMotion: boolean): Partial<Edge> {
  const arrowBase = { width: 14, height: 14 }
  switch (state) {
    case 'active':
      return {
        style: { stroke: '#38BDF8', strokeWidth: 2.5 },
        animated: !prefersReducedMotion,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#38BDF8', ...arrowBase },
      }
    case 'completed':
      return {
        style: { stroke: '#34D399', strokeWidth: 2 },
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#34D399', ...arrowBase },
      }
    case 'blocked':
      return {
        style: { stroke: '#FCD34D', strokeWidth: 2, strokeDasharray: '6 4' },
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#FCD34D', ...arrowBase },
      }
    default: // 'inactive'
      return {
        style: { stroke: '#CBD5E1', strokeWidth: 1.5 },
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#CBD5E1', width: 11, height: 11 },
      }
  }
}

// ─── component ────────────────────────────────────────────────────────────────

interface WorkflowFlowGraphProps {
  graph: WorkflowGraphPayload
  selectedNodeId?: string
  onNodeSelect?: (nodeId: string) => void
  compact?: boolean
  showLegend?: boolean
}

export function WorkflowFlowGraph({
  graph,
  selectedNodeId,
  onNodeSelect,
  compact = false,
  showLegend = true,
}: WorkflowFlowGraphProps) {
  const { t, getStageShortLabel } = useI18n()

  const cfg = compact ? COMPACT : FULL

  // Determine which lanes are actually used (preserving canonical order)
  const activeLanes = useMemo(() => {
    const groupsInGraph = new Set(graph.nodes.map(n => n.group))
    return WORKFLOW_LANES.filter(lane => groupsInGraph.has(lane.id))
  }, [graph.nodes])

  // Max column across all nodes in this graph
  const maxColumn = useMemo(() => {
    return Math.max(...graph.nodes.map(n => WORKFLOW_NODE_DEFINITIONS[n.id]?.column ?? 1))
  }, [graph.nodes])

  const laneWidth = (maxColumn - 1) * cfg.COLUMN_SPACING + cfg.PADDING_X * 2 + cfg.NODE_WIDTH / 2

  // Reduce motion via CSS media query check (avoid framer-motion dep here)
  const prefersReducedMotion =
    typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

  // ── React Flow nodes ──────────────────────────────────────────────────────

  const rfNodes = useMemo<Node[]>(() => {
    // Lane background nodes (rendered first for z-ordering)
    const laneNodes: Node[] = activeLanes.map((lane, laneIndex) => ({
      id: `lane-bg-${lane.id}`,
      type: 'laneBg',
      position: { x: 0, y: laneIndex * cfg.LANE_HEIGHT },
      data: {
        label: t.workflow.lanes[lane.id],
        nodeWidth: laneWidth,
        nodeHeight: cfg.LANE_HEIGHT,
      } satisfies LaneBgData,
      width: laneWidth,
      height: cfg.LANE_HEIGHT,
      selectable: false,
      draggable: false,
      focusable: false,
      zIndex: 0,
    }))

    // Workflow circle nodes
    const workflowNodes: Node[] = []
    for (const node of graph.nodes) {
      const def = WORKFLOW_NODE_DEFINITIONS[node.id]
      if (!def) continue

      const laneIndex = activeLanes.findIndex(l => l.id === def.group)
      if (laneIndex < 0) continue

      // Top-left of node wrapper: centre the node horizontally and vertically in the lane
      const x = (def.column - 1) * cfg.COLUMN_SPACING + cfg.PADDING_X - cfg.NODE_WIDTH / 2
      const y = laneIndex * cfg.LANE_HEIGHT + cfg.LANE_HEIGHT / 2 - cfg.CIRCLE / 2 - 4

      const data: WorkflowFlowNodeData = {
        node,
        compact,
        shortLabel: getStageShortLabel(node.id as StageShortKey),
        isSelected: node.id === selectedNodeId,
        onSelect: onNodeSelect,
      }

      workflowNodes.push({
        id: node.id,
        type: 'workflowCircle',
        position: { x, y },
        data,
        width: cfg.NODE_WIDTH,
        height: cfg.NODE_HEIGHT,
        selectable: true,
        draggable: false,
        focusable: true,
        zIndex: 10,
      })
    }

    return [...laneNodes, ...workflowNodes]
  }, [
    graph.nodes,
    activeLanes,
    compact,
    selectedNodeId,
    onNodeSelect,
    cfg,
    laneWidth,
    t.workflow.lanes,
    getStageShortLabel,
  ])

  // ── React Flow edges ──────────────────────────────────────────────────────

  const rfEdges = useMemo<Edge[]>(() => {
    return graph.edges.map(edge => ({
      id: `${edge.from}--${edge.to}`,
      source: edge.from,
      target: edge.to,
      type: 'smoothstep',
      ...edgeProps(edge.state, prefersReducedMotion),
    }))
  }, [graph.edges, prefersReducedMotion])

  // ── container sizing ──────────────────────────────────────────────────────

  const containerHeight = activeLanes.length * cfg.LANE_HEIGHT + (compact ? 16 : 24)

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (node.type === 'workflowCircle') {
        onNodeSelect?.(node.id)
      }
    },
    [onNodeSelect],
  )

  return (
    <div className={cn('space-y-3', compact && 'space-y-2')}>
      {showLegend && <WorkflowLegend />}

      <div
        className={cn(
          'overflow-hidden rounded-[28px] border border-slate-200/80',
          'bg-gradient-to-br from-white via-slate-50 to-sky-50/40',
          'shadow-[0_20px_70px_-30px_rgba(15,23,42,0.3)]',
          compact && 'rounded-[20px]',
        )}
        style={{ height: containerHeight }}
      >
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: compact ? 0.1 : 0.12, includeHiddenNodes: false }}
          nodesDraggable={false}
          nodesConnectable={false}
          panOnDrag={!compact}
          zoomOnScroll={!compact}
          zoomOnDoubleClick={!compact}
          preventScrolling={compact}
          selectNodesOnDrag={false}
          proOptions={{ hideAttribution: true }}
          onNodeClick={onNodeClick}
          minZoom={0.25}
          maxZoom={2}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={28}
            size={1}
            color={compact ? '#e8edf3' : '#dde4ed'}
          />
        </ReactFlow>
      </div>
    </div>
  )
}
