import type { WorkflowGraph } from '../types'

function getAutoSelectedStageId(currentStage: string | null | undefined, graph: WorkflowGraph | undefined) {
  return currentStage ?? graph?.nodes[0]?.id ?? null
}

export function resolveActiveStageId(
  userSelectedStageId: string | null | undefined,
  currentStage: string | null | undefined,
  graph: WorkflowGraph | undefined,
) {
  if (userSelectedStageId !== undefined) {
    return userSelectedStageId
  }

  return getAutoSelectedStageId(currentStage, graph)
}

export function resolveRerunStage(
  userSelectedRerunStage: string | undefined,
  currentStage: string | null | undefined,
  graph: WorkflowGraph | undefined,
) {
  return userSelectedRerunStage ?? getAutoSelectedStageId(currentStage, graph) ?? 'stage1'
}
