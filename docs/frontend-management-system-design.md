# 前端管理系统技术设计方案

- 项目: `video-voice-separate`
- 文档状态: Draft v1
- 创建日期: 2026-04-14

---

## 1. 目标

为 `video-voice-separate` 视频配音流水线构建一个管理后台前端，用于:

1. 可视化配置流水线参数（全局配置、各节点独立配置）
2. 管理任务列表（创建、查看、重跑、删除）
3. 实时展示任务执行进度（节点级进度 + 整体进度）
4. 查看每个节点的产物和质量报告
5. 最终交付物预览与下载

不需要登录注册，单用户本地管理系统。

---

## 2. 整体架构

```
┌─────────────────────────────────────────────┐
│                  Frontend                    │
│          React + TypeScript + Vite           │
│     TailwindCSS + Framer Motion + shadcn/ui │
└──────────────────┬──────────────────────────┘
                   │  REST + SSE
┌──────────────────┴──────────────────────────┐
│                  Backend                     │
│           FastAPI (Python 3.11+)             │
│     调用已有 Runner 函数 + 监控 Status JSON    │
└────────┬─────────────────┬──────────────────┘
         │                 │
┌────────┴────────┐  ┌─────┴──────────────────┐
│   SQLite (DB)    │  │  Existing Pipeline Core │
│  任务/预设/日志   │  │  orchestration/runners  │
└─────────────────┘  └────────────────────────┘
```

### 2.1 为什么选这套技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 前端框架 | **React 18 + TypeScript** | 生态最成熟，组件库丰富，类型安全 |
| 构建 | **Vite** | 启动快、HMR 快、零配置 |
| UI 组件 | **shadcn/ui** | 基于 Radix UI，风格现代，可定制性强，不依赖重型组件库 |
| 样式 | **TailwindCSS 4** | 原子化 CSS，开发效率高，配合 shadcn/ui 最佳搭档 |
| 动画 | **Framer Motion** | 声明式动画，支持 layout animation、exit animation、spring 物理效果 |
| 图表 | **Recharts** | 轻量，React 原生，用于质量报告可视化 |
| 状态管理 | **Zustand** | 轻量、无 boilerplate，适合中小型应用 |
| 请求 | **TanStack Query (React Query)** | 自动缓存、轮询、乐观更新，完美适配进度监控场景 |
| 后端 | **FastAPI** | 与项目同为 Python，可直接调用已有 Runner/Request 类，零胶水成本 |
| 数据库 | **SQLite + SQLModel** | 零部署、单文件、Python 内置驱动；SQLModel 是 FastAPI 作者的 ORM，Pydantic + SQLAlchemy 无缝融合 |
| 实时通信 | **SSE (Server-Sent Events)** | 服务端推送进度，比 WebSocket 更简单，足够满足单向进度推送需求 |

### 2.2 目录结构建议

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── index.html
├── public/
│   └── favicon.svg
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── routes.tsx                    # React Router 路由定义
│   ├── api/
│   │   ├── client.ts                 # axios / fetch 封装
│   │   ├── tasks.ts                  # 任务 CRUD API
│   │   ├── config.ts                 # 配置读写 API
│   │   └── progress.ts               # SSE 进度订阅
│   ├── stores/
│   │   ├── taskStore.ts              # 任务列表状态
│   │   └── progressStore.ts          # 实时进度状态
│   ├── hooks/
│   │   ├── useTaskProgress.ts        # 进度轮询 / SSE hook
│   │   ├── usePipelineConfig.ts      # 配置表单 hook
│   │   └── useTaskList.ts            # 任务列表查询 hook
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx           # 侧边导航栏
│   │   │   ├── Header.tsx            # 顶栏
│   │   │   └── MainLayout.tsx        # 主布局容器
│   │   ├── pipeline/
│   │   │   ├── PipelineGraph.tsx      # 流水线 DAG 可视化
│   │   │   ├── StageCard.tsx          # 单节点卡片
│   │   │   ├── StageConnector.tsx     # 节点间连线 + 动画
│   │   │   └── ProgressRing.tsx       # 环形进度指示器
│   │   ├── task/
│   │   │   ├── TaskList.tsx           # 任务列表表格
│   │   │   ├── TaskRow.tsx            # 单任务行
│   │   │   ├── TaskDetail.tsx         # 任务详情面板
│   │   │   └── TaskCreateForm.tsx     # 新建任务表单
│   │   ├── config/
│   │   │   ├── GlobalConfig.tsx       # 全局配置面板
│   │   │   ├── StageConfigPanel.tsx   # 节点配置面板
│   │   │   └── ConfigField.tsx        # 通用配置字段组件
│   │   ├── report/
│   │   │   ├── ManifestViewer.tsx     # Manifest JSON 查看器
│   │   │   ├── QualityReport.tsx      # 质量报告概览
│   │   │   └── SegmentTable.tsx       # 片段级详情表
│   │   └── shared/
│   │       ├── StatusBadge.tsx        # 状态标签
│   │       ├── FileSize.tsx           # 文件大小格式化
│   │       └── DurationDisplay.tsx    # 时长格式化
│   ├── pages/
│   │   ├── DashboardPage.tsx          # 首页仪表盘
│   │   ├── TaskListPage.tsx           # 任务列表页
│   │   ├── TaskDetailPage.tsx         # 任务详情页
│   │   ├── NewTaskPage.tsx            # 新建任务页
│   │   └── SettingsPage.tsx           # 全局设置页
│   ├── types/
│   │   ├── pipeline.ts               # 流水线相关类型
│   │   ├── task.ts                    # 任务相关类型
│   │   └── config.ts                 # 配置相关类型
│   └── lib/
│       ├── constants.ts              # 常量定义
│       └── utils.ts                  # 工具函数
└── .env.local                         # API 地址等环境变量
```

---

## 3. 后端 API 设计

### 3.1 API 模块结构

```
src/video_voice_separate/
├── server/
│   ├── __init__.py
│   ├── app.py                    # FastAPI app 入口
│   ├── database.py               # SQLite 引擎、会话、建表
│   ├── models.py                 # SQLModel ORM 模型
│   ├── routes/
│   │   ├── tasks.py              # 任务 CRUD + 执行
│   │   ├── config.py             # 配置管理
│   │   ├── progress.py           # SSE 进度推送
│   │   ├── artifacts.py          # 产物查看与下载
│   │   └── system.py             # 系统信息（设备、模型可用性）
│   ├── schemas.py                # Pydantic 请求/响应模型
│   ├── task_manager.py           # 任务队列管理器
│   └── sse.py                    # SSE 事件封装
```

### 3.2 核心 API 端点

#### 任务管理

| 方法 | 路径 | 描述 |
|------|------|------|
| `POST` | `/api/tasks` | 创建新任务（提交 PipelineRequest） |
| `GET` | `/api/tasks` | 获取任务列表（分页、过滤、排序） |
| `GET` | `/api/tasks/{task_id}` | 获取任务详情（含各阶段状态） |
| `DELETE` | `/api/tasks/{task_id}` | 删除任务及其产物 |
| `POST` | `/api/tasks/{task_id}/rerun` | 重跑任务（可指定从哪个阶段开始） |
| `POST` | `/api/tasks/{task_id}/stop` | 停止正在运行的任务 |

#### 进度推送

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/tasks/{task_id}/progress` | SSE 端点，实时推送进度事件 |
| `GET` | `/api/tasks/{task_id}/status` | 一次性获取当前状态快照 |

#### 产物与报告

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/tasks/{task_id}/manifest` | 获取 pipeline-manifest.json |
| `GET` | `/api/tasks/{task_id}/stages/{stage}/manifest` | 获取单阶段 manifest |
| `GET` | `/api/tasks/{task_id}/stages/{stage}/report` | 获取单阶段 report |
| `GET` | `/api/tasks/{task_id}/artifacts` | 列出所有产物文件 |
| `GET` | `/api/tasks/{task_id}/artifacts/{path}` | 下载/预览具体产物文件 |
| `GET` | `/api/tasks/{task_id}/delivery` | 获取最终交付物列表 |

#### 配置

| 方法 | 路径 | 描述 |
|------|------|------|
| `GET` | `/api/config/defaults` | 获取流水线默认配置 |
| `GET` | `/api/config/presets` | 获取预设配置列表 |
| `POST` | `/api/config/presets` | 保存自定义预设 |
| `GET` | `/api/system/info` | 获取系统信息（GPU、可用模型等） |

#### 响应数据示例

**POST /api/tasks — 创建任务**

请求体:

```json
{
  "name": "迪拜旅拍配音",
  "input_path": "/path/to/video.mp4",
  "target_lang": "en",
  "config": {
    "device": "auto",
    "translation_backend": "local-m2m100",
    "tts_backend": "qwen3tts",
    "run_to_stage": "task-g",
    "fit_policy": "conservative",
    "mix_profile": "preview"
  }
}
```

响应:

```json
{
  "task_id": "task-20260414-173015",
  "name": "迪拜旅拍配音",
  "status": "pending",
  "created_at": "2026-04-14T17:30:15+08:00",
  "config": { ... }
}
```

**GET /api/tasks/{task_id}/progress — SSE 流**

```
event: stage_start
data: {"stage": "stage1", "step": "separating audio", "overall_percent": 0}

event: stage_progress
data: {"stage": "stage1", "percent": 45, "step": "running demucs", "overall_percent": 4.5}

event: stage_complete
data: {"stage": "stage1", "status": "succeeded", "overall_percent": 10}

event: stage_start
data: {"stage": "task-a", "step": "loading ASR model", "overall_percent": 10}

event: pipeline_complete
data: {"status": "succeeded", "overall_percent": 100, "elapsed_sec": 1247.5}
```

### 3.3 后端实现要点

**任务管理器 (TaskManager)**:

```python
class TaskManager:
    """管理任务队列，每个任务在独立线程/进程中运行 pipeline。"""

    def create_task(self, session: Session, request: CreateTaskRequest) -> Task:
        # 1. 生成 task_id
        # 2. 构建 PipelineRequest（复用已有 types.py）
        # 3. 写入 DB（Task 表 + TaskStage 表 + TaskLog）
        # 4. 启动后台线程调用 run_pipeline()
        # 5. 启动进度同步协程
        ...

    def get_task_status(self, session: Session, task_id: str) -> TaskStatus:
        # 优先从 DB 读取（支持离线查询）
        # 运行中的任务补充读取 pipeline-status.json 获取最新进度
        ...

    def list_tasks(self, session: Session, *, status, lang, page, size) -> list[Task]:
        # DB 查询，支持分页、筛选、排序
        ...

    def stream_progress(self, task_id: str) -> AsyncGenerator:
        # 监听 pipeline-status.json 变更，推送 SSE 事件
        ...
```

**核心原则**: 后端不重新实现流水线逻辑，而是直接调用已有的 `run_pipeline()`、`export_delivery()` 等 Runner 函数。进度监控复用已有的 `PipelineMonitor` + `pipeline-status.json` 机制。

### 3.4 数据持久化: 为什么需要数据库

当前流水线的产物（manifest、status.json）都是分散在各任务输出目录下的 JSON 文件。这在 CLI 场景下足够，但管理系统需要:

| 需求 | 纯 JSON 文件 | SQLite |
|------|-------------|--------|
| 任务列表查询（分页、筛选、排序） | 需要遍历所有目录读取 JSON，O(n) | 索引查询，O(log n) |
| 任务统计（总数、各状态计数） | 每次全量扫描 | `SELECT COUNT(*) GROUP BY status` |
| 任务搜索（按名称、语言、时间范围） | 无法高效实现 | `WHERE name LIKE ? AND created_at > ?` |
| 配置预设管理 | 需要额外维护一个 JSON 文件 | 标准 CRUD 表 |
| 操作日志审计 | 无 | 结构化日志表 |
| 任务间的历史关联（重跑关系） | 需手动维护引用 | 外键关联 |
| 后端重启后恢复状态 | 需扫描所有目录重建内存状态 | 直接从 DB 加载 |

结论: **需要数据库**。选择 **SQLite**，原因:

- **零部署**: 不需要安装额外服务，单文件 `data.db`
- **Python 内置**: `sqlite3` 在标准库中，无额外依赖
- **单用户足够**: 本地管理系统不需要并发写入性能
- **可移植**: 数据库文件可直接拷贝备份
- **与 JSON 互补**: DB 负责索引和查询，JSON manifest 保持不变（作为产物的一部分）

#### 3.4.1 数据库文件位置

```
~/.cache/video-voice-separate/
├── data.db                    # SQLite 数据库（主存储）
├── data.db-wal                # WAL 模式日志（自动生成）
└── models/                    # 模型缓存（已有）
```

也可通过环境变量 `VIDEO_VOICE_SEPARATE_DB_PATH` 自定义路径。

#### 3.4.2 ORM 选型: SQLModel

选择 **SQLModel** 而不是裸 SQLAlchemy，原因:

- 由 FastAPI 作者 (tiangolo) 开发，与 FastAPI 天然集成
- 同一个类同时是 **Pydantic model**（请求/响应校验）和 **SQLAlchemy model**（ORM 操作）
- 减少重复定义：不需要分别写 DB model 和 API schema
- 类型安全，IDE 补全友好

#### 3.4.3 数据模型

```python
# server/models.py
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, Column, JSON


class Task(SQLModel, table=True):
    """任务主表 — 每条记录对应一次 pipeline 执行。"""
    __tablename__ = "tasks"

    id: str = Field(primary_key=True)           # task-20260414-173015
    name: str = Field(index=True)               # 用户给的任务名
    status: str = Field(index=True)             # pending / running / succeeded / failed
    input_path: str                             # 原始视频路径
    output_root: str                            # 输出目录根路径
    source_lang: str = Field(default="zh")
    target_lang: str = Field(default="en", index=True)
    config: dict = Field(sa_column=Column(JSON))  # 完整 PipelineConfig JSON

    # 进度快照（从 pipeline-status.json 同步）
    overall_progress: float = Field(default=0.0)  # 0.0 ~ 100.0
    current_stage: Optional[str] = Field(default=None)

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    elapsed_sec: Optional[float] = Field(default=None)

    # 结果
    error_message: Optional[str] = Field(default=None)
    manifest_path: Optional[str] = Field(default=None)

    # 重跑关联
    parent_task_id: Optional[str] = Field(default=None, index=True)


class TaskStage(SQLModel, table=True):
    """任务阶段表 — 记录每个阶段的执行状态。"""
    __tablename__ = "task_stages"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)            # 关联 Task.id
    stage_name: str                             # stage1 / task-a / ... / task-g
    status: str = Field(default="pending")      # pending / running / succeeded / cached / failed / skipped
    progress_percent: float = Field(default=0.0)
    current_step: Optional[str] = Field(default=None)
    cache_hit: bool = Field(default=False)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    elapsed_sec: Optional[float] = Field(default=None)
    manifest_path: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)


class ConfigPreset(SQLModel, table=True):
    """配置预设表 — 用户保存的可复用配置模板。"""
    __tablename__ = "config_presets"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)  # 预设名称
    description: Optional[str] = Field(default=None)
    source_lang: str = Field(default="zh")
    target_lang: str = Field(default="en")
    config: dict = Field(sa_column=Column(JSON))  # 完整配置 JSON
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class TaskLog(SQLModel, table=True):
    """操作日志表 — 记录关键操作供审计和回溯。"""
    __tablename__ = "task_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    action: str                                 # created / started / stage_completed / failed / rerun / deleted
    stage_name: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None) # 附加信息 JSON
    created_at: datetime = Field(default_factory=datetime.now)
```

#### 3.4.4 ER 图

```
┌─────────────┐       ┌──────────────┐
│    Task      │ 1───* │  TaskStage   │
├─────────────┤       ├──────────────┤
│ id (PK)      │       │ id (PK)      │
│ name         │       │ task_id (FK)  │
│ status       │       │ stage_name   │
│ input_path   │       │ status       │
│ output_root  │       │ progress_%   │
│ source_lang  │       │ cache_hit    │
│ target_lang  │       │ elapsed_sec  │
│ config (JSON)│       │ manifest_path│
│ overall_%    │       │ error_message│
│ current_stage│       └──────────────┘
│ created_at   │
│ error_message│       ┌──────────────┐
│ parent_id    │       │  TaskLog     │
└──────┬───────┘       ├──────────────┤
       │          1───* │ id (PK)      │
       │               │ task_id (FK)  │
       │               │ action       │
       │               │ stage_name   │
       │               │ detail (JSON)│
       │               │ created_at   │
       │               └──────────────┘
       │
       │  self-ref (parent_task_id → id) 用于重跑关联
       └──────→ Task

┌──────────────┐
│ ConfigPreset │
├──────────────┤
│ id (PK)      │
│ name (UNIQUE)│
│ description  │
│ source_lang  │
│ target_lang  │
│ config (JSON)│
│ created_at   │
│ updated_at   │
└──────────────┘
```

#### 3.4.5 数据库初始化

```python
# server/database.py
from __future__ import annotations

from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine

from ..config import CACHE_ROOT

_DB_PATH = Path(
    os.environ.get("VIDEO_VOICE_SEPARATE_DB_PATH", CACHE_ROOT / "data.db")
)

engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},  # FastAPI 多线程需要
)


def init_db() -> None:
    """建表（如果不存在）。在 app startup 时调用。"""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 启用 WAL 模式提升并发读性能
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI 依赖注入：每个请求一个 Session。"""
    with Session(engine) as session:
        yield session
```

#### 3.4.6 DB 与 JSON 的职责边界

| 数据 | 存储位置 | 说明 |
|------|---------|------|
| 任务元数据（名称、状态、配置、时间） | **SQLite** | 支持查询、排序、统计 |
| 配置预设 | **SQLite** | CRUD 管理 |
| 操作日志 | **SQLite** | 审计追溯 |
| 实时进度快照 | **pipeline-status.json → SSE** | 高频写入，DB 只做定期同步 |
| 阶段 manifest（产物详情） | **JSON 文件** | 保持与 CLI 兼容，DB 只存路径 |
| 产物文件（音视频、SRT 等） | **文件系统** | DB 只记录路径 |

**原则**: DB 是索引层，JSON 是详情层，文件系统是产物层。三者互补，不重复。

#### 3.4.7 进度同步策略

任务执行时，`PipelineMonitor` 持续写入 `pipeline-status.json`。后端需要将进度同步到 DB 以支持列表页查询:

```python
# 后台线程定期同步进度到 DB（每 5 秒）
async def _sync_progress_to_db(task_id: str, status_path: Path):
    while True:
        if status_path.exists():
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            with Session(engine) as session:
                task = session.get(Task, task_id)
                if task:
                    task.status = payload["status"]
                    task.overall_progress = payload["overall_progress_percent"]
                    task.current_stage = payload.get("current_stage")
                    task.updated_at = datetime.now()
                    # 同步各阶段状态
                    for stage_data in payload.get("stages", []):
                        _upsert_stage(session, task_id, stage_data)
                    session.commit()
            if payload["status"] in ("succeeded", "failed"):
                break
        await asyncio.sleep(5)
```

---

## 4. 页面设计

### 4.1 整体布局

```
┌────────────────────────────────────────────────────────────┐
│  ┌──────┐  Video Voice Separate                     🖥 GPU │
│  │ Logo │  Pipeline Management                      ✓ Ready│
│  └──────┘                                                  │
├────────┬───────────────────────────────────────────────────┤
│        │                                                   │
│  📊    │                                                   │
│ 仪表盘  │              主内容区域                             │
│        │         （根据路由切换页面）                          │
│  📋    │                                                   │
│ 任务列表 │                                                   │
│        │                                                   │
│  ➕    │                                                   │
│ 新建任务│                                                   │
│        │                                                   │
│  ⚙️    │                                                   │
│ 全局设置│                                                   │
│        │                                                   │
│        │                                                   │
├────────┴───────────────────────────────────────────────────┤
│  v0.1.0 · Pipeline Engine Ready                            │
└────────────────────────────────────────────────────────────┘
```

- **侧边栏**: 固定 220px 宽，深色背景 (`slate-900`)，图标 + 文字导航
- **顶栏**: 64px 高，显示项目名 + 系统状态（GPU 可用性、模型状态）
- **主内容区**: 自适应宽度，白色/浅灰背景，内边距 24px

### 4.2 仪表盘页 (Dashboard)

仪表盘是打开应用后的首页，提供全局一览。

```
┌─────────────────────────────────────────────────────────┐
│  仪表盘                                                  │
│                                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │  总任务   │ │ 运行中   │ │ 已完成   │ │ 失败     │      │
│  │   12     │ │   2     │ │   8     │ │   2     │      │
│  │  ↑3 本周  │ │ ● 动画  │ │ ✓       │ │ ✕       │      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
│                                                         │
│  活跃任务                                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 迪拜旅拍配音                           整体 45%    │    │
│  │ ████████████░░░░░░░░░░░░░░░░░░░░░░░░░          │    │
│  │                                                 │    │
│  │ stage1 ──→ task-a ──→ task-b ──→ [task-c] → ·· │    │
│  │   ✓         ✓         ✓       ⟳ 67%            │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 会议录制英文版                         整体 12%    │    │
│  │ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░          │    │
│  │                                                 │    │
│  │ [stage1] ──→ task-a → ···                       │    │
│  │  ⟳ 78%                                          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  最近完成                                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 名称           状态      耗时      完成时间        │   │
│  │ 产品演示JA    ✓ 完成   23m 15s  今天 14:22       │   │
│  │ 教学视频EN    ✓ 完成   45m 02s  今天 11:05       │   │
│  │ 播客配音DE    ✕ 失败    8m 33s  昨天 22:18       │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**设计要点**:

- **统计卡片**: 4 张数字卡片，hover 时轻微上浮 (`translateY(-2px)`)，卡片之间使用 Framer Motion `staggerChildren` 入场动画（依次弹入）
- **活跃任务卡片**: 显示流水线节点图 + 整体进度条。当前执行节点有脉冲动画 (`pulse`)。进度条使用 `spring` 动画平滑过渡
- **最近完成表格**: 简洁表格，状态列用彩色圆点 + 文字

**色彩规范**:

| 状态 | 颜色 | TailwindCSS |
|------|------|-------------|
| 运行中 | 蓝色 | `blue-500` |
| 已完成 | 绿色 | `emerald-500` |
| 失败 | 红色 | `red-500` |
| 等待中 | 灰色 | `slate-400` |
| 已缓存 | 紫色 | `violet-500` |
| 已跳过 | 橙色 | `amber-500` |

### 4.3 任务列表页 (Task List)

```
┌─────────────────────────────────────────────────────────┐
│  任务列表                              🔍 搜索   ➕ 新建  │
│                                                         │
│  筛选: [全部 ▾]  [状态 ▾]  [语言 ▾]    排序: [创建时间 ▾] │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │ □ │ 名称          │ 状态   │ 进度  │ 语言  │ 耗时  │   │
│  ├───┼───────────────┼────────┼───────┼──────┼──────┤   │
│  │ □ │ 迪拜旅拍配音    │ ⟳ 运行 │ 45%  │zh→en│ 12m  │   │
│  │ □ │ 会议录制英文版  │ ⟳ 运行 │ 12%  │zh→en│  3m  │   │
│  │ □ │ 产品演示JA     │ ✓ 完成 │ 100% │zh→ja│ 23m  │   │
│  │ □ │ 教学视频EN     │ ✓ 完成 │ 100% │zh→en│ 45m  │   │
│  │ □ │ 播客配音DE     │ ✕ 失败 │  35% │zh→de│  8m  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  显示 1-5 / 共 12 条                     < 1 2 3 >       │
└─────────────────────────────────────────────────────────┘
```

**设计要点**:

- 表格行 hover 高亮，点击进入任务详情
- 运行中的任务行左侧有蓝色竖条指示器 (`border-left: 3px solid blue-500`)
- 进度列使用 mini 进度条 (高度 6px，圆角)
- 状态标签使用 `StatusBadge` 组件，带柔和背景色
- 支持批量操作（全选 → 批量删除 / 批量重跑）
- 列表使用 Framer Motion `AnimatePresence` 做行的增删动画

### 4.4 新建任务页 (New Task)

新建任务页使用分步表单 (Stepper Form)，将配置分组，降低复杂度。

```
┌─────────────────────────────────────────────────────────┐
│  新建任务                                                │
│                                                         │
│  ① 基础信息 ──── ② 节点配置 ──── ③ 高级选项 ──── ④ 确认   │
│     ●              ○              ○              ○      │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  步骤 1: 基础信息                                 │    │
│  │                                                 │    │
│  │  任务名称    [ 迪拜旅拍配音                    ]  │    │
│  │                                                 │    │
│  │  输入视频    [ 📁 选择文件...                   ]  │    │
│  │              preview: 00:08:54 · 1080p · 44.1kHz│    │
│  │                                                 │    │
│  │  源语言      [ 中文 (zh)              ▾ ]       │    │
│  │  目标语言    [ English (en)           ▾ ]       │    │
│  │                                                 │    │
│  │  配置预设    [ 默认配置               ▾ ]       │    │
│  │                                                 │    │
│  │                           [ 下一步 →]           │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**步骤 2: 节点配置**

```
┌─────────────────────────────────────────────────────────┐
│  步骤 2: 节点配置                                        │
│                                                         │
│  执行范围  从 [stage1 ▾]  到 [task-g ▾]                  │
│                                                         │
│  ┌──── Stage 1: 音频分离 ──────────────────────────┐    │
│  │  模式           [ auto           ▾ ]             │    │
│  │  质量           [ balanced       ▾ ]             │    │
│  │  音乐后端       [ demucs         ▾ ]             │    │
│  │  对话后端       [ cdx23          ▾ ]             │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──── Task A: 语音转写 ───────────────────────────┐    │
│  │  ASR 模型       [ small          ▾ ]             │    │
│  │  生成 SRT       [ ✓ ]                            │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──── Task B: 说话人注册 ─────────────────────────┐    │
│  │  已有注册表      [ 📁 选择...（可选）          ]  │    │
│  │  Top K           [ 3              ]              │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──── Task C: 翻译 ──────────────────────────────┐    │
│  │  翻译后端       [ local-m2m100    ▾ ]            │    │
│  │  术语表         [ 📁 选择...（可选）          ]   │    │
│  │  批量大小       [ 4               ]              │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──── Task D: 语音合成 ──────────────────────────┐    │
│  │  TTS 后端       [ qwen3tts        ▾ ]            │    │
│  │  最大片段数     [ 不限制           ]              │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──── Task E: 时间线装配 ─────────────────────────┐    │
│  │  贴合策略       [ conservative    ▾ ]             │    │
│  │  贴合后端       [ atempo          ▾ ]             │    │
│  │  混音配置       [ preview         ▾ ]             │    │
│  │  降噪模式       [ static          ▾ ]             │    │
│  │  背景增益(dB)   [ -8.0            ]              │    │
│  └──────────────────────────────────────────────────┘    │
│  ┌──── Task G: 视频交付 ──────────────────────────┐    │
│  │  导出 Preview   [ ✓ ]                            │    │
│  │  导出 Dub       [ ✓ ]                            │    │
│  │  容器格式       [ mp4             ▾ ]             │    │
│  │  视频编码       [ copy            ▾ ]             │    │
│  │  音频编码       [ aac             ▾ ]             │    │
│  └──────────────────────────────────────────────────┘    │
│                                                         │
│                  [← 上一步]    [下一步 →]                 │
└─────────────────────────────────────────────────────────┘
```

**步骤 3: 高级选项**

```
┌─────────────────────────────────────────────────────────┐
│  步骤 3: 高级选项                                        │
│                                                         │
│  设备           [ auto (自动检测)    ▾ ]                 │
│  缓存复用       [ ✓ ] 跳过已成功完成的阶段                │
│  保留中间文件   [ ]                                      │
│  保存日志       [ ✓ ]                                    │
│                                                         │
│  API 配置 (SiliconFlow 后端)                             │
│  API Base URL   [ __________________________________ ]  │
│  API Model      [ __________________________________ ]  │
│                                                         │
│                  [← 上一步]    [下一步 →]                 │
└─────────────────────────────────────────────────────────┘
```

**步骤 4: 确认并提交**

```
┌─────────────────────────────────────────────────────────┐
│  步骤 4: 确认                                            │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  任务名称:    迪拜旅拍配音                        │    │
│  │  输入视频:    我在迪拜等你.mp4 (08:54, 1080p)     │    │
│  │  语言方向:    zh → en                            │    │
│  │  执行范围:    stage1 → task-g (全部)              │    │
│  │  翻译后端:    local-m2m100                       │    │
│  │  TTS 后端:    qwen3tts                           │    │
│  │  设备:        auto                               │    │
│  │  缓存复用:    是                                  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  [ ] 保存为预设                                          │
│  预设名称  [ __________________________________ ]       │
│                                                         │
│                  [← 上一步]    [🚀 开始执行]              │
└─────────────────────────────────────────────────────────┘
```

**设计要点**:

- Stepper 指示器使用 Framer Motion 做步骤切换过渡（滑入滑出）
- 节点配置面板使用可折叠的 `Collapsible` 组件（shadcn/ui Accordion）
- 每个配置字段带 tooltip 说明
- 文件选择后自动 probe 媒体信息并预览
- 步骤间切换用 `AnimatePresence` 动画

### 4.5 任务详情页 (Task Detail)

这是系统中最重要的页面，用于查看正在执行或已完成任务的全部信息。

```
┌─────────────────────────────────────────────────────────┐
│  ← 返回列表   迪拜旅拍配音                                │
│                                                         │
│  状态: ⟳ 运行中 · 已运行 12m 34s · 整体 45%              │
│  ████████████████████░░░░░░░░░░░░░░░░░░░░░ 45%          │
│                                                         │
│  ┌─ 流水线进度 ────────────────────────────────────┐    │
│  │                                                 │    │
│  │  ┌────────┐    ┌────────┐    ┌────────┐        │    │
│  │  │Stage 1 │───→│Task A  │───→│Task B  │───→    │    │
│  │  │  ✓     │    │  ✓     │    │  ✓     │        │    │
│  │  │ 2m 15s │    │ 3m 42s │    │ 1m 08s │        │    │
│  │  └────────┘    └────────┘    └────────┘        │    │
│  │                                                 │    │
│  │      ┌────────┐    ┌────────┐    ┌────────┐    │    │
│  │  ───→│Task C  │───→│Task D  │───→│Task E  │──→ │    │
│  │      │ ⟳ 67% │    │ 待执行  │    │ 待执行  │    │    │
│  │      │ 5m 29s │    │  ···   │    │  ···   │    │    │
│  │      └────────┘    └────────┘    └────────┘    │    │
│  │                                                 │    │
│  │                          ┌────────┐             │    │
│  │                     ───→ │Task G  │             │    │
│  │                          │ 待执行  │             │    │
│  │                          │  ···   │             │    │
│  │                          └────────┘             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 节点详情 ──────────────────────────────────────┐    │
│  │  Tabs: [概览] [Stage 1] [Task A] [Task B]       │    │
│  │        [Task C ●] [Task D] [Task E] [Task G]    │    │
│  │                                                 │    │
│  │  ── Task C: 翻译 ──                  状态: ⟳    │    │
│  │                                                 │    │
│  │  进度:  ██████████████░░░░░░░░░░ 67%            │    │
│  │  当前:  批量翻译第 3/4 批                         │    │
│  │  耗时:  5m 29s                                  │    │
│  │                                                 │    │
│  │  配置:                                          │    │
│  │  ┌──────────────────────────────────────────┐   │    │
│  │  │ 翻译后端: local-m2m100                    │   │    │
│  │  │ 模型:     facebook/m2m100_418M           │   │    │
│  │  │ 批量大小: 4                               │   │    │
│  │  │ 术语表:   glossary.json                   │   │    │
│  │  │ 源语言:   zh → en                        │   │    │
│  │  └──────────────────────────────────────────┘   │    │
│  │                                                 │    │
│  │  产物:  (任务完成后展示)                          │    │
│  │  ┌──────────────────────────────────────────┐   │    │
│  │  │ 📄 translation.en.json          下载 👁   │   │    │
│  │  │ 📄 translation.en.editable.json 下载 👁   │   │    │
│  │  │ 📄 translation.en.srt           下载 👁   │   │    │
│  │  │ 📄 task-c-manifest.json         下载 👁   │   │    │
│  │  └──────────────────────────────────────────┘   │    │
│  │                                                 │    │
│  │  Manifest 预览:                                  │    │
│  │  ┌──────────────────────────────────────────┐   │    │
│  │  │ {                                        │   │    │
│  │  │   "job_id": "voice",                     │   │    │
│  │  │   "request": { ... },                    │   │    │
│  │  │   "resolved": {                          │   │    │
│  │  │     "segment_count": 171,                │   │    │
│  │  │     "qa_flag_counts": { ... }            │   │    │
│  │  │   },                                     │   │    │
│  │  │   "status": "succeeded"                  │   │    │
│  │  │ }                                        │   │    │
│  │  └──────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 操作 ─────────────────────────────────────────┐    │
│  │  [🔄 从 Task C 重跑]  [⏹ 停止任务]  [🗑 删除]    │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

**设计要点**:

- **流水线 DAG 图**: 节点用圆角卡片呈现，节点之间用 SVG 连线。已完成节点为绿色填充，运行中节点有蓝色呼吸灯效果 (`animate-pulse`)，待执行节点为灰色虚线边框。使用 Framer Motion 的 `layout` 属性让节点状态切换有平滑过渡
- **节点详情 Tabs**: 点击 DAG 图的节点或 Tab 切换详情。运行中的 Tab 标签带动画指示器（蓝色脉冲点）
- **产物列表**: 任务完成后展示产物文件，支持直接下载和 JSON 预览
- **Manifest 预览**: 使用语法高亮的 JSON 查看器，可折叠/展开
- **操作区**: 重跑支持从指定阶段开始（dropdown 选择起始阶段）

### 4.6 全局设置页 (Settings)

```
┌─────────────────────────────────────────────────────────┐
│  全局设置                                                │
│                                                         │
│  ┌─ 系统信息 ─────────────────────────────────────┐    │
│  │  Python:  3.12.3                                │    │
│  │  设备:    MPS (Apple M2 Pro)                    │    │
│  │  缓存目录: ~/.cache/video-voice-separate        │    │
│  │  缓存大小: 4.2 GB                 [清理缓存]     │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 模型状态 ─────────────────────────────────────┐    │
│  │  模型名称              状态       操作           │    │
│  │  CDX23 weights        ✓ 已下载    —             │    │
│  │  faster-whisper small ✓ 已下载    —             │    │
│  │  SpeechBrain ECAPA    ✓ 已下载    —             │    │
│  │  M2M100 418M          ✕ 未下载   [下载]         │    │
│  │  Qwen3TTS             ✓ 已下载    —             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 默认配置 ─────────────────────────────────────┐    │
│  │  默认设备         [ auto           ▾ ]          │    │
│  │  默认目标语言     [ en             ▾ ]          │    │
│  │  默认翻译后端     [ local-m2m100   ▾ ]          │    │
│  │  默认 TTS 后端    [ qwen3tts       ▾ ]          │    │
│  │  输出目录         [ ./output-pipeline        ]  │    │
│  │                                   [保存]        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─ 配置预设 ─────────────────────────────────────┐    │
│  │  预设名称         语言方向   创建时间     操作    │    │
│  │  高质量中英配音   zh→en   04-12 10:00  编辑 删除 │    │
│  │  快速预览日语     zh→ja   04-10 15:30  编辑 删除 │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## 5. 核心交互与动画设计

### 5.1 流水线节点动画

| 状态 | 视觉效果 | Framer Motion 代码 |
|------|----------|-------------------|
| 待执行 | 灰色虚线边框，50% 透明度 | `opacity: 0.5, borderStyle: "dashed"` |
| 运行中 | 蓝色实线边框 + 呼吸灯 | `animate={{ boxShadow: ["0 0 0 0 rgba(59,130,246,0)", "0 0 0 8px rgba(59,130,246,0.3)", "0 0 0 0 rgba(59,130,246,0)"] }}, transition={{ duration: 2, repeat: Infinity }}` |
| 已完成 | 绿色填充，勾号图标弹入 | `initial={{ scale: 0 }}, animate={{ scale: 1 }}, transition={{ type: "spring", stiffness: 300 }}` |
| 缓存命中 | 紫色填充，缓存图标 | 同已完成，颜色不同 |
| 失败 | 红色边框 + 抖动 | `animate={{ x: [0, -4, 4, -4, 0] }}, transition={{ duration: 0.4 }}` |

### 5.2 进度条动画

- 进度条使用 Framer Motion `animate` 配合 `spring` 物理效果，每次进度更新平滑过渡
- 进度百分比数字使用 `useMotionValue` + `useTransform` 做数字滚动效果

```tsx
// 伪代码
<motion.div
  className="h-2 rounded-full bg-blue-500"
  initial={{ width: "0%" }}
  animate={{ width: `${percent}%` }}
  transition={{ type: "spring", stiffness: 100, damping: 20 }}
/>
```

### 5.3 页面切换动画

- 路由切换使用 `AnimatePresence` + `motion.div`，fade + slide 过渡
- Stepper 步骤切换使用左右滑动动画
- 列表项增减使用 `layoutId` 做 FLIP 动画

### 5.4 卡片入场动画

- 统计卡片使用 `staggerChildren: 0.1`，从左到右依次弹入
- 任务列表首次加载使用 `staggerChildren: 0.05`，逐行淡入

### 5.5 状态切换微动画

- StatusBadge 切换时缩放弹跳 (`scale: [1, 1.2, 1]`)
- Tab 指示器使用 `layoutId` 做滑动跟随

---

## 6. 实时进度方案

### 6.1 进度数据流

```
PipelineMonitor                      FastAPI                        Frontend
(pipeline-status.json)              (SSE endpoint)              (React Query + SSE)
       │                                │                              │
       │  每 2s 写入 status.json         │                              │
       ├───────────────────────────────→│                              │
       │                                │  watchfiles 检测变更           │
       │                                ├─────────────────────────────→│
       │                                │  SSE: stage_progress event   │
       │                                │                              │
       │                                │                              ├─→ 更新 Zustand Store
       │                                │                              ├─→ 更新进度条动画
       │                                │                              └─→ 更新 DAG 节点状态
```

### 6.2 后端 SSE 实现

```python
# server/routes/progress.py
import asyncio
from pathlib import Path
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/api/tasks/{task_id}/progress")
async def stream_progress(task_id: str):
    status_path = _resolve_status_path(task_id)

    async def event_generator():
        last_mtime = 0.0
        while True:
            if status_path.exists():
                mtime = status_path.stat().st_mtime
                if mtime > last_mtime:
                    last_mtime = mtime
                    payload = json.loads(
                        status_path.read_text(encoding="utf-8")
                    )
                    yield {
                        "event": _classify_event(payload),
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
                    if payload.get("status") in ("succeeded", "failed"):
                        break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
```

### 6.3 前端 SSE 消费

```typescript
// hooks/useTaskProgress.ts
function useTaskProgress(taskId: string) {
  const updateProgress = useProgressStore((s) => s.updateProgress);

  useEffect(() => {
    const source = new EventSource(`/api/tasks/${taskId}/progress`);

    source.addEventListener("stage_progress", (e) => {
      const data = JSON.parse(e.data);
      updateProgress(taskId, data);
    });

    source.addEventListener("pipeline_complete", (e) => {
      const data = JSON.parse(e.data);
      updateProgress(taskId, data);
      source.close();
    });

    return () => source.close();
  }, [taskId]);
}
```

### 6.4 进度权重映射

复用已有的 `STAGE_WEIGHTS` (orchestration/stages.py):

```typescript
const STAGE_WEIGHTS: Record<string, number> = {
  "stage1": 0.10,
  "task-a": 0.10,
  "task-b": 0.10,
  "task-c": 0.15,
  "task-d": 0.35,  // 最耗时
  "task-e": 0.20,
};

// 整体进度 = Σ (已完成阶段权重 × 100) + (当前阶段权重 × 当前阶段进度)
```

---

## 7. 关键 TypeScript 类型定义

```typescript
// types/pipeline.ts

type StageStatus = "pending" | "running" | "succeeded" | "cached" | "failed" | "skipped";
type TaskStatus = "pending" | "running" | "succeeded" | "failed";
type PipelineStageName = "stage1" | "task-a" | "task-b" | "task-c" | "task-d" | "task-e" | "task-g";

interface StageProgress {
  stage_name: PipelineStageName;
  status: StageStatus;
  progress_percent: number;
  current_step: string;
  updated_at: string;
  elapsed_sec?: number;
  artifacts?: Record<string, string>;
  error?: string;
}

interface TaskProgress {
  job_id: string;
  status: TaskStatus;
  overall_progress_percent: number;
  current_stage: PipelineStageName | null;
  updated_at: string;
  stages: StageProgress[];
}

interface Task {
  task_id: string;
  name: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  input_path: string;
  source_lang: string;
  target_lang: string;
  config: PipelineConfig;
  progress?: TaskProgress;
  manifest?: PipelineManifest;
  elapsed_sec?: number;
  error?: string;
}

// types/config.ts

interface PipelineConfig {
  device: "auto" | "cpu" | "cuda" | "mps";
  run_from_stage: PipelineStageName;
  run_to_stage: PipelineStageName;
  reuse_existing: boolean;

  // Stage 1
  separation_mode: "auto" | "music" | "dialogue";
  separation_quality: "balanced" | "high";

  // Task A
  asr_model: string;
  write_srt: boolean;

  // Task B
  registry_path?: string;
  top_k: number;

  // Task C
  translation_backend: "local-m2m100" | "siliconflow";
  glossary_path?: string;
  batch_size: number;

  // Task D
  tts_backend: "qwen3tts" | "f5tts";
  max_segments?: number;

  // Task E
  fit_policy: "conservative" | "high_quality";
  fit_backend: "atempo" | "rubberband";
  mix_profile: "preview" | "enhanced";
  ducking_mode: "static" | "sidechain";
  background_gain_db: number;

  // Task G
  export_preview: boolean;
  export_dub: boolean;
  container: "mp4";
  video_codec: "copy" | "libx264";
  audio_codec: "aac";
  audio_bitrate: string;
}
```

---

## 8. 后端与现有代码集成方案

### 8.1 集成原则

1. **不修改现有 Runner 逻辑**: 后端作为薄层调用已有函数
2. **复用已有类型**: `ExportVideoRequest`, `PipelineRequest` 等直接使用
3. **复用已有进度机制**: `PipelineMonitor` + `pipeline-status.json` 不改
4. **新增代码放在 `server/` 子包**: 与现有模块隔离

### 8.2 FastAPI 入口

```python
# src/video_voice_separate/server/app.py
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routes import tasks, config, progress, artifacts, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    init_db()
    yield


app = FastAPI(title="Video Voice Separate", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(progress.router)
app.include_router(artifacts.router)
app.include_router(system.router)

# 生产环境可挂载前端 build 产物
# app.mount("/", StaticFiles(directory="frontend/dist", html=True))
```

### 8.3 任务执行模型

```python
# server/task_manager.py
from concurrent.futures import ThreadPoolExecutor
from sqlmodel import Session
from .database import engine
from .models import Task, TaskStage, TaskLog

class TaskManager:
    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active: dict[str, Future] = {}

    def submit(self, task_id: str, request: PipelineRequest) -> None:
        """在线程池中启动 pipeline 执行。"""
        future = self._executor.submit(self._run, task_id, request)
        self._active[task_id] = future

    def _run(self, task_id: str, request: PipelineRequest) -> None:
        """实际调用已有 run_pipeline()，完成后更新 DB。"""
        from ..orchestration.runner import run_pipeline

        # 更新状态为 running
        with Session(engine) as session:
            task = session.get(Task, task_id)
            task.status = "running"
            task.started_at = datetime.now()
            session.add(TaskLog(
                task_id=task_id, action="started"
            ))
            session.commit()

        try:
            result = run_pipeline(request)
            # 写回 DB
            with Session(engine) as session:
                task = session.get(Task, task_id)
                task.status = "succeeded" if result.status == "succeeded" else "failed"
                task.finished_at = datetime.now()
                task.elapsed_sec = result.elapsed_sec
                task.manifest_path = str(result.manifest_path)
                task.overall_progress = 100.0
                task.error_message = result.error
                session.commit()
        except Exception as exc:
            with Session(engine) as session:
                task = session.get(Task, task_id)
                task.status = "failed"
                task.finished_at = datetime.now()
                task.error_message = str(exc)
                session.add(TaskLog(
                    task_id=task_id, action="failed", detail=str(exc)
                ))
                session.commit()
        finally:
            self._active.pop(task_id, None)
```

### 8.4 CLI 扩展

建议在 `cli.py` 中新增一个 `serve` 子命令:

```bash
uv run video-voice-separate serve --port 8000 --host 0.0.0.0
```

---

## 9. 开发与部署

### 9.1 开发环境

```bash
# 后端
cd /path/to/video-voice-separate
uv sync
uv run video-voice-separate serve --port 8000 --reload

# 前端
cd frontend
npm install
npm run dev  # Vite dev server at :5173, proxy API to :8000
```

Vite 开发代理配置:

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

### 9.2 生产部署

```bash
# 1. 构建前端
cd frontend && npm run build

# 2. 启动后端（挂载前端静态文件）
uv run video-voice-separate serve --port 8000 --static-dir frontend/dist
```

单进程部署，FastAPI 挂载前端 `dist/` 为 static files，不需要 nginx。

### 9.3 依赖新增

后端新增 Python 依赖:

```toml
# pyproject.toml [project.optional-dependencies]
[project.optional-dependencies]
server = [
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.34,<1",
    "sse-starlette>=2.0,<3",
    "watchfiles>=1.0,<2",
    "sqlmodel>=0.0.22,<1",
]
```

安装: `uv sync --extra server`

> 注: SQLite 驱动 `sqlite3` 是 Python 标准库，无需额外安装。`sqlmodel` 内含 `sqlalchemy` 和 `pydantic` 依赖。

---

## 10. 实现顺序建议

| 阶段 | 内容 | 预期产出 |
|------|------|----------|
| **Phase 1** | 后端骨架 | FastAPI app, SQLite 建表, 任务 CRUD API, 系统信息 API |
| **Phase 2** | 前端骨架 | 项目初始化, 布局, 路由, 空页面 |
| **Phase 3** | 任务创建流程 | 新建任务页 (Stepper Form) + 后端创建 & 执行 |
| **Phase 4** | 实时进度 | SSE 端点 + 进度条 + 流水线 DAG 可视化 |
| **Phase 5** | 任务列表 + 仪表盘 | 列表页, 筛选排序, 仪表盘统计 |
| **Phase 6** | 详情与产物 | 节点详情 Tabs, Manifest 查看, 产物下载 |
| **Phase 7** | 动画打磨 | 入场动画, 节点状态动画, 微交互优化 |
| **Phase 8** | 设置与预设 | 全局设置页, 配置预设管理 |

---

## 11. 风险与取舍

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Task D 耗时极长 (占 35%) | 用户等待焦虑，页面可能被关闭 | SSE 保证重连后恢复进度；进度细粒度到 speaker 级别 |
| 大文件产物下载 | WAV 文件可达数百 MB | 产物下载走独立 streaming 端点，不走 JSON |
| 并发任务资源抢占 | GPU 显存不足导致 OOM | TaskManager 限制 `max_workers`，默认 1；队列排队 |
| Pipeline 中途崩溃 | 前端状态不一致 | 每次进入详情页先读一次 status.json 做状态校正；后端启动时扫描 running 状态任务标记为 failed |
| 后端长期运行稳定性 | 内存泄漏、线程泄漏 | 使用 ProcessPoolExecutor 替代 ThreadPoolExecutor 隔离 |
| SQLite 并发写入 | 写锁竞争导致超时 | WAL 模式 + 单 TaskManager 串行写入；进度同步间隔 5 秒降低写频率 |
| 数据库与文件系统不一致 | DB 记录存在但产物被手动删除 | 任务详情页加载时校验关键文件存在性，标记异常 |

---

## 12. 当前建议结论

首发建议:

- 后端: FastAPI 薄层，直接调用已有 Runner 函数，复用 `pipeline-status.json` 做进度推送
- 前端: React + shadcn/ui + Framer Motion，管理系统风格，侧边栏 + 多页面
- 核心页面: 仪表盘、任务列表、新建任务 (Stepper)、任务详情 (DAG + Tabs)、全局设置
- 实时进度: SSE 推送，前端 Zustand 状态管理，Framer Motion 动画增强体验
- 不做: 登录注册、多用户、WebSocket 双向通信、复杂权限

以最小可用、最大稳定为原则，先跑通创建→执行→进度→产物的完整闭环，再逐步增强动画和细节。
