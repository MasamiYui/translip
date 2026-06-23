# 实验室（Lab）模块产品需求文档（PRD）

> 文档版本：v1.0
> 完成日期：2026-06-22
> 文档定位：基于当前已落地代码反推的需求文档。用于：① 让产品/设计/工程团队对齐当前模块的能力边界；② 为下一阶段的迭代规划提供可继承的基线。
> 范围：translip 项目「实验室」模块，包括后端 `translip_lab` 包、`translip-lab-server` HTTP 服务，以及前端 `/lab` 页面（即内嵌实验室）。

---

## 1. 背景与目标

### 1.1 业务背景

translip 是面向中文影视剧的字幕提取 / ASR / 翻译 / 配音流水线产品。在持续迭代中，团队面临几个无法回避的问题：

1. **模型升级缺乏量化依据**：新接入一个 ASR / Diarization / TTS 模型时，无法快速回答「这次改动是真的更好，还是只是个例感觉更好」。
2. **没有可重复的回归基线**：每一次工程改动都可能引入隐性 regression，但缺乏一个跨场景、可复跑、可对比的评测台。
3. **公开数据集的价值无法沉淀**：WenetSpeech-Drama、AISHELL-4、AliMeeting 等中文公开数据集质量好但接入成本高，且每个团队成员各自跑各自的脚本，结果不可比。

### 1.2 产品目标

实验室模块的产品目标是：

> **以"标准化数据集 × 标准化场景指标 × 可对比 Run 历史"为核心，把模型/流水线优化从经验驱动转为数据驱动。**

它不是终端用户面向的功能（普通字幕/配音用户用不到），而是面向**算法工程师、产品决策者、QA**三类内部用户的"产品研发支持系统"。

### 1.3 三个 Tier 的成功指标

| 层级 | 指标 | 目标 |
|---|---|---|
| **体验** | 不启动后端也能体验完整产品形态 | ✅ 已落地：mock fallback + 演示数据徽标 |
| **能力** | 可以一键跑 1 个 ASR/Diarization/分离 等场景的小规模评测 | ✅ 已落地：`translip-lab run --suite X --limit N` |
| **决策** | 可以选 2 个 run 自动算出每个场景主指标的相对变化、判定 winner | ✅ 已落地：回归对比 Tab |

---

## 2. 用户画像与典型场景

### 2.1 用户画像

| 角色 | 关心什么 | 痛点 |
|---|---|---|
| **算法工程师 A** | 我新换的 paraformer-large 比 whisper-large-v3 在影视剧场景下 CER 差多少？ | 之前要自己写脚本 + 自己整理 manifest + 自己算指标 |
| **产品经理 B** | 现在产品在 wenetspeech-drama 的最佳 CER 是多少？比上次发版前进步了吗？ | 没有可视化的 leaderboard 与历史 |
| **QA C** | 这次合入 PR 之后，分离/OCR/配音三个场景的指标是否有 regression？ | 缺少跨场景的统一回归视图 |

### 2.2 典型场景（Job Stories）

- **JS-01**：当一个工程师**接入新模型**时，他想要**用 3 条样本快速跑通 pipeline**，以便**确认接口是通的、不会浪费时间在小规模上**。
  - 当前能力对应：[ExperimentsTab](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L273-L357) 的 `--limit 3` 试跑按钮。
- **JS-02**：当一个工程师**完成一次较大规模评测**后，他想要**把这次 run 加入历史排行榜**，以便**与团队其他 arm 比较**。
  - 当前能力对应：[LeaderboardTab](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L359-L462) 自动排序 + 🏆 标记最佳。
- **JS-03**：当一个产品决策者**要在两个候选模型间做选择**时，他想要**让系统自动算出每个场景的 delta 与 winner**，以便**不依赖人为判断**。
  - 当前能力对应：[RegressionTab](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L485-L612) 的回归对比表格。
- **JS-04**：当一个新成员**第一次打开模块**时，他想要**不下载任何数据集就能看到完整产品形态**，以便**判断这个东西是不是对自己有用**。
  - 当前能力对应：[callOrFallback](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/lab.ts#L57-L79) mock fallback + 紫色「演示数据」徽标。

---

## 3. 功能架构总览

```
┌────────────────────────────────────────────────────────────────┐
│                    实验室前端 ( /lab 路由 )                     │
│  ┌────────────┬───────────────┬──────────────┬──────────────┐  │
│  │ 数据集 Tab │ 评测实验 Tab  │ 排行榜 Tab   │ 回归对比 Tab │  │
│  └────────────┴───────────────┴──────────────┴──────────────┘  │
│         + 顶部 4 张 StatCard（数据集/套件/run/最佳 CER）        │
│         + SourceBadge（实时数据 / 演示数据）                    │
└────────────────────────────┬───────────────────────────────────┘
                             │ HTTP (axios, baseURL=:8799)
                             │ ↓ 网络错误自动 fallback ↓
              ┌──────────────┴───────────────┐
              │                              │
   ┌──────────▼──────────┐        ┌──────────▼──────────┐
   │ translip-lab-server │        │ labMock.ts (前端)   │
   │  FastAPI :8799      │        │  6 场景/8 套件/     │
   │  /api/lab/*         │        │  6 数据集/7 run     │
   └──────────┬──────────┘        └─────────────────────┘
              │
   ┌──────────▼─────────────────────────────────────────┐
   │ translip_lab 包 (Python)                            │
   │  ├─ datasets/     6 种适配器（wenetspeech_drama 等）│
   │  ├─ scenarios/    6 类场景（asr/diar/sep/ocr/...）  │
   │  ├─ metrics/      text/audio/image/diarization      │
   │  ├─ core/         runner / cache / run_store        │
   │  ├─ report/       markdown / html 导出              │
   │  ├─ server/       FastAPI 服务                      │
   │  ├─ cli.py        `translip-lab` 命令               │
   │  └─ suites/       *.toml 评测套件定义               │
   └────────────────────────────────────────────────────┘
```

---

## 4. 功能模块详细说明

### 4.1 模块一：数据集中心（Datasets）

#### 4.1.1 已实现能力

- **数据集注册中心**：通过 `translip_lab.datasets` 包内置多种适配器，每个适配器声明自己适合做什么（`provides: ['asr', 'diarization']`）、期望本地目录结构、是否已就绪。
- **6 个已实现的数据集适配器**：
  - [wenetspeech_drama](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/wenetspeech_drama.py) — 22,435 h 总量中 4,338.2 h drama 子集（YouTube 影视）
  - [aishell4](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/aishell4.py) — 8 人会议室
  - [alimeeting](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/alimeeting.py) — 8K 会议
  - [synthetic_subtitle](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/synthetic_subtitle.py) — 用于 OCR
  - [synthetic_mix](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/synthetic_mix.py) — 用于人声分离
  - [folder](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/folder.py) / [textgrid_folder](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/textgrid_folder.py) / [clip](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets/clip.py) — 通用本地目录
- **前端展示**：[DatasetsTab](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L186-L271) 以表格形式呈现：
  - 名称（+ subset）
  - 许可证
  - 适用场景（chip）
  - 本地就绪状态（绿色 "已就绪" / 灰色 "未放置"）
  - 样本量 + 总时长
  - 期望目录结构

#### 4.1.2 关键设计决策

- **目录优先而非云优先**：所有数据集都以「本地是否存在 expected_layout」作为可用性判定，不绑定具体云存储，便于离线部署。
- **WenetSpeech 三档下载策略**：
  - mini 1-2 GB：仅 demo
  - drama 全量 150-180 GB：影视专项
  - 全量 ≥500 GB：完整能力
- **Mock 数据兜底**：[MOCK_DATASETS](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/labMock.ts) 让前端无后端即可体验。

#### 4.1.3 需求来源 & 已知缺口

| 需求来源 | 是否覆盖 | 缺口 |
|---|---|---|
| 用户能看见有哪些数据集可用 | ✅ | — |
| 用户能知道本地是否已就绪 | ✅ | — |
| 用户能从 UI 触发下载 | ❌ | 当前需手工 + EULA |
| 用户能看到完整性校验 | ⚠️ | 仅 exists，不校验 sha |

---

### 4.2 模块二：评测场景（Scenarios）

#### 4.2.1 已实现能力

- **6 个已实现的场景适配器**（每个都标注主指标 + 越大/越小越好）：

| 场景 ID | 中文名 | 主指标 | 越小越好 | 文件 |
|---|---|---|---|---|
| `asr` | 语音转写 | `cer_micro` | ✅ | [asr.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios/asr.py) |
| `diarization` | 说话人分离 | `der` | ✅ | [diarization.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios/diarization.py) |
| `separation` | 人声分离 | `si_sdr` | ❌ | [separation.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios/separation.py) |
| `ocr_detect` | 字幕定位 | `f1` | ❌ | [ocr_detect.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios/ocr_detect.py) |
| `subtitle_erase` | 字幕擦除 | `psnr` | ❌ | [subtitle_erase.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios/subtitle_erase.py) |
| `e2e_dub` | 端到端配音 | `mcd` | ✅ | [e2e_dub.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios/e2e_dub.py) |

- **场景的统一接口**（[core/scenario.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/core/scenario.py)）：
  - `required_gt`：声明需要哪些 ground truth 字段
  - `primary_metric` + `higher_is_better`
  - `run(sample, arm) → metrics dict`

#### 4.2.2 需求来源 & 已知缺口

| 需求来源 | 是否覆盖 | 缺口 |
|---|---|---|
| 6 个核心场景都能跑 | ✅ | — |
| 同一场景下多个 arm 并发对比 | ✅ | 通过 suite TOML 配置 |
| 自定义场景 | ⚠️ | 需写 Python，无 UI |

---

### 4.3 模块三：评测套件（Suites & Runs）

#### 4.3.1 已实现能力

- **Suite 即"一次评测的配方"**，由 TOML 文件描述（[asr-drama-wenetspeech.toml](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/suites/asr-drama-wenetspeech.toml)）：包含数据集、场景、参与对比的 arms（模型组合）。
- **CLI 入口**：
  ```bash
  translip-lab run --suite asr-drama-wenetspeech --limit 32
  translip-lab compare --baseline <run1> --candidate <run2>
  translip-lab doctor   # 环境/数据集检查
  ```
- **前端触发**：[ExperimentsTab](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L273-L357) 显示套件卡片，每张卡有：
  - 套件名、数据集
  - 场景 chip
  - **「试跑 (limit=3)」**按钮 → POST `/api/lab/runs` → 返回拼装好的 cmd
- **Run 状态**：4 种（`finished` / `running` / `failed` / `queued`），UI 用复用的 [StatusBadge](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/shared/StatusBadge.tsx) 呈现，running 行加左侧蓝条。
- **Run 历史持久化**：[core/run_store.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/core/run_store.py)，文件系统型。
- **缓存层**：[core/cache.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/core/cache.py) — 同输入相同 arm 命中缓存，加 `--no-cache` 绕过。

#### 4.3.2 需求来源 & 已知缺口

| 需求来源 | 是否覆盖 | 缺口 |
|---|---|---|
| 一键触发评测 | ✅ | 但目前是触发拼装命令，不是后端真跑（webhook 模式） |
| 查看历史 run | ✅ | — |
| Run 进度可视化 | ⚠️ | 只有 finished/running 二分，没有 % 进度 |
| 失败原因可追溯 | ❌ | 需要 UI 展示 stderr |
| 任务队列（多 run 排队） | ❌ | 目前是同步触发 |

---

### 4.4 模块四：排行榜（Leaderboard）

#### 4.4.1 已实现能力

- 自动从全部 run 中按**主指标** + **LOWER_IS_BETTER 集合**排序。
- 🏆 标记当前最佳，其它行显示排名数字。
- 展示列：`#` / `Run ID` / `Suite` / `模型 arm` / `场景 chip` / `状态` / `主指标值 + 指标名` / `RTF` / `创建时间` / `耗时`。
- **响应式**：次要列在窄屏隐藏（`hidden md:table-cell` / `hidden lg:table-cell`），对齐 [TaskListPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/TaskListPage.tsx) 风格。

#### 4.4.2 需求来源 & 已知缺口

| 需求来源 | 是否覆盖 | 缺口 |
|---|---|---|
| 一眼看出"现在的最佳模型" | ✅ | — |
| 按场景过滤 | ❌ | 当前混排所有场景 |
| 按时间窗口过滤 | ❌ | — |
| 多指标可切换 | ❌ | 只看主指标 |
| 行点击进 run 详情页 | ❌ | 当前只展示，没有详情路由 |

---

### 4.5 模块五：回归对比（Regression）

#### 4.5.1 已实现能力

- **两个 select**：baseline & candidate，默认自动预选最近两个 `finished` run（[useMemo + finishedRuns[0/1]](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L499-L506)）。
- **对比按钮触发**：调用 [labApi.compare](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/lab.ts#L173-L180)（mock 时走 [buildMockCompare](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/labMock.ts) 计算）。
- **结果表格**展示 per_scenario：
  - 场景 chip + 主指标名（+ "越大/越小越好"）
  - baseline 值 / candidate 值
  - delta（绿色 ↓ improved / 红色 ↑ regressed / 灰色 - no change，由 [DeltaCell](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx#L464-L483) 可视化）
  - 相对变化 %
- **Winner 判定**：自动算出谁更好或持平。

#### 4.5.2 需求来源 & 已知缺口

| 需求来源 | 是否覆盖 | 缺口 |
|---|---|---|
| 自动判定 winner | ✅ | — |
| 每个场景每个指标分别看 | ⚠️ | 当前只看每场景的"主指标"，不显示次要指标 |
| 多于 2 个 run 对比 | ❌ | 只能两两 |
| 导出对比报告 | ❌ | [report/markdown.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/report/markdown.py) 已有但前端没暴露 |

---

### 4.6 模块六：体验保障层（前端基础设施）

#### 4.6.1 已实现能力

- **Mock fallback**：[callOrFallback](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/lab.ts#L57-L79) — 后端不在/网络错误自动降级到 mock，非网络错误（4xx/5xx）继续抛。
- **SourceBadge**：右上角实时显示「实时数据 / 演示数据」徽标，让用户始终知道当前看到的是不是真实运行结果。
- **i18n 双语**：中英文完全对称的 ~30 个 lab 文案，集中在 [messages.ts](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/i18n/messages.ts#L2110-L2218)。
- **URL 状态**：当前 Tab 写入 `?tab=xxx`，刷新保留。
- **UI 规范对齐**：完全对齐项目 UI 规范（主蓝 `#3b5bdb`、卡片 `border-[#e5e7eb] shadow-[0_1px_3px_rgba(0,0,0,.04)]`、表头 `text-[#9ca3af] uppercase tracking-wide`、复用项目共享的 [PageContainer](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/PageContainer.tsx) 与 [StatusBadge](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/shared/StatusBadge.tsx)）。

#### 4.6.2 关键设计原则

- 复用 > 重写：所有项目已有的共享原语（PageContainer、StatusBadge）优先复用，不再造轮子。
- 视觉一致性 > 个性化：lab 是项目的一部分，不应跟主产品割裂。
- 离线优先：mock fallback 不是"开发模式"，是产品演示能力。

---

## 5. 数据/接口契约

### 5.1 HTTP API（FastAPI in [server/app.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/server/app.py)）

| 方法 | 路径 | 用途 | 前端调用方 |
|---|---|---|---|
| GET | `/api/lab/scenarios` | 列出所有场景定义 | （暂未在 UI 中使用） |
| GET | `/api/lab/datasets` | 列出已注册数据集 + 本地就绪状态 | DatasetsTab |
| GET | `/api/lab/suites` | 列出所有 suite 名 | ExperimentsTab |
| GET | `/api/lab/runs` | 列出所有 run | Leaderboard / Regression |
| GET | `/api/lab/runs/{run_id}` | 单个 run 详情（含 manifest、前 N 条样本） | （暂未在 UI 中使用） |
| GET | `/api/lab/compare?baseline=&candidate=` | 两个 run 的 per-scenario delta | RegressionTab |
| POST | `/api/lab/runs` | 触发一次 run（返回拼装好的 cmd） | ExperimentsTab |

### 5.2 关键 TypeScript 接口（见 [lab.ts](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/lab.ts#L81-L142)）

- `LabScenario` / `LabDataset` / `LabRunSummary` / `LabRunDetail` / `LabCompareResult` / `LabTriggerRunPayload`

---

## 6. 已知问题与下一阶段路线图

### 6.1 P0（基础能力补齐）

| 编号 | 需求 | 状态 / 落地 |
|---|---|---|
| P0-1 ✅ | **Run 详情页**：点击 leaderboard 行进入，展示 manifest、样本指标、stderr | 已落地：`/lab/runs/:runId`（`RunDetailPage`）——头部 + 聚合指标表 + 样本结果表 |
| P0-2 ✅ | **失败可追溯**：failed 样本的 stderr/traceback 在 UI 可见 | 已落地：详情页每条失败样本「查看错误」可展开 stderr 面板 |
| P0-3 ✅ | **Lab server 真后端化**：tracked worker（queued→running→succeeded/failed），单 worker 串行 + 日志捕获 | 已落地：[server/jobs.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/server/jobs.py) `JobManager` + `GET /api/lab/jobs[/{id}]` + 前端 `JobStatus` 轮询 |
| P0-4 ✅ | **Markdown 报告下载** | 已落地：`GET /api/lab/runs/{id}/report.md` + 详情页下载按钮 |

### 6.2 P1（产品力提升）

| 编号 | 需求 | 价值 |
|---|---|---|
| P1-1 🟡 | **Leaderboard 过滤**：场景 / 状态 / 搜索（已落地）+ 时间窗口（待补） | 已落地：选场景即按该场景主指标排名，解决「混排不利于单场景决策」 |
| P1-2 | **多 run 横向对比**（>2 个） | 选模型时一次看 4-5 个候选 |
| P1-3 | **数据集一键下载向导**（含 WenetSpeech EULA 引导） | 降低使用门槛 |
| P1-4 | **样本级 hypothesis vs reference diff** | 定位 CER 高来自哪些 sample |
| P1-5 | **指标选择器**：除主指标外，可看次要指标（CER + WER + RTF 同屏） | 全维度评估 |

### 6.3 P2（生态化）

| 编号 | 需求 | 价值 |
|---|---|---|
| P2-1 | **CI 钩子**：PR merge 自动跑 smoke suite，把结果回写到 PR 评论 | 真正闭环 |
| P2-2 | **自定义 suite 的可视化编辑器** | 不再写 TOML |
| P2-3 | **多用户 + 团队历史 run 隔离** | 公司内多团队共用一套部署 |
| P2-4 | **Run 标签 / 笔记**：给每个 run 加 label 与 markdown 备注 | 实验上下文留痕 |

---

## 7. 非功能性需求

| 维度 | 要求 | 当前状态 |
|---|---|---|
| **离线可演示** | 无后端可看完整 UI | ✅ |
| **响应式** | 移动到 >=mobile 都能用 | ✅ 次要列 hidden 处理 |
| **i18n** | zh / en 双语对称 | ✅ |
| **可达性** | 颜色不是唯一信息载体（图标 + 文字） | ✅ ↑/↓ + 文字 |
| **可观测性** | 操作可追溯到具体 run_id | ✅ 行内显示 run_id |

---

## 8. 风险与依赖

| 风险 | 影响 | 缓解 |
|---|---|---|
| WenetSpeech 下载体量大、需 EULA | 新成员上手慢 | mock 兜底已做；待补下载向导 |
| Lab server 当前只拼装命令 | 用户预期"点了就跑"会失望 | P0-3：真起 worker；或在 UI 明示"复制命令到终端运行" |
| 排行榜混排所有场景 | 决策时易误读 | P1-1 加场景过滤 |
| 缓存命中误判 | 改了模型但缓存没失效 | `--no-cache` 已有；前端需暴露开关 |

---

## 9. 附录

### 9.1 当前模块代码地图

| 类别 | 路径 |
|---|---|
| **前端入口** | [LabPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/lab/LabPage.tsx) |
| **前端 API + Mock** | [lab.ts](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/lab.ts) / [labMock.ts](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/api/labMock.ts) |
| **前端 i18n** | [messages.ts#L2110-L2218 (zh)](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/i18n/messages.ts#L2110-L2218) |
| **后端包根** | [translip_lab](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab) |
| **CLI** | [cli.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/cli.py) |
| **HTTP Server** | [server/app.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/server/app.py) |
| **核心 Runner** | [core/runner.py](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/core/runner.py) |
| **场景** | [scenarios](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/scenarios) |
| **数据集** | [datasets](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/datasets) |
| **指标** | [metrics](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/metrics) |
| **报告** | [report](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/report) |
| **Suites 配置** | [suites](file:///Users/yinyijun/OpenSourceProjects/translip/src/translip_lab/suites) |
| **测试** | [tests/lab](file:///Users/yinyijun/OpenSourceProjects/translip/tests/lab) |

### 9.2 启动命令

```bash
# 1) 仅看前端产品形态（mock 数据）
cd frontend
VITE_LAB_USE_MOCK=1 npm run dev
# → 浏览器打开 http://localhost:5173/lab

# 2) 起后端 + 真实数据
translip-lab-server   # 默认 :8799
cd frontend && npm run dev   # 自动连接

# 3) CLI 直跑
translip-lab doctor
translip-lab run --suite asr-drama-wenetspeech --limit 32
translip-lab compare --baseline <run1> --candidate <run2>
```

### 9.3 文档版本约定

- 本文档反映 **2026-06-22** 时刻代码状态。
- 之后每个 P0/P1/P2 项落地后，在第 6 节标注 ✅，并把新增能力补到第 4 节对应小节。

