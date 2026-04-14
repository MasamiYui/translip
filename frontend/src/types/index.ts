export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'failed'
export type StageStatus = 'pending' | 'running' | 'succeeded' | 'cached' | 'failed' | 'skipped'

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
  config: Record<string, unknown>
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

export interface TaskConfig {
  device: string
  run_from_stage: string
  run_to_stage: string
  use_cache: boolean
  keep_intermediate: boolean
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
  tts_backend: string
  max_segments?: number
  fit_policy: string
  fit_backend: string
  mix_profile: string
  ducking_mode: string
  background_gain_db: number
  export_preview: boolean
  export_dub: boolean
  delivery_container: string
  delivery_video_codec: string
  delivery_audio_codec: string
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
