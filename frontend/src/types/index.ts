export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'partial_success' | 'failed'
export type StageStatus = 'pending' | 'running' | 'succeeded' | 'cached' | 'failed' | 'skipped'
export type WorkflowStatus = TaskStatus
export type WorkflowEdgeState = 'inactive' | 'active' | 'completed' | 'blocked'
export type WorkflowNodeGroup = 'audio-spine' | 'ocr-subtitles' | 'video-cleanup' | 'delivery'
export type TaskOutputIntent = 'dub_final' | 'bilingual_review' | 'english_subtitle' | 'fast_validation'
export type TaskQualityPreset = 'fast' | 'standard' | 'high_quality'
export type TaskExportProfile = 'dub_no_subtitles' | 'bilingual_review' | 'english_subtitle_burned' | 'preview_only'
export type TaskExportReadinessStatus = 'not_ready' | 'ready' | 'exported' | 'blocked' | 'exporting'

export interface TaskAssetEntry {
  status: 'available' | 'missing' | 'building' | 'failed'
  path: string | null
}

export interface TaskAssetSummary {
  video: {
    original: TaskAssetEntry
    clean: TaskAssetEntry
  }
  audio: {
    preview: TaskAssetEntry
    dub: TaskAssetEntry
  }
  subtitles: {
    ocr_translated: TaskAssetEntry
    asr_translated: TaskAssetEntry
  }
  exports: {
    subtitle_preview: TaskAssetEntry
    final_preview: TaskAssetEntry
    final_dub: TaskAssetEntry
  }
}

export interface TaskExportBlocker {
  code: string
  message: string
  action: string
  action_label: string
}

export interface TaskExportReadiness {
  status: TaskExportReadinessStatus
  recommended_profile: TaskExportProfile
  summary: string
  blockers: TaskExportBlocker[]
}

export interface TaskLastExportFile {
  kind: string
  label: string
  path: string
}

export interface TaskLastExportSummary {
  status: 'not_exported' | 'exported'
  profile: TaskExportProfile | null
  updated_at?: string | null
  files: TaskLastExportFile[]
}

export interface TaskStage {
  stage_name: string
  status: StageStatus
  progress_percent: number
  current_step?: string
  cache_hit: boolean
  started_at?: string
  finished_at?: string
  elapsed_sec?: number
  manifest_path?: string
  error_message?: string
}

export interface Task {
  id: string
  name: string
  status: TaskStatus
  input_path: string
  output_root: string
  source_lang: string
  target_lang: string
  output_intent: TaskOutputIntent
  quality_preset: TaskQualityPreset
  config: Partial<TaskConfig>
  delivery_config: Partial<TaskDeliveryConfig>
  asset_summary: TaskAssetSummary
  export_readiness: TaskExportReadiness
  last_export_summary: TaskLastExportSummary
  overall_progress: number
  current_stage?: string
  created_at: string
  updated_at: string
  started_at?: string
  finished_at?: string
  elapsed_sec?: number
  error_message?: string
  manifest_path?: string
  parent_task_id?: string
  stages: TaskStage[]
}

export interface TaskListResponse {
  items: Task[]
  total: number
  page: number
  size: number
}

export interface TaskDeliveryConfig {
  export_preview: boolean
  export_dub: boolean
  delivery_container: string
  delivery_video_codec: string
  delivery_audio_codec: string
  subtitle_mode: 'none' | 'chinese_only' | 'english_only' | 'bilingual'
  subtitle_render_source: 'ocr' | 'asr'
  subtitle_font?: string | null
  subtitle_font_size?: number
  subtitle_color?: string
  subtitle_outline_color?: string
  subtitle_outline_width?: number
  subtitle_position?: 'top' | 'bottom'
  subtitle_margin_v?: number
  subtitle_bold?: boolean
  bilingual_chinese_position?: 'top' | 'bottom'
  bilingual_english_position?: 'top' | 'bottom'
  subtitle_preview_duration_sec?: number
}

export interface TaskConfig {
  device: string
  output_intent: TaskOutputIntent
  quality_preset: TaskQualityPreset
  template: 'asr-dub-basic' | 'asr-dub+ocr-subs' | 'asr-dub+ocr-subs+erase'
  run_from_stage: string
  run_to_stage: string
  use_cache: boolean
  keep_intermediate: boolean
  video_source: 'original' | 'clean' | 'clean_if_available'
  audio_source: 'dub' | 'preview' | 'both'
  subtitle_source: 'none' | 'asr' | 'ocr' | 'both'
  subtitle_mode?: 'none' | 'chinese_only' | 'english_only' | 'bilingual'
  subtitle_render_source?: 'ocr' | 'asr'
  subtitle_font?: string
  subtitle_font_size?: number
  subtitle_color?: string
  subtitle_outline_color?: string
  subtitle_outline_width?: number
  subtitle_position?: 'top' | 'bottom'
  subtitle_margin_v?: number
  subtitle_bold?: boolean
  bilingual_chinese_position?: 'top' | 'bottom'
  bilingual_english_position?: 'top' | 'bottom'
  subtitle_preview_duration_sec?: number
  separation_mode: string
  separation_quality: string
  music_backend: string
  dialogue_backend: string
  asr_model: string
  generate_srt: boolean
  top_k: number
  translation_backend: string
  translation_glossary?: string
  translation_batch_size: number
  siliconflow_base_url?: string
  siliconflow_model?: string
  condense_mode?: string
  tts_backend: string
  max_segments?: number
  fit_policy: string
  fit_backend: string
  mix_profile: string
  ducking_mode: string
  background_gain_db: number
  ocr_project_root?: string
  erase_project_root?: string
}

export interface CreateTaskRequest {
  name: string
  input_path: string
  source_lang: string
  target_lang: string
  config: Partial<TaskConfig>
  output_root?: string
  save_as_preset?: boolean
  preset_name?: string
}

export interface ConfigPreset {
  id: number
  name: string
  description?: string
  source_lang: string
  target_lang: string
  config: Partial<TaskConfig>
  created_at: string
  updated_at: string
}

export interface SystemInfo {
  python_version: string
  platform: string
  device: string
  cache_dir: string
  cache_size_bytes: number
  models: Array<{ name: string; status: 'available' | 'missing' }>
}

export interface Artifact {
  path: string
  size_bytes: number
  suffix: string
}

export interface ProgressEvent {
  type: 'progress' | 'done' | 'error' | 'timeout'
  stage?: string
  overall_percent?: number
  status?: string
  stages?: TaskStage[]
  message?: string
}

export interface WorkflowGraphNode {
  id: string
  label: string
  group: WorkflowNodeGroup
  required: boolean
  status: StageStatus
  progress_percent: number
  manifest_path?: string | null
  log_path?: string | null
  error_message?: string | null
  current_step?: string
  cache_hit?: boolean
  elapsed_sec?: number
}

export interface WorkflowGraphEdge {
  from: string
  to: string
  state: WorkflowEdgeState
}

export interface WorkflowGraph {
  workflow: {
    template_id: TaskConfig['template']
    status: WorkflowStatus
  }
  nodes: WorkflowGraphNode[]
  edges: WorkflowGraphEdge[]
}
