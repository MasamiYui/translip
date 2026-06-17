// Mirrors src/translip/server/assistant/models.py

export type BindingSource = 'upload' | 'step'

export interface Binding {
  source: BindingSource
  upload_index?: number | null
  step_id?: string | null
  output?: string | null
}

export interface PlanStep {
  id: string
  tool_id: string
  title: string
  rationale: string
  params: Record<string, unknown>
  inputs: Record<string, Binding>
}

export interface StepEdge {
  source: string
  target: string
}

export interface AssistantPlan {
  summary: string
  steps: PlanStep[]
  edges: StepEdge[]
}

export interface Clarification {
  question: string
  options: string[]
}

export interface ConversationTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface AvailableFileRef {
  label: string
  filename: string
}

export interface PlanResult {
  type: 'plan' | 'clarification'
  plan?: AssistantPlan | null
  clarification?: Clarification | null
}

export type RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface StepArtifact {
  filename: string
  download_url: string
  file_id?: string | null
  size_bytes: number
  content_type: string
}

export interface RunStepState {
  id: string
  tool_id: string
  title: string
  job_id?: string | null
  status: string
  progress_percent: number
  current_step?: string | null
  error_message?: string | null
  artifacts: StepArtifact[]
}

export interface RunState {
  run_id: string
  status: RunStatus
  message: string
  summary: string
  steps: RunStepState[]
  error_message?: string | null
}
