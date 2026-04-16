# 原子工具集 — 技术设计文档

> 版本: v1.0 · 最后更新: 2026-04-16

---

## 1. 系统架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                            │
│                                                                     │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │ Sidebar  │  │ ToolListPage     │  │ ToolPage (per-tool)       │  │
│  │ (nav)    │  │ /tools           │  │ /tools/:toolId            │  │
│  │          │  │                  │  │                           │  │
│  │ 🧰 展开  │→│ 7 tool cards     │→│ upload → params → result  │  │
│  └──────────┘  └──────────────────┘  └───────────┬───────────────┘  │
│                                                   │ REST API         │
├───────────────────────────────────────────────────┼─────────────────┤
│                         Backend (FastAPI)          │                 │
│                                                   ▼                 │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  /api/atomic-tools/                                           │  │
│  │  ├─ POST /upload                  文件上传                    │  │
│  │  ├─ POST /{tool_id}/run           提交任务                    │  │
│  │  ├─ GET  /{tool_id}/jobs/{job_id} 查询状态                    │  │
│  │  ├─ GET  /{tool_id}/jobs/{job_id}/result  获取结果            │  │
│  │  └─ GET  /{tool_id}/jobs/{job_id}/artifacts/{filename} 下载  │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                  │                                  │
│  ┌───────────────────────────────▼───────────────────────────────┐  │
│  │  AtomicToolRunner (调度层)                                     │  │
│  │  ├─ 输入校验                                                  │  │
│  │  ├─ 临时目录管理                                              │  │
│  │  ├─ 调用已有 runner 函数                                      │  │
│  │  └─ 产物收集 + 清理                                          │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
│                                  │                                  │
│  ┌───────────────────────────────▼───────────────────────────────┐  │
│  │  现有 Runner 函数 (复用，不修改)                                │  │
│  │  pipeline/runner.py  transcription/runner.py  rendering/...   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**核心原则**: 原子工具层不重新实现任何处理逻辑，仅作为现有 runner 函数的**轻量适配层**。

---

## 2. 后端设计

### 2.1 目录结构

```
src/translip/server/
├── routes/
│   ├── tasks.py          # 现有 Pipeline 任务路由
│   ├── system.py         # 现有系统路由
│   ├── config.py         # 现有配置路由
│   ├── artifacts.py      # 现有产物路由
│   ├── progress.py       # 现有进度路由
│   └── atomic_tools.py   # 🆕 原子工具路由
├── atomic_tools/         # 🆕 原子工具适配层
│   ├── __init__.py
│   ├── registry.py       # 工具注册表
│   ├── schemas.py        # Pydantic 请求/响应模型
│   ├── job_manager.py    # 任务生命周期管理
│   └── adapters/         # 各工具适配器
│       ├── __init__.py
│       ├── separation.py     # AT-1
│       ├── mixing.py         # AT-2
│       ├── transcription.py  # AT-3
│       ├── translation.py    # AT-4
│       ├── tts.py            # AT-5
│       ├── probe.py          # AT-6
│       └── muxing.py         # AT-7
└── ...
```

### 2.2 工具注册表

```python
# src/translip/server/atomic_tools/registry.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ToolCategory = Literal["audio", "speech", "video"]

@dataclass(slots=True)
class ToolSpec:
    """静态工具元信息，前端从此获取工具列表。"""
    tool_id: str                      # e.g. "separation"
    name_zh: str                      # "人声/背景分离"
    name_en: str                      # "Audio Separation"
    description_zh: str
    description_en: str
    category: ToolCategory
    icon: str                         # Lucide icon name
    accept_formats: list[str]         # e.g. [".mp4", ".wav", ".mp3"]
    max_file_size_mb: int = 500
    max_files: int = 1                # 单工具最多上传文件数

TOOL_REGISTRY: dict[str, ToolSpec] = {}

def register_tool(spec: ToolSpec) -> None:
    TOOL_REGISTRY[spec.tool_id] = spec

def get_all_tools() -> list[ToolSpec]:
    return list(TOOL_REGISTRY.values())
```

各适配器模块在导入时通过 `register_tool()` 注册自己。

### 2.3 请求/响应 Schema

```python
# src/translip/server/atomic_tools/schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

# ── 通用 ──

class ToolInfo(BaseModel):
    tool_id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    category: str
    icon: str
    accept_formats: list[str]
    max_file_size_mb: int
    max_files: int

class FileUploadResponse(BaseModel):
    file_id: str          # UUID
    filename: str
    size_bytes: int
    content_type: str

JobStatus = Literal["pending", "running", "completed", "failed"]

class JobResponse(BaseModel):
    job_id: str
    tool_id: str
    status: JobStatus
    progress_percent: float
    current_step: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_sec: float | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None    # 工具特定的结果数据

class ArtifactInfo(BaseModel):
    filename: str
    size_bytes: int
    content_type: str
    download_url: str    # 相对路径

# ── 各工具请求 ──

class SeparationToolRequest(BaseModel):
    file_id: str
    mode: str = "auto"
    quality: str = "balanced"
    output_format: str = "wav"

class MixingToolRequest(BaseModel):
    voice_file_id: str
    background_file_id: str
    background_gain_db: float = -8.0
    ducking_mode: str = "static"
    output_format: str = "wav"

class TranscriptionToolRequest(BaseModel):
    file_id: str
    language: str = "zh"
    asr_model: str = "small"
    enable_diarization: bool = False
    generate_srt: bool = True

class TranslationToolRequest(BaseModel):
    text: str | None = None
    file_id: str | None = None
    source_lang: str = "zh"
    target_lang: str = "en"
    backend: str = "local-m2m100"
    glossary_file_id: str | None = None

class TtsToolRequest(BaseModel):
    text: str
    language: str = "auto"
    reference_audio_file_id: str | None = None

class ProbeToolRequest(BaseModel):
    file_id: str

class MuxingToolRequest(BaseModel):
    video_file_id: str
    audio_file_id: str
    video_codec: str = "copy"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
```

### 2.4 API 路由

```python
# src/translip/server/routes/atomic_tools.py
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from ..atomic_tools.registry import get_all_tools, TOOL_REGISTRY
from ..atomic_tools.schemas import (
    ToolInfo, FileUploadResponse, JobResponse, ArtifactInfo,
)
from ..atomic_tools.job_manager import job_manager

router = APIRouter(prefix="/api/atomic-tools", tags=["atomic-tools"])


# ── 元信息 ──

@router.get("/tools", response_model=list[ToolInfo])
def list_tools():
    """返回所有可用的原子工具列表。"""
    return [ToolInfo(**vars(spec)) for spec in get_all_tools()]


# ── 文件上传 ──

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传文件到临时存储，返回 file_id 供后续工具使用。"""
    return await job_manager.save_upload(file)


# ── 提交任务 ──

@router.post("/{tool_id}/run", response_model=JobResponse)
async def run_tool(
    tool_id: str,
    params: dict,          # 动态参数，由各适配器校验
    background_tasks: BackgroundTasks,
):
    """创建并启动一个原子工具任务。"""
    if tool_id not in TOOL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")
    job = job_manager.create_job(tool_id, params)
    background_tasks.add_task(job_manager.execute_job, job.job_id)
    return job


# ── 状态查询 ──

@router.get("/{tool_id}/jobs/{job_id}", response_model=JobResponse)
def get_job_status(tool_id: str, job_id: str):
    """查询任务执行状态。"""
    return job_manager.get_job(job_id)


# ── 结果产物 ──

@router.get("/{tool_id}/jobs/{job_id}/artifacts", response_model=list[ArtifactInfo])
def list_job_artifacts(tool_id: str, job_id: str):
    """列出任务产出的所有文件。"""
    return job_manager.list_artifacts(job_id)


@router.get("/{tool_id}/jobs/{job_id}/artifacts/{filename}")
def download_artifact(tool_id: str, job_id: str, filename: str):
    """下载指定产物文件。"""
    from fastapi.responses import FileResponse
    path = job_manager.get_artifact_path(job_id, filename)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=filename)
```

### 2.5 任务管理器 (Job Manager)

```python
# src/translip/server/atomic_tools/job_manager.py 核心接口
from __future__ import annotations

class JobManager:
    """
    管理原子工具任务的完整生命周期。
    使用内存存储（适合单机部署），不入 SQLite 主库。
    """

    async def save_upload(self, file: UploadFile) -> FileUploadResponse:
        """
        保存上传文件到临时目录，返回 file_id。
        存储路径: {CACHE_ROOT}/atomic-tools/uploads/{file_id}/{original_name}
        """
        ...

    def create_job(self, tool_id: str, params: dict) -> JobResponse:
        """
        创建 Job 记录（status=pending），分配 UUID，
        工作目录: {CACHE_ROOT}/atomic-tools/jobs/{job_id}/
        """
        ...

    async def execute_job(self, job_id: str) -> None:
        """
        后台执行流程:
        1. status → running
        2. 调用对应 adapter.run(params, input_dir, output_dir)
        3. 收集产物
        4. status → completed | failed
        """
        ...

    def get_job(self, job_id: str) -> JobResponse: ...
    def list_artifacts(self, job_id: str) -> list[ArtifactInfo]: ...
    def get_artifact_path(self, job_id: str, filename: str) -> Path | None: ...
    def cleanup_expired(self, max_age_hours: int = 24) -> int: ...
```

**存储策略**:
- Job 元信息：内存字典 `dict[str, JobRecord]`，不持久化到 SQLite（原子工具是轻量一次性任务）
- 文件存储：文件系统 `{CACHE_ROOT}/atomic-tools/`
- 清理：后台定时任务，每小时扫描一次，清理超过 24h 的 uploads 和 jobs 目录

### 2.6 适配器接口 (Adapter Protocol)

每个工具实现统一的 Adapter 接口：

```python
# src/translip/server/atomic_tools/adapters/__init__.py
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class ToolAdapter(ABC):
    """所有原子工具适配器的基类。"""

    @abstractmethod
    def validate_params(self, params: dict) -> dict:
        """校验并标准化请求参数，返回清洗后的参数。失败抛 ValueError。"""
        ...

    @abstractmethod
    def run(
        self,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        on_progress: callable,  # (percent: float, step: str) -> None
    ) -> dict[str, Any]:
        """
        执行工具逻辑。
        - input_dir: 包含已上传文件的目录
        - output_dir: 产出文件写入此目录
        - on_progress: 进度回调
        - 返回: 工具特定的结果数据 dict
        """
        ...
```

### 2.7 适配器实现示例

#### AT-1: 人声/背景分离

```python
# src/translip/server/atomic_tools/adapters/separation.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from ....types import SeparationRequest
from ....pipeline.runner import separate_file
from ..registry import register_tool, ToolSpec
from . import ToolAdapter

register_tool(ToolSpec(
    tool_id="separation",
    name_zh="人声/背景分离",
    name_en="Audio Separation",
    description_zh="从音视频中分离人声轨与背景轨",
    description_en="Separate vocal and background tracks from audio/video",
    category="audio",
    icon="AudioLines",
    accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".m4a", ".ogg"],
    max_file_size_mb=500,
    max_files=1,
))

class SeparationAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        from ..schemas import SeparationToolRequest
        return SeparationToolRequest(**params).model_dump()

    def run(
        self,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        on_progress: callable,
    ) -> dict[str, Any]:
        # 找到上传的输入文件
        input_file = next(input_dir.iterdir())

        on_progress(5.0, "preparing")

        # 构建现有 runner 的 Request
        req = SeparationRequest(
            input_path=input_file,
            output_dir=output_dir,
            mode=params.get("mode", "auto"),
            quality=params.get("quality", "balanced"),
            output_format=params.get("output_format", "wav"),
        ).normalized()

        on_progress(10.0, "separating")

        # 直接复用现有 runner
        result = separate_file(req)

        on_progress(95.0, "collecting_artifacts")

        return {
            "route": result.route.route,
            "route_reason": result.route.reason,
            "backend": result.artifacts.voice_path.parent.name,
            "voice_file": result.artifacts.voice_path.name,
            "background_file": result.artifacts.background_path.name,
        }
```

#### AT-3: 语音转文字

```python
# src/translip/server/atomic_tools/adapters/transcription.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from ....types import TranscriptionRequest
from ....transcription.runner import transcribe_file
from ..registry import register_tool, ToolSpec
from . import ToolAdapter

register_tool(ToolSpec(
    tool_id="transcription",
    name_zh="语音转文字",
    name_en="Speech to Text",
    description_zh="语音识别 + 可选说话人识别，生成带时间戳的文字和字幕",
    description_en="ASR with optional speaker diarization, generates timestamped text and subtitles",
    category="speech",
    icon="MessageSquareText",
    accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".m4a", ".ogg"],
    max_file_size_mb=500,
    max_files=1,
))

class TranscriptionAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        from ..schemas import TranscriptionToolRequest
        return TranscriptionToolRequest(**params).model_dump()

    def run(
        self,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        on_progress: callable,
    ) -> dict[str, Any]:
        input_file = next(input_dir.iterdir())

        on_progress(5.0, "loading_model")

        req = TranscriptionRequest(
            input_path=input_file,
            output_dir=output_dir,
            language=params.get("language", "zh"),
            asr_model=params.get("asr_model", "small"),
            write_srt=params.get("generate_srt", True),
        ).normalized()

        on_progress(10.0, "transcribing")

        result = transcribe_file(req)

        on_progress(90.0, "diarization" if params.get("enable_diarization") else "finalizing")

        # 说话人识别: transcribe_file 内置了 diarization
        # enable_diarization=False 时，结果中 speaker_label 全为同一值
        # 这里无需额外处理，前端根据 segments 中 speaker_label 渲染即可

        segments_summary = []
        for seg in result.segments:
            segments_summary.append({
                "id": seg.segment_id,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "speaker": seg.speaker_label,
            })

        unique_speakers = list({s.speaker_label for s in result.segments})

        return {
            "total_segments": len(result.segments),
            "total_duration_sec": result.media_info.duration_sec,
            "language": params.get("language", "zh"),
            "speaker_count": len(unique_speakers),
            "speakers": unique_speakers,
            "segments": segments_summary,
            "has_srt": result.artifacts.srt_path is not None,
            "srt_file": result.artifacts.srt_path.name if result.artifacts.srt_path else None,
            "segments_file": result.artifacts.segments_json_path.name,
        }
```

#### AT-6: 媒体探测 (最简适配器)

```python
# src/translip/server/atomic_tools/adapters/probe.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from ....utils.ffmpeg import probe_media
from ..registry import register_tool, ToolSpec
from . import ToolAdapter

register_tool(ToolSpec(
    tool_id="probe",
    name_zh="媒体信息探测",
    name_en="Media Probe",
    description_zh="检测音视频文件的格式、时长、编码等详细参数",
    description_en="Inspect media file format, duration, codecs, and metadata",
    category="video",
    icon="ScanSearch",
    accept_formats=[".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".flac", ".m4a", ".ogg", ".webm", ".ts"],
    max_file_size_mb=2000,    # probe 不需要读全文件，可以支持更大的
    max_files=1,
))

class ProbeAdapter(ToolAdapter):
    def validate_params(self, params: dict) -> dict:
        from ..schemas import ProbeToolRequest
        return ProbeToolRequest(**params).model_dump()

    def run(
        self,
        params: dict,
        input_dir: Path,
        output_dir: Path,
        on_progress: callable,
    ) -> dict[str, Any]:
        input_file = next(input_dir.iterdir())
        on_progress(50.0, "probing")

        info = probe_media(input_file)

        return {
            "path": str(input_file.name),
            "media_type": info.media_type,
            "format_name": info.format_name,
            "duration_sec": info.duration_sec,
            "has_video": info.media_type == "video",
            "has_audio": info.audio_stream_count > 0,
            "audio_streams": info.audio_stream_count,
            "sample_rate": info.sample_rate,
            "channels": info.channels,
        }
```

### 2.8 路由注册

在 `app.py` 中新增路由挂载：

```python
# 在 app.py 中新增
from .routes.atomic_tools import router as atomic_tools_router

# 在 include_router 区域添加
app.include_router(atomic_tools_router)
```

### 2.9 清理定时任务

```python
# 在 app.py startup 事件中新增
from .atomic_tools.job_manager import job_manager

@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("Database initialized")

    # 启动原子工具临时文件清理
    import asyncio
    async def cleanup_loop():
        while True:
            await asyncio.sleep(3600)  # 每小时
            count = job_manager.cleanup_expired(max_age_hours=24)
            if count:
                logger.info("Cleaned up %d expired atomic tool jobs", count)
    asyncio.create_task(cleanup_loop())
```

---

## 3. 前端设计

### 3.1 目录结构

```
frontend/src/
├── pages/
│   ├── ToolListPage.tsx            # 🆕 工具列表页 (/tools)
│   └── ToolPage.tsx                # 🆕 单工具页面 (/tools/:toolId)
├── components/
│   └── atomic-tools/               # 🆕 原子工具组件
│       ├── ToolCard.tsx            # 工具卡片
│       ├── ToolLayout.tsx          # 单工具页面通用布局
│       ├── FileUploadZone.tsx      # 文件上传区域
│       ├── ParamForm.tsx           # 通用参数表单
│       ├── ResultPanel.tsx         # 结果面板
│       ├── AudioPlayer.tsx         # 音频播放器
│       ├── ToolProgressBar.tsx     # 工具执行进度
│       ├── CrossToolAction.tsx     # "在其他工具中使用"按钮
│       └── tool-configs/           # 各工具的参数配置组件
│           ├── SeparationParams.tsx
│           ├── MixingParams.tsx
│           ├── TranscriptionParams.tsx
│           ├── TranslationParams.tsx
│           ├── TtsParams.tsx
│           ├── ProbeParams.tsx
│           └── MuxingParams.tsx
├── api/
│   └── atomic-tools.ts             # 🆕 原子工具 API 客户端
├── types/
│   └── atomic-tools.ts             # 🆕 原子工具类型定义
├── hooks/
│   └── useAtomicTool.ts            # 🆕 原子工具通用 Hook
└── i18n/
    └── messages.ts                 # 扩展: 新增 atomicTools 命名空间
```

### 3.2 TypeScript 类型

```typescript
// frontend/src/types/atomic-tools.ts

export type ToolCategory = 'audio' | 'speech' | 'video'
export type AtomicJobStatus = 'pending' | 'running' | 'completed' | 'failed'

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

export interface ArtifactInfo {
  filename: string
  size_bytes: number
  content_type: string
  download_url: string
}

// 工具特定参数类型
export interface SeparationParams {
  file_id: string
  mode?: 'auto' | 'music' | 'dialogue'
  quality?: 'balanced' | 'high'
  output_format?: 'wav' | 'mp3' | 'flac'
}

export interface MixingParams {
  voice_file_id: string
  background_file_id: string
  background_gain_db?: number
  ducking_mode?: 'static' | 'sidechain'
  output_format?: 'wav' | 'mp3'
}

export interface TranscriptionParams {
  file_id: string
  language?: string
  asr_model?: 'tiny' | 'base' | 'small' | 'medium' | 'large-v3'
  enable_diarization?: boolean
  generate_srt?: boolean
}

export interface TranslationParams {
  text?: string
  file_id?: string
  source_lang?: string
  target_lang?: string
  backend?: 'local-m2m100' | 'siliconflow'
  glossary_file_id?: string
}

export interface TtsParams {
  text: string
  language?: 'auto' | 'zh' | 'en' | 'ja'
  reference_audio_file_id?: string
}

export interface ProbeParams {
  file_id: string
}

export interface MuxingParams {
  video_file_id: string
  audio_file_id: string
  video_codec?: 'copy' | 'libx264'
  audio_codec?: 'aac'
  audio_bitrate?: string
}
```

### 3.3 API 客户端

```typescript
// frontend/src/api/atomic-tools.ts
import api from './client'
import type {
  ToolInfo,
  FileUploadResponse,
  AtomicJob,
  ArtifactInfo,
} from '../types/atomic-tools'

export const atomicToolsApi = {
  // 获取所有工具列表
  listTools: () =>
    api.get<ToolInfo[]>('/api/atomic-tools/tools').then(r => r.data),

  // 上传文件
  upload: (file: File, onProgress?: (percent: number) => void) => {
    const formData = new FormData()
    formData.append('file', file)
    return api
      .post<FileUploadResponse>('/api/atomic-tools/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: e => {
          if (onProgress && e.total) onProgress((e.loaded / e.total) * 100)
        },
      })
      .then(r => r.data)
  },

  // 运行工具
  run: (toolId: string, params: Record<string, unknown>) =>
    api.post<AtomicJob>(`/api/atomic-tools/${toolId}/run`, params).then(r => r.data),

  // 查询状态
  getJob: (toolId: string, jobId: string) =>
    api.get<AtomicJob>(`/api/atomic-tools/${toolId}/jobs/${jobId}`).then(r => r.data),

  // 列出产物
  listArtifacts: (toolId: string, jobId: string) =>
    api
      .get<ArtifactInfo[]>(`/api/atomic-tools/${toolId}/jobs/${jobId}/artifacts`)
      .then(r => r.data),

  // 下载产物 URL
  getArtifactUrl: (toolId: string, jobId: string, filename: string) =>
    `/api/atomic-tools/${toolId}/jobs/${jobId}/artifacts/${encodeURIComponent(filename)}`,
}
```

### 3.4 通用 Hook

```typescript
// frontend/src/hooks/useAtomicTool.ts
import { useState, useCallback, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { atomicToolsApi } from '../api/atomic-tools'
import type { AtomicJob, ArtifactInfo, FileUploadResponse } from '../types/atomic-tools'

interface UseAtomicToolOptions {
  toolId: string
  pollInterval?: number   // 默认 1000ms
}

interface UseAtomicToolReturn {
  // 文件上传
  uploadedFiles: FileUploadResponse[]
  uploadFile: (file: File) => Promise<FileUploadResponse>
  uploadProgress: number
  isUploading: boolean

  // 任务执行
  job: AtomicJob | null
  runTool: (params: Record<string, unknown>) => Promise<void>
  isRunning: boolean

  // 结果
  artifacts: ArtifactInfo[]
  getDownloadUrl: (filename: string) => string

  // 重置
  reset: () => void
}

export function useAtomicTool(options: UseAtomicToolOptions): UseAtomicToolReturn {
  // 实现:
  // 1. 管理上传文件列表和上传进度
  // 2. 用 useMutation 执行 run
  // 3. run 成功后用 useQuery + refetchInterval 轮询 job 状态
  // 4. job.status === 'completed' 后拉取 artifacts
  // 5. reset() 清空所有状态
  ...
}
```

### 3.5 路由注册

```typescript
// App.tsx 新增路由
import { ToolListPage } from './pages/ToolListPage'
import { ToolPage } from './pages/ToolPage'

// 在 <Routes> 中添加:
<Route path="/tools" element={<ToolListPage />} />
<Route path="/tools/:toolId" element={<ToolPage />} />
```

### 3.6 侧边栏改造

在 `Sidebar.tsx` 中新增可折叠的工具组菜单：

```typescript
// 新增导入
import { Wrench, AudioLines, MessageSquareText, Languages, Mic, ScanSearch, Clapperboard, Music } from 'lucide-react'

// 工具列表（静态定义，与后端 registry 对应）
const toolNavItems = [
  { to: '/tools/separation',    label: t.atomicTools.tools.separation,    icon: AudioLines,        category: 'audio' },
  { to: '/tools/mixing',        label: t.atomicTools.tools.mixing,        icon: Music,             category: 'audio' },
  { to: '/tools/transcription',  label: t.atomicTools.tools.transcription, icon: MessageSquareText, category: 'speech' },
  { to: '/tools/translation',    label: t.atomicTools.tools.translation,   icon: Languages,         category: 'speech' },
  { to: '/tools/tts',            label: t.atomicTools.tools.tts,           icon: Mic,               category: 'speech' },
  { to: '/tools/probe',          label: t.atomicTools.tools.probe,         icon: ScanSearch,        category: 'video' },
  { to: '/tools/muxing',         label: t.atomicTools.tools.muxing,        icon: Clapperboard,      category: 'video' },
]

// 侧边栏中在 Settings 之前渲染:
<div>
  <button onClick={toggleToolsExpanded} className="flex items-center gap-3 px-3 py-2.5 w-full ...">
    <Wrench size={16} />
    {t.atomicTools.title}
    <ChevronDown className={cn('ml-auto transition', isExpanded && 'rotate-180')} size={14} />
  </button>
  {isExpanded && (
    <div className="ml-4 space-y-0.5">
      {toolNavItems.map(item => (
        <Link key={item.to} to={item.to} className="flex items-center gap-2 px-3 py-1.5 text-xs ...">
          <item.icon size={14} />
          {item.label}
        </Link>
      ))}
    </div>
  )}
</div>
```

### 3.7 i18n 扩展

```typescript
// messages.ts 新增 atomicTools 命名空间

// zh-CN
atomicTools: {
  title: '原子工具集',
  subtitle: '独立使用的核心能力',
  backToTools: '返回工具集',
  categories: {
    audio: '音频处理',
    speech: '语音与文字',
    video: '视频与媒体',
  },
  tools: {
    separation: '人声/背景分离',
    mixing: '音频混合',
    transcription: '语音转文字',
    translation: '文本翻译',
    tts: '语音合成',
    probe: '媒体信息探测',
    muxing: '音视频合并',
  },
  descriptions: {
    separation: '从音视频中分离人声轨与背景轨',
    mixing: '将人声与背景音按指定参数混合',
    transcription: '语音识别 + 可选说话人识别，生成带时间戳的文字和字幕',
    translation: '多语言文本翻译，支持术语表',
    tts: '文字转语音，支持声音克隆',
    probe: '检测音视频文件的格式、时长、编码等参数',
    muxing: '将音频轨合并到视频文件中',
  },
  common: {
    start: '开始处理',
    processing: '处理中...',
    completed: '处理完成',
    failed: '处理失败',
    retry: '重试',
    download: '下载',
    downloadAll: '下载全部',
    reset: '重新开始',
    useInTool: '在其他工具中使用',
    uploadHint: '拖入文件或点击上传',
    uploadingFile: '上传中...',
    advancedParams: '高级参数',
    elapsed: (sec: string) => `用时 ${sec}s`,
    fileTooLarge: (max: number) => `文件大小超过限制 (${max}MB)`,
    unsupportedFormat: '不支持的文件格式',
    maxConcurrent: '已达到最大并发，请等待其他任务完成',
  },
  // 各工具特定 labels
  separation: {
    mode: '分离模式',
    quality: '质量',
    outputFormat: '输出格式',
    voiceTrack: '人声轨',
    backgroundTrack: '背景轨',
    routeDecision: '路由决策',
  },
  mixing: {
    voiceFile: '人声音频',
    backgroundFile: '背景音频',
    backgroundGain: '背景音量 (dB)',
    duckingMode: '闪避模式',
  },
  transcription: {
    language: '识别语言',
    asrModel: 'ASR 模型',
    enableDiarization: '启用说话人识别',
    diarizationHint: '识别不同说话人并标注，适合多人对话/会议场景',
    generateSrt: '生成 SRT 字幕',
    totalSegments: '总段落数',
    speakerCount: '说话人数',
  },
  translation: {
    inputMode: '输入方式',
    inputText: '直接输入',
    inputFile: '上传文件',
    sourceLang: '源语言',
    targetLang: '目标语言',
    swap: '互换',
    backend: '翻译后端',
    glossary: '术语表',
    originalText: '原文',
    translatedText: '译文',
  },
  tts: {
    inputText: '合成文本',
    textPlaceholder: '输入要合成的文字...',
    language: '合成语言',
    referenceAudio: '参考音色',
    referenceHint: '上传10-30秒清晰语音作为音色参考',
    synthesizedSpeech: '合成语音',
  },
  probe: {
    mediaType: '媒体类型',
    format: '格式',
    duration: '时长',
    videoStream: '视频流',
    audioStream: '音频流',
    sampleRate: '采样率',
    channels: '声道数',
    copyJson: '复制 JSON',
  },
  muxing: {
    videoFile: '视频文件',
    audioFile: '音频文件',
    videoCodec: '视频编码',
    audioCodec: '音频编码',
    audioBitrate: '音频码率',
    durationMismatch: '视频与音频时长不一致',
  },
},

// en-US (对应英文翻译)
atomicTools: {
  title: 'Atomic Tools',
  subtitle: 'Standalone core capabilities',
  backToTools: 'Back to tools',
  categories: {
    audio: 'Audio Processing',
    speech: 'Speech & Text',
    video: 'Video & Media',
  },
  tools: {
    separation: 'Audio Separation',
    mixing: 'Audio Mixing',
    transcription: 'Speech to Text',
    translation: 'Text Translation',
    tts: 'Text to Speech',
    probe: 'Media Probe',
    muxing: 'Video-Audio Muxing',
  },
  descriptions: {
    separation: 'Separate vocal and background tracks from audio/video',
    mixing: 'Mix voice and background audio with adjustable parameters',
    transcription: 'ASR with optional speaker diarization, generates timestamped text and subtitles',
    translation: 'Multilingual text translation with glossary support',
    tts: 'Text to speech with voice cloning support',
    probe: 'Inspect media file format, duration, codecs, and metadata',
    muxing: 'Merge an audio track into a video file',
  },
  common: {
    start: 'Start',
    processing: 'Processing...',
    completed: 'Completed',
    failed: 'Failed',
    retry: 'Retry',
    download: 'Download',
    downloadAll: 'Download All',
    reset: 'Start Over',
    useInTool: 'Use in another tool',
    uploadHint: 'Drop file here or click to upload',
    uploadingFile: 'Uploading...',
    advancedParams: 'Advanced Options',
    elapsed: (sec: string) => `Elapsed: ${sec}s`,
    fileTooLarge: (max: number) => `File exceeds the ${max}MB limit`,
    unsupportedFormat: 'Unsupported file format',
    maxConcurrent: 'Maximum concurrent jobs reached, please wait',
  },
  separation: {
    mode: 'Mode',
    quality: 'Quality',
    outputFormat: 'Output Format',
    voiceTrack: 'Voice Track',
    backgroundTrack: 'Background Track',
    routeDecision: 'Route Decision',
  },
  mixing: {
    voiceFile: 'Voice Audio',
    backgroundFile: 'Background Audio',
    backgroundGain: 'Background Gain (dB)',
    duckingMode: 'Ducking Mode',
  },
  transcription: {
    language: 'Language',
    asrModel: 'ASR Model',
    enableDiarization: 'Enable Speaker Diarization',
    diarizationHint: 'Identify and label different speakers, ideal for meetings and multi-speaker content',
    generateSrt: 'Generate SRT subtitles',
    totalSegments: 'Total Segments',
    speakerCount: 'Speaker Count',
  },
  translation: {
    inputMode: 'Input Mode',
    inputText: 'Direct Input',
    inputFile: 'Upload File',
    sourceLang: 'Source Language',
    targetLang: 'Target Language',
    swap: 'Swap',
    backend: 'Backend',
    glossary: 'Glossary',
    originalText: 'Original',
    translatedText: 'Translated',
  },
  tts: {
    inputText: 'Input Text',
    textPlaceholder: 'Enter text to synthesize...',
    language: 'Language',
    referenceAudio: 'Reference Voice',
    referenceHint: 'Upload 10-30s of clear speech as a voice reference',
    synthesizedSpeech: 'Synthesized Speech',
  },
  probe: {
    mediaType: 'Media Type',
    format: 'Format',
    duration: 'Duration',
    videoStream: 'Video Stream',
    audioStream: 'Audio Stream',
    sampleRate: 'Sample Rate',
    channels: 'Channels',
    copyJson: 'Copy JSON',
  },
  muxing: {
    videoFile: 'Video File',
    audioFile: 'Audio File',
    videoCodec: 'Video Codec',
    audioCodec: 'Audio Codec',
    audioBitrate: 'Audio Bitrate',
    durationMismatch: 'Video and audio durations do not match',
  },
},
```

---

## 4. 数据流与时序

### 4.1 典型工具执行时序

```
Frontend                    Backend Router              JobManager               Adapter              Runner
   │                            │                          │                       │                    │
   │── POST /upload ──────────→ │                          │                       │                    │
   │                            │── save_upload() ────────→│                       │                    │
   │←── { file_id } ────────── │←────────────────────────│                       │                    │
   │                            │                          │                       │                    │
   │── POST /{tool}/run ─────→ │                          │                       │                    │
   │                            │── create_job() ────────→ │                       │                    │
   │                            │── background: execute() →│                       │                    │
   │←── { job_id, pending } ── │                          │                       │                    │
   │                            │                          │── validate_params() ─→│                    │
   │                            │                          │── run() ─────────────→│                    │
   │                            │                          │                       │── runner func() ──→│
   │── GET /{tool}/jobs/{id} ─→│                          │                       │                    │
   │←── { running, 45% } ───── │←── get_job() ──────────│                       │                    │
   │                            │                          │                       │←── result ─────── │
   │── GET /{tool}/jobs/{id} ─→│                          │←── status=completed ──│                    │
   │←── { completed, result } ─│                          │                       │                    │
   │                            │                          │                       │                    │
   │── GET /../artifacts ─────→│                          │                       │                    │
   │←── [{ filename, url }] ── │                          │                       │                    │
   │                            │                          │                       │                    │
   │── GET /../artifacts/f.wav→│                          │                       │                    │
   │←── [binary data] ──────── │                          │                       │                    │
```

### 4.2 轮询策略

前端在 `useAtomicTool` hook 中使用 React Query 的 `refetchInterval` 轮询：

- Job status 为 `pending` 或 `running` 时：每 1s 轮询
- Job status 为 `completed` 或 `failed` 时：停止轮询
- 第一次拿到 `completed` 后自动拉取 artifacts 列表

---

## 5. 安全考量

### 5.1 文件上传安全

- **文件类型白名单**: 仅接受 `accept_formats` 中定义的扩展名
- **文件头校验**: 对上传文件检查 magic bytes，不仅依赖扩展名
- **路径遍历防护**: file_id 使用 UUID，文件名经过 sanitize，所有路径使用 `.resolve()` + `.relative_to()` 验证
- **大小限制**: 在 nginx/FastAPI 层双重限制

### 5.2 资源保护

- **并发限制**: 单用户最多 2 个并发 Job
- **超时机制**: 每个工具有独立的超时时间（如 probe: 30s, separation: 600s）
- **磁盘空间**: 定期清理 + 启动时检查磁盘可用空间

### 5.3 输入校验

- 所有请求参数通过 Pydantic model 严格校验
- 文本输入长度限制（翻译: 10000字, TTS: 5000字）
- API key 等敏感配置仅从服务端环境变量读取，不从前端传入

---

## 6. 测试策略

### 6.1 后端测试

```
tests/
├── test_atomic_tools_registry.py      # 工具注册表测试
├── test_atomic_tools_job_manager.py   # Job 生命周期测试
├── test_atomic_tools_api.py           # API 路由集成测试
└── test_atomic_tools_adapters/        # 各适配器单测
    ├── test_separation_adapter.py
    ├── test_transcription_adapter.py
    ├── test_translation_adapter.py
    ├── test_tts_adapter.py
    ├── test_probe_adapter.py
    ├── test_mixing_adapter.py
    └── test_muxing_adapter.py
```

测试原则：
- Adapter 测试 monkeypatch 底层 runner 函数，不加载真实模型
- Job Manager 测试使用 `tmp_path`
- API 测试使用 FastAPI TestClient

### 6.2 前端测试

```
frontend/src/test/
├── atomic-tools/
│   ├── useAtomicTool.test.ts        # Hook 测试
│   ├── ToolListPage.test.tsx        # 页面渲染测试
│   └── FileUploadZone.test.tsx      # 组件测试
```

---

## 7. 各工具与现有模块映射

| 原子工具 | 适配器 | 复用的 Runner | 复用的 Request/Result 类型 |
|---------|--------|--------------|--------------------------|
| AT-1 人声分离 | `adapters/separation.py` | `pipeline.runner.separate_file()` | `SeparationRequest` → `SeparationResult` |
| AT-2 音频混合 | `adapters/mixing.py` | `rendering.mixer` (部分复用) | 新建轻量 request |
| AT-3 语音转文字 | `adapters/transcription.py` | `transcription.runner.transcribe_file()` | `TranscriptionRequest` → `TranscriptionResult` |
| AT-4 文本翻译 | `adapters/translation.py` | `translation.runner.translate_script()` | `TranslationRequest` → `TranslationResult` |
| AT-5 语音合成 | `adapters/tts.py` | `dubbing.runner.synthesize_speaker()` | `DubbingRequest` → `DubbingResult` |
| AT-6 媒体探测 | `adapters/probe.py` | `utils.ffmpeg.probe_media()` | `MediaInfo` |
| AT-7 音视频合并 | `adapters/muxing.py` | `utils.ffmpeg.mux_video_with_audio()` | 新建轻量 request |

**AT-2 和 AT-7 说明**: 这两个工具的底层操作较简单（FFmpeg 调用），适配器可直接调用 `utils/ffmpeg.py` 的工具函数，无需走完整的 runner 流程。

---

## 8. 文件组织总览

新增文件清单：

```
# 后端 (Python)
src/translip/server/
├── routes/atomic_tools.py                     # API 路由
└── atomic_tools/
    ├── __init__.py
    ├── registry.py                             # 工具注册表
    ├── schemas.py                              # Pydantic 模型
    ├── job_manager.py                          # 任务管理器
    └── adapters/
        ├── __init__.py                         # ToolAdapter 基类
        ├── separation.py                       # AT-1
        ├── mixing.py                           # AT-2
        ├── transcription.py                    # AT-3
        ├── translation.py                      # AT-4
        ├── tts.py                              # AT-5
        ├── probe.py                            # AT-6
        └── muxing.py                           # AT-7

# 前端 (TypeScript/React)
frontend/src/
├── api/atomic-tools.ts                         # API 客户端
├── types/atomic-tools.ts                       # 类型定义
├── hooks/useAtomicTool.ts                      # 通用 Hook
├── pages/
│   ├── ToolListPage.tsx                        # 工具列表页
│   └── ToolPage.tsx                            # 单工具页
└── components/atomic-tools/
    ├── ToolCard.tsx
    ├── ToolLayout.tsx
    ├── FileUploadZone.tsx
    ├── ParamForm.tsx
    ├── ResultPanel.tsx
    ├── AudioPlayer.tsx
    ├── ToolProgressBar.tsx
    ├── CrossToolAction.tsx
    └── tool-configs/
        ├── SeparationParams.tsx
        ├── MixingParams.tsx
        ├── TranscriptionParams.tsx
        ├── TranslationParams.tsx
        ├── TtsParams.tsx
        ├── ProbeParams.tsx
        └── MuxingParams.tsx

# 测试
tests/
├── test_atomic_tools_registry.py
├── test_atomic_tools_job_manager.py
├── test_atomic_tools_api.py
└── test_atomic_tools_adapters/
    └── ...

# 修改的现有文件
src/translip/server/app.py                      # 挂载新路由 + 清理任务
frontend/src/App.tsx                            # 新增路由
frontend/src/components/layout/Sidebar.tsx      # 新增工具集导航
frontend/src/i18n/messages.ts                   # 新增 atomicTools i18n
```

共计新增约 **25 个文件**，修改 **4 个现有文件**。
