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
| TTS-1 | 长度/语速目标传 MOSS/VoxCPM + task-e 前 micro-fit | S–M |
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
| SPK-1 | task-b 存 gender/F0 → 同性别参考 + 双峰拆簇 | M–L |
| REN-1 | task-e 两遍/全局时间轴拟合 | M–L |
| REN-3 | 切尾级联 + 上游"需更短译文"反馈 | M |
| QA-1 | `perceptual_score`（切尾惩罚 + 最终混音 ASR 往返） | M |
| QA-2 | autofix 升级阶梯（换参考/换 backend） | M |

### 第 3 波 — 结构 / 新功能
| ID | 标题 | 工作量 |
|---|---|---|
| ARCH-1 | DAG 并行调度（独立分支并发） | M |
| ARCH-2 | task-d 多说话人批处理/并行 | M |
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
- **验收**：`asr-dub+ocr-subs` 模板 OCR 与 stage1→task-a 并发；端到端产物与串行一致；墙钟下降。
- **测试**：`tests/test_orchestration.py` 加并发调度单测（mock 子进程）；真实 `+ocr-subs` 跑批对比墙钟。

### ARCH-2 — task-d 多说话人批处理/并行 ｜ TODO ｜ C/性能 ｜ M ｜ ◻待确认
- **现状**：`runner.py:460` 逐说话人一个 `synthesize-speaker` 子进程＝N 人 N 次模型冷加载；`dubbing_workers` 只并行单说话人内的段。task-d 权重 0.35（`stages.py:23`）最长。
- **方案**：优先做"多说话人批模式"（一进程跑全部选定说话人，摊销模型加载）；或退而求其次用 VRAM 限制的进程池跑若干说话人。注意保持子进程隔离带来的 ML 模型清理/崩溃隔离优势的权衡。
- **验收**：多说话人任务 task-d 墙钟显著下降，产物逐段一致。
- **测试**：`tests/` 加批模式单测；真实多说话人跑批计时。

### ARCH-3 — 流水线并发队列 + admission control ｜ TODO ｜ 健壮性 ｜ M ｜ ◻待确认
- **现状**：`task_manager.create_task` 无并发上限地起守护线程；atomic-tools 却有 `max_concurrent_jobs=2`（`job_manager.py:114`），两套策略相反。多任务同提会争抢单 GPU。
- **方案**：共享 bounded executor/队列（参照 atomic-tools 的 `_active_job_count` 闸），并发默认 1（单 GPU）；新增"queued"任务状态。
- **验收**：连提多任务时按并发上限排队执行，不 OOM。
- **测试**：单测队列闸；手动连提验证。

### ARCH-4 — 缓存键补上游产物指纹 ｜ TODO ｜ D/正确性 ｜ S ｜ ◻待确认
- **现状**：`_stage_cache_payload`（`runner.py:120`）对 task-b/c/e、subtitle-erase 有上游指纹，但 **task-a 键不含 stage1 `voice.*` 指纹**，task-d 键不含 task-c/task-b 指纹（只有标量）。上游文件变了但参数 hash 不变 → false hit on stale。
- **方案**：用已存在的 `_file_fingerprint` 给 task-a（←stage1 voice）、task-d（←translation+profiles+voice_bank）补指纹。
- **验收**：替换上游产物后对应阶段必重算。
- **测试**：`tests/` 缓存命中/失效单测覆盖新指纹。

### ARCH-5 — 缓存键混入 code/model 版本 ｜ TODO ｜ D/正确性 ｜ S ｜ ◻待确认
- **现状**：`compute_cache_key`（`cache.py:19`）只 hash 参数；换模型 checkpoint 或修阶段 bug 后旧 manifest 仍命中。
- **方案**：每个 payload 混入粗粒度 `cache_epoch` 常量（行为变更时手动 bump），可选含所选 backend 的模型权重 mtime/sha。
- **验收**：bump epoch 后强制全量重算。
- **测试**：单测 epoch 改变导致 miss。

### ARCH-6 — 阶段内续跑（per-speaker 缓存）｜ TODO ｜ 健壮性/性能 ｜ M ｜ ◻待确认
- **现状**：缓存粒度是整节点；task-d 跑到 5/6 崩了全部重来。
- **方案**：task-d 按说话人缓存（`speaker_segments.<lang>.json` 已是离散产物，`commands.py:128`），跳过已有非空 report 的说话人。与 ARCH-2 配套。
- **验收**：崩溃重跑只补未完成说话人。
- **测试**：单测 per-speaker 跳过逻辑。

### ARCH-7 — 输出 GC / 容量管理 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：`output-pipeline/<task_id>/` 仅显式删除时清（`tasks.py:191`），无 TTL/容量上限；`cache_manager.py` 能算明细但未对流水线输出做驱逐。
- **方案**：对 `output-pipeline` 加 LRU/容量上限 GC（尊重 DB 仍引用的任务），接入现有缓存 UI。
- **验收**：超限时按 LRU 清理未被引用产物。
- **测试**：单测 GC 选择逻辑。

### ARCH-8 — Stop 真正传递到子进程 ｜ TODO ｜ D/健壮性 ｜ S–M ｜ ✅已核实
- **现状**：`subprocess_runner.run_stage_command` 完整支持 `should_cancel`（看门狗 + SIGTERM→SIGKILL，`subprocess_runner.py:111`），但 `run_pipeline` 的全部 7 处调用（`runner.py:394,403,412,425,470,517,731`）**都没传**；`task_manager.stop_task` 只改 DB 状态，子进程跑到底再覆盖。路由文案声称"发送终止信号"——实际没有。
- **方案**：从 `task_manager` 传 `threading.Event` 进 `run_pipeline(..., should_cancel=event.is_set)`，转发给每个 `run_stage_command`；用 `{task_id: event}` 映射（照搬 `job_manager._cancel_events` 模式，`job_manager.py:413`）。
- **验收**：点 Stop 后正在运行的子进程在秒级内被杀，状态置为 cancelled/failed。
- **测试**：单测取消传播；手动起长任务点停验证进程退出。

### ARCH-9 — 启动时回收悬空流水线任务 ｜ TODO ｜ D/健壮性 ｜ S ｜ ◻待确认
- **现状**：`job_manager.mark_interrupted_jobs()` 在 `app.py:59` 回收孤儿原子任务，但**无流水线 Task 版**；server 崩溃后 Task 永远卡 `running`/`pending`。
- **方案**：加 `mark_interrupted_tasks()`，启动时把 `pipeline-status.json` 非 running 或缺失的 `running`/`pending` Task 置 `interrupted`/`failed`。
- **验收**：重启后无幽灵 running 任务。
- **测试**：单测回收逻辑。

### ARCH-10 — 进度双轮询 + SSE 假 timeout ｜ TODO ｜ 性能/产品 ｜ S–M ｜ ◻待确认
- **现状**：每任务 `_sync_status_to_db` 3s（`task_manager.py:315`）+ `stream_progress` 独立 1.5s（`:445`）重读同一 JSON；`monitor._write()` 每 tick 全量重写 JSON；SSE `max_wait=300`（`:440`）让 >5 分钟任务报假 timeout。
- **方案**：SSE 改读已同步的 DB 行（消除重复 reader）；去掉/心跳化 300s 上限；长期把 `PipelineMonitor` 改进程内 pub/sub。
- **验收**：长任务不再断流；磁盘读减少。
- **测试**：手动长任务观察 SSE 不 timeout。

### ARCH-11 — DB 迁移版本化 ｜ TODO ｜ 健壮性 ｜ M ｜ ◻待确认
- **现状**：`database.py:36` 手写 `ALTER ADD COLUMN` 列表，加列幂等但无版本、无降级、不支持改名/改类型/回填，部分失败不可检测。
- **方案**：上 Alembic 或 `schema_version` 表 + 有序迁移函数；至少包裹迁移使部分失败可检测并记录已应用版本。
- **验收**：迁移可重放、可检测失败。
- **测试**：迁移单测（空库→当前）。

### ARCH-12 — 统一默认值单一来源（24k/48k 等）｜ DONE ｜ D/正确性 ｜ S ｜ ✅已核实
> 已修：4 处 `output_sample_rate` 24000→48000（`routes/config.py` 与 `task_manager.py` 用 `DEFAULT_RENDER_OUTPUT_SAMPLE_RATE` 常量，前端 NewTaskPage/SettingsPage 改 48000）；4 处 `separation_mode` "auto"→"dialogue"（对齐 dataclass/CLAUDE.md，UI 任务由自动路由改为强制 dialogue 分离）。加回归测试断言三处后端默认源一致；顺手把 `test_config_defaults_*` 改为 hermetic（原先读开发机 `~/.translip/config.json` 致环境性失败）。后端 505 passed。
- **现状**：同一默认值分散且冲突：`output_sample_rate` 在 `config.py:52`/`pipeline.py:79`=48000，但 `task_manager.py:91`=`cfg.get(..., 24000)` → **UI 建的任务以 24kHz 配音**（可听音质降级）；`separation_mode` 在 `pipeline.py:92`="dialogue" vs `task_manager.py`/`config.py`="auto"。
- **方案**：`_build_pipeline_request` 改为 `cfg.get(k, <config.py 常量>)`；`PipelineRequest` 字段默认引用同一常量。
- **验收**：CLI 与 server 构造的 request 默认值一致；新建任务输出 48kHz。
- **测试**：单测两条构造路径默认值一致。

### ARCH-13 — env 配置提升到 UI + 有效配置内省 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：~30 个 env 变量，UI 只能改 HF/LLM/TMDB key；TTS CLI/模型目录、OCR/erase 模型目录、device 只能 export 后重启。
- **方案**：把运营关键路径提升进现有 settings store（`cache_manager` 用户设置已能桥接 env）；加"有效配置"内省端点（每个 knob 的值 + 来源 env/default/setting）。
- **验收**：UI 可配置 TTS/OCR/erase 路径与 device，无需改 env 重启。
- **测试**：前后端单测 + 手动改配置生效。

### ARCH-14 — `PipelineRequest.normalized()` 用 `dataclasses.replace` ｜ TODO ｜ D/架构 ｜ S ｜ ◻待确认
- **现状**：`types/pipeline.py:139` 手写 90 行逐字段重列；新字段忘了在此 + `_build_pipeline_request` 加就会被静默丢。
- **方案**：`normalized()` 改 `dataclasses.replace(self, **overrides)`（近零风险）；长期拆嵌套 sub-config。
- **验收**：新增字段不再需要改 `normalized()`。
- **测试**：单测 normalize 保留所有字段。

### ARCH-15 — 前后端契约生成/校验 ｜ TODO ｜ 架构/产品 ｜ M ｜ ◻待确认
- **现状**：前端 `api/` 手工镜像后端 Pydantic；`node_name`/`stage_name` 双键（`monitor.py:126`）显示已有改名中途。
- **方案**：从 FastAPI OpenAPI 生成 TS 客户端（openapi-typescript/orval）纳入 `npm run build`，或 CI diff 校验；统一双键为单一 canonical key。
- **验收**：契约漂移在 CI 被捕获。
- **测试**：CI 校验脚本。

### ARCH-16 — 列表分页下推 SQL ｜ TODO ｜ 性能 ｜ S–M ｜ ◻待确认
- **现状**：`tasks.py:152` 全表加载后 Python 切片，且逐任务查 `TaskStage`（N+1）；`job_manager.list_jobs`、`works.py:751` 同样 all-then-slice。
- **方案**：`LIMIT/OFFSET`+`COUNT` 下推 SQL；stages 用单条 `IN(...)` 或 join 批量加载。
- **验收**：列表查询不随表增长线性变慢。
- **测试**：单测分页 SQL；造数据计时。

### SEC-1 — 路径穿越改 `is_relative_to` ｜ TODO ｜ D/安全 ｜ S ｜ ✅已核实
- **现状**：`artifacts.py:55`、`analysis.py:186` 用 `str(full_path).startswith(str(output_root))`——`../task-1-evil/secret` 可通过（已验证）；`job_manager.py:560` 旧式 fallback 同病（`:558` 已是正确的 `is_relative_to`）。
- **方案**：三处统一改 `full_path.resolve().is_relative_to(output_root)`（`dubbing_editor.py` 已是正确写法可参照）。
- **验收**：`..` 逃逸被拒。
- **测试**：单测穿越路径返回 403。

### SEC-2 — 鉴权 + 127.0.0.1 + 收窄 CORS ｜ TODO ｜ 安全 ｜ S–M ｜ ◻待确认
- **现状**：`app.py:47` `allow_origins=["*"]`+`allow_credentials=True`（自相矛盾）；全路由无鉴权，含写 API key（`system.py:463`）、读任意产物、删任务。
- **方案**：默认 127.0.0.1 绑定（`run_server` 已是默认，明确/强制）；可选共享 token 中间件（env 开关）；CORS 收窄到 `http://127.0.0.1:5173` 并去 `allow_credentials`（除非需要）。
- **验收**：跨域被拒；开启 token 后未授权 401。
- **测试**：单测 CORS/鉴权中间件。

### SEC-3 — argv 输入轻量校验 ｜ TODO ｜ 安全 ｜ S ｜ ◻待确认
- **现状**：argv 列表传参（shell=False）**不可注入**，但 `speaker_id`/`api_base_url`/`target_lang` 等无校验流入 argv。
- **方案**：加 charset/enum 校验（白名单字符、枚举值）。
- **验收**：非法值被拒于构造前。
- **测试**：单测非法输入。

---

## stage1 — 分离（SEP）

### SEP-1 — 内部 task-a 供给改无损 ｜ TODO ｜ B/算法 ｜ S ｜ ◻待确认
- **现状**：`stage1_output_format="mp3"`（`types/pipeline.py`），有损 stem 直喂 ASR + ECAPA（`commands.py:168`、`transcription/runner.py:106,123`），丢掉 ECAPA 依赖的高频音色。
- **方案**：内部供给改 FLAC/WAV（用户可见产物可保留 mp3）。
- **验收**：task-a 读到无损 stem；与 ASR-1 配合评估 diarization 改善。
- **测试**：跑批对比 cross-speaker 相似度分布。

### SEP-2 — 分离质量/SNR 度量 ｜ TODO ｜ A/算法 ｜ M ｜ ◻待确认
- **现状**：分离只写 timing/route，无任何输出质量度量（grep `snr|si-sdr|leakage` 0 命中）。
- **方案**：算 voice/bg RMS 比、残差 `‖mix−(voice+bg)‖`、VAD 覆盖率 → `separation_confidence` 写入 stage1 manifest，低置信告警 / 触发 SEP/质量升级。
- **验收**：manifest 含置信度；低质能被发现。
- **测试**：单测度量计算；坏样本验证告警。

### SEP-3 — `enhance_voice` 死代码处理 ｜ TODO ｜ D ｜ S/M ｜ ◻待确认
- **现状**：`NoOpVoiceEnhancer` 字节拷贝（`models/clearervoice.py:8`），仅 `separate` CLI 接线、流水线未用，但 CLAUDE.md 列其为真 backend。
- **方案**：要么实现真 denoise/dereverb（ClearerVoice/DeepFilterNet）放 ASR/diarization 前，要么删死代码 + 文档。
- **验收**：不再有"假能力"。
- **测试**：若实现则加质量 A/B。

---

## task-a — 转写 + 说话人分离（ASR）

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

### ASR-3 — 聚类阈值/`expected_speakers` 可调入缓存 ｜ TODO ｜ 算法/产品 ｜ M ｜ ◻待确认
- **现状**：`DEFAULT_SAME_SPEAKER_SIMILARITY=0.62`/`SINGLE_SPEAKER_FLOOR=0.52` 是模块常量（`speaker.py:21`），无 `min/max/expected_speakers`，不在 Request/CLI/task-a 缓存键。
- **方案**：暴露 `same_speaker_similarity`/`expected_speakers`/`min/max` 到 Request+CLI+缓存；已知 k 用 `n_clusters=k`；考虑 silhouette/eigengap 自适应切点。
- **验收**：用户能指定说话人数；改阈值触发重算。
- **测试**：单测 k 指定路径；缓存键含新参数。

### ASR-4 — 单说话人闸自适应 ｜ TODO ｜ 算法/产品 ｜ S ｜ ◻待确认
- **现状**：p20 相似度 ≥0.52 即全员压成一人（`speaker.py:156`）；降质音频全对 ~0.81 时极易误触发=最致命错误。
- **方案**：floor 改相对 spread（p20–p80 间隙）；`expected_speakers>1` 时跳过该捷径；触发时记日志。
- **验收**：多说话人场景不被误压成一人。
- **测试**：构造高相似度多说话人样本验证不塌缩。

### ASR-5 — 词级时间戳 + Paraformer 默认 ｜ TODO ｜ B/算法 ｜ M ｜ ✅已核实
- **现状**：`word_timestamps` 全代码库 0 命中；默认 ASR backend=`funasr`（`config.py:19`），SenseVoice **按字数比例伪造句内时间**（`funasr_backend.py:165`）；这些 start/end 正是 task-e 时间轴拟合的依据。
- **方案**：faster-whisper 开 `word_timestamps=True` 并把段边界吸附到词边、收紧首尾静音；默认切到产真实时间的 Paraformer（`sentence_info`）；或加轻量强制对齐替代比例估计。
- **验收**：时间戳精度提升，配音同步改善。
- **测试**：对齐误差度量；端到端听感同步。

### ASR-6 — ASR 幻觉/置信度处理 ｜ TODO ｜ A/算法 ｜ S–M ｜ ◻待确认
- **现状**：faster-whisper 只传 language/vad/beam/best_of/temperature（`asr.py:124`），无 `no_speech/compression_ratio/log_prob` 阈值与 temperature 回退；只丢空文本；不记 `avg_logprob`/`no_speech_prob`。
- **方案**：传上述阈值 + temperature 回退列表；把置信字段存进 `segments.zh.json` 与 manifest → 自动丢幻觉 + UI 标低置信 + 喂 OCR 仲裁。
- **验收**：静音/音乐段幻觉显著减少。
- **测试**：含残留噪声样本验证幻觉段被丢/标记。

### ASR-7 — glossary → ASR 偏置 ｜ TODO ｜ A/算法/产品 ｜ S–M ｜ ◻待确认
- **现状**：`glossary_path` 仅 task-c 用；SeACo Paraformer 是 contextual 模型却没传 `hotword`（`funasr_backend.py:360`）。
- **方案**：把人名/术语作 faster-whisper `initial_prompt/hotwords`、SeACo `hotword=` 传入 task-a。
- **验收**：专名识别率提升。
- **测试**：含专名样本对比识别正确率。

### ASR-8 — `vad_max_segment_sec` 接线 ｜ TODO ｜ 算法 ｜ S ｜ ◻待确认
- **现状**：`AsrOptions.vad_max_segment_sec` 两 backend 都支持，但 `PipelineRequest` 无此字段、CLI 无此 flag、不在缓存键 → 固定 30s（对 TTS 拟合/diarization 都太长）。
- **方案**：加进 `PipelineRequest`+CLI+`build_task_a_command`+缓存键；配音默认降到 12–15s；长独白按词间停顿切（接 ASR-5）。
- **验收**：长段被合理切分。
- **测试**：长独白样本验证切分。

### ASR-9 — `diarization_report` 输出 ｜ TODO ｜ A/产品 ｜ S ｜ ◻待确认
- **现状**：task-a 输出无相似度矩阵/阈值/强制贴标数/ASR 置信度；`speaker_review/diagnostics.py` 有计算但是事后独立工具。
- **方案**：task-a 时即产 `diarization_report`（相似度矩阵、簇内凝聚、采用阈值、强制贴标/低 margin 段数、+ASR-6 置信度），让 `speaker_review` 诊断默认在 task-a 输出上跑。
- **验收**：用户能在 task-a 后看到 diarization 证据。
- **测试**：单测报告生成。

---

## task-b — 说话人库（SPK）

### SPK-1 — 存 gender/F0 → 同性别参考 + 双峰拆簇 ｜ TODO ｜ A/算法/产品 ｜ M–L ｜ ◻待确认
- **现状**：gender/F0 基础设施（`quality/audio_signature.py`）只接事后诊断（`characters/ledger.py:180`）；task-b profile/registry **不存** gender/F0；`_prototype_from_embeddings`（`profile.py:15`）只 cos≥0.6 过滤 → M+F 混簇作单一原型存活；参考选择无性别意识。
- **方案**：(1) task-b 计算 per-clip F0 + 性别估计存 profile/clip；(2) 簇内 F0 双峰则拆簇（治合并的 M+F）；(3) 参考选择按主性别下调/排除异性别 clip（**严格上游选择，非 R4 回退的 pitch-centrality**）。
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

## task-c — 翻译（TRA）

### TRA-1 — 时长预算注入翻译 + 默认重译/condense ｜ TODO ｜ A/产品/算法 ｜ S–M ｜ ✅已核实
- **现状**：deepseek prompt 仅软指令"简洁"（`deepseek_backend.py:88`），预算翻译**后**才算；默认 backend `local-m2m100`（`supports_condensation=False`）+ `DEFAULT_CONDENSE_MODE="off"`（`config.py:31,36`）= **默认完全不控文长**。overflow/切尾的根因。
- **方案**：(1) 用 `duration.py:estimate_tts_duration` 系数算 `max_chars=source_dur×chars_per_sec` 注入 prompt；(2) `fit_level=="risky"` 默认重译 1 次再降级 condense；(3) LLM 系默认 `condense_mode="smart"`。
- **验收**：默认配置下 overflow/severe/切尾段数下降。
- **测试**：在 `output-pipeline/voxcpm-dubai-*` 上跑 task-c→task-e，对比 `qa_summary.timeline`（overflow/`cut_audio_sec`）。

### TRA-2 — glossary 自动抽取 + 去硬编码哪吒 ｜ TODO ｜ 产品/算法 ｜ M ｜ ◻待确认
- **现状**：`BUILTIN_DUBBING_GLOSSARY` 硬编码《哪吒》专名（`glossary.py:20`），`dubbing_script.py` 硬编码整行译文；batch 独立 → 同名多译。
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

### TRA-5 — 数字/单位本地化 + TTS 停顿标点 ｜ TODO ｜ 产品 ｜ S–M ｜ ◻待确认
- **现状**：无数字/单位本地化（QA 只 flag `contains_number`）；TTS 停顿只 `_punctuate_for_tts` 给英文补末尾句号（`dubbing_script.py:94`）。
- **方案**：加目标侧数字/日期/单位规范化（拼写 vs 数字按语言）；长句插逗号/停顿改善 TTS 韵律。
- **验收**：数字/日期发音正确；长句韵律改善。
- **测试**：含数字/长句样本听感。

---

## task-d — TTS（TTS）

### TTS-1 — 长度/语速目标传 MOSS/VoxCPM + micro-fit ｜ TODO ｜ A/产品/算法 ｜ S–M ｜ ◻待确认
- **现状**：`SynthSegmentInput.duration_budget_sec` 只有 Qwen 消费（单边 `max_new_tokens`）；MOSS 固定 `max_new_frames=375`（`moss_tts_nano_backend.py:291`）；VoxCPM 无时长信号；拟合全推给 task-e atempo。
- **方案**：MOSS frames 按预算缩放；task-d 选最佳 take 时若 `duration_ratio>1.3` 选更短候选或在 task-e 前触发改写；可支持的 backend 暴露 speed/rate 作锦标赛候选轴。
- **验收**：进 task-e 前 duration_ratio 收敛，atempo 拉伸减少。
- **测试**：真实合成对比 duration_ratio 分布。

### TTS-2 — 修复死键 `estimated_target_sec` ｜ TODO ｜ D/算法 ｜ S ｜ ✅已核实
- **现状**：`dubbing/runner.py:551,575` 先读 `duration_budget["estimated_target_sec"]` 再 fallback，但全树**无 producer**（只 `estimated_tts_duration_sec`），故 Qwen 长度上限/预算永远用粗估。
- **方案**：要么删死键查找；要么真产出——用该说话人自身参考/历史 take 的实测语速（task-d report 已收 `generated_duration_sec`、`voice_bank` 聚合 `avg_duration_ratio`）校准 `estimated_target_sec`。
- **验收**：Qwen 长度上限匹配实际语速。
- **测试**：单测校准；真实合成验证。

---

## task-e — 渲染（REN）

### REN-1 — 两遍/全局时间轴拟合 ｜ TODO ｜ C/算法 ｜ M–L ｜ ◻待确认
- **现状**：`_assign_available_durations`（`runner.py:550`）只给本地预算（本段 slot 或到下一句的间隙），`_apply_fit_strategy` 逐段独立拟合，`_placement_start_for_item` 永远锚定 `anchor_start`——只往后溢出、不借前停顿、不移锚。
- **方案**：按 speech island（被真静音隔开的最大连续段）做全局：最小化 `Σ wᵢ|log tempoᵢ|` s.t. 不重叠，placement 起点可在 `[prev_end, anchor_start]` 自由；至少先做两遍贪心（后向=现状，前向借前间隙 + 容差内微调锚点）。
- **验收**：chipmunk 与切尾段数下降。
- **测试**：用 `/tmp/dub_lab` 式重跑 task-e 出 scorecard（overflow/trim/ratio）对比。

### REN-2 — 视频变速选项 ｜ TODO ｜ 算法/产品 ｜ L ｜ ◻待确认
- **现状**：所有 fit 策略只 `compress_audio`，视频从不动（`utils/ffmpeg.py:220`）。
- **方案**：对 `overflow_unfitted` 段 opt-in `setpts` 慢 ≤8–10%（先限非脸/远景）；或全局 ±X% 节目速率 knob。
- **验收**：最差溢出段改为视频微慢而非音频狂压。
- **测试**：样本对比听感/观感。

### REN-3 — 切尾级联 + 上游反馈 ｜ TODO ｜ C/产品/算法 ｜ M ｜ ◻待确认
- **现状**：`overflow_unfitted` 压到 `max_compress_ratio` 仍超则 `_trim_audio_inplace`（`runner.py:1103`）切尾，QA 仅报 `cut_audio_sec`，render 时最终定案，无上游回路。
- **方案**：(a) 切尾改级联：前向借用(REN-1)→视频微慢(REN-2)→才切，且切在词边界；(b) 切尾/触顶时写 `needs_shorter_translation`（秒→目标字数）回 task-c/repair。
- **验收**：切尾总秒数下降；触发上游重译。
- **测试**：端到端验证切尾减少 + 信号产生。

### REN-4 — 最终混音无条件 R128 + 接线 `loudnorm_file` ｜ TODO ｜ D/产品 ｜ S ｜ ✅已核实
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

### REN-7 — dub 导出缺背景乐床 ｜ TODO ｜ D/产品 ｜ S ｜ ✅已核实
- **现状**：`export_dub` 走 `_resolve_dub_audio_path`→`dub_voice.<lang>.wav`（裸求和人声、仅 peak 限幅、**无 bg/ducking/R128**，`delivery/runner.py:493`）；带床的只有 `preview_mix`。
- **方案**：先定义"dub"语义——若是交付物应为全混 + 响度归一（dub+床）；若有意是 voice-only stem 则改名并把带床混音设为默认交付。
- **验收**：选 dub 导出得到符合定义的音频（很可能应带床）。
- **测试**：导出后听是否有 BGM。
- **备注**：⚠ 需你做产品判断"dub 应否带床"。

---

## task-g — 交付（DEL）

### DEL-1 — 软字幕 + 多音轨 + CRF/语言元数据 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：`_export_video_variant`（`delivery/runner.py:372`）只烧录字幕（`ass=` filter）；强制 `libx264 crf=18`；单音轨（`-map 1:a:0`）无语言 metadata；AAC 192k。
- **方案**：加软字幕模式（mp4 `mov_text`/mkv copy，免重编码）；`-metadata:s:a:0 language=`+disposition；mkv 多音轨(dub+原声)；CRF/preset 暴露并按分辨率缩放；AAC 256k 或 Opus。
- **验收**：可选软字幕（不重编码）、多音轨、带语言标签。
- **测试**：导出后用 ffprobe 验证轨道/字幕流/元数据。

### DEL-2 — 重活移出请求线程 ｜ TODO ｜ 健壮性/产品 ｜ M ｜ ◻待确认
- **现状**：`delivery.py:133 compose_delivery` 在 FastAPI handler 内同步跑 `export_video`（整段 ffmpeg 编码阻塞 worker）；analysis/dubbing_editor 同样同步跑合成/probe。
- **方案**：走后台任务机制（或至少 `asyncio.to_thread`），返回 job 句柄给 UI 轮询，与 atomic-tools/流水线一致。
- **验收**：长编码不阻塞、不超时。
- **测试**：手动大文件导出验证服务不卡。

---

## repair（REP）

### REP-1 — LLM 长度目标重译替换硬编码 ｜ TODO ｜ A/算法/产品 ｜ M ｜ ◻待确认
- **现状**：`repair/rewrite.py:139` 是《迪拜/哪吒》中→英硬编码字典；通用 `_shorten_english`（`:273`）仅 ~8 个缩写正则；换视频即近 no-op。
- **方案**：改用现有 deepseek 做带硬字符/时长预算（`estimate_tts_duration`）的多变体重译，glossary 保护，保留规则法作离线 fallback；tournament（`executor._attempt_specs`）已能吃多文本候选。
- **验收**：任意视频的 overflow/pacing 修复能产出真正更短译文。
- **测试**：非迪拜样本验证重译变短且达标。

### REP-2 — 修复 vs 原段改进闸 ｜ TODO ｜ 算法 ｜ S ｜ ◻待确认
- **现状**：`_select_attempt`（`executor.py:532`）只在绝对阈值内选最高分，**不与修复前比较**；可能"修"得比原来差仍被接受。
- **方案**：选择门改为"超过原段分数(或失败维度) margin 才替换"，否则保留原段。
- **验收**：修复不引入回退。
- **测试**：单测改进闸。

### REP-3 — ECAPA 一致性闸 ｜ TODO ｜ 算法 ｜ M ｜ ◻待确认
- **现状**：声线一致性用 3 桶 pitch class（`executor.py:617`，同性别不同人蒙混）；`dub_embeddings` 算了 per-段 ECAPA cos 但权威 `speaker_similarity` 是 task-d 对参考的值，最终混音从不重嵌入。
- **方案**：用 `dub_embeddings` 的 ECAPA cos 对说话人 centroid 做一致性闸（pitch class 留作廉价预筛）；加整片说话人相似度检查。
- **验收**：音色不一致被捕获。
- **测试**：换音色样本验证被拒。

---

## quality / 评测（QA）

### QA-1 — `perceptual_score`（切尾 + ASR 往返）｜ TODO ｜ A/产品/算法 ｜ M ｜ ◻待确认
- **现状**：`_score`（`dub_benchmark.py:215`）全是流水线状态计数/比例，无任何客观音频指标（grep PESQ/STOI/DNSMOS 0 命中），`cut_audio_sec` 不进式；故 90.3 分却丢 62.5s 切尾。
- **方案**：保留 `_score`（历史可比）；另建 `perceptual_score`：(a) 切尾/severe_overflow 惩罚；(b) 对**最终混音**做 ASR 往返(再转写 dub/preview diff 目标文本)捕捉 ducking/叠加/变速损失；(c) 可选 DNSMOS/UTMOS。
- **验收**：切尾严重的产物 perceptual_score 明显低于 `_score`。
- **测试**：在 `voxcpm-dubai-rerun-*`（已知 62.5s 切尾）上验证新分诚实反映。

### QA-2 — autofix 升级阶梯 ｜ TODO ｜ 算法/产品 ｜ M ｜ ◻待确认
- **现状**：`_choose_backends`（`autofix.py:241`）循环前算一次全程复用；每段最多试一次就退役；remediation 推荐的 escalation backend 被忽略。
- **方案**：rounds 做阶梯：R1 重合成(多 attempts)→R2 换参考 + LLM 改写(REP-1)→R3 换 backend(尊重 directive escalation list)；仍失败段可换策略再试；保留 accept-if-better 单调闸。
- **验收**：每次自动修复实际修好的段更多。
- **测试**：`tests/test_autofix_loop.py` 扩展阶梯；monkeypatch e2e。

---

## 字幕子系统 — OCR / Erase / 字幕输出（SUB）

### SUB-1 — 翻译字幕 CPS/折行/可读性引擎 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：`write_ocr_translation_bundle`（`subtitles/export.py:24`）逐 cue 原样输出译文；`srt_to_ass`（`burn.py:120`）仅 `\n→\\N`；`SubtitleStyle`（`types/common.py:82`）无 CPS/每行字数/最大行；dub 的 `max_chars` 预算到不了字幕。
- **方案**：烧录前对译文 SRT 做可读性 pass：CPS 上限(拉丁17/CJK9)、≤2 行平衡折行、违反最短时长/最小间隔则延长/合并；`SubtitleStyle` 加 `max_cps/max_chars_per_line/max_lines`。
- **验收**：长译文不再单行溢出。
- **测试**：长英译样本烧录目检 + 单测折行/CPS。

### SUB-2 — OCR cue 时间吸附真实帧 ｜ TODO ｜ 算法 ｜ M ｜ ◻待确认
- **现状**：单帧 cue `end=start+min_duration`（`subtitle_merger.py:458`）；多帧 `end=最后匹配采样帧`，不向缺失帧外延；默认 `ocr_sample_interval=0.25` → ±0.25s 量化且尾部系统性偏短。
- **方案**：merge 后在边界 ±sample_interval 做几帧二分/线性搜索（用 `should_run_ocr` textness 或快速重 OCR）吸附真实出现/消失帧。
- **验收**：cue 时间误差下降；erase 不再漏擦尾部、字幕不早消。
- **测试**：已知边界样本对比吸附前后误差。

### SUB-3 — cue 几何存 union ｜ TODO ｜ 算法 ｜ S ｜ ◻待确认
- **现状**：`_compute_stable_geometry`（`merger.py:557`）存中位框（低估长行）；erase 侧才 union 补偿（`planning._event_box:104` 注释自认）。
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

### SUB-6 — opencc + OCR 文本纠错 ｜ TODO ｜ 算法/清理 ｜ S–M ｜ ◻待确认
- **现状**：`_COMMON_VARIANT_TRANSLATION` 手写 ~290 条繁简表（`merger.py:16`，含 `亂` 重复键/`了→了` 空操作）；无通用混淆纠错/词典。
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

### ATOM-1 — adapter 自动发现 ｜ TODO ｜ 架构 ｜ S ｜ ◻待确认
- **现状**：adapter 靠 import 副作用 `register_tool`，`adapters/__init__.py:46` 手写列举 10 个；漏一行静默丢工具。
- **方案**：启动时 `pkgutil.iter_modules` 遍历 `adapters` 包自动 import；装饰器契约不变。
- **验收**：新增 adapter 文件即被发现，无需改 `__init__`。
- **测试**：单测自动发现注册全部工具。

### ATOM-2 — 真队列 + 重启 re-enqueue ｜ TODO ｜ 产品/健壮性 ｜ M ｜ ◻待确认
- **现状**：`create_job` 满载直接 429（`job_manager.py:114`），非队列；重启丢未启动任务（停 `pending` 仅标 interrupted）。
- **方案**：bounded `asyncio.Queue`+worker，提交入队不 429；启动时 re-enqueue `pending`。
- **验收**：超载排队而非报错；重启续跑。
- **测试**：单测队列 + 重启恢复。

### ATOM-3 — cancel 契约统一 ｜ TODO ｜ 架构 ｜ S ｜ ◻待确认
- **现状**：subtitle adapter 接 `should_cancel`（`subtitle_erase.py:156`），但同一 erase/ocr bridge 在流水线路径不可取消（同 ARCH-8 根因）。
- **方案**：统一单一 cancel 契约（随 ARCH-8 一起做）。
- **验收**：两条路径都可取消。
- **测试**：随 ARCH-8 验证。

### ATOM-4 — list_jobs SQL 分页 ｜ TODO ｜ 性能 ｜ S–M ｜ ◻待确认
- **现状**：`job_manager.py:276` 全行加载→Python 过滤→逐行 `list_artifacts`（N+1）。
- **方案**：SQL prefix 过滤 + 分页 + 分组算 artifact 数。
- **验收**：作业列表不随增长变慢。
- **测试**：造数据计时。

---

## 前端 / UI（UI）

> 已强（保留）：DubbingEditor 逐段闭环（LiveFitPredictor/ClipFitMeter/候选锦标赛/回译/撤销重做/快捷键）、Evaluation 闭环（before/after + 回滚 + A/B 原声配音）、统一 Dashboard、原子工具链式跳转、persona 绑定导出。

### UI-1 — 修 Preview 音频 A/B ｜ TODO ｜ D/产品 ｜ M ｜ ✅已核实
- **现状**：`PreviewPane`（`DubbingEditorPage.tsx`）的 `audioTrack`（`:4141` 的 original|dub）只用于选字幕文本(`:4248`)与按钮样式(`:4339`)，video src 固定(`:4151`)；`EditMonitorPane`（`:3655`）才有正确 3 路真音频切换。
- **方案**：在 PreviewPane 复用 EditMonitorPane 的外部音频同步（original→视频静音、dub→视频音、mix→preview_mix），加"正在对比：原声/配音"标注。
- **验收**：Preview 能真正切原声/配音。
- **测试**：手动播放验证音频切换。

### UI-2 — 移动端导航 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：`MainLayout.tsx:80` Sidebar+TopNav 都 `hidden md:block`，`md` 以下无任何导航；Header 无汉堡。
- **方案**：Header 加 `md:hidden` 汉堡开 off-canvas Sidebar，或小屏底部 tab bar(主 4–5 路由)。
- **验收**：手机可在页面间导航。
- **测试**：移动视口手测。

### UI-3 — i18n 补全核心页 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：TaskDetailPage(~144 行中文硬编码:重跑/停止/交付/清单/三步流程)、SpeakerReviewDrawer(~106 行,无英文路径)、SettingsPage(~114 行,节点高级参数)绕过 i18n；编译期 key parity(`messages.ts:1626`)是好的,问题是字面量没走 `useI18n()`。
- **方案**：迁移 TaskDetail/SpeakerReviewDrawer/Settings 字面量进 `messages.ts`(优先前两者,在交付/说话人关键流程);加 lint 挡 `.tsx` 内 CJK 字面量。
- **验收**：英文 locale 下核心页全英文。
- **测试**：切 en-US 目检 + lint。

### UI-4 — 完成通知 + 全局 toast ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
- **现状**：无 `document.title`/Notification/favicon badge；只有 `CacheSection.tsx:68` 一个局部 toast，其余 mutation 内联 banner 或静默。
- **方案**：app 级 toast provider 接所有 mutation；任务转 succeeded/failed 时 Notification + `document.title`；header "N running" 徽标。
- **验收**：长任务完成有可感知通知。
- **测试**：起任务切走 tab 验证通知。

### UI-5 — 阶段日志在 UI 可见 ｜ TODO ｜ 产品 ｜ M ｜ ◻待确认
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
