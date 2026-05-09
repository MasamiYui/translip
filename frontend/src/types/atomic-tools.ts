export type ToolCategory = 'audio' | 'speech' | 'video'
export type AtomicJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'

export interface ToolInfo {
  tool_id: string
  name_zh: string
  name_en: string
  description_zh: string
  description_en: string
  category: ToolCategory
  icon: string
  accept_formats: string[]
  max_file_size_mb: number
  max_files: number
}

export interface FileUploadResponse {
  file_id: string
  filename: string
  size_bytes: number
  content_type: string
}

export interface AtomicJob {
  job_id: string
  tool_id: string
  status: AtomicJobStatus
  progress_percent: number
  current_step: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  elapsed_sec: number | null
  error_message: string | null
  result: Record<string, unknown> | null
}

export interface AtomicStoredFileInfo {
  file_id: string
  filename: string
  size_bytes: number
  content_type: string
}

export interface AtomicJobRead extends AtomicJob {
  tool_name: string
  input_files: AtomicStoredFileInfo[]
  artifact_count: number
  updated_at: string | null
}

export interface AtomicJobDetail extends AtomicJobRead {
  params: Record<string, unknown>
  artifacts: ArtifactInfo[]
}

export interface AtomicJobListResponse {
  items: AtomicJobRead[]
  total: number
  page: number
  size: number
}

export interface ArtifactInfo {
  filename: string
  size_bytes: number
  content_type: string
  download_url: string
  file_id?: string | null
}
