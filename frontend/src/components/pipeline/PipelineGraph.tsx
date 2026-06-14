import { buildGraphFromStages, normalizeWorkflowGraph } from '../../lib/workflowPreview'
import type { TaskConfig, TaskStage, WorkflowGraph as WorkflowGraphPayload } from '../../types'
import { WorkflowCompactCardGraph } from '../workflow/WorkflowCompactCardGraph'

interface PipelineGraphProps {
  stages?: TaskStage[]
  graph?: WorkflowGraphPayload
  activeStage?: string
  onStageClick?: (stageName: string) => void
  compact?: boolean
  showLegend?: boolean
  templateId?: TaskConfig['template']
}

export function PipelineGraph({
  stages = [],
  graph,
  activeStage,
  onStageClick,
  compact = false,
  showLegend = false,
  templateId = 'asr-dub-basic',
}: PipelineGraphProps) {
  const baseGraph = graph ?? buildGraphFromStages(stages, templateId)
  // `compact` still gates normalization (full mode normalizes a provided graph);
  // both modes render the same card graph, so there is a single return.
  const resolvedGraph = !compact && graph ? normalizeWorkflowGraph(baseGraph) : baseGraph

  return (
    <WorkflowCompactCardGraph
      graph={resolvedGraph}
      selectedNodeId={activeStage}
      onNodeSelect={onStageClick}
      showLegend={showLegend}
    />
  )
}
