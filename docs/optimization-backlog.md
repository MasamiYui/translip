# translip 优化 Backlog（可转工单）

> 面向 `translip` Beta 阶段的**产品 + 算法**优化盘点，按 **架构 / 流水线节点 / 字幕子系统 / 原子功能 / UI** 组织。
> 每条都是一张可独立处理的工单：带 **ID、现状(file:line)、方案、验收标准、测试方式**。
> 与 `docs/project-optimization-analysis.md`（旧版高层产品分析，不含代码方案）互补——本文是**可落地、带代码定位**的执行版。
>
> 生成于 2026-06。基线：R0–R6 配音优化、评测闭环、backend registry 重构均已完成（见下"已完成基线"），本文只列**未着手**的余地。

## 图例与流程约定

- **状态**：`TODO` 待办 / `DOING` 处理中 / `DONE` 已完成（提交后回填 commit 短 hash）/ `HOLD` 暂缓 / `WONTFIX`。
- **核实**：`✅已核实` = 本次盘点已用实际代码确认；`◻待确认` = agent 报告并给了 file:line，但未逐字复核，动工前先打开确认。
- **工作量**：S < 1 天 / M 2–5 天 / L > 1 周。
- **主线**：A 诊断成熟·预防缺位 / B 默认配置最弱 / C 结构性贪心 / D 潜在 bug·死代码 / E 健壮性·安全后补。
- **每张工单的处理流程（约定）**：
  1. 动工前打开引用文件复核现状（尤其 `◻待确认` 项）。
  2. 实现改动，**匹配周边代码风格**（无 ruff/black，手动对齐）。
  3. **加/改测试**：后端 `uv run pytest`（相关文件 + 全量回归），前端 `npm run test` / `npm run lint` / `npm run build`，必要时 e2e（需先 `./scripts/dev.sh start`）。
  4. 在真实产物上验证（配音类用 `output-pipeline/...` 现有跑批做 A/B；详见各工单"测试方式"）。
  5. 验证通过 → `git commit`（Conventional Commits；建议先开分支，不要直接 push）。

---

## 已完成基线（勿重复提案）

- **配音质量 R0–R6**：gap-aware 溢出拟合、配音前去首尾静音（砍 ~55% 溢出/60% 切尾）、OCR 字幕权威化纠正 ASR、`max_compress_ratio` 调优、VoxCPM `cfg_value=2.5`（男声更稳）、fail-soft 单段失败 + abort 闸、VoxCPM 离线加载。
- **R4 负结果**：pitch-centrality 参考重排对**混性别簇有害**，已回退为 opt-in——**不要再提"把参考往簇中位 pitch 拉"**。治"男变女"的正解是上游**性别感知拆簇 + 同性别参考**（见 `SPK-1`）。
- **评测闭环**：`quality/dub_qa.py` → `remediation.py` → `server/routes/autofix.py`（plan→repair→render→evaluate，有界多轮 accept-if-better）；`qa_summary.timeline` 已暴露 overflow/severe/unfitted/`cut_audio_sec`。**刻意未改 `_score` 公式**以保历史可比（见 `QA-1`）。
- **架构重构（2026-05-31）**：统一 `BackendRegistry`（加 backend = 注册 lazy factory，非 if/elif）、`utils/io.py`、`utils/torch_device.py`、`types/` 包化、dubbing_editor 路由拆分。
- ⚠️ `orchestration/commands.py` 是用户高频手编文件——**改动需谨慎、勿大重构**。

---

## 优先级路线图

### 第 0 波 — 即得 / 已核实 bug / 低风险（先做）
| ID | 标题 | 工作量 |
|---|---|---|
| ARCH-12 | 统一 24k/48k 等默认值的单一来源 ✅ | S |
| ARCH-8 | Stop 真正传递到子进程（取消接线）✅ | S–M |
| ARCH-9 | 启动时回收悬空流水线任务 | S |
| SEC-1 | 路径穿越改 `is_relative_to` ✅ | S |
| SEC-2 | 鉴权 + 127.0.0.1 绑定 + 收窄 CORS | S–M |
| REN-4 | 最终混音无条件 R128 + 接线死代码 `loudnorm_file` ✅ | S |
| REN-7 | 确认/修复 dub 导出缺背景乐床 ✅ | S |
| TTS-2 | 修复死键 `estimated_target_sec` ✅ | S |
| ARCH-4 | 缓存键补上游产物指纹 | S |
| ARCH-5 | 缓存键混入 `cache_epoch`/code 版本 | S |

### 第 1 波 — 感知质量根本（主线 A，ROI 最高）
| ID | 标题 | 工作量 |
|---|---|---|
| TRA-1 | 时长预算注入翻译 + 默认重译/condense ✅ | S–M |
| TTS-1 | 长度/语速目标传 MOSS/VoxCPM + render 前 micro-fit | S–M |
| REP-1 | repair 改写换成 LLM 长度目标重译（删硬编码字典） | M |
| UI-1 | 修 Preview 音频 A/B（只切字幕的 bug）✅ | M |
| UI-5 | 阶段日志在 UI 可见 | M |
| UI-4 | 长任务完成通知 + 全局 toast | M |

### 第 2 波 — 已知硬骨头（主线 B/C）
| ID | 标题 | 工作量 |
|---|---|---|
| ASR-1 | diarization 用非降质音源 | M |
| ASR-2 | ECAPA 多窗 mean-pool + 情绪不变特征 | M |
| ASR-3 | 聚类阈值/`expected_speakers` 可调且入缓存 | M |
| ASR-5 | 词级时间戳 + Paraformer 默认（治 SenseVoice 伪造时间）✅ | M |
| ASR-6 | ASR 幻觉/置信度处理 | S–M |
| SPK-1 | speaker-registry 存 gender/F0 → 同性别参考 + 双峰拆簇 | M–L |
| REN-1 | render 两遍/全局时间轴拟合 | M–L |
| REN-3 | 切尾级联 + 上游"需更短译文"反馈 | M |
| QA-1 | `perceptual_score`（切尾惩罚 + 最终混音 ASR 往返） | M |
| QA-2 | autofix 升级阶梯（换参考/换 backend） | M |

### 第 3 波 — 结构 / 新功能
| ID | 标题 | 工作量 |
|---|---|---|
| ARCH-1 | DAG 并行调度（独立分支并发） | M |
| ARCH-2 | synthesis 多说话人批处理/并行 | M |
| ARCH-3 | 流水线并发队列 + admission control | M |
| SUB-1 | 翻译字幕 CPS/折行/可读性引擎 | M |
| SUB-2 | OCR cue 时间吸附真实帧 | M |
| SUB-4 | erase 逐帧掩码 | M–L |
| SUB-5 | erase 前 cue 审核闸（UI） | M |
| DEL-1 | 软字幕 + 多音轨 + CRF/语言元数据 | M |
| UI-2 | 移动端导航 | M |
| UI-3 | i18n 补全核心页 | M |
| ATOM-1 | adapter 自动发现 | S |
| ATOM-2 | 原子工具真队列 + 重启 re-enqueue | M |

> 其余工单（ARCH-6/7/10/11/13/14/15/16, SEP-*, SPK-2/3, TRA-2/3/4/5, REN-2/5/6, DEL-2, REP-2/3, ASR-4/7/8/9, SUB-3/6/7, ATOM-3/4, UI-6/7/8/9/10, SEC-3）见下方明细，按需穿插。

---

# 工单明细

## 架构（ARCH / SEC）

### ARCH-1 — DAG 并行调度，独立分支并发 ｜ TODO ｜ 主线 — ｜ M ｜ ◻待确认
- **现状**：`orchestration/runner.py:810` 是拓扑拍平后的裸 `for`，完全串行；`graph.py` 有真依赖图但 `plan.dependencies` 不参与调度。`+ocr-subs` 模板里 OCR 检测（数分钟）排在音频主线后串行，明明独立。
- **方案**：用 `plan.dependencies` 做 ready-set 调度器，依赖满足的节点并发启动，受 VRAM/device 信号量约束（勿同时调度两个 GPU 阶段）。每个节点已是独立子进程，主要是调度改动。
- **验收**：`asr-dub+ocr-subs` 模板 OCR 与 separation→transcription 并发；端到端产物与串行一致；墙钟下降。
- **测试**：`tests/test_orchestration.py` 加并发调度单测（mock 子进程）；真实 `+ocr-subs` 跑批对比墙钟。

### ARCH-2 — synthesis 多说话人批处理/并行 ｜ TODO ｜ C/性能 ｜ M ｜ ◻待确认
- **现状**：`runner.py:460` 逐说话人一个 `synthesize-speaker` 子进程＝N 人 N 次模型冷加载；`dubbing_workers` 只并行单说话人内的段。synthesis 权重 0.35（`stages.py:23`）最长。
- **方案**：优先做"多说话人批模式"（一进程跑全部选定说话人，摊销模型加载）；或退而求其次用 VRAM 限制的进程池跑若干说话人。注意保持子进程隔离带来的 ML 模型清理/崩溃隔离优势的权衡。
- **验收**：多说话人任务 synthesis 墙钟显著下降，产物逐段一致。
- **测试**：`tests/` 加批模式单测；真实多说话人跑批计时。

### ARCH-3 — 流水线并发队列 + admission control ｜ TODO ｜ 健壮性 ｜ M ｜ ◻待确认
- **现状**：`task_manager.create_task` 无并发上限地起守护线程；atomic-tools 却有 `max_concurrent_jobs=2`（`job_manager.py:114`），两套策略相反。多任务同提会争抢单 GPU。
- **方案**：共享 bounded executor/队列（参照 atomic-tools 的 `_active_job_count` 闸），并发默认 1（单 GPU）；新增"queued"任务状态。
- **验收**：连提多任务时按并发上限排队执行，不 OOM。
- **测试**：单测队列闸；手动连提验证。

### ARCH-4 — 缓存键补上游产物指纹 ｜ DONE ｜ D/正确性 ｜ S ｜ ◻待确认
> 已修：transcription 缓存 payload 加 `voice` = `_file_fingerprint(stage1_voice_path)`；synthesis 加 `translation`/`profiles`/`voice_bank` 三个上游指纹。原先这两段只含标量参数，上游产物变了但参数 hash 不变会 false hit。缓存键在节点循环里、上游已完成后计算，故指纹有效。加 2 回归测试（改 separation voice → transcription 键变；改 translation/speaker-registry → synthesis 键变）。后端 511 passed。
> 🔎 **ARCH-4c 审计补漏**（2026-06）：程序化比对每个 stage 的 `build_X_command` 用的 `request.*` 参数 vs 其缓存 payload 参数，抓到 **translation 命令用 `--batch-size` 但缓存 payload 缺 `translation_batch_size`**——改 batch size 不重算 translation（batch 影响 LLM prompt 分组→可变译文）。已补入 translation payload。其余 stage（含 synthesis）审计无缺失。加回归测试（batch 4↔8 → translation 键变）。全量 655 passed。
- **现状**：`_stage_cache_payload`（`runner.py:120`）对 speaker-registry/c/e、subtitle-erase 有上游指纹，但 **transcription 键不含 separation `voice.*` 指纹**，synthesis 键不含 translation/speaker-registry 指纹（只有标量）。上游文件变了但参数 hash 不变 → false hit on stale。
- **方案**：用已存在的 `_file_fingerprint` 给 transcription（←separation voice）、synthesis（←translation+profiles+voice_bank）补指纹。
- **验收**：替换上游产物后对应阶段必重算。
- **测试**：`tests/` 缓存命中/失效单测覆盖新指纹。

### ARCH-5 — 缓存键混入 code/model 版本 ｜ DONE ｜ D/正确性 ｜ S ｜ ◻待确认
> 已修：`cache.py` 加 `CACHE_EPOCH=1` 常量并在 `compute_cache_key` 内把 payload 包成 `{"cache_epoch": CACHE_EPOCH, "payload": ...}` 再哈希——所有缓存键都含版本，行为变更（换模型 checkpoint / 修阶段 bug / 改默认）时 bump 即强制全量重算。加测试（bump epoch → 键变）。后端 512 passed。可选的 per-stage code_version / 模型权重 sha 暂未做（更细粒度，按需再加）。
- **现状**：`compute_cache_key`（`cache.py:19`）只 hash 参数；换模型 checkpoint 或修阶段 bug 后旧 manifest 仍命中。
- **方案**：每个 payload 混入粗粒度 `cache_epoch` 常量（行为变更时手动 bump），可选含所选 backend 的模型权重 mtime/sha。
- **验收**：bump epoch 后强制全量重算。
- **测试**：单测 epoch 改变导致 miss。

### ARCH-6 — 阶段内续跑（per-speaker 缓存）｜ DONE ｜ 健壮性/性能 ｜ M ｜ ✅已核实
> 已修：synthesis 循环对每个说话人先查 `speaker_segments.<lang>.json`——若已有**可渲染**(≥1 dict segment)report 则复用、跳过重合成（`_task_d_speaker_already_rendered` helper）。**安全闸**：仅当 `resume_ok` 为真才跳过——`resume_ok = cache_spec.cache_key == previous_cache_key`（即同参数的崩溃续跑；tts/翻译/profiles 等参数一变 cache key 变→`resume_ok=False`→全员重合成，绝不复用 stale 报告）。signal 经 `run_pipeline → execute_node → execute_stage` 三级透传（均加 `resume_ok` 参数，默认 False）。加 `_task_d_speaker_already_rendered` 单测（4 case 决策矩阵：resume 关→不跳、缺报告→不跳、空报告→不跳、可渲染+resume→跳）。全量 627 passed。
- **现状（原）**：缓存粒度是整节点；synthesis 跑到 5/6 崩了全部重来。
- **方案**：synthesis 按说话人缓存（`speaker_segments.<lang>.json` 已是离散产物，`commands.py:128`），跳过已有非空 report 的说话人。与 ARCH-2 配套。
- **验收**：崩溃重跑只补未完成说话人。
- **测试**：单测 per-speaker 跳过逻辑。

### ARCH-7 — 输出 GC / 容量管理 ｜ DONE（GC+API；UI 按钮留子项）｜ 产品 ｜ M ｜ ✅已核实
> 已修：`cache_manager` 加 `select_evictable_pipeline_outputs(infos, max_bytes, max_count)` **纯选择函数**（按 LRU=mtime 最旧优先驱逐**未被 DB 引用**的目录直到低于上限；引用中的目录永不驱逐）+ `gc_pipeline_outputs(max_bytes,max_count,dry_run,cache_root,db_engine)` runner（扫 output-pipeline 子目录、从 DB `Task.output_root` 取引用集、算 dir_size/mtime、选择、删除、返回报告）。两上限默认 None ＝ 无操作（可无条件调用）。加 `POST /api/system/cache/gc-outputs` 端点（max_bytes/max_count/dry_run）接入系统路由。加 6 测试（选择逻辑：LRU/数量/字节/引用保护/无操作 + runner：孤儿驱逐保留引用、dry_run 不删）。全量 613 passed。
> ⏸ **余项**：前端缓存页的"回收产物"按钮 + 自动触发（启动/定时）——后端 API 已就绪，UI 接入属前端 session。
- **现状（原）**：`output-pipeline/<task_id>/` 仅显式删除时清（`tasks.py:191`），无 TTL/容量上限；`cache_manager.py` 能算明细但未对流水线输出做驱逐。
- **方案**：对 `output-pipeline` 加 LRU/容量上限 GC（尊重 DB 仍引用的任务），接入现有缓存 UI。
- **验收**：超限时按 LRU 清理未被引用产物。
- **测试**：单测 GC 选择逻辑。

### ARCH-8 — Stop 真正传递到子进程 ｜ DONE ｜ D/健壮性 ｜ S–M ｜ ✅已核实
> 已修：`run_pipeline`/`execute_node`/`execute_stage` + ocr/erase bridge 全程下传 `should_cancel`，每个 `run_stage_command` 接 SIGTERM 机制；循环内每节点前加取消检查，`StageSubprocessCancelled` 独立于 required 性传播（取消可选节点也会停整条）。`task_manager` 加 `{task_id: Event}` 注册表，`stop_task` 置位事件、`_run_pipeline_in_thread` 注入 `cancel_event.is_set` 并在 finally 清理、保留 "Stopped by user" 文案。加 2 测试（run_pipeline 取消中止 + stop_task 置位事件）。后端 507 passed。
- **现状**：`subprocess_runner.run_stage_command` 完整支持 `should_cancel`（看门狗 + SIGTERM→SIGKILL，`subprocess_runner.py:111`），但 `run_pipeline` 的全部 7 处调用（`runner.py:394,403,412,425,470,517,731`）**都没传**；`task_manager.stop_task` 只改 DB 状态，子进程跑到底再覆盖。路由文案声称"发送终止信号"——实际没有。
- **方案**：从 `task_manager` 传 `threading.Event` 进 `run_pipeline(..., should_cancel=event.is_set)`，转发给每个 `run_stage_command`；用 `{task_id: event}` 映射（照搬 `job_manager._cancel_events` 模式，`job_manager.py:413`）。
- **验收**：点 Stop 后正在运行的子进程在秒级内被杀，状态置为 cancelled/failed。
- **测试**：单测取消传播；手动起长任务点停验证进程退出。

### ARCH-9 — 启动时回收悬空流水线任务 ｜ DONE ｜ D/健壮性 ｜ S ｜ ◻待确认
> 已修：`task_manager.mark_interrupted_tasks()`（重启时把 running/pending Task 置 interrupted，前端 StatusBadge/i18n 已支持该态），在 `app.py` 启动钩子调用（紧随 `mark_interrupted_jobs`）。加测试。后端 508 passed。
> 顺带发现并记录 `TEST-1`（atomic 测试非 hermetic，污染真实库）——本工单期间清理了真实库 931 条测试垃圾 job 以解除其引发的假失败。
- **现状**：`job_manager.mark_interrupted_jobs()` 在 `app.py:59` 回收孤儿原子任务，但**无流水线 Task 版**；server 崩溃后 Task 永远卡 `running`/`pending`。
- **方案**：加 `mark_interrupted_tasks()`，启动时把 `pipeline-status.json` 非 running 或缺失的 `running`/`pending` Task 置 `interrupted`/`failed`。
- **验收**：重启后无幽灵 running 任务。
- **测试**：单测回收逻辑。

### ARCH-10 — 进度双轮询 + SSE 假 timeout ｜ DONE（假 timeout+心跳；pub/sub 留子项）｜ 性能/产品 ｜ S–M ｜ ✅已核实
> 已修核心 bug：`stream_progress` 去掉 **300s 硬上限**（>5min 长任务不再报假 `timeout`）——改为**循环到终态**，且终态判定以**DB 行为权威**（`_sync_status_to_db` 保持其最新，故 JSON 停更/缺失也能正确结束）；无变化时每 `heartbeat_sec` 发 `: keepalive` SSE 注释**保活**（防 idle 代理掐断）；Starlette 在客户端断开时取消生成器，故无界循环安全。加 `interval`/`heartbeat_sec` 参数便于快测。加 4 测试（DB 终态退出无 timeout、JSON 进度+done、running 心跳、not-found）。全量 633 passed。
> 🔌 **ARCH-10b 接线死字段 + 降 churn**（2026-06）：审计 `PipelineRequest` 字段发现 `status_update_interval_sec` **被 set 从不 read**（monitor 每次 update 全量重写 JSON，正是上面的 churn 源）。`PipelineMonitor` 加 `status_update_interval_sec` 参数（默认 0.0=不节流，向后兼容）+ `_write(force)`：**running 中间进度节流**到每 interval 一次、**transition/terminal（start/complete/fail/finalize）强制写**（终态永不丢）；run_pipeline 传 `request.status_update_interval_sec`(默认 2s)。加 `_write_count` 可观测 + 4 测试（不节流每次写/大 interval 节流 running/终态强制写且文件反映终态/fail+finalize 强制）。全量 659 passed。
> ⏸ **余项**：彻底消除"双 reader"（SSE 仍读 JSON 取富 per-stage 数据，DB 只作终态权威）+ 把 `PipelineMonitor` 改进程内 pub/sub——较大重构，留 TODO。
> 🔎 **同次审计未修的 unwired 字段**（需产品判断，未动）：`resume`（`--resume` 设它但 run_pipeline 只读 `reuse_existing`，redundant 死 flag）；`keep_logs`（set 不 read——但删日志与 UI-5 日志查看端点冲突 + 失败时丢诊断）；`config_path`（无加载方）。建议另开工单决定 wire/删除。
- **现状**：每任务 `_sync_status_to_db` 3s（`task_manager.py:315`）+ `stream_progress` 独立 1.5s（`:445`）重读同一 JSON；`monitor._write()` 每 tick 全量重写 JSON；SSE `max_wait=300`（`:440`）让 >5 分钟任务报假 timeout。
- **方案**：SSE 改读已同步的 DB 行（消除重复 reader）；去掉/心跳化 300s 上限；长期把 `PipelineMonitor` 改进程内 pub/sub。
- **验收**：长任务不再断流；磁盘读减少。
- **测试**：手动长任务观察 SSE 不 timeout。

### ARCH-11 — DB 迁移版本化 ｜ DONE（schema_version 框架）｜ 健壮性 ｜ M ｜ ✅已核实
> 已修（选轻量 `schema_version` 表方案，不引 Alembic）：`database.py` 加版本化迁移框架——`schema_version(version,name,applied_at)` 表 + 有序 `_MIGRATIONS=[(version,name,fn)]` 列表 + `run_migrations(engine)`。每个迁移在**独立事务** `engine.begin()` 中跑，仅成功后写 schema_version 行；**失败回滚且抛出**（半应用 schema 可检测，不静默），已应用版本跳过（每次启动可安全重放）。原手写 `ALTER ADD COLUMN` 收编为幂等的 migration v1（`_add_missing_columns` 仍 PRAGMA 守卫——故已有列的旧库只记版本不报错）。`init_db` 改调 `run_migrations()`；加 `applied_versions()` 内省。加 3 测试（空库→记 v1+幂等重放、旧库补列、注入失败迁移验证回滚+不记版本）。全量 602 passed。
> ⏸ 降级/改名/改类型/回填等高级迁移：框架已就位，按需在 `_MIGRATIONS` 追加 v2+ 即可（勿重编号已发布版本）。
- **现状（原）**：`database.py:36` 手写 `ALTER ADD COLUMN` 列表，加列幂等但无版本、无降级、不支持改名/改类型/回填，部分失败不可检测。
- **方案**：上 Alembic 或 `schema_version` 表 + 有序迁移函数；至少包裹迁移使部分失败可检测并记录已应用版本。
- **验收**：迁移可重放、可检测失败。
- **测试**：迁移单测（空库→当前）。

### ARCH-12 — 统一默认值单一来源（24k/48k 等）｜ DONE ｜ D/正确性 ｜ S ｜ ✅已核实
> 已修：4 处 `output_sample_rate` 24000→48000（`routes/config.py` 与 `task_manager.py` 用 `DEFAULT_RENDER_OUTPUT_SAMPLE_RATE` 常量，前端 NewTaskPage/SettingsPage 改 48000）；4 处 `separation_mode` "auto"→"dialogue"（对齐 dataclass/CLAUDE.md，UI 任务由自动路由改为强制 dialogue 分离）。加回归测试断言三处后端默认源一致；顺手把 `test_config_defaults_*` 改为 hermetic（原先读开发机 `~/.translip/config.json` 致环境性失败）。后端 505 passed。
- **现状**：同一默认值分散且冲突：`output_sample_rate` 在 `config.py:52`/`pipeline.py:79`=48000，但 `task_manager.py:91`=`cfg.get(..., 24000)` → **UI 建的任务以 24kHz 配音**（可听音质降级）；`separation_mode` 在 `pipeline.py:92`="dialogue" vs `task_manager.py`/`config.py`="auto"。
- **方案**：`_build_pipeline_request` 改为 `cfg.get(k, <config.py 常量>)`；`PipelineRequest` 字段默认引用同一常量。
- **验收**：CLI 与 server 构造的 request 默认值一致；新建任务输出 48kHz。
- **测试**：单测两条构造路径默认值一致。

### ARCH-13 — env 配置提升到 UI + 有效配置内省 ｜ DONE（内省端点；UI 编辑留前端子项）｜ 产品 ｜ M ｜ ✅已核实
> 已修内省核心：新增 `server/config_introspect.py`——curated `CONFIG_KNOBS` 注册表（20 个运营关键 knob：cache/db/user-config 路径、ffmpeg、default-glossary、deepseek key/base_url/model、moss/qwen/voxcpm TTS、paddleocr/erase 模型目录、HF/pyannote/tmdb token）+ `introspect_config(environ=)` 解析每项**有效值与来源**（env 覆盖 vs 内置默认；因 resolver 都直接读 `os.environ`、settings 启动时已应用到 env，故读 environ 即 resolver 所见，准确）。**密钥类只报 `value:"set"/null`，绝不回传明文**。加 `GET /api/system/config/effective` 端点。加 5 测试（全默认、env 覆盖、secret 掩码、未设 secret 报 null、端点不泄漏明文）。全量 626 passed。
> ⏸ **余项**：把 TTS/OCR/erase 路径与 device **写入** settings store 并接前端可编辑面板（无需改 env 重启）——后端内省已就绪、写入需前端 session。
- **现状**：~30 个 env 变量，UI 只能改 HF/LLM/TMDB key；TTS CLI/模型目录、OCR/erase 模型目录、device 只能 export 后重启。
- **方案**：把运营关键路径提升进现有 settings store（`cache_manager` 用户设置已能桥接 env）；加"有效配置"内省端点（每个 knob 的值 + 来源 env/default/setting）。
- **验收**：UI 可配置 TTS/OCR/erase 路径与 device，无需改 env 重启。
- **测试**：前后端单测 + 手动改配置生效。

### ARCH-14 — `PipelineRequest.normalized()` 用 `dataclasses.replace` ｜ DONE ｜ D/架构 ｜ S ｜ ✅已核实
> 已修：`normalized()` 从手写 90 行逐字段重列改为只把**需变换**的 ~35 个字段放进 `overrides` dict（路径 resolve、int/float/bool/list/dict 强制、`normalize_dubbing_quality_check_mode`），其余全部由 `dataclasses.replace(self, **overrides)` 原样保留——**新增字段不再会被静默丢成默认值**。加测试 `test_pipeline_request_normalized_preserves_all_passthrough_fields`（设 11 个非默认 pass-through 值 + 路径 resolve + temperature int→float 强制）。全量 577 passed。
> 🔒 **ARCH-14b 系统性加固**（2026-06）：DEL-1 暴露同型 bug 后，把**其余 7 个** `Request.normalized()`（separation/rendering/dubbing/translation/speakers/transcription/delivery）也全部从手列重建转为 `dataclasses.replace`——只保留 path resolve + 少量 int/float/bool/list 强制为 overrides。整类"手列重建漏字段"bug 自此消除。加参数化回归闸 `tests/test_request_normalized_preserves_fields.py`（每个 Request 验代表性 pass-through 字段存活 + 路径 resolve）。全量 648 passed。
- **现状（原）**：`types/pipeline.py:139` 手写 90 行逐字段重列；新字段忘了在此 + `_build_pipeline_request` 加就会被静默丢。
- **方案**：`normalized()` 改 `dataclasses.replace(self, **overrides)`（近零风险）；长期拆嵌套 sub-config。
- **验收**：新增字段不再需要改 `normalized()`。
- **测试**：单测 normalize 保留所有字段。

### ARCH-15 — 前后端契约生成/校验 ｜ TODO ｜ 架构/产品 ｜ M ｜ ◻待确认
- **现状**：前端 `api/` 手工镜像后端 Pydantic；`node_name`/`stage_name` 双键（`monitor.py:126`）显示已有改名中途。
- **方案**：从 FastAPI OpenAPI 生成 TS 客户端（openapi-typescript/orval）纳入 `npm run build`，或 CI diff 校验；统一双键为单一 canonical key。
- **验收**：契约漂移在 CI 被捕获。
- **测试**：CI 校验脚本。

### ARCH-16 — 列表分页下推 SQL ｜ DONE(tasks) ｜ 性能 ｜ S–M ｜ ◻待确认
> 已修 `routes/tasks.py::list_tasks`：COUNT 走 `select(func.count()).select_from(stmt.subquery())`、LIMIT/OFFSET 下推、stages 用单条 `IN(...)` 批量分组——不再全表加载+Python 切片+per-task N+1。加测试(total/分页/stages 分组)。后端 520 passed。`job_manager.list_jobs`/`works.py` 的同类 all-then-slice 留作 ATOM-4/后续。
- **现状**：`tasks.py:152` 全表加载后 Python 切片，且逐任务查 `TaskStage`（N+1）；`job_manager.list_jobs`、`works.py:751` 同样 all-then-slice。
- **方案**：`LIMIT/OFFSET`+`COUNT` 下推 SQL；stages 用单条 `IN(...)` 或 join 批量加载。
- **验收**：列表查询不随表增长线性变慢。
- **测试**：单测分页 SQL；造数据计时。

### SEC-1 — 路径穿越改 `is_relative_to` ｜ DONE ｜ D/安全 ｜ S ｜ ✅已核实
> 已修：`artifacts.py:55`、`analysis.py:186` 的 `str(p).startswith(str(root))` 改 `full_path.is_relative_to(root)`；`job_manager._owns_job` 去掉 `startswith` 兜底（改为 `except → return False`，不再接受 `jobs-evil/` 同前缀兄弟目录）。加 handler 直调的 403 穿越测试（`task-1` vs `task-1-evil`）。后端 509 passed。
- **现状**：`artifacts.py:55`、`analysis.py:186` 用 `str(full_path).startswith(str(output_root))`——`../task-1-evil/secret` 可通过（已验证）；`job_manager.py:560` 旧式 fallback 同病（`:558` 已是正确的 `is_relative_to`）。
- **方案**：三处统一改 `full_path.resolve().is_relative_to(output_root)`（`dubbing_editor.py` 已是正确写法可参照）。
- **验收**：`..` 逃逸被拒。
- **测试**：单测穿越路径返回 403。

### SEC-2 — 鉴权 + 127.0.0.1 + 收窄 CORS ｜ HOLD ｜ 安全 ｜ S–M ｜ ◻待确认
> 2026-06 用户决定暂缓（local-first 单用户，dev 走 Vite 代理同源、prod 后端同源托管 SPA，CORS 极少被命中）。需要时再议鉴权强度。
- **现状**：`app.py:47` `allow_origins=["*"]`+`allow_credentials=True`（自相矛盾）；全路由无鉴权，含写 API key（`system.py:463`）、读任意产物、删任务。
- **方案**：默认 127.0.0.1 绑定（`run_server` 已是默认，明确/强制）；可选共享 token 中间件（env 开关）；CORS 收窄到 `http://127.0.0.1:5173` 并去 `allow_credentials`（除非需要）。
- **验收**：跨域被拒；开启 token 后未授权 401。
- **测试**：单测 CORS/鉴权中间件。

### SEC-3 — argv 输入轻量校验 ｜ DONE ｜ 安全 ｜ S ｜ ✅已核实
> 已修：新增 `orchestration/argv_safety.py`（白名单校验器 `validate_lang/url/model/path_identifier`），在 argv 构造**前**拦截两类真实风险——① **参数注入**（`-` 前缀值被子进程 argparse 当 flag）；② **路径穿越**（`speaker_id` 直接作目录组件 `task_d_voice_dir/speaker_id`，拒 `..`/分隔符）。接入 `commands.py`：transcription 校验 `transcription_language`，translation 校验 `target_lang`/`api_model`/`api_base_url`，synthesis 校验 `speaker_id`+每个 `segment_id`，render 校验 `target_lang`。校验器接受 Unicode 词字符（CJK persona 名不误伤），`asr_model` 故意不校验（可为含 `/` 的 HF 路径）。加 `tests/test_argv_safety.py`（50 例）。全量 576 passed。
- **现状（原）**：argv 列表传参（shell=False）**不可注入**，但 `speaker_id`/`api_base_url`/`target_lang` 等无校验流入 argv。
- **方案**：加 charset/enum 校验（白名单字符、枚举值）。

---

## separation — 分离（SEP）

### SEP-1 — 内部 transcription 供给改无损 ｜ TODO ｜ B/算法 ｜ S ｜ ◻待确认
- **现状**：`stage1_output_format="mp3"`（`types/pipeline.py`），有损 stem 直喂 ASR + ECAPA（`commands.py:168`、`transcription/runner.py:106,123`），丢掉 ECAPA 依赖的高频音色。
- **方案**：内部供给改 FLAC/WAV（用户可见产物可保留 mp3）。
- **验收**：transcription 读到无损 stem；与 ASR-1 配合评估 diarization 改善。
- **测试**：跑批对比 cross-speaker 相似度分布。

### SEP-2 — 分离质量/SNR 度量 ｜ DONE（核心度量；VAD 覆盖率留子项）｜ A/算法 ｜ M ｜ ✅已核实
> 已修（UI-3 HOLD 的替补）：新增纯 numpy 模块 `pipeline/separation_quality.py`——`separation_metrics(voice,bg,mix)` 算 `voice_rms`/`background_rms`/`voice_to_background_db` + 残差重构比 `‖mix−(voice+bg)‖/‖mix‖` → `separation_confidence∈[0,1]`（同采样率才报残差）；`compute_separation_metrics` 读三个 WAV。`pipeline/runner.py` 在分离后用无损中间件算度量（**try/except 包裹——绝不因可选度量拖垮分离**），写入 separation manifest 新增 `quality` 字段（`build_manifest` 加可选 `quality` 参数）。低置信分离从此可被发现/驱动质量升级。加 `tests/test_separation_quality.py`（完美重构→conf>0.99、坏样本→conf<0.5、异采样率跳残差、空信号→{}、文件往返）。全量 607 passed。
> ⏸ **余项**：VAD 覆盖率指标 + 低置信自动告警/触发 SEP 升级——框架（manifest.quality）已就位，按需追加。
- **现状（原）**：分离只写 timing/route，无任何输出质量度量（grep `snr|si-sdr|leakage` 0 命中）。
- **方案**：算 voice/bg RMS 比、残差 `‖mix−(voice+bg)‖`、VAD 覆盖率 → `separation_confidence` 写入 separation manifest，低置信告警 / 触发 SEP/质量升级。
- **验收**：manifest 含置信度；低质能被发现。
- **测试**：单测度量计算；坏样本验证告警。

### SEP-3 — `enhance_voice` 死代码处理 ｜ DONE（诚实占位）｜ D ｜ S/M ｜ ✅已核实
> 选"诚实占位"路径（真 denoise 需真实合成 A/B，本地不可验）：① `pipeline/runner.py` 启用 `enhance_voice` 时把误导的 `logger.info("Enhancing voice track.")` 改为 **WARNING**——明说"无真实增强 backend，原样拷贝、未降噪/去混响"；② `NoOpVoiceEnhancer` 加 docstring 明确是 passthrough 占位、勿当增强音；③ 修文档去"假能力"——CLAUDE.md/README/README.en 的 separation backend 列表把 `clearervoice` 改注为"`--enhance-voice` 为空操作占位，无真实降噪"。加 `tests/test_voice_enhancer.py`（passthrough 字节相等 + 是 VoiceEnhancer 子类）。真 denoise 集成仍挂 SEP-3 待真实合成验证。
- **现状（原）**：`NoOpVoiceEnhancer` 字节拷贝（`models/clearervoice.py:8`），仅 `separate` CLI 接线、流水线未用，但 CLAUDE.md 列其为真 backend。
- **方案**：要么实现真 denoise/dereverb（ClearerVoice/DeepFilterNet）放 ASR/diarization 前，要么删死代码 + 文档。

---

## transcription — 转写 + 说话人分离（ASR）

### ASR-1 — diarization 用非降质音源 ｜ TODO ｜ B/算法 ｜ M ｜ ◻待确认
- **现状**：ECAPA 与 ASR 共用降质 mp3 stem（`transcription/runner.py:123`），继承分离 artifact，cross-speaker 相似度被抬到 ≥0.81（已知问题）。
- **方案**：ECAPA 改在**原混音 / demucs vocals** 同时间戳上提取（diarizer 已接受独立 `audio_path`，`speaker.py:230`），加 `--diarization-audio`；ASR 仍用 dialogue stem。
- **验收**：cross-speaker 相似度分布拉开。
- **测试**：真实多说话人跑批对比相似度矩阵 + 贴标正确率。

### ASR-2 — ECAPA 多窗 mean-pool + 情绪不变特征 ｜ TODO ｜ 算法 ｜ M ｜ ◻待确认
- **现状**：`_build_embedding_groups` 把 ≤5 段/8s 合并成一个嵌入窗（`speaker.py:86`），单向量聚类；情绪/F0 起伏被当"另一个人"。
- **方案**：每组取多短窗(~1.5s) L2 归一后 mean-pool；聚类前拼接长时平均谱/共振峰带比 + F0 中位统计（情绪不变）。
- **验收**：同一说话人情绪波动不再过度拆分。
- **测试**：用已知双峰 F0 的同一角色片段验证不拆。

### ASR-3 — 聚类阈值/`expected_speakers` 可调入缓存 ｜ DONE(expected_speakers) ｜ 算法/产品 ｜ M ｜ ◻待确认
> 已做 `expected_speakers`(0=auto) 端到端：`_cluster_embeddings` 在 >0 时强制 `n_clusters=k`(跳过单说话人塌缩+启发式 cap，治降质音频上的过度合并/塌缩)；ecapa+pyannote 两个 `assign_speaker_labels` 都接受该 kwarg(pyannote 用原生 `num_speakers`)；`_run_diarization`/`transcribe_file` 传递；plumbing 镜像 ASR-8(PipelineRequest/TranscriptionRequest 字段+normalized、transcribe/pipeline CLI、build_task_a_command、transcription 缓存、request.py/task_manager)。加 2 测试(聚类按 k 出簇 + 命令含 flag+缓存键随其变)。后端 524 passed。⏳ `same_speaker_similarity` 阈值暴露 + 自适应切点(silhouette/eigengap) 留作后续。
- **现状**：`DEFAULT_SAME_SPEAKER_SIMILARITY=0.62`/`SINGLE_SPEAKER_FLOOR=0.52` 是模块常量（`speaker.py:21`），无 `min/max/expected_speakers`，不在 Request/CLI/transcription 缓存键。
- **方案**：暴露 `same_speaker_similarity`/`expected_speakers`/`min/max` 到 Request+CLI+缓存；已知 k 用 `n_clusters=k`；考虑 silhouette/eigengap 自适应切点。
- **验收**：用户能指定说话人数；改阈值触发重算。
- **测试**：单测 k 指定路径；缓存键含新参数。

### ASR-4 — 单说话人闸自适应 ｜ TODO ｜ 算法/产品 ｜ S ｜ ◻待确认
- **现状**：p20 相似度 ≥0.52 即全员压成一人（`speaker.py:156`）；降质音频全对 ~0.81 时极易误触发=最致命错误。
- **方案**：floor 改相对 spread（p20–p80 间隙）；`expected_speakers>1` 时跳过该捷径；触发时记日志。
- **验收**：多说话人场景不被误压成一人。
- **测试**：构造高相似度多说话人样本验证不塌缩。

### ASR-5 — 词级时间戳 + Paraformer 默认 ｜ TODO ｜ B/算法 ｜ M ｜ ✅已核实
- **现状**：`word_timestamps` 全代码库 0 命中；默认 ASR backend=`funasr`（`config.py:19`），SenseVoice **按字数比例伪造句内时间**（`funasr_backend.py:165`）；这些 start/end 正是 render 时间轴拟合的依据。
- **方案**：faster-whisper 开 `word_timestamps=True` 并把段边界吸附到词边、收紧首尾静音；默认切到产真实时间的 Paraformer（`sentence_info`）；或加轻量强制对齐替代比例估计。
- **验收**：时间戳精度提升，配音同步改善。
- **测试**：对齐误差度量；端到端听感同步。

### ASR-6 — ASR 幻觉/置信度处理 ｜ TODO ｜ A/算法 ｜ S–M ｜ ◻待确认
- **现状**：faster-whisper 只传 language/vad/beam/best_of/temperature（`asr.py:124`），无 `no_speech/compression_ratio/log_prob` 阈值与 temperature 回退；只丢空文本；不记 `avg_logprob`/`no_speech_prob`。
- **方案**：传上述阈值 + temperature 回退列表；把置信字段存进 `segments.zh.json` 与 manifest → 自动丢幻觉 + UI 标低置信 + 喂 OCR 仲裁。
- **验收**：静音/音乐段幻觉显著减少。
- **测试**：含残留噪声样本验证幻觉段被丢/标记。

### ASR-7 — glossary → ASR 偏置 ｜ DONE（机制；glossary 自动喂+质量验证留子项）｜ A/算法/产品 ｜ S–M ｜ ✅机制已核实
> 已修 hotword 机制（标准加性特征，只帮专名识别、不回退其他）：`AsrOptions` 加 `hotwords: tuple[str,...]`（+ metadata 序列化为 list）+ 纯 helper `hotword_string`（join/strip/去空）；**faster-whisper** 把 `hotwords=` 加进 transcribe_kwargs，**funasr** Paraformer(`hotword=`,默认路径)+SenseVoice(`_run_asr_on_chunk` kwargs) 两路都接（非 contextual 模型忽略，无害）；`TranscriptionRequest.hotwords` + `transcribe` runner 透传；CLI `--hotwords`(逗号分隔)+`_parse_hotwords`。加 5 测试（hotword_string/_parse_hotwords/AsrOptions.metadata/faster-whisper 经 fake model 验证 hotwords 真传入/空时不传）。全量 638 passed。
> ✅ **glossary 自动喂已补齐**（ASR-7b）：`build_task_a_command` 用 `glossary_hotwords(request)` 从 pipeline glossary 提取 source_variants（去重、跳含逗号项、cap 64）自动作 `--hotwords` 喂 transcription；并把派生 hotwords 加进 **transcription 缓存键**（`_stage_cache_payload`），改 glossary→重算 transcription（防 stale ASR，ARCH-4 同理）。加 6 测试（提取/去重/跳逗号/缺文件容错/build_task_a 含 --hotwords/缓存键随 glossary 变）。全量 654 passed。
> ⏸ **唯一余项**：**质量收益**（专名识别率↑）需真实音频 + 真实 SeACo/whisper 模型验证（本机不可验，机制本身是 ASR 既有标准能力）。
- **现状**：`glossary_path` 仅 translation 用；SeACo Paraformer 是 contextual 模型却没传 `hotword`（`funasr_backend.py:360`）。
- **方案**：把人名/术语作 faster-whisper `initial_prompt/hotwords`、SeACo `hotword=` 传入 transcription。
- **验收**：专名识别率提升。
- **测试**：含专名样本对比识别正确率。

### ASR-8 — `vad_max_segment_sec` 接线 ｜ DONE ｜ 算法 ｜ S ｜ ◻待确认
> 已修：镜像 `vad_min_silence_duration_ms` 的端到端 wiring 把 `vad_max_segment_sec`(default 30.0 保持现状、可调) 接通——`PipelineRequest` 字段+normalized、transcribe/pipeline CLI flag、`build_task_a_command` argv、transcription 缓存键、`request.py`/`task_manager` 两个构造器。原先固定 30s 够不着。加测试(命令含 flag + 缓存键随其变)。后端 518 passed。默认仍 30(不改行为)；配音降到 12–15 属需真验证的默认变更，未改。
- **现状**：`AsrOptions.vad_max_segment_sec` 两 backend 都支持，但 `PipelineRequest` 无此字段、CLI 无此 flag、不在缓存键 → 固定 30s（对 TTS 拟合/diarization 都太长）。
- **方案**：加进 `PipelineRequest`+CLI+`build_task_a_command`+缓存键；配音默认降到 12–15s；长独白按词间停顿切（接 ASR-5）。
- **验收**：长段被合理切分。
- **测试**：长独白样本验证切分。

### ASR-9 — `diarization_report` 输出 ｜ DONE（部分，余项见下）｜ A/产品 ｜ S ｜ ✅已核实
> 已修：`speaker_review/diagnostics.py` 加薄封装 `build_diarization_report(payload, diarization_metadata, source_path)`——复用既有 `build_speaker_diagnostics`（相似度矩阵、per-speaker 风险、similar_peers），再折入 diarizer 运行 metadata（backend/device、采用的 same-speaker 阈值、expected/observed speaker 数、group_count/valid_embeddings）+ 增强 summary（建议合并对数）。`transcription/runner.py` 在写完 segments 后即产 `transcription/voice/diarization_report.json`（try/except 包裹——辅助产物绝不拖垮 transcription），加入 `TranscriptionArtifacts.diarization_report_path`。ECAPA `speaker.py` metadata 廉价补上 `same_speaker_similarity`(0.62)+`expected_speakers` 以便报告显示采用阈值。加 2 测试（折入 metadata / 缺 metadata 回退）。全量 584 passed。
> ⏸ **余项**（需更深内部，留 TODO）：强制贴标/低 margin 段数需改聚类内部暴露每段 margin；ASR 置信度依赖 **ASR-6**（未做）。
- **现状（原）**：transcription 输出无相似度矩阵/阈值/强制贴标数/ASR 置信度；`speaker_review/diagnostics.py` 有计算但是事后独立工具。
- **方案**：transcription 时即产 `diarization_report`（相似度矩阵、簇内凝聚、采用阈值、强制贴标/低 margin 段数、+ASR-6 置信度），让 `speaker_review` 诊断默认在 transcription 输出上跑。
- **验收**：用户能在 transcription 后看到 diarization 证据。
- **测试**：单测报告生成。

---

## speaker-registry — 说话人库（SPK）

### SPK-1 — 存 gender/F0 → 同性别参考 + 双峰拆簇 ｜ TODO ｜ A/算法/产品 ｜ M–L ｜ ◻待确认
- **现状**：gender/F0 基础设施（`quality/audio_signature.py`）只接事后诊断（`characters/ledger.py:180`）；speaker-registry profile/registry **不存** gender/F0；`_prototype_from_embeddings`（`profile.py:15`）只 cos≥0.6 过滤 → M+F 混簇作单一原型存活；参考选择无性别意识。
- **方案**：(1) speaker-registry 计算 per-clip F0 + 性别估计存 profile/clip；(2) 簇内 F0 双峰则拆簇（治合并的 M+F）；(3) 参考选择按主性别下调/排除异性别 clip（**严格上游选择，非 R4 回退的 pitch-centrality**）。
- **验收**：男声不再漂向女声；同性别参考被选。
- **测试**：⚠ 鉴于 R4 教训，**必须真实 CPU 合成验证**（离线指标会骗人）；在混性别簇样本上验证拆簇正确。
- **关联**：R4 负结果、`SPK-2`。

### SPK-2 — SNR 参考打分 + denoise/normalize ｜ TODO ｜ A/算法/产品 ｜ M ｜ ◻待确认
- **现状**：参考打分按 `rms`（音量非干净度，`reference.py:217`、`voice_bank.py:433`）；`prepare_reference_package`（`reference.py:83`）只裁 11s + 补静音，无 denoise/归一/去首静音；VoxCPM denoiser 默认 OFF。
- **方案**：加 SNR/噪声底估计入打分；prepare 步做去静音 + 响度归一 + 轻 denoise；参考音默认开 VoxCPM denoiser；加大对混响/表情 clip 的惩罚。
- **验收**：克隆 `poor_speaker_match` 重试下降。
- **测试**：参考音质量 A/B（真实合成）。

### SPK-3 — composite reference 重采样修复 ｜ TODO ｜ 算法 ｜ M ｜ ◻待确认
- **现状**：`voice_bank._composite_reference`（`:235`）对采样率不同的 clip 静默 `continue` 丢弃（`:265`），且文本对齐近似导致恒降权。
- **方案**：拼接前统一重采样；保持文本对齐使 composite 不被惩罚；接缝交叉淡化避免咔哒。
- **验收**：低数据说话人 composite 可被推荐。
- **测试**：少 clip 说话人验证 composite 质量。

---

## translation — 翻译（TRA）

### TRA-1 — 时长预算注入翻译 + 默认重译/condense ｜ DONE ｜ A/产品/算法 ｜ S–M ｜ ✅已核实
> 已修，两部分：
> - **Part B（generate-to-fit）**：`duration.py` 加 `target_char_budget(source_dur, lang)`（en≈17 / zh≈4.5 / ja≈6.25 c/s 反推）；`_translate_units` 把 `target_duration_sec`+`max_chars` 塞进 `BackendSegmentInput.metadata`；`deepseek._translate_once` 把预算写进 per-segment JSON + system prompt 约束（非 LLM 后端忽略 metadata，无影响）。即首译就向时长收敛。
> - **Part A（总阀门）**：默认 `condense_mode` "off"→"smart"，启用既有的 duration-aware 修正回路（deepseek `_condense_once` 用 max_chars 重写 risky 段 / m2m100 走 rule-based）。跨 9 处默认源统一（config/types×2/schemas/task_manager/routes-config/前端×2），task_manager 用常量。
> 加 3 测试（target_char_budget / deepseek prompt 含预算 / 默认 smart）。后端 514 passed，前端 build+页面单测通过。
> ⚠️ **行为变更**：① condense 默认开——deepseek 会对 risky 段增加 condense API 调用，m2m100 走 rule-based(仅英文、无成本)；② deepseek 翻译 prompt 现带长度预算。**默认 backend 是 m2m100（无法 prompt、condense 弱），所以 "默认配置 overflow 下降" 的收益主要在 deepseek 路径**。
> ✅ **真实 A/B 已核实**（deepseek-v4-pro，迪拜 `voxcpm-dubai-rerun-20260531/transcription/voice/segments.zh.json` 前 60 段，2026-06）：
>
> | 条件 | fit | review | risky | 预估溢出 | overall_ratio |
> |---|---|---|---|---|---|
> | 基线（无预算/无 condense = TRA-1 前） | 32 | 9 | **19** | **17.0s** | 0.722 |
> | +翻译带 max_chars 预算（Part B） | 44 | 9 | **7** | **6.2s** | 0.663 |
> | +risky 段 condense（完整 TRA-1） | 49 | 8 | **3** | **3.2s** | 0.635 |
>
> risky 段 **19→3（−84%）**、预估溢出 **17.0s→3.2s（−81%）**；Part B 预算单独贡献大头（risky −63%、溢出 −64%），condense 清尾。REP-1 short 变体走同一 `condense_batch`，由此同步核实。key 仅走环境变量、未入库。
- **现状**：deepseek prompt 仅软指令"简洁"（`deepseek_backend.py:88`），预算翻译**后**才算；默认 backend `local-m2m100`（`supports_condensation=False`）+ `DEFAULT_CONDENSE_MODE="off"`（`config.py:31,36`）= **默认完全不控文长**。overflow/切尾的根因。
- **方案**：(1) 用 `duration.py:estimate_tts_duration` 系数算 `max_chars=source_dur×chars_per_sec` 注入 prompt；(2) `fit_level=="risky"` 默认重译 1 次再降级 condense；(3) LLM 系默认 `condense_mode="smart"`。
- **验收**：默认配置下 overflow/severe/切尾段数下降。
- **测试**：在 `output-pipeline/voxcpm-dubai-*` 上跑 translation→render，对比 `qa_summary.timeline`（overflow/`cut_audio_sec`）。

### TRA-2 — glossary 自动抽取 + 去硬编码哪吒 ｜ DONE（去硬编码+可配默认；抽取器留子项）｜ 产品/算法 ｜ M ｜ ✅已核实
> 已修去硬编码核心：`BUILTIN_DUBBING_GLOSSARY` 清空为 `()`（默认不再把《哪吒》专名强加到每个 zh→en 任务上——之前会把无关内容里的"哪吒"等错改）。7 条电影专名挪到**样例资产** `examples/glossary.zh-en.sample.json`（`--glossary` 加载格式）。`built_in_dubbing_glossary` 改为：空 builtin + 可选 `TRANSLIP_DEFAULT_GLOSSARY` env 指向的默认 glossary（去硬编码后给用户**可配置默认**而非纯删除；加载失败 WARN 跳过）。测试：原 builtin 测试改为显式 `--glossary` 验证机制 + 新增"默认 builtin 为空 + 样例资产可加载" + "env 默认生效"。全量 615 passed。
> ⏸ **余项**（算法部分）：专名**自动抽取器**（全局扫复现实体、各译一次、合成 glossary 注入解决"同名多译"）+ `dubbing_script.py` 硬编码整行译文清理 + 持久化到 registry 供系列复用——较大，留 TODO。
- **现状（原）**：`BUILTIN_DUBBING_GLOSSARY` 硬编码《哪吒》专名（`glossary.py:20`），`dubbing_script.py` 硬编码整行译文；batch 独立 → 同名多译。
- **方案**：把电影专名挪到样例资产；加专名抽取器（全局扫复现实体，各译一次，合成 glossary 注入）；可选持久化到 registry 供系列复用。
- **验收**：跨段同名一致；默认不含特定影片词。
- **测试**：多段含复现专名样本验证一致性。

### TRA-3 — 跨说话人/语域上下文 ｜ TODO ｜ 算法/产品 ｜ M ｜ ◻待确认
- **现状**：`build_context_units`（`units.py:32`）只拼同一说话人连续段；prompt 不含说话人身份/对方上句/语域（`speaker_label` 是 metadata 但不入 prompt）。
- **方案**：滚动窗纳入全说话人邻句 + per-speaker 语域提示。
- **验收**：代词/敬体一致性提升。
- **测试**：对话样本人工评估。

### TRA-4 — judge 时长维度 + 自动重译闭环 ｜ TODO ｜ A/产品/算法 ｜ M ｜ ◻待确认
- **现状**：`translation_judge.py` 只评 adequacy/fluency 且仅写 `judge_scores.json`；`remediation.py` 有 RETRANSLATE/REWRITE 但需人/loop 拾取。
- **方案**：把 `duration_budget.fit_level` 作首类 defect 喂 remediation；低分/`risky` 触发有界自动重译。
- **验收**：低分段自动改善无需人工。
- **测试**：单测闭环触发；端到端验证。

### TRA-5 — 数字/单位本地化 + TTS 停顿标点 ｜ DONE(部分) ｜ 产品 ｜ S–M ｜ ◻待确认
> 已做：`_punctuate_for_tts` 末尾标点从"仅英文"扩展到**所有语言**(zh/ja→。其它→.)，让 TTS 应用收尾语调；并对**长英文句**在 but/because/though/however/while 前插一个换气逗号(保守:≥12词、无内部标点、不靠两端;排除 and/or/so 等易误判)。纯函数+保意，加单测。后端 521 passed。⏳ 数字/日期/单位拼写本地化推迟(locale 重、收益需真 TTS 验证)。
- **现状**：无数字/单位本地化（QA 只 flag `contains_number`）；TTS 停顿只 `_punctuate_for_tts` 给英文补末尾句号（`dubbing_script.py:94`）。
- **方案**：加目标侧数字/日期/单位规范化（拼写 vs 数字按语言）；长句插逗号/停顿改善 TTS 韵律。
- **验收**：数字/日期发音正确；长句韵律改善。
- **测试**：含数字/长句样本听感。

---

## synthesis — TTS（TTS）

### TTS-1 — 长度/语速目标传 MOSS/VoxCPM + micro-fit ｜ HOLD ｜ A/产品/算法 ｜ S–M ｜ ◻待确认
> 2026-06 推迟：改的是 TTS 生成行为，但本机 **MOSS CLI 缺失、VoxCPM 太慢**，无法真合成验证；MOSS `max_new_frames` 的 frame→秒 映射未知，盲缩会截断语音（比现状差）。memory 红线「长度/音色必须真合成验证，离线指标会骗我」(R4)。待有可用 TTS 环境再做；届时优先做"安全上界"式 frame 缩放（只增不减、留 headroom）+ best-take 时长 tiebreaker（纯逻辑可单测）。
- **现状**：`SynthSegmentInput.duration_budget_sec` 只有 Qwen 消费（单边 `max_new_tokens`）；MOSS 固定 `max_new_frames=375`（`moss_tts_nano_backend.py:291`）；VoxCPM 无时长信号；拟合全推给 render atempo。
- **方案**：MOSS frames 按预算缩放；synthesis 选最佳 take 时若 `duration_ratio>1.3` 选更短候选或在 render 前触发改写；可支持的 backend 暴露 speed/rate 作锦标赛候选轴。
- **验收**：进 render 前 duration_ratio 收敛，atempo 拉伸减少。
- **测试**：真实合成对比 duration_ratio 分布。

### TTS-2 — 修复死键 `estimated_target_sec` ｜ DONE ｜ D/算法 ｜ S ｜ ✅已核实
> 已修：生产代码（`translation/duration.py`）只写 `estimated_tts_duration_sec`、从不写 `estimated_target_sec`；但 `dubbing/runner.py` 两处消费端先读 `estimated_target_sec` 再回退——而 17 处测试 fixture 又只给 `estimated_target_sec`，使两边各走一支、掩盖了不一致。改为消费端只读真实键 `estimated_tts_duration_sec`，并把测试 fixtures 的键对齐（生产行为不变）。后端 509 passed。选了"删死键"而非"校准产出"（后者属 length-control，归 TTS-1/Wave-1）。
- **现状**：`dubbing/runner.py:551,575` 先读 `duration_budget["estimated_target_sec"]` 再 fallback，但全树**无 producer**（只 `estimated_tts_duration_sec`），故 Qwen 长度上限/预算永远用粗估。
- **方案**：要么删死键查找；要么真产出——用该说话人自身参考/历史 take 的实测语速（synthesis report 已收 `generated_duration_sec`、`voice_bank` 聚合 `avg_duration_ratio`）校准 `estimated_target_sec`。
- **验收**：Qwen 长度上限匹配实际语速。
- **测试**：单测校准；真实合成验证。

---

## render — 渲染（REN）

### REN-1 — 两遍/全局时间轴拟合 ｜ TODO ｜ C/算法 ｜ M–L ｜ ◻待确认
- **现状**：`_assign_available_durations`（`runner.py:550`）只给本地预算（本段 slot 或到下一句的间隙），`_apply_fit_strategy` 逐段独立拟合，`_placement_start_for_item` 永远锚定 `anchor_start`——只往后溢出、不借前停顿、不移锚。
- **方案**：按 speech island（被真静音隔开的最大连续段）做全局：最小化 `Σ wᵢ|log tempoᵢ|` s.t. 不重叠，placement 起点可在 `[prev_end, anchor_start]` 自由；至少先做两遍贪心（后向=现状，前向借前间隙 + 容差内微调锚点）。
- **验收**：chipmunk 与切尾段数下降。
- **测试**：用 `/tmp/dub_lab` 式重跑 render 出 scorecard（overflow/trim/ratio）对比。

### REN-2 — 视频变速选项 ｜ TODO ｜ 算法/产品 ｜ L ｜ ◻待确认
- **现状**：所有 fit 策略只 `compress_audio`，视频从不动（`utils/ffmpeg.py:220`）。
- **方案**：对 `overflow_unfitted` 段 opt-in `setpts` 慢 ≤8–10%（先限非脸/远景）；或全局 ±X% 节目速率 knob。
- **验收**：最差溢出段改为视频微慢而非音频狂压。
- **测试**：样本对比听感/观感。

### REN-3 — 切尾级联 + 上游反馈 ｜ TODO ｜ C/产品/算法 ｜ M ｜ ◻待确认
- **现状**：`overflow_unfitted` 压到 `max_compress_ratio` 仍超则 `_trim_audio_inplace`（`runner.py:1103`）切尾，QA 仅报 `cut_audio_sec`，render 时最终定案，无上游回路。
- **方案**：(a) 切尾改级联：前向借用(REN-1)→视频微慢(REN-2)→才切，且切在词边界；(b) 切尾/触顶时写 `needs_shorter_translation`（秒→目标字数）回 translation/repair。
- **验收**：切尾总秒数下降；触发上游重译。
- **测试**：端到端验证切尾减少 + 信号产生。

### REN-4 — 最终混音无条件 R128 + 接线 `loudnorm_file` ｜ DONE ｜ D/产品 ｜ S ｜ ✅已核实
> 已修：交付混音无条件 R128（-16 LUFS / TP -1.5 + alimiter）。实现选了 **mux 内联 chain**（ticket 允许的 "or inline chain"）：`mux_video_with_audio`/`burn_subtitle_and_mux` 加 `loudnorm` 参数，仅 `delivery/_export_video_variant` 传 True（scoped 到交付，不波及 atomic mux / 字幕烧录；`loudnorm=False` 路径与原命令字节级一致）。**未走 `loudnorm_file` 前置 pass**（会改 `input_audio_path` 破坏 `test_delivery` 音源契约 + 采样率探测在测试中被 mock 不可靠），该函数遂成冗余死代码、已删除。加 delivery 断言 loudnorm=True。后端 509 passed。
- **现状**：R128 仅 `mix_profile=="enhanced"` 跑（`runner.py:834,889`），默认 `preview`（`types/rendering.py:29`）→ 只 peak 归一；`loudnorm_file`（`audio.py:85`）被 import（`runner.py:22`）但**从不调用**。
- **方案**：交付混音无条件 R128（≈-16 LUFS/TP -1.5），接线 `loudnorm_file`（或内联链）到 delivery；`mix_profile` 只控处理质量、不控"有无响度"。
- **验收**：preview 与 dub 变体都达一致响度。
- **测试**：ffmpeg loudnorm 测量输出 LUFS。

### REN-5 — 边界淡化/交叉淡化/去 DC ｜ TODO ｜ 算法 ｜ S ｜ ◻待确认
- **现状**：每 clip 归一 + 10ms 线性淡化后**相加**（`runner.py:812`）；叠加层固定增益无交叉淡化；切尾 30ms 淡化。
- **方案**：等功率(cos/sin)淡化；相邻/叠加用交叉淡化而非硬加；TTS clip 求和前去 DC 偏置。
- **验收**：密集对话无可闻爆音。
- **测试**：密集对话样本听感 + 波形检查。

### REN-6 — sidechain 默认 + 参数可调 ｜ TODO ｜ 产品 ｜ S–M ｜ ◻待确认
- **现状**：默认 `ducking_mode="static"`（`types/rendering.py:30`）仅 -3dB 浅压；sidechain 参数硬编码（`audio.py:200`）。
- **方案**：交付默认 `sidechain`（跟随 dub 包络）；暴露 threshold/ratio/attack/release；默认压深 -6〜-9dB；用 QA-1 的可懂度往返选压深。
- **验收**：对白可懂度/混音感改善。
- **测试**：可懂度往返（QA-1）度量。

### REN-7 — dub 导出缺背景乐床 ｜ DONE ｜ D/产品 ｜ S ｜ ✅已核实
> 2026-06 用户决定：**改标签对齐现实**（保持音频产物不变：preview=含背景全混 / dub=纯人声轨）。前端 i18n `audioSource` 两处（zh/en）改为 dub→"纯人声轨（无背景音乐）"/"Voice-only stem (no music)"、preview→"配音成片（含背景音乐）"/"Dubbed film (with music)"、both→"两者都导出（成片 + 人声轨）"。键 dub/preview 不变，后端映射不变。TaskDetailPage 结果区的 profile 描述属 UI-3（i18n 泄漏）范畴、描述基本准确，未纳入本工单。前端 build/类型检查通过。
- **现状**：`export_dub` 走 `_resolve_dub_audio_path`→`dub_voice.<lang>.wav`（裸求和人声、仅 peak 限幅、**无 bg/ducking/R128**，`delivery/runner.py:493`）；带床的只有 `preview_mix`。
- **方案**：先定义"dub"语义——若是交付物应为全混 + 响度归一（dub+床）；若有意是 voice-only stem 则改名并把带床混音设为默认交付。
- **验收**：选 dub 导出得到符合定义的音频（很可能应带床）。
- **测试**：导出后听是否有 BGM。
- **备注**：⚠ 需你做产品判断"dub 应否带床"。

---

## delivery — 交付（DEL）

### DEL-1 — 软字幕 + 多音轨 + CRF/语言元数据 ｜ DONE（核心+CLI+直连API）｜ 产品 ｜ M ｜ ✅已核实
> 已修：**ffmpeg 层**新增纯 arg-builder `build_soft_subtitle_mux_args`（可单测、不跑 ffmpeg）+ `mux_with_soft_subtitle` 包装——`-c:v copy` **免重编码**、dub 为默认轨、可选 `-map 0:a:0?` 原声第二轨、`-c:s mov_text`(mp4)/`srt`(mkv) **软字幕流**、per-stream 语言标签(`iso639_2` en→eng/zh→zho/…)+disposition、`-filter:a:0` 只对 dub 做 loudnorm；`mux_video_with_audio`/`burn_subtitle_and_mux` 加 `audio_language` 元数据，burn 暴露 `crf`/`preset`。**请求**：`ExportVideoRequest` 加 `subtitle_delivery`(burn/soft 默认 burn)/`embed_original_audio`/`crf`/`preset`，`SubtitleDeliveryMode` 字面量。**runner** `_export_video_variant` soft 分支走新 muxer，burn 透传 crf/preset/语言。**接线** CLI(`--subtitle-delivery/--embed-original-audio/--crf/--preset`) + server 直连 `/export-video` 路由。
> 🐞 **顺手修真实 bug**：`export_video`+`_resolve_request` 两处**手工逐字段重建** request（ARCH-14 同型反模式）会把**任何新字段静默丢成默认**——改 `dataclasses.replace` 根治（否则 soft 永不生效）。
> 加 11 测试（arg-builder 全特性/无字幕/mkv/非法 end_policy、iso639_2、两 muxer 语言/crf/preset monkeypatch、runner soft 路由集成）。全量 595 passed。
> ⏸ **余项**：mkv 容器(`DeliveryContainer` 仍 Literal["mp4"])、按分辨率缩放 CRF、Opus、前端 toggle + 流水线集成导出(task_manager)的 4 字段透传——属后续。
- **现状（原）**：`_export_video_variant`（`delivery/runner.py:372`）只烧录字幕（`ass=` filter）；强制 `libx264 crf=18`；单音轨（`-map 1:a:0`）无语言 metadata；AAC 192k。
- **方案**：加软字幕模式（mp4 `mov_text`/mkv copy，免重编码）；`-metadata:s:a:0 language=`+disposition；mkv 多音轨(dub+原声)；CRF/preset 暴露并按分辨率缩放；AAC 256k 或 Opus。
- **验收**：可选软字幕（不重编码）、多音轨、带语言标签。
- **测试**：导出后用 ffprobe 验证轨道/字幕流/元数据。

### DEL-2 — 重活移出请求线程 ｜ HOLD（严重度已纠偏；正解前端耦合）｜ 健壮性/产品 ｜ M ｜ ◻待确认
> 🔎 **调研纠偏**：核查所有路由后，"阻塞 **worker**" 的严重解读（阻塞事件循环）**不成立**——`compose_delivery`/`synthesize_unit`/`render-range` 等重 handler 全是**同步 `def`**，FastAPI/Starlette 自动在 anyio 线程池（默认 ~40 线程）跑，**事件循环不阻塞**、服务对其他请求仍响应；唯二 `async def`（atomic upload/run_tool 委托 job_manager 线程、SSE 异步生成器）也无阻塞。且 **analysis dub-qa 已正确后台线程化**（返回 pending 记录 + `threading.Thread(_run_dub_qa_in_thread)` + 轮询，`analysis.py:91`）——`asyncio.to_thread` 对同步 `def` handler **无意义**（已在线程池）。
> ⏸ **残留 + 暂缓理由**：真正剩下的只是 `compose_delivery` 长编码会让**该客户端请求**久等（可能超时），其正解＝像 atomic-tools 那样返回 job 句柄 + UI 轮询，属**破坏性契约变更 + 前端改造**（compose 现同步返回结果），需前端协同 + 目检。本地单机场景下"线程池占一线程、客户端等待"可接受，故暂缓到能改前端的 session。
- **现状（原）**：`delivery.py:133 compose_delivery` 在 FastAPI handler 内同步跑 `export_video`（整段 ffmpeg 编码阻塞 worker）；analysis/dubbing_editor 同样同步跑合成/probe。
- **方案**：走后台任务机制（或至少 `asyncio.to_thread`），返回 job 句柄给 UI 轮询，与 atomic-tools/流水线一致。

---

## repair（REP）

### REP-1 — LLM 长度目标重译替换硬编码 ｜ DONE ｜ A/算法/产品 ｜ M ｜ ◻待确认
> 已修：`rewrite_for_dubbing` 加可选 `llm_backend`，short 变体优先走 **deepseek `condense_batch`**（duration-aware，复用 TRA-1 的 `target_char_budget` + glossary 保护）；失败/无 backend 回退既有规则法（保留，旧测试不破）。`RepairPlanRequest` 加 `api_model`/`api_base_url`，`plan_dub_repair` 从 env+config 建 deepseek（无 `DEEPSEEK_API_KEY`→None→规则法），orchestration 传入 request 的 api 配置。加 mock-LLM 测试。后端 516 passed。未删硬编码字典（删会破坏 `test_rewrite_for_dubbing_fixes_common_bad_phrase`；LLM 可用时取代之、仅作离线 fallback）。闭环完整效果需带 API key + 真 TTS 验证。
- **现状**：`repair/rewrite.py:139` 是《迪拜/哪吒》中→英硬编码字典；通用 `_shorten_english`（`:273`）仅 ~8 个缩写正则；换视频即近 no-op。
- **方案**：改用现有 deepseek 做带硬字符/时长预算（`estimate_tts_duration`）的多变体重译，glossary 保护，保留规则法作离线 fallback；tournament（`executor._attempt_specs`）已能吃多文本候选。
- **验收**：任意视频的 overflow/pacing 修复能产出真正更短译文。
- **测试**：非迪拜样本验证重译变短且达标。

### REP-2 — 修复 vs 原段改进闸 ｜ DONE ｜ 算法 ｜ S ｜ ◻待确认
> 已修：`executor._select_attempt` 加 `baseline_score`+`min_gain`(0.05) 闸——只在最佳 attempt 分数超过原段（`item['metrics']` 用同公式算的 `_baseline_score`）一个 margin 时才替换，否则保留原段（转人工）。防止修得不比原来好的回退。加单测（弱于原段不选 / 明显更好选 / 无 baseline 向后兼容）。后端 519 passed。
- **现状**：`_select_attempt`（`executor.py:532`）只在绝对阈值内选最高分，**不与修复前比较**；可能"修"得比原来差仍被接受。
- **方案**：选择门改为"超过原段分数(或失败维度) margin 才替换"，否则保留原段。
- **验收**：修复不引入回退。
- **测试**：单测改进闸。

### REP-3 — ECAPA 一致性闸 ｜ TODO ｜ 算法 ｜ M ｜ ◻待确认
- **现状**：声线一致性用 3 桶 pitch class（`executor.py:617`，同性别不同人蒙混）；`dub_embeddings` 算了 per-段 ECAPA cos 但权威 `speaker_similarity` 是 synthesis 对参考的值，最终混音从不重嵌入。
- **方案**：用 `dub_embeddings` 的 ECAPA cos 对说话人 centroid 做一致性闸（pitch class 留作廉价预筛）；加整片说话人相似度检查。
- **验收**：音色不一致被捕获。
- **测试**：换音色样本验证被拒。

---

## quality / 评测（QA）

### QA-1 — `perceptual_score`（切尾 + ASR 往返）｜ DONE(部分) ｜ A/产品/算法 ｜ M ｜ ◻待确认
> 已做：`dub_qa._perceptual_score` 纯函数 → 写入 `qa_summary.perceptual_score`（与 timeline 同处）。惩罚切尾 `cut_audio_sec`(≤40)、严重溢出比(≤35)、未配音比(≤25)；**不动 `_score`**（保历史可比，正合 [[dubbing-evaluation-loop]] 的「做成额外惩罚项别动权重」）。加单测（clean=100、62.5s 切尾≤60、切尾单调、空=100）。后端 517 passed。
> ⏳ 留作后续：对最终混音做 **ASR 往返**可懂度（需 ASR infra/较重，未做）；前端 EvaluationPage 展示 perceptual_score（UI 后续）。
- **现状**：`_score`（`dub_benchmark.py:215`）全是流水线状态计数/比例，无任何客观音频指标（grep PESQ/STOI/DNSMOS 0 命中），`cut_audio_sec` 不进式；故 90.3 分却丢 62.5s 切尾。
- **方案**：保留 `_score`（历史可比）；另建 `perceptual_score`：(a) 切尾/severe_overflow 惩罚；(b) 对**最终混音**做 ASR 往返(再转写 dub/preview diff 目标文本)捕捉 ducking/叠加/变速损失；(c) 可选 DNSMOS/UTMOS。
- **验收**：切尾严重的产物 perceptual_score 明显低于 `_score`。
- **测试**：在 `voxcpm-dubai-rerun-*`（已知 62.5s 切尾）上验证新分诚实反映。

### QA-2 — autofix 升级阶梯 ｜ HOLD ｜ 算法/产品 ｜ M ｜ ◻待确认
> 2026-06 推迟：memory [[dubbing-evaluation-loop]] 记载此项是**有意未做**——「升级换 backend 需真合成验证(离线指标会骗人)」。换轨/换 backend 是否真改善、会不会换到 VoxCPM 零样本不稳后端反而更糟，本机无 TTS 无法验证（同 TTS-1 红线）。待有真合成环境再做；届时 escalation 决策可写纯函数单测，但效果须真跑批验证。
- **现状**：`_choose_backends`（`autofix.py:241`）循环前算一次全程复用；每段最多试一次就退役；remediation 推荐的 escalation backend 被忽略。
- **方案**：rounds 做阶梯：R1 重合成(多 attempts)→R2 换参考 + LLM 改写(REP-1)→R3 换 backend(尊重 directive escalation list)；仍失败段可换策略再试；保留 accept-if-better 单调闸。
- **验收**：每次自动修复实际修好的段更多。
- **测试**：`tests/test_autofix_loop.py` 扩展阶梯；monkeypatch e2e。

---

## 字幕子系统 — OCR / Erase / 字幕输出（SUB）

### SUB-1 — 翻译字幕 CPS/折行/可读性引擎 ｜ DONE(折行) ｜ 产品 ｜ M ｜ ◻待确认
> 已做：`SubtitleStyle` 加 `max_chars_per_line`(0=auto)/`max_lines`(2)；`subtitles/burn.wrap_subtitle_text` 纯函数把字幕压成单逻辑行再折成 ≤max_lines 行、每行 ≤限宽(auto ~42 Latin / ~16 CJK，按脚本判断)，词/字不丢；srt_to_ass + merge_bilingual_ass(中/英各用各自 style) 全部接入。长译文不再单行溢出。加单测；既有 srt_to_ass 测试不受影响(短行不动)。后端 522 passed。⏳ CPS 强制(改 cue 时长/最短尺/合并) + 平衡到中点 留作后续。
- **现状**：`write_ocr_translation_bundle`（`subtitles/export.py:24`）逐 cue 原样输出译文；`srt_to_ass`（`burn.py:120`）仅 `\n→\\N`；`SubtitleStyle`（`types/common.py:82`）无 CPS/每行字数/最大行；dub 的 `max_chars` 预算到不了字幕。
- **方案**：烧录前对译文 SRT 做可读性 pass：CPS 上限(拉丁17/CJK9)、≤2 行平衡折行、违反最短时长/最小间隔则延长/合并；`SubtitleStyle` 加 `max_cps/max_chars_per_line/max_lines`。
- **验收**：长译文不再单行溢出。
- **测试**：长英译样本烧录目检 + 单测折行/CPS。

### SUB-2 — OCR cue 时间吸附真实帧 ｜ TODO ｜ 算法 ｜ M ｜ ◻待确认
- **现状**：单帧 cue `end=start+min_duration`（`subtitle_merger.py:458`）；多帧 `end=最后匹配采样帧`，不向缺失帧外延；默认 `ocr_sample_interval=0.25` → ±0.25s 量化且尾部系统性偏短。
- **方案**：merge 后在边界 ±sample_interval 做几帧二分/线性搜索（用 `should_run_ocr` textness 或快速重 OCR）吸附真实出现/消失帧。
- **验收**：cue 时间误差下降；erase 不再漏擦尾部、字幕不早消。
- **测试**：已知边界样本对比吸附前后误差。

### SUB-3 — cue 几何存 union ｜ DONE ｜ 算法 ｜ S ｜ ✅已核实
> 已修：`ocr/core/subtitle_merger.py` 的 `_compute_stable_geometry` 在中位 `stable_box` 之外，用 `_full_extent_box` 计算**全组检测框并集**（含全部检测，非仅高置信子集；同 padding 策略；并 fold 进 stable_box 保证不小于它）作 `box_full_extent` 返回；`Subtitle` dataclass 加 `box_full_extent` 字段，`_create_subtitle_from_group` 透传；`ocr/extract.py` 把 `box_full_extent` 写进 `ocr_events.json`/`detection.json` 两处 cue（缺失回退 box）。长行即便只在少数/低置信帧出现全宽，overlay/编辑 UI 与 erase 也能拿到真实范围。加 `tests/test_subtitle_merger_geometry.py`（低置信长帧并集覆盖、单检测=stable、端到端 Subtitle 带 full_extent）。全量 587 passed。erase 侧改用此字段属 SUB-4 范畴。
- **现状（原）**：`_compute_stable_geometry`（`merger.py:557`）存中位框（低估长行）；erase 侧才 union 补偿（`planning._event_box:104` 注释自认）。
- **方案**：cue 几何存 union/高分位宽度，或附 `box_full_extent`，让 overlay/编辑 UI 拿到真实范围。
- **验收**：长行 cue 框覆盖完整。
- **测试**：长行样本目检框范围。

### SUB-4 — erase 逐帧掩码 ｜ TODO ｜ 算法/产品 ｜ M–L ｜ ◻待确认
- **现状**：`erase_service._run` 用整区间 union 单掩码套全帧（`:249`），`plan_ranges` 合并 ≤10 帧（`planning.py:72`）；动画/移动/伸缩字幕过/欠擦。
- **方案**：用 `FrameBoxes` 的 frame→box 建逐帧掩码（至少按 box-set 不变子区间）；STTN 传逐帧掩码栈或在 box-set 变化时切批。
- **验收**：动画字幕无残影/拖影。
- **测试**：移动/伸缩字幕样本目检。

### SUB-5 — erase 前 cue 审核闸（UI）｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：检测到 erase 之间只有全局 lead/trail/dilate 常量；有 `--region` 逃生口但无法逐 cue 审核/删误检/改边界；流水线自动擦、事后报 `erased_range_count`。
- **方案**：UI 展示 `ocr_events.json` cue 列表 + 框 overlay + 每 cue 缩略帧，让用户开关/编辑，编辑后 detection.json 喂 erase（bridge 已接受任意 detection）。
- **验收**：可在不可逆擦除前审核/修正。
- **测试**：e2e 审核 → 编辑 → erase。

### SUB-6 — opencc + OCR 文本纠错 ｜ DONE（opencc 繁简；LLM 清洗留子项）｜ 算法/清理 ｜ S–M ｜ ✅已核实
> 已修：`subtitle_merger.py` 加 `to_simplified(text)`——优先 `opencc` `OpenCC('t2s')`（懒加载+缓存，sentinel 区分"未加载/不可用"便于测试 fallback），缺失时 fallback 到原手写繁简表（base 安装不受影响）。`_apply_common_variant_map`（仅用于 `_normalize_text` 的 dedup/相似度 key，**不改输出字幕**）改走 `to_simplified` → 繁/简同句归一到同 key、dedup 更准、覆盖远超手写表。`opencc-python-reimplemented` 加入 `ocr` extra。**实装 opencc 验证**：`OpenCC('t2s').convert('亂世佳人與東風')`→'乱世佳人与东风'，opencc 路径测试真跑通过（非 skip）。加 4 测试（opencc 路径 importorskip / 强制 fallback / 空串 / 繁简 dedup 归一）。全量 621 passed。
> ⏸ **余项**：用 deepseek 仲裁**清洗 OCR 源文**错字（OCR 是权威台本，错字会传到 dub+字幕）——属 LLM 调用，留 TODO。
- **现状（原）**：`_COMMON_VARIANT_TRANSLATION` 手写 ~290 条繁简表（`merger.py:16`，含 `亂` 重复键/`了→了` 空操作）；无通用混淆纠错/词典。
- **方案**：换 `opencc`(t2s)；可选用现有 deepseek 仲裁清洗 OCR 源文（OCR 是权威台本，错字传到 dub + 字幕）。
- **验收**：繁简/常见 OCR 错降低。
- **测试**：繁体样本验证转换正确。

### SUB-7 — STTN/LaMa 自动选择 ｜ TODO ｜ 算法/产品 ｜ M ｜ ◻待确认
- **现状**：backend 由 `erase_backend` 定（默认 sttn），不按内容选；STTN `neighbor_stride/reference_length` 固定。
- **方案**：字幕带运动估计：低运动/动画选 LaMa，否则 STTN；`reference_length` 随 fps 缩放。
- **验收**：静止用 LaMa(更锐)、运动用 STTN(更连贯)。
- **测试**：静止/运动样本对比 artifact。

---

## 原子功能（ATOM）

### ATOM-1 — adapter 自动发现 ｜ DONE ｜ 架构 ｜ S ｜ ◻待确认
> 已修：`adapters/__init__.py` 手写 10 行 import 改为 `pkgutil.iter_modules(__path__)`(排序确定性)自动 import 每个子模块触发 `register_tool`。掉一个新 adapter 文件即注册，无需改 `__init__`。registry 测试改为集合断言(顺序无意义)。后端 518 passed。
- **现状**：adapter 靠 import 副作用 `register_tool`，`adapters/__init__.py:46` 手写列举 10 个；漏一行静默丢工具。
- **方案**：启动时 `pkgutil.iter_modules` 遍历 `adapters` 包自动 import；装饰器契约不变。
- **验收**：新增 adapter 文件即被发现，无需改 `__init__`。
- **测试**：单测自动发现注册全部工具。

### ATOM-2 — 真队列 + 重启 re-enqueue ｜ DONE ｜ 产品/健壮性 ｜ M ｜ ✅已核实
> 已修（信号量排队 + 重启恢复，最小扰动）：① `create_job` **去掉 429**——满载也只写 `pending` 行；② `JobManager` 加 `BoundedSemaphore(max_concurrent_jobs)`，`_execute_job_sync` 在实际工作前 `acquire`/`finally release`——超额的 execute 在各自线程阻塞排队（路由仍 `create_task(execute_job)` 触发，故 api 测试"立即 completed"时序不变、单作业即获槽）；③ `mark_interrupted_jobs` 改为**只标 running**（崩溃中途的不自动续），新增 `recover_pending_jobs`（启动时对残留 `pending` 各起守护线程跑、同样受信号量约束）；④ app 启动 `mark_interrupted_jobs()`→`recover_pending_jobs()`。重写过时的"429"测试为"排队不拒"；加信号量限并发（ConcurrencyProbeAdapter 测 max_active==1）+ "mark_interrupted 保留 pending 且 recover 跑完"测试。全量 617 passed。
> 注：未引入 asyncio.Queue/独立 worker 池（信号量 + 线程已满足"排队不拒 + 重启续跑"），本地低并发场景足够。
- **现状（原）**：`create_job` 满载直接 429（`job_manager.py:114`），非队列；重启丢未启动任务（停 `pending` 仅标 interrupted）。
- **方案**：bounded `asyncio.Queue`+worker，提交入队不 429；启动时 re-enqueue `pending`。
- **验收**：超载排队而非报错；重启续跑。
- **测试**：单测队列 + 重启恢复。

### ATOM-3 — cancel 契约统一 ｜ DONE ｜ 架构 ｜ S ｜ ✅已核实
> 功能面**已由 ARCH-8 闭合**：核查确认 `execute_node` 已把 `should_cancel` 传给 `run_ocr_detect`/`run_subtitle_erase`（runner.py:745/792），流水线侧 erase/ocr 子进程可取消；atomic 侧 shell-out 的 `subtitle_detect`/`subtitle_erase` 也已接取消，in-process 的 `tts` 在 `on_progress` 检查点协作取消（其"worker subprocess"是注释、实为 in-process 推理）。
> 本工单剩余价值＝消除**易漏的隐式 hack**：两条 shell-out adapter 此前各自写死 `getattr(on_progress,"is_cancelled",None)`（魔法属性名重复、新 adapter 易忘）。新增 `atomic_tools/cancellation.py` 统一契约——`attach_cancel_checker(on_progress, predicate)`（job_manager 用，规范属性名 `should_cancel`）+ `cancel_checker(on_progress)`（adapter 用，返回 `Callable[[],bool]|None` 直喂 `run_stage_command`，等同流水线契约）。两 adapter 改用 helper，job_manager 改用 `attach_cancel_checker`。加 helper 单测 + job_manager 经统一契约把可用 checker 传到 adapter 的集成测试 + 迁移 3 处旧测试 stub（反向验证契约）。全量 599 passed。
- **现状（原）**：subtitle adapter 接 `should_cancel`（`subtitle_erase.py:156`），但同一 erase/ocr bridge 在流水线路径不可取消（同 ARCH-8 根因）。
- **方案**：统一单一 cancel 契约（随 ARCH-8 一起做）。

### ATOM-4 — list_jobs SQL 分页 ｜ DONE ｜ 性能 ｜ S–M ｜ ✅已核实
> 已修（仿 ARCH-16 `routes/tasks.py` 范式）：`list_jobs` 从"全行加载→Python 过滤→Python 切片→逐 job `list_artifacts`(N+1)"改为全 SQL——`status`/`tool_id`/`search` 下推 WHERE（命中 status/tool_id/created_at 索引），`func.count()`+subquery 算 total，`order_by(created_at desc).offset().limit()` 取页，artifact 数用**一条** `GROUP BY job_id` 批量查询（替代 N+1）。**ownership** 用 SQL `job_root LIKE '<jobs_root>/%'`（带分隔符边界，等价 `_owns_job` 的 is_relative_to——sibling `jobs-evil/` 因无 `/jobs/` 边界被正确排除），LIKE 通配符 `_`/`%`/`\` 转义；`input_files`(JSON) 经 `cast→lower→LIKE` 支持文件名子串搜索（语义为旧 per-filename 检查的超集）。`_job_to_read` 加可选 `artifact_count` 参数复用批量计数。加 3 测试（分页+批量计数、status/tool/search 过滤、foreign job_root 排除）。全量 582 passed。
- **现状（原）**：`job_manager.py:276` 全行加载→Python 过滤→逐行 `list_artifacts`（N+1）。
- **方案**：SQL prefix 过滤 + 分页 + 分组算 artifact 数。
- **验收**：作业列表不随增长变慢。
- **测试**：造数据计时。

---

## 前端 / UI（UI）

> 已强（保留）：DubbingEditor 逐段闭环（LiveFitPredictor/ClipFitMeter/候选锦标赛/回译/撤销重做/快捷键）、Evaluation 闭环（before/after + 回滚 + A/B 原声配音）、统一 Dashboard、原子工具链式跳转、persona 绑定导出。

### UI-1 — 修 Preview 音频 A/B ｜ DONE ｜ D/产品 ｜ M ｜ ✅已核实
> 已修：PreviewPane 的 original/dub 开关原先只切字幕、video src 固定（始终原声）。现镜像 EditMonitorPane 的成熟做法：加 `monitorAudioRef` + 从 `project.artifact_paths.preview_mix` 取配音全混 URL，`usesExternalAudio = audioTrack==='dub' && 有混音`；选 dub 时 video `muted`，外部 `<audio>` 与 video play/pause/seek/drift 锁同步；toggleMute 改为受控 state（video 与外部音轨共用）。无混音时优雅回退原声。tsc 通过，DubbingEditor 布局测试除 2 个既有失败(inspector preview/autosave，非本次)外全过。⚠ 音频同步需真实播放手验（jsdom 无法）。
- **现状**：`PreviewPane`（`DubbingEditorPage.tsx`）的 `audioTrack`（`:4141` 的 original|dub）只用于选字幕文本(`:4248`)与按钮样式(`:4339`)，video src 固定(`:4151`)；`EditMonitorPane`（`:3655`）才有正确 3 路真音频切换。
- **方案**：在 PreviewPane 复用 EditMonitorPane 的外部音频同步（original→视频静音、dub→视频音、mix→preview_mix），加"正在对比：原声/配音"标注。
- **验收**：Preview 能真正切原声/配音。
- **测试**：手动播放验证音频切换。

### UI-2 — 移动端导航 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：`MainLayout.tsx:80` Sidebar+TopNav 都 `hidden md:block`，`md` 以下无任何导航；Header 无汉堡。
- **方案**：Header 加 `md:hidden` 汉堡开 off-canvas Sidebar，或小屏底部 tab bar(主 4–5 路由)。
- **验收**：手机可在页面间导航。
- **测试**：移动视口手测。

### UI-3 — i18n 补全核心页 ｜ HOLD（需视觉验证）｜ 产品 ｜ M ｜ ◻待确认
> ⏸ **暂缓理由**：CJK 字面量散布 17 个 .tsx，大头 TaskDetailPage(144 行)/NewTaskPage(110)/SpeakerReviewDrawer(106) 均为大组件，总计 400+ 串。验收标准是**视觉**的（"英文 locale 下核心页全英文"），自动化只能验 tsc 编译期 key-parity，**无法捕获漏译、插值/复数断裂、英文文案比中文长导致的布局溢出**。需要能目检 en-US 渲染的专门前端 session 来做（迁移→切 en→逐页核对→修布局）。盲迁移风险高于收益，按 [[dubbing-evaluation-loop]] 同类纪律（离线/无目检指标会骗人）暂缓，候补做干净的后端工单。
- **现状**：TaskDetailPage(~144 行中文硬编码:重跑/停止/交付/清单/三步流程)、SpeakerReviewDrawer(~106 行,无英文路径)、SettingsPage(~114 行,节点高级参数)绕过 i18n；编译期 key parity(`messages.ts:1626`)是好的,问题是字面量没走 `useI18n()`。
- **方案**：迁移 TaskDetail/SpeakerReviewDrawer/Settings 字面量进 `messages.ts`(优先前两者,在交付/说话人关键流程);加 lint 挡 `.tsx` 内 CJK 字面量。
- **验收**：英文 locale 下核心页全英文。
- **测试**：切 en-US 目检 + lint。

### UI-4 — 完成通知 + 全局 toast ｜ DONE(部分) ｜ 产品 ｜ M ｜ ◻待确认
> 已做核心：`hooks/useTaskNotifications`（MainLayout 全局挂载）轮询任务列表，检测 running/pending→终态(succeeded/partial/failed/interrupted)，触发浏览器 Notification（懒申请权限）+ 后台时闪烁 `document.title`、聚焦时还原。纯函数 `diffFinishedTasks` 抽出可单测（2 测试通过）。MainLayout 布局测试加 hook mock 避免需要 QueryClientProvider。前端 build/类型检查通过，无新增测试失败。
> ⏳ **留作后续**：header "N running" 徽标、全局 toast provider 接所有 mutation（较广、需逐个改 onError）——本次未做以保持可控。
- **现状**：无 `document.title`/Notification/favicon badge；只有 `CacheSection.tsx:68` 一个局部 toast，其余 mutation 内联 banner 或静默。
- **方案**：app 级 toast provider 接所有 mutation；任务转 succeeded/failed 时 Notification + `document.title`；header "N running" 徽标。
- **验收**：长任务完成有可感知通知。
- **测试**：起任务切走 tab 验证通知。

### UI-5 — 阶段日志在 UI 可见 ｜ DONE ｜ 产品 ｜ M ｜ ◻待确认
> 已修：后端加 `GET /api/tasks/{id}/logs/{node}`，读 `<output_root>/logs/<node>.log` 末尾片段（max_bytes 限幅、`is_relative_to` 路径安全、缺失优雅返回 exists:false）。前端 `tasksApi.getNodeLogs` + WorkflowNodeDrawer 在 Error 与 Artifacts 之间加"查看日志"区（折叠 + <pre> 滚动 + 截断提示），i18n zh/en 双语键。后端 515 passed，前端 build/类型检查通过。（实时 SSE 流式留作后续；当前为按需拉取末尾。）
- **现状**：`WorkflowNodeDrawer.tsx` 有状态/进度/一行 `error_message`/产物 JSON，但无日志查看;`api/tasks.ts` 无 logs 端点;后端写 `logs/<node>.log` 不可达。
- **方案**：后端加 tail/stream `logs/<node>.log` 端点 + drawer "查看日志" tab(折叠/自动滚/running 时走 SSE)。
- **验收**：能在 UI 看阶段日志诊断卡顿/失败。
- **测试**：失败阶段验证日志可见。

### UI-6 — drawer 内重跑 ｜ TODO ｜ 产品 ｜ S ｜ ◻待确认
- **现状**：重跑只在 TaskDetail 顶部(`:478`);故障阶段 drawer 内无"从此重跑"(点节点设了 `rerunStage:460` 但按钮不在此)。
- **方案**：`WorkflowNodeDrawer` 加"从此阶段重跑"接现有 `rerunMutation`。
- **验收**：可在检查故障处直接重跑。
- **测试**：手测 drawer 重跑。

### UI-7 — NewTask 简化 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：`NewTaskPage.tsx` `defaultConfig` ~70 字段;step3 暴露 11 个 backend 选择器 + "Developer Settings"(template ID/`run_from/to_stage`);intent 已推导 template+sources(`getIntentDefaults:1254`)。
- **方案**：收敛为 step1 源/语言、step2 intent(已蕴含一切)、step3 质量 + 单个可选"高级";Developer 藏到 Settings 的 power-user 开关;按质量预设显示预计耗时。
- **验收**：新手不再面对几十个不解的旋钮。
- **测试**：可用性走查。

### UI-8 — persona 声音样本 ｜ TODO ｜ 产品 ｜ L ｜ ◻待确认
- **现状**：`CharacterLibraryPage.tsx` persona 有丰富身份元数据但**无声音字段/样本/试听**;声音分配在 editor 的 VoicePickerModal 另做。
- **方案**：persona 挂参考音样本 + inline `<audio>` 试听,并带入声音分配,实现跨集"该角色固定该声音"(需后端 persona-voice 支持)。
- **验收**：persona 可试听并复用声音。
- **测试**：跨任务复用验证。

### UI-9 — 骨架/空/错误态 + 批量操作 ｜ TODO ｜ 产品 ｜ S–M ｜ ◻待确认
- **现状**：骨架只在 3 文件;多数页裸 spinner;TaskListPage 多选只删除且串行 `for await`(`:63`)无进度。
- **方案**：TaskDetail/DubbingEditor 加骨架;`components/shared/` 统一空/错/载三件套;加批量重跑/导出 + 逐项进度。
- **验收**：慢后端下结构可见;批量有进度。
- **测试**：组件测 + 手测批量。

### UI-10 — drag&drop 上传 ｜ TODO ｜ 产品 ｜ S ｜ ◻待确认
- **现状**：`FileUploadZone.tsx` 是 dashed 投放区视觉但只 click(无 `onDrop/onDragOver`)。
- **方案**：接真 D&D(`onDrop`→`onFileSelected`)+ 拖拽高亮。
- **验收**：可拖文件上传。
- **测试**：手测拖放。

---

## 测试卫生（TEST）

### TEST-1 — atomic 测试非 hermetic，污染真实库 ｜ DONE ｜ D/测试 ｜ S ｜ ✅已核实
> 已修：`test_atomic_tools_job_manager.py`(5处)/`test_atomic_tools_api.py`(3处) 的 `JobManager` 改传隔离 `db_engine`(per-test tmp sqlite，镜像 persistence 测试的 `_engine`)，不再写真实 `CACHE_ROOT` 库。验证：连跑两次都绿、真实库 `/pytest` job 数 8→8 不增。后端 518 passed。
- **现状**：`test_atomic_tools_job_manager.py` / `test_atomic_tools_api.py` 多处 `JobManager(...)` 与 TestClient(app) 走真实全局 `default_engine`（`~/.cache/translip/data.db`），创建的 job 留在 pending 不清理，跨次运行累积（本次盘点时真实库已积 931 条 `/pytest-of-*` 垃圾 job），按运行顺序偶发触发 `_active_job_count` 假阳性导致 "Too many" 假失败。
- **方案**：这些测试改为传入隔离的 `db_engine=`（JobManager 已支持该参数）与隔离 `root`，或加 fixture 用 in-memory engine；避免触碰 `CACHE_ROOT` 真实库。
- **验收**：atomic 测试在脏真实库下也稳定通过；不再写真实库。
- **测试**：连续多次 `uv run pytest tests/test_atomic_tools_*.py` 全绿。

## 附录：本次已核实事实清单

逐条用实际代码确认（`git grep`/读取），可直接动工：

1. `DEFAULT_TRANSLATION_BACKEND="local-m2m100"` + `DEFAULT_CONDENSE_MODE="off"`（`config.py:31,36`）→ 默认无文长控制。【TRA-1】
2. `run_pipeline` 全部 `run_stage_command`（`runner.py:394,403,412,425,470,517,731`）未传 `should_cancel`。【ARCH-8】
3. `artifacts.py:55`、`analysis.py:186` 用 `startswith` 前缀匹配;`job_manager.py:560` 旧式 fallback,`:558` 已正确。【SEC-1】
4. `loudnorm_file`（`audio.py:85`）仅被 `runner.py:22` import,无调用;`mix_profile` 默认 `"preview"`（`types/rendering.py:29`）。【REN-4】
5. dub 导出走 `dub_voice.<lang>.wav`(无床);带床是 `preview_mix`（`delivery/runner.py:42-43,493`）。【REN-7】
6. `output_sample_rate`:`config.py:52`/`pipeline.py:79`=48000 vs `task_manager.py:91`=24000。【ARCH-12】
7. `word_timestamps` 全库 0 命中;默认 ASR backend=`funasr`（`config.py:19`）。【ASR-5】
8. `estimated_target_sec` 被 `dubbing/runner.py:551` 读但无 producer。【TTS-2】
9. PreviewPane `audioTrack` 仅用于字幕/样式(`DubbingEditorPage.tsx:4248,4339`),video src 固定(`:4151`);EditMonitorPane(`:3655`)才真切音频。【UI-1】
