# 任务 F 技术设计: 流水线与工程封装

- 项目: `translip`
- 文档状态: Draft v2
- 创建日期: 2026-04-14
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/speaker-aware-dubbing-task-breakdown.md)
- 前置依赖:
  - [technical-design.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/technical-design.md)
  - [task-a-speaker-attributed-transcription.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-a-speaker-attributed-transcription.md)
  - [task-b-speaker-registry-and-retrieval.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-b-speaker-registry-and-retrieval.md)
  - [task-c-dubbing-script-generation.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-c-dubbing-script-generation.md)
  - [task-d-single-speaker-voice-cloning.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-d-single-speaker-voice-cloning.md)
  - [task-e-timeline-fitting-and-mixing.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-e-timeline-fitting-and-mixing.md)

## 1. 目标

任务 F 的目标不是新增语音算法能力，而是把已经成立的 `stage 1 + task A-E` 组织成一个真正可重复运行、可恢复、可调试的工程流水线。

它解决的是 6 件事:

1. 如何用一个统一入口稳定编排 `stage 1 -> A -> B -> C -> D -> E`
2. 如何复用阶段产物，避免每次都从头全量重跑
3. 如何在中途失败后恢复，而不是整条链路重来
4. 如何把每个阶段的输入、输出、状态和错误记录成统一 manifest/report
5. 如何让后面的 `Task G` 直接消费 Task F 的标准目录和元数据
6. 如何提供一个简单但统一的全局监控视图，能看到阶段状态、阶段进度和整体进度

任务 F 的首发目标应该是:

- 输入一条原始视频
- 统一调度已有的 Stage 1、Task A、Task B、Task C、Task D、Task E
- 输出一套结构稳定的流水线目录
- 支持缓存命中、阶段重跑、resume、总报告
- 支持简单的全局运行状态与进度监控

## 2. 为什么现在做任务 F

截至 **2026-04-14**，项目已经具备这些事实能力:

- Stage 1 能从本地视频/音频中分离 `voice/background`
- Task A 能生成带 speaker 标签的中文转写
- Task B 能生成文件化 speaker registry 与匹配结果
- Task C 能生成多语种翻译脚本
- Task D 已迁移为单模型 `Qwen3-TTS`
- Task E 已能生成目标语言音频时间线与预混音轨

问题不再是“单个能力是否存在”，而是:

- 入口分散在多个 CLI 和 demo 脚本上
- 阶段复用规则还不统一
- 缺少正式的全链路 manifest
- 缺少标准化的恢复和重跑策略

因此，任务 F 的本质是把“已经能跑的一堆阶段”变成“一个可以长期维护和复用的工程产品”。

## 3. 范围与非目标

### 3.1 任务范围

任务 F 负责:

- 统一的全链路入口
- 阶段顺序与依赖管理
- 阶段输入输出路径解析
- 阶段缓存命中与失效规则
- resume / rerun / from-stage / to-stage 控制
- 全链路 manifest 与 report
- 全局状态与进度监控
- 阶段日志归档
- 对现有 A-E 能力的工程封装

### 3.2 非目标

任务 F 当前不负责:

- 改善 ASR / diarization / translation / TTS / mixing 质量
- 最终视频 `mp4` 封装
- 字幕轨合成
- UI 或 Web 控制台
- 分布式调度
- 多机任务队列
- 复杂监控后端，例如 Prometheus / OpenTelemetry / 时序数据库

最终视频交付属于 **Task G**，不放进任务 F。

## 4. 当前现实约束

这一节必须基于当前代码库现状，而不是假设一个全新的架构。

截至当前仓库状态:

- 现有 demo 脚本 `run_task_a_to_d.py` 和 `run_task_a_to_e.py` 已证明一个关键事实:
  **大模型阶段不应长期共存于同一个 Python 进程**
- 在 `MacBook M4 16GB` 上，`Task D` 的本地模型如果和前面阶段常驻在同一进程，会造成明显吞吐和稳定性问题
- 各阶段当前已经各自有 CLI 和 manifest
- 各阶段当前输出目录已初步稳定

所以任务 F 的首发设计必须基于这个结论:

**全链路编排应采用“阶段级子进程 orchestration”，而不是“单进程函数串联”。**

## 5. 核心结论

任务 F 首发推荐做成一个 **Pipeline Orchestrator**，而不是一堆更长的 shell 脚本。

推荐架构:

`pipeline request -> stage planner -> stage subprocess runner -> cache resolver -> pipeline manifest -> pipeline report`

这意味着:

- 每个阶段继续保持自己现有的 CLI 和产物结构
- 任务 F 不直接重写各阶段内部逻辑
- 任务 F 只负责“什么时候跑、跑哪一步、是否复用、失败后怎么恢复”

这条路线的好处是:

- 对现有代码入侵最小
- 与当前已验证的阶段代码天然兼容
- 更适合本地模型占用大的开发环境
- 后续扩展 `Task G` 时边界清晰

## 6. 方案选型

任务 F 有 3 条可选路线。

### 6.1 方案 A: 继续扩展 demo 脚本

做法:

- 继续在 `scripts/run_task_a_to_e.py` 这一类脚本上叠参数和逻辑

优点:

- 起步快
- 代码改动少

问题:

- 很快会把 demo 脚本变成事实上的产品入口
- 缓存、状态机、恢复逻辑会越来越散
- 长期维护性差

### 6.2 方案 B: 单进程 Python orchestrator

做法:

- 在一个 Python 进程里直接调用各阶段函数

优点:

- 数据传递直接
- 日志整合方便

问题:

- 与当前本地模型内存行为冲突
- 真实验证已经证明这条路线在本机上不稳

### 6.3 方案 C: 子进程编排器

做法:

- 由 Task F 的统一入口负责解析参数、规划阶段
- 每个阶段通过独立 CLI 子进程运行
- 以产物和 manifest 作为阶段边界

优点:

- 与现有架构最兼容
- 最符合本地模型环境现实
- 易做缓存和恢复
- 各阶段失败边界清晰

问题:

- 需要更明确的路径协议
- 需要额外的阶段状态管理

### 6.4 选型结论

任务 F 首发采用 **方案 C: 子进程编排器**。

## 7. 首发交付物

任务 F 首发建议输出 6 类产物:

1. `pipeline-manifest.json`
   全链路执行摘要与阶段状态
2. `pipeline-report.json`
   面向人工阅读的统计报告
3. `logs/`
   每个阶段独立日志
4. 标准化阶段目录
   `stage1/`, `task-a/`, `task-b/`, `task-c/`, `task-d/`, `task-e/`
5. `request.json`
   本次流水线归一化后的请求参数快照
6. `cache-index.json`
   可选，记录阶段 cache key 与命中情况
7. `pipeline-status.json`
   全局运行状态与进度快照

## 8. 标准目录设计

任务 F 首发建议输出根目录结构如下:

```text
<output-root>/
  source/
    input.json
  stage1/
    <bundle>/
      voice.mp3
      background.mp3
      manifest.json
  task-a/
    voice/
      segments.zh.json
      segments.zh.srt
      task-a-manifest.json
  task-b/
    voice/
      speaker_profiles.json
      speaker_matches.json
      speaker_registry.json
      task-b-manifest.json
  task-c/
    voice/
      translation.en.json
      translation.en.editable.json
      translation.en.srt
      task-c-manifest.json
  task-d/
    voice/
      spk_0001/
      spk_0003/
      ...
  task-e/
    voice/
      dub_voice.en.wav
      preview_mix.en.wav
      timeline.en.json
      mix_report.en.json
      task-e-manifest.json
  logs/
    stage1.log
    task-a.log
    task-b.log
    task-c.log
    task-d.log
    task-e.log
  pipeline-manifest.json
  pipeline-report.json
  pipeline-status.json
  request.json
```

设计原则:

- 阶段目录与当前已有产物命名尽量保持一致
- 不在任务 F 首发里重新发明新的文件命名体系
- `pipeline-manifest.json` 位于根目录，作为统一入口索引
- `pipeline-status.json` 位于根目录，作为运行中可轮询的监控快照

## 9. 阶段模型

任务 F 首发只调度以下阶段:

1. `stage1`
2. `task-a`
3. `task-b`
4. `task-c`
5. `task-d`
6. `task-e`

每个阶段都应具备统一元数据:

- `stage_name`
- `status`
- `started_at`
- `finished_at`
- `elapsed_sec`
- `cache_key`
- `cache_hit`
- `input_paths`
- `artifact_paths`
- `manifest_path`
- `log_path`
- `progress_percent`
- `updated_at`
- `current_step`
- `error`

建议状态集:

- `pending`
- `running`
- `succeeded`
- `cached`
- `failed`
- `skipped`

阶段级进度在任务 F 首发里不追求极高精度，但必须保证:

- 有进度值
- 有最近更新时间
- 能区分“正在运行”和“疑似卡住”

## 10. 流水线节点图

任务 F 首发的节点图建议固定为:

```text
source input
  -> stage1
  -> task-a
  -> task-b
  -> task-c
  -> task-d
  -> task-e
```

依赖关系建议明确写死:

- `stage1` 依赖原始输入视频或音频
- `task-a` 依赖 `stage1/voice`
- `task-b` 依赖 `task-a/segments + stage1/voice`
- `task-c` 依赖 `task-a/segments + task-b/profiles`
- `task-d` 依赖 `task-c/translation + task-b/profiles`
- `task-e` 依赖 `stage1/background + task-a/segments + task-c/translation + task-d/reports`

这张图在任务 F 首发里不做动态 DAG，自定义节点顺序不是目标。

原因是:

- 当前链路已经稳定成线性依赖
- 先把缓存和恢复做稳，比一开始支持任意图更重要

## 10.1 全局监控目标

任务 F 首发的“全局监控”建议只做到 3 件事:

1. 能看到每个阶段当前状态
2. 能看到每个阶段的简单进度
3. 能看到全链路整体进度

首发不做:

- Web 仪表盘
- 图形化时间轴
- 远程推送
- 告警系统

简单版就足够:

- CLI 实时输出
- `pipeline-status.json` 持续更新
- 必要时一个只读状态命令

## 11. 配置面设计原则

任务 F 需要在这一阶段把“什么参数可配、什么参数不公开”定下来。

首发建议采用 3 层配置模型:

### 11.1 Pipeline 级公开配置

这类参数控制全链路行为，必须在任务 F 首发就定下来。

例如:

- 输入输出路径
- 运行到哪个阶段
- 是否 resume
- 是否复用缓存
- 哪个翻译 backend
- 哪个 TTS backend
- 目标语言

### 11.2 Stage 级公开配置

这类参数是各阶段确实有业务意义、而且用户/开发者需要调整的参数。

例如:

- `fit_policy`
- `fit_backend`
- `mix_profile`
- `ducking_mode`

这部分应该适量暴露，但不宜过多。

### 11.3 Stage 内部调参

这类参数先不作为任务 F 公开配置项。

例如:

- `Task D` 的 `max_new_tokens`
- `Task E` 的 overlap tolerance
- 质量分数权重
- 各种内部阈值

这类参数继续放在阶段内部管理，后面确认确有必要再公开。

## 12. 输入请求设计

任务 F 首发建议定义统一请求 `pipeline request`。

示意结构:

```json
{
  "input_path": "./test_video/example.mp4",
  "output_root": "./output-pipeline",
  "target_lang": "en",
  "translation_backend": "local-m2m100",
  "tts_backend": "qwen3tts",
  "device": "auto",
  "run_from_stage": "stage1",
  "run_to_stage": "task-e",
  "resume": true,
  "force_stages": [],
  "reuse_existing": true
}
```

其中最关键的控制参数是:

- `run_from_stage`
- `run_to_stage`
- `resume`
- `force_stages`
- `reuse_existing`

## 13. 公开配置清单

任务 F 首发建议把公开配置分成 4 类。

### 13.1 输入与路径配置

- `input_path`
- `output_root`
- `registry_path`
- `glossary_path`

说明:

- `input_path` 和 `output_root` 是必配项
- `registry_path`、`glossary_path` 是可选项

### 13.2 流水线控制配置

- `run_from_stage`
- `run_to_stage`
- `resume`
- `force_stages`
- `reuse_existing`
- `keep_logs`
- `write_status`
- `status_update_interval_sec`

说明:

- 这是任务 F 最核心的一组配置
- 它们决定的是“怎么跑”，不是“算法怎么做”
- `write_status` 决定是否持续写出全局状态文件
- `status_update_interval_sec` 控制状态刷新频率

### 13.3 能力选择配置

- `target_lang`
- `device`
- `translation_backend`
- `tts_backend`

说明:

- 这组配置会直接参与缓存指纹
- 任何变化都应导致相关阶段失效

### 13.4 阶段级公开行为配置

- `fit_policy`
- `fit_backend`
- `mix_profile`
- `ducking_mode`
- `preview_format`

说明:

- 这组配置主要影响任务 E
- 它们既影响产物，也应影响缓存命中判断

## 14. 配置优先级

任务 F 首发建议明确配置优先级:

`CLI 参数 > pipeline 配置文件 > 代码默认值`

解释:

- 用户在 CLI 上显式传入的值拥有最高优先级
- 若提供 pipeline 配置文件，则用它补全未显式传入的参数
- 其余字段回落到稳定默认值

这样做的好处是:

- 日常使用时，简单命令即可运行
- 复杂场景可以用配置文件保存参数集合
- 临时调试又能直接在 CLI 上覆盖

## 15. 配置文件设计

任务 F 首发建议支持一个可选配置文件，例如:

```bash
uv run translip run-pipeline \
  --config ./pipeline.example.json \
  --input ./test_video/example.mp4
```

建议首发使用 `json` 或 `yaml` 二选一。

如果追求最小实现成本，推荐先用 `json`。

示意结构:

```json
{
  "target_lang": "en",
  "translation_backend": "local-m2m100",
  "tts_backend": "qwen3tts",
  "device": "auto",
  "fit_policy": "high_quality",
  "fit_backend": "atempo",
  "mix_profile": "preview",
  "ducking_mode": "static",
  "write_status": true,
  "status_update_interval_sec": 2,
  "resume": true,
  "reuse_existing": true
}
```

任务 F 首发不建议同时引入复杂 profile 继承机制。

## 16. 公开参数与内部参数边界

任务 F 需要明确“哪些参数是稳定接口，哪些不是”。

### 16.1 建议公开的参数

以下参数建议视为稳定公开接口:

- 输入输出路径
- 阶段起止控制
- 缓存/恢复控制
- backend 选择
- `target_lang`
- `device`
- `fit_policy`
- `fit_backend`
- `mix_profile`
- `ducking_mode`
- `preview_format`
- `write_status`
- `status_update_interval_sec`

### 16.2 不建议在首发公开的参数

以下参数建议继续保留在内部:

- `Task A` 聚类和切句内部阈值
- `Task B` 匹配分数阈值
- `Task C` 翻译批大小之外的内部 prompt 细节
- `Task D` 的 `max_new_tokens`
- `Task D` 质量门控权重
- `Task E` overlap tolerance
- `Task E` 各种波形细调参数

### 16.3 Debug-only 参数

有一类参数可以保留给调试，但不建议进入公开产品接口。

例如:

- `--dump-stage-env`
- `--print-subprocess-command`
- `--keep-workdirs`

这类参数如果实现，建议明确标记为 debug-only。

## 17. CLI 设计

任务 F 首发建议新增一个正式 CLI，例如:

```bash
uv run translip run-pipeline \
  --input ./test_video/example.mp4 \
  --output-root ./output-pipeline \
  --target-lang en \
  --translation-backend local-m2m100 \
  --tts-backend qwen3tts \
  --run-to-stage task-e \
  --resume
```

建议支持这些参数:

- `--config`
- `--input`
- `--output-root`
- `--target-lang`
- `--translation-backend`
- `--tts-backend`
- `--device`
- `--run-from-stage`
- `--run-to-stage`
- `--resume`
- `--force-stage`，可重复传入
- `--reuse-existing / --no-reuse-existing`
- `--keep-logs`
- `--write-status / --no-write-status`
- `--status-update-interval-sec`

后续 `Task G` 再新增单独的最终交付命令，不混进这个入口。

## 17.1 监控相关 CLI 建议

任务 F 首发建议至少提供两种监控方式:

### 方式 A: 运行时实时输出

`run-pipeline` 在 stdout 中输出:

- 当前阶段
- 当前阶段状态
- 当前阶段进度
- 整体进度

示意:

```text
[pipeline] status=running overall=42%
[stage:task-d] status=running progress=31% message="speaker spk_0003 12/39"
```

### 方式 B: 只读状态命令

建议后续增加一个简单命令，例如:

```bash
uv run translip pipeline-status \
  --output-root ./output-pipeline
```

该命令只读取 `pipeline-status.json`，不触发任何执行。

首发如果想控制范围，也可以先不做独立命令，只先保证状态文件存在。

## 18. 缓存策略

任务 F 的缓存不建议首发就做成复杂数据库，而建议基于“阶段目录 + manifest + 请求指纹”。

### 18.1 缓存命中原则

一个阶段满足以下条件时，可视为 cache hit:

1. 该阶段 manifest 存在
2. manifest 状态为 `succeeded`
3. 关键产物存在
4. 当前请求的关键参数指纹与上次一致

### 18.2 缓存失效触发条件

以下任一变化应导致该阶段及其下游失效:

- 输入文件路径变化
- 上游关键产物变化
- 关键模型或 backend 变化
- 关键阶段参数变化
- 用户显式 `--force-stage`

### 18.3 首发策略

首发不做跨目录全局缓存池，只做当前 `output-root` 内的局部复用。

这是为了:

- 降低复杂度
- 避免缓存污染
- 保持行为可解释

## 19. 缓存指纹建议

任务 F 首发建议把缓存指纹拆成“全局请求指纹 + 阶段局部指纹”。

### 19.1 全局请求指纹

参与字段建议包括:

- `input_path`
- `target_lang`
- `translation_backend`
- `tts_backend`
- `device`

### 19.2 阶段局部指纹

每个阶段再加自己的关键字段:

- `stage1`: `mode`, `quality`, `audio_stream_index`
- `task-a`: `language`, `asr_model`
- `task-b`: `registry_path`, `top_k`, `update_registry`
- `task-c`: `glossary_path`, `translation_backend`
- `task-d`: `tts_backend`, speaker selection strategy
- `task-e`: `fit_policy`, `fit_backend`, `mix_profile`, `ducking_mode`, `preview_format`

这部分建议在实现时封装成单独模块，不散落在各阶段 runner 中。

## 19.3 进度计算建议

任务 F 首发建议采用“加权阶段进度”来计算整体进度，而不是追求精确时间预测。

建议权重可先写死为:

- `stage1 = 0.10`
- `task-a = 0.10`
- `task-b = 0.10`
- `task-c = 0.15`
- `task-d = 0.35`
- `task-e = 0.20`

原因:

- 这更贴近当前本地运行真实耗时结构
- `task-d` 明显比其他阶段重
- 简单权重法已经足够支持首发监控

整体进度计算:

- 已完成阶段按 100% 记
- 当前运行阶段按阶段内部 `progress_percent` 记
- 未开始阶段按 0% 记

## 19.4 阶段内部进度建议

任务 F 首发对各阶段的进度精度要求可以不同。

建议:

- `stage1`: 按固定阶段状态，直接用 `0 / 100`
- `task-a`: 按主流程阶段点，粗粒度 `0 / 50 / 100`
- `task-b`: 按流程阶段点，粗粒度 `0 / 50 / 100`
- `task-c`: 按 unit 批次进度估算
- `task-d`: 按 `speaker_count` 与 `segment_count` 组合进度估算
- `task-e`: 按 `candidate -> fit -> overlap -> render -> export` 五段估算

其中 `task-d` 是最值得细化的，因为它通常耗时最长。

## 19.5 状态文件设计

任务 F 首发建议持续写出 `pipeline-status.json`。

建议结构:

```json
{
  "job_id": "pipeline-20260414-120000",
  "status": "running",
  "overall_progress_percent": 42.3,
  "current_stage": "task-d",
  "updated_at": "2026-04-14T12:34:56Z",
  "stages": [
    {
      "stage_name": "task-c",
      "status": "succeeded",
      "progress_percent": 100.0,
      "current_step": "completed",
      "updated_at": "..."
    },
    {
      "stage_name": "task-d",
      "status": "running",
      "progress_percent": 31.4,
      "current_step": "speaker spk_0003 12/39",
      "updated_at": "..."
    }
  ]
}
```

设计要求:

- 运行中持续覆盖写入
- 文件结构稳定，便于 CLI 或外部脚本读取
- 即使异常退出，也尽量保留最后一次状态快照

## 20. Resume 与重跑策略

任务 F 首发建议支持 3 类控制方式。

### 20.1 Resume

场景:

- 上次跑到某一阶段失败
- 重新执行时希望直接从失败阶段恢复

行为:

- 找到最近一次成功的上游阶段
- 跳过命中的阶段
- 从第一个未完成或被强制重跑的阶段继续

### 20.2 Force stage

场景:

- 用户明确知道某个阶段需要重跑

行为:

- 该阶段及其下游阶段一律重跑
- 上游已命中的阶段继续复用

### 20.3 Run from / run to

场景:

- 单独调试某几段

行为:

- `run_from_stage` 之前的阶段只做依赖检查和必要复用
- `run_to_stage` 之后的阶段不执行

## 21. 子进程编排设计

任务 F 首发建议统一通过 CLI 子进程运行每个阶段。

例如:

- `translip run`
- `translip transcribe`
- `translip build-speaker-registry`
- `translip translate-script`
- `translip synthesize-speaker`
- `translip render-dub`

核心原则:

- 阶段之间通过文件路径和 manifest 交接
- 编排器不跨阶段持有大模型对象
- 每个子进程都有独立日志文件
- 子进程失败时要捕获退出码、stderr 摘要和阶段上下文
- 子进程运行期间要能向编排器回传简单进度信息

## 21.1 进度采集策略

任务 F 首发建议采用“弱侵入式进度采集”。

优先级建议如下:

1. **直接已知的阶段级进度**
   例如 orchestrator 自己知道某阶段开始/结束
2. **可从子进程结构推导的进度**
   例如 task-d 已知 speaker 数和 segment 数
3. **子进程标准输出中的结构化进度行**
   例如:
   `PROGRESS task-d 31.4 speaker spk_0003 12/39`

首发不建议:

- 解析任意自然语言日志
- 依赖复杂 IPC 或 socket 通信

如果阶段暂时不支持结构化进度输出，也允许先用编排器侧的粗粒度估算。

## 22. Manifest 设计

任务 F 首发建议把 `pipeline-manifest.json` 作为最重要的工程产物。

建议结构:

```json
{
  "job_id": "pipeline-20260414-120000",
  "request": {},
  "stages": [
    {
      "stage_name": "stage1",
      "status": "cached",
      "cache_hit": true,
      "manifest_path": "...",
      "artifact_paths": {},
      "started_at": "...",
      "finished_at": "...",
      "elapsed_sec": 0.31,
      "error": null
    }
  ],
  "final_artifacts": {
    "voice_path": "...",
    "background_path": "...",
    "translation_path": "...",
    "dub_voice_path": "...",
    "preview_mix_path": "..."
  },
  "status": "succeeded"
}
```

设计要求:

- 人类可读
- 程序也容易读取
- 能明确定位失败阶段
- 能被 `Task G` 直接消费

注意:

- `pipeline-manifest.json` 是执行结束后的正式记录
- `pipeline-status.json` 是运行中的动态快照
- 两者不要混成同一个文件

## 23. Report 设计

`pipeline-report.json` 建议是面向调试与人工查看的统计汇总。

至少包含:

- 执行了哪些阶段
- 哪些阶段命中缓存
- 各阶段耗时
- 最终产物路径
- 本次失败或跳过原因摘要
- Task D / Task E 的关键统计透传
- 各阶段进度与耗时摘要

这份报告不替代各阶段 manifest，而是做跨阶段总览。

## 24. 错误处理

任务 F 首发必须把错误边界做清楚。

### 24.1 阶段失败

如果某个阶段子进程返回非零:

- 当前阶段状态写为 `failed`
- 记录退出码和 stderr 摘要
- 停止执行后续阶段
- 仍然写出 `pipeline-manifest.json`

### 24.2 产物缺失

如果子进程返回成功，但关键产物缺失:

- 视为阶段失败
- 错误类型标记为 `missing_artifact`

### 24.3 缓存不一致

如果 manifest 说成功，但关键产物不存在:

- 视为缓存失效
- 忽略该阶段缓存并重跑

### 24.4 监控心跳中断

如果某阶段长时间没有更新 `updated_at`:

- 不直接判定为失败
- 先标记为 `stale`
- 由 orchestrator 在 report 中记录“可能卡住”

首发可以只做记录，不做自动中断。

## 25. 模块拆分建议

任务 F 首发建议新增这些模块:

### 25.1 `pipeline/request.py`

职责:

- 定义全链路请求对象
- 归一化参数

### 25.2 `pipeline/stages.py`

职责:

- 定义阶段枚举
- 定义阶段依赖顺序
- 解析 `run_from_stage / run_to_stage`

### 25.3 `pipeline/cache.py`

职责:

- 计算 cache key
- 判断 cache hit / stale / force rerun

### 25.4 `pipeline/subprocess_runner.py`

职责:

- 运行 CLI 子进程
- 收集 stdout / stderr
- 写阶段日志
- 收集结构化进度事件

### 25.5 `pipeline/manifest.py`

职责:

- 生成 `pipeline-manifest.json`
- 生成 `pipeline-report.json`
- 生成 `pipeline-status.json`

### 25.6 `pipeline/monitor.py`

职责:

- 维护运行中状态
- 计算整体进度
- 更新 `pipeline-status.json`

### 25.7 `pipeline/runner.py`

职责:

- 主编排逻辑
- 串联所有阶段
- 写最终状态

## 26. 测试策略

任务 F 首发测试建议分 3 层。

### 26.1 单元测试

- 阶段顺序解析测试
- `run_from_stage / run_to_stage` 测试
- cache key 稳定性测试
- force-stage 失效规则测试
- manifest schema 测试

### 26.2 集成测试

- 用一个短样本跑通 `stage1 -> task-e`
- 中途故意删除某个阶段产物，再验证 resume 行为
- 在已有产物基础上只重跑 `task-e`

### 26.3 真实验证

- 使用 `test_video` 中的真实视频
- 至少做 1 次完整 `stage1 -> task-e`
- 至少做 1 次“命中缓存的重跑”
- 至少做 1 次“强制重跑某个阶段”

## 27. 验收标准

任务 F 可以视为完成，需要同时满足:

1. 能通过一个统一 CLI 跑通 `stage1 -> task-e`
2. 能稳定生成 `pipeline-manifest.json` 和 `pipeline-report.json`
3. 同一输入第二次运行时，上游阶段能正确命中缓存
4. 支持从中间阶段恢复
5. 失败时能明确定位到具体阶段和原因

## 28. 实现顺序建议

任务 F 推荐按这个顺序落地:

1. 先定义阶段枚举、请求结构和目录协议
2. 再实现子进程编排器
3. 接着实现统一 manifest/report
4. 然后实现缓存命中和失效规则
5. 最后补 resume、force-stage、真实集成测试

## 29. 与任务 G 的边界

任务 F 到此为止只输出:

- 标准化流水线目录
- 目标语言音频产物
- 全链路 manifest/report

任务 G 才负责:

- 把 `preview_mix` 或 `dub_voice` mux 回原视频
- 导出最终交付视频
- 组织最终交付目录

这条边界必须保持清楚，否则任务 F 会同时承担“工程编排”和“视频交付”两类职责，复杂度会明显失控。
