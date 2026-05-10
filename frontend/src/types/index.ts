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

export type CacheGroupKind = 'model' | 'hub' | 'pipeline' | 'temp'

export interface CacheBreakdownItem {
  key: string
  label: string
  group: CacheGroupKind
  bytes: number
  paths: string[]
  removable: boolean
  present: boolean
}

export interface CacheBreakdown {
  cache_dir: string
  huggingface_hub_dir: string
  total_bytes: number
  items: CacheBreakdownItem[]
}

export type CacheMigrateState = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface CacheMigrateProgress {
  total_bytes: number
  copied_bytes: number
  current_file: string | null
  speed_bps: number
}

export interface CacheMigrateTask {
  task_id: string
  status: CacheMigrateState
  state: CacheMigrateState
  src: string
  dst: string
  mode: 'move' | 'copy'
  switch_after: boolean
  progress: CacheMigrateProgress
  error: string | null
  started_at: number | null
  finished_at: number | null
}

export interface CacheCleanupDetail {
  key: string
  freed_bytes: number
  error?: string
}

export interface CacheCleanupResult {
  ok: boolean
  freed_bytes: number
  details: CacheCleanupDetail[]
}

export interface Artifact {
  path: string
  size_bytes: number
  suffix: string
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

export interface SpeakerReferenceClip {
  clip_id: string
  segment_id: string
  start: number
  end: number
  duration: number
  text: string
  is_best: boolean
  score: number
  url: string
}

export interface SpeakerSimilarPeer {
  label: string
  similarity: number
  suggest_merge: boolean
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
  reference_clips?: SpeakerReferenceClip[]
  best_reference_clip_id?: string | null
  similar_peers?: SpeakerSimilarPeer[]
  recommended_action?: string
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
  audio_url?: string
  prev_context_url?: string | null
  next_context_url?: string | null
  recommended_action?: string
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
  audio_url?: string
  prev_context_url?: string | null
  next_context_url?: string | null
  recommended_action?: string
}

export interface SpeakerSimilarityMatrix {
  labels: string[]
  matrix: number[][]
  threshold_suggest_merge: number
  method?: string
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

export interface SpeakerPersona {
  id: string
  name: string
  bindings: string[]
  aliases?: string[]
  color?: string | null
  avatar_emoji?: string | null
  gender?: string | null
  age_hint?: string | null
  note?: string | null
  role?: string | null
  pinned?: boolean
  is_target?: boolean
  confidence?: number | null
  tts_skip?: boolean
  tts_voice_id?: string | null
  created_at?: string
  updated_at?: string
}

export interface SpeakerPersonaBrief {
  persona_id?: string | null
  name?: string | null
  color?: string | null
  avatar_emoji?: string | null
}

export interface SpeakerPersonasBundle {
  items: SpeakerPersona[]
  unassigned_bindings: string[]
  by_speaker: Record<string, SpeakerPersonaBrief>
  updated_at?: string
}

export interface PersonaSuggestCandidate {
  name: string
  confidence: number
  source: string
}

export interface PersonaNameConflict {
  code: 'persona_name_conflict'
  existing_id: string
  existing_name: string
  message: string
}

export interface PersonaHistoryStatus {
  total: number
  cursor: number
  can_undo: boolean
  can_redo: boolean
  last_undo_op?: string | null
  next_redo_op?: string | null
}

export interface PersonaApplyPreviewChange {
  segment_id?: string | number | null
  start?: number | null
  end?: number | null
  original_speaker?: string
  new_speaker?: string
  original_persona?: string | null
  new_persona?: string | null
}

export interface PersonaApplyPreviewResponse {
  ok: boolean
  summary: {
    total_segments: number
    changed_segments: number
    unassigned_segments: number
    personas_used: Record<string, number>
    merges: Record<string, string>
  }
  sample_changes: PersonaApplyPreviewChange[]
}

export interface GlobalPersona {
  id: string
  name: string
  aliases?: string[]
  color?: string | null
  avatar_emoji?: string | null
  gender?: string | null
  age_hint?: string | null
  note?: string | null
  role?: string | null
  actor_name?: string | null
  tags?: string[]
  work_id?: string | null
  guest_work_ids?: string[]
  episodes?: string[]
  confidence?: number | null
  tts_voice_id?: string | null
  tts_skip?: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface Work {
  id: string
  title: string
  type: string
  year?: number | null
  aliases?: string[]
  cover_emoji?: string | null
  color?: string | null
  note?: string | null
  tags?: string[]
  default_tts_voice_map?: Record<string, string>
  persona_count?: number
  created_at?: string | null
  updated_at?: string | null
}

export interface WorkType {
  key: string
  label_zh: string
  label_en: string
  builtin: boolean
}

export interface WorksListResponse {
  ok: boolean
  path: string
  works: Work[]
  unassigned_count: number
  updated_at?: string | null
  version: number
}

export interface WorkInferCandidate {
  work_id: string | null
  title?: string
  score: number
  reason: string
  episode_label?: string | null
  suggest_create?: { title: string; year: number | null }
}

export interface GlobalPersonasListResponse {
  ok: boolean
  path: string
  personas: GlobalPersona[]
  updated_at?: string | null
  version: number
}

export interface GlobalPersonaImportResponse {
  ok: boolean
  accepted: number
  skipped: number
  total: number
  personas: GlobalPersona[]
}

export interface GlobalExportFromTaskResponse {
  ok: boolean
  exported: string[]
  skipped: string[]
  total: number
}

export interface ImportFromGlobalConflict {
  persona_id: string
  name: string
  existing_id?: string
}

export interface ImportFromGlobalResponse {
  ok: boolean
  imported: SpeakerPersona[]
  conflicts: ImportFromGlobalConflict[]
  personas: SpeakerPersonasBundle
}

export interface SuggestFromGlobalCandidate {
  persona_id: string
  name: string
  score: number
  reason: string
  role?: string | null
  gender?: string | null
  tts_voice_id?: string | null
  color?: string | null
  avatar_emoji?: string | null
}

export interface SuggestFromGlobalMatch {
  speaker_label: string
  candidates: SuggestFromGlobalCandidate[]
}

export interface SuggestFromGlobalResponse {
  ok: boolean
  matches: SuggestFromGlobalMatch[]
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
    unnamed_speaker_count?: number
  }
  artifact_paths: Record<string, string>
  speakers: SpeakerReviewSpeaker[]
  speaker_runs: SpeakerReviewRun[]
  segments: SpeakerReviewSegment[]
  similarity?: SpeakerSimilarityMatrix
  review_plan: {
    summary?: Record<string, unknown>
    items: SpeakerReviewPlanItem[]
  }
  decisions: SpeakerReviewDecision[]
  manifest: Record<string, unknown>
  personas?: SpeakerPersonasBundle
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
  archive_path?: string | null
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
