import { useLayoutEffect, useRef, useState } from 'react'
import { useI18n } from '../../i18n/useI18n'
import { getWorkflowColumn, WORKFLOW_LANES } from '../../lib/workflowPreview'
import { cn } from '../../lib/utils'
import type { WorkflowGraph as WorkflowGraphPayload } from '../../types'
import { WorkflowEdge } from './WorkflowEdge'
import { WorkflowLane } from './WorkflowLane'
import { WorkflowLegend } from './WorkflowLegend'
import { WorkflowNodeCard } from './WorkflowNodeCard'

interface WorkflowGraphProps {
  graph: WorkflowGraphPayload
  selectedNodeId?: string
  onNodeSelect?: (nodeId: string) => void
  compact?: boolean
  showLegend?: boolean
}

interface NodePosition {
  x: number
  y: number
}

export function WorkflowGraph({
  graph,
  selectedNodeId,
  onNodeSelect,
  compact = false,
  showLegend = true,
}: WorkflowGraphProps) {
  const { t } = useI18n()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const nodeRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const [positions, setPositions] = useState<Record<string, NodePosition>>({})

  const groupedNodes = WORKFLOW_LANES.map(lane => ({
    lane: lane.id,
    label: t.workflow.lanes[lane.id],
    nodes: graph.nodes
      .filter(node => node.group === lane.id)
      .sort((left, right) => getWorkflowColumn(left.id) - getWorkflowColumn(right.id)),
  })).filter(entry => entry.nodes.length > 0)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) {
      return
    }

    const measure = () => {
      const containerRect = container.getBoundingClientRect()
      const nextPositions: Record<string, NodePosition> = {}
      for (const node of graph.nodes) {
        const element = nodeRefs.current[node.id]
        if (!element) {
          continue
        }
        const rect = element.getBoundingClientRect()
        nextPositions[node.id] = {
          x: rect.left - containerRect.left + rect.width / 2,
          y: rect.top - containerRect.top + rect.height / 2,
        }
      }
      setPositions(nextPositions)
    }

    measure()

    const observer = new ResizeObserver(() => {
      measure()
    })
    observer.observe(container)
    for (const node of graph.nodes) {
      const element = nodeRefs.current[node.id]
      if (element) {
        observer.observe(element)
      }
    }
    window.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [graph.nodes])

  return (
    <div className="space-y-4">
      {showLegend && <WorkflowLegend />}
      <div
        ref={containerRef}
        className={cn(
          'relative overflow-hidden rounded-[30px] border border-slate-200/80 bg-linear-to-br from-white via-slate-50 to-sky-50/60 p-4 shadow-[0_28px_90px_-44px_rgba(15,23,42,0.45)]',
          compact && 'rounded-[24px] p-3',
        )}
      >
        <svg className="pointer-events-none absolute inset-0 h-full w-full">
          {graph.edges.map(edge => {
            const source = positions[edge.from]
            const target = positions[edge.to]
            if (!source || !target) {
              return null
            }
            const dx = target.x - source.x
            const handle = Math.max(36, Math.abs(dx) * 0.32)
            const path = [
              `M ${source.x} ${source.y}`,
              `C ${source.x + handle} ${source.y}, ${target.x - handle} ${target.y}, ${target.x} ${target.y}`,
            ].join(' ')
            return <WorkflowEdge key={`${edge.from}:${edge.to}`} path={path} state={edge.state} />
          })}
        </svg>

        <div className="relative space-y-4">
          {groupedNodes.map(entry => (
            <WorkflowLane key={entry.lane} label={entry.label} compact={compact}>
              <div className={cn('grid', compact ? 'gap-2 grid-cols-7' : 'gap-3 grid-cols-7')}>
                {entry.nodes.map(node => (
                  <div key={node.id} style={{ gridColumn: `${getWorkflowColumn(node.id)} / span 1` }}>
                    <div ref={element => { nodeRefs.current[node.id] = element?.querySelector('button') ?? null }}>
                      <WorkflowNodeCard
                        node={node}
                        compact={compact}
                        selected={node.id === selectedNodeId}
                        onClick={onNodeSelect}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </WorkflowLane>
          ))}
        </div>
      </div>
    </div>
  )
}
