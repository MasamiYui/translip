export type TaskStatus = 'pending' | 'running' | 'succeeded' | 'partial_success' | 'failed'
export type StageStatus = 'pending' | 'running' | 'succeeded' | 'cached' | 'failed' | 'skipped'
export type WorkflowStatus = TaskStatus
export type WorkflowEdgeState = 'inactive' | 'active' | 'completed' | 'blocked'
export type WorkflowNodeGroup = 'audio-spine' | 'ocr-subtitles' | 'video-cleanup' | 'delivery'
export type TaskOutputIntent = 'dub_final' | 'bilingual_review' | 'english_subtitle' | 'fast_validation'
export type TaskQualityPreset = 'fast' | 'standard' | 'high_quality'
export type TaskExportProfile = 'dub_no_subtitles' | 'bilingual_review' | 'english_subtitle_burned' | 'preview_only'
export type TaskExportReadinessStatus = 'not_ready' | 'ready' | 'exported' | 'blocked' | 'exporting'
export type HardSubtitleStatus = 'none' | 'confirmed'
export type BilingualExportStrategy =
  | 'auto_standard_bilingual'
  | 'preserve_hard_subtitles_add_english'
  | 'clean_video_rebuild_bilingual'
export type TranscriptionCorrectionPreset = 'conservative' | 'standard' | 'aggressive'

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

export interface TranscriptionCorrectionConfig {
  enabled: boolean
  preset: TranscriptionCorrectionPreset
  ocr_only_policy: 'report_only'
  llm_arbitration: 'off'
}

export interface TranscriptionCorrectionSummary {
  status: 'not_available' | 'available' | 'unreadable'
  corrected_count: number
  kept_asr_count: number
  review_count: number
  ocr_only_count: number
  auto_correction_rate?: number
  review_rate?: number
  algorithm_version?: string
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
  hard_subtitle_status?: HardSubtitleStatus
  asset_summary: TaskAssetSummary
  export_readiness: TaskExportReadiness
  last_export_summary: TaskLastExportSummary
  transcription_correction_summary?: TranscriptionCorrectionSummary
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
  bilingual_export_strategy?: BilingualExportStrategy
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
  transcription_correction?: Partial<TranscriptionCorrectionConfig>
  top_k: number
  translation_backend: string
  translation_glossary?: string
  translation_batch_size: number
  siliconflow_base_url?: string
  siliconflow_model?: string
  condense_mode?: string
  tts_backend: string
  max_segments?: number
  dub_repair_enabled?: boolean
  dub_repair_backend?: string[]
  dub_repair_backends?: string[]
  dub_repair_max_items?: number
  dub_repair_attempts_per_item?: number
  dub_repair_include_risk?: boolean
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

export interface DubbingReviewDecision {
  category: 'reference' | 'merge' | 'repair'
  item_id: string
  decision: string
  speaker_id?: string | null
  reference_path?: string | null
  attempt_id?: string | null
  payload?: Record<string, unknown>
  updated_at?: string
}

export interface DubbingReviewReferenceCandidate {
  reference_id: string
  source: string
  path: string
  artifact_path: string | null
  duration_sec: number | null
  text: string
  rms: number | null
  quality_score: number | null
  selection_reason?: string | null
  risk_flags: string[]
  is_current: boolean
  is_recommended: boolean
}

export interface DubbingReviewSpeaker {
  speaker_id: string
  profile_id: string
  display_name: string
  source_label?: string | null
  status: string
  total_speech_sec: number | null
  segment_count: number
  reference_clip_count: number
  speaker_failed_count: number
  repair_item_count: number
  current_reference_path?: string | null
  recommended_reference_path?: string | null
  bank_status?: string | null
  recommended_reference_id?: string | null
  decision?: DubbingReviewDecision | null
  candidates: DubbingReviewReferenceCandidate[]
}

export interface DubbingReviewMergeChild {
  segment_id: string
  speaker_id?: string | null
  source_text?: string | null
  target_text?: string | null
  start?: number | null
  end?: number | null
}

export interface DubbingReviewMergeCandidate {
  group_id: string
  group_type: string
  status: string
  source: string
  source_segment_ids: string[]
  speaker_id?: string | null
  anchor_start_sec: number | null
  anchor_end_sec: number | null
  source_text?: string | null
  target_text?: string | null
  audio_path?: string | null
  audio_artifact_path?: string | null
  metrics: Record<string, unknown>
  decision?: DubbingReviewDecision | null
  children: DubbingReviewMergeChild[]
}

export interface DubbingReviewAttempt {
  attempt_id: string
  status?: string
  target_text?: string
  text_variant?: string | null
  backend?: string
  reference_path?: string
  audio_path?: string
  audio_artifact_path?: string | null
  generated_duration_sec?: number
  metrics?: Record<string, unknown>
  score?: number
  strict_accepted?: boolean
  error?: string | null
}

export interface DubbingReviewRepairItem {
  segment_id: string
  speaker_id?: string | null
  source_text?: string | null
  target_text?: string | null
  anchor_start: number | null
  anchor_end: number | null
  source_duration_sec: number | null
  generated_duration_sec: number | null
  audio_path?: string | null
  audio_artifact_path?: string | null
  reference_path?: string | null
  queue_class?: string | null
  strict_blocker: boolean
  priority?: string | null
  priority_score: number | null
  failure_reasons: string[]
  suggested_actions: string[]
  metrics: Record<string, unknown>
  rewrite_candidates: Array<Record<string, unknown>>
  attempts: DubbingReviewAttempt[]
  decision?: DubbingReviewDecision | null
}

export interface DubbingReviewCharacter {
  character_id: string
  display_name: string
  speaker_ids: string[]
  source_label?: string | null
  profile_id?: string | null
  reference_path?: string | null
  pitch_class?: string | null
  pitch_hz?: number | null
  review_status: string
  risk_flags: string[]
  stats: Record<string, unknown>
}

export interface DubbingQualityBenchmark {
  version?: string | null
  status?: string | null
  score?: number | null
  reasons: string[]
  metrics: Record<string, unknown>
  gates: Array<Record<string, unknown>>
}

export interface DubbingReviewResponse {
  task_id: string
  target_lang: string
  status: 'available' | 'missing'
  summary: {
    speaker_count: number
    merge_candidate_count: number
    repair_item_count: number
    reference_decision_count: number
    merge_decision_count: number
    repair_decision_count: number
    quality_status?: string | null
    quality_score?: number | null
    character_review_count?: number
  }
  stats: Record<string, unknown>
  artifact_paths: Record<string, string>
  quality_benchmark?: DubbingQualityBenchmark | null
  characters: DubbingReviewCharacter[]
  speakers: DubbingReviewSpeaker[]
  merge_candidates: DubbingReviewMergeCandidate[]
  repair_items: DubbingReviewRepairItem[]
  decisions: {
    reference: DubbingReviewDecision[]
    merge: DubbingReviewDecision[]
    repair: DubbingReviewDecision[]
  }
}

export interface DubbingReviewDecisionPayload {
  category: 'reference' | 'merge' | 'repair'
  item_id: string
  decision: string
  speaker_id?: string | null
  reference_path?: string | null
  attempt_id?: string | null
  payload?: Record<string, unknown>
}

export interface SpeakerReviewDecision {
  item_id: string
  item_type: 'speaker_profile' | 'speaker_run' | 'segment' | string
  decision: string
  source_speaker_label?: string | null
  target_speaker_label?: string | null
  segment_ids?: string[]
  payload?: Record<string, unknown>
  updated_at?: string
}

export interface SpeakerReviewSpeaker {
  speaker_label: string
  segment_count: number
  segment_ids: string[]
  total_speech_sec: number
  avg_duration_sec: number
  short_segment_count: number
  risk_flags: string[]
  risk_level: 'low' | 'medium' | 'high'
  cloneable_by_default: boolean
  decision?: SpeakerReviewDecision | null
}

export interface SpeakerReviewRun {
  run_id: string
  speaker_label: string
  start: number
  end: number
  duration: number
  segment_count: number
  segment_ids: string[]
  text: string
  previous_speaker_label?: string | null
  next_speaker_label?: string | null
  gap_before_sec?: number | null
  gap_after_sec?: number | null
  risk_flags: string[]
  risk_level: 'low' | 'medium' | 'high'
  decision?: SpeakerReviewDecision | null
}

export interface SpeakerReviewSegment {
  segment_id: string
  index: number
  speaker_label: string
  start: number
  end: number
  duration: number
  text: string
  previous_speaker_label?: string | null
  next_speaker_label?: string | null
  risk_flags: string[]
  risk_level: 'low' | 'medium' | 'high'
  decision?: SpeakerReviewDecision | null
}

export interface SpeakerReviewPlanItem {
  item_id: string
  item_type: string
  speaker_label?: string | null
  risk_level?: string | null
  risk_flags: string[]
  segment_ids: string[]
  previous_speaker_label?: string | null
  next_speaker_label?: string | null
  recommended_actions: string[]
}

export interface SpeakerReviewResponse {
  task_id: string
  status: 'available' | 'missing'
  summary: {
    segment_count: number
    speaker_count: number
    high_risk_speaker_count: number
    speaker_run_count: number
    review_run_count?: number
    high_risk_run_count: number
    review_segment_count: number
    decision_count: number
    corrected_exists: boolean
  }
  artifact_paths: Record<string, string>
  speakers: SpeakerReviewSpeaker[]
  speaker_runs: SpeakerReviewRun[]
  segments: SpeakerReviewSegment[]
  review_plan: {
    summary?: Record<string, unknown>
    items: SpeakerReviewPlanItem[]
  }
  decisions: SpeakerReviewDecision[]
  manifest: Record<string, unknown>
}

export interface SpeakerReviewDecisionPayload {
  item_id: string
  item_type: 'speaker_profile' | 'speaker_run' | 'segment' | string
  decision: string
  source_speaker_label?: string | null
  target_speaker_label?: string | null
  segment_ids?: string[]
  payload?: Record<string, unknown>
}

export interface SpeakerReviewApplyResponse {
  ok: boolean
  path: string
  srt_path: string
  manifest_path: string
  summary: Record<string, unknown>
  applied_at: string
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
