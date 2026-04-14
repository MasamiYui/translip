# 任务 C 技术设计: 面向配音的多语种翻译脚本生成

- 项目: `translip`
- 文档状态: Implemented v1
- 创建日期: 2026-04-12
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/speaker-aware-dubbing-task-breakdown.md)
- 对应测试报告: [task-c-test-report.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-c-test-report.md)
- 前置依赖:
  - [task-a-speaker-attributed-transcription.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-a-speaker-attributed-transcription.md)
  - [task-b-speaker-registry-and-retrieval.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-b-speaker-registry-and-retrieval.md)

## 1. 目标

任务 C 的目标不是“把源语言逐字翻成某一种固定目标语言”，而是生成 **可用于后续多语种配音** 的翻译脚本。

这一步要回答四个问题:

1. 每条源语言句段对应的目标语言文案是什么
2. 目标语言文案是否保持忠实翻译，而不是自由改写
3. 同一 speaker 的上下文是否被保留下来
4. 翻译成其他语种以后，是否能预先暴露潜在的时长风险，方便后续 TTS 和时间线回填

## 2. 范围与非目标

### 2.1 任务范围

任务 C 负责:

- 读取任务 A 的 `segments.zh.json`
- 读取任务 B 的 `speaker_profiles.json`
- 为每条句段生成目标语言译文
- 保留段级映射关系
- 导出可编辑翻译脚本 JSON
- 导出可供检查的目标语言 SRT
- 生成时长预算与超长风险标记
- 生成基础 QA 标记，提示哪些句段需要人工复核

### 2.2 非目标

任务 C 当前不负责:

- 目标语言音频生成
- 说话人音色克隆
- 时间拉伸或混音
- 自动 lip-sync
- 高级术语库协同编辑界面
- 自由发挥式脚本改写

## 3. 与任务 A/B 的关系

任务 C 的输入建立在任务 A/B 已完成的前提上:

- 任务 A 提供:
  - `segment_id`
  - `start`
  - `end`
  - `speaker_label`
  - `text`
- 任务 B 提供:
  - `speaker_id`
  - `speaker_profiles.json`
  - speaker registry 的匹配结果

因此任务 C 的核心不是重新处理音频，而是做一层 **文本与编辑层**:

- 从 `source_text` 变成 `target_text`
- 从“机器翻译结果”变成“可配音、可校验、可继续进入后续 TTS”的翻译稿

## 4. 设计原则

任务 C 的设计必须满足这 7 个原则:

1. **段级映射不能丢**
   后续 TTS 和时间线回填都依赖 `segment_id`
2. **上下文要被利用**
   不能把每条句段当成完全孤立句子
3. **翻译要忠实，不做自由发挥**
   任务 C 先以翻译为主，不引入创作型改写
4. **脚本要可编辑**
   人工改稿必须是正常路径，不是例外路径
5. **术语要可控**
   地名、品牌名、数字表达不能完全交给黑箱模型
6. **时长风险要前置暴露**
   任务 C 就要为后续配音输出长度预算，不把问题全部留给任务 D/E
7. **实现先稳后强**
   V1 先把稳定输出、可编辑性和时长标记做稳，再考虑更强模型

## 5. 核心结论

截至 **2026-04-12**，任务 C 的 V1 不建议做成“先整段改写，再反向拆回句段”的方案，也不建议在这一阶段做自由发挥式脚本润色。

原因:

- 反拆句段会破坏 `segment_id -> target_text` 的稳定映射
- 一旦映射不稳定，任务 D 的逐句 TTS、任务 E 的时间线回填都会变得很难调试

因此，任务 C 的 V1 采用:

- **段级翻译为主**
- **speaker-turn 分组作为上下文辅助**
- **时长预算与风险标记同步导出**
- **可编辑脚本单独导出**

也就是:

`segments.zh.json + speaker_profiles.json -> context-aware segment translation -> duration-aware QA -> translation.<target>.json + translation.<target>.editable.json`

## 6. 技术选型

## 6.1 V1 首发后端策略

任务 C V1 首发支持两类后端:

- 本地后端: `facebook/m2m100_418M`
- 第三方 API 后端: `SiliconFlow Chat Completions`

原因:

- `M2M100` 是开源本地模型，支持多语言翻译，且 `MIT` 许可更适合后续商用演进
- `SiliconFlow` 可以接入 `GLM`、`DeepSeek` 等大模型，方便补齐更强的复杂句段翻译能力
- 两条后端共用同一套任务 C 数据结构，便于对照测试、回退和未来扩展

说明:

- 本地默认后端改为 `M2M100`
- `NLLB` 不再作为首发默认，只保留在设计讨论层，不进入本轮实现
- 当前真实测试素材仍然以中文源音频为主，因此首发实现优先验证 `zh -> en`
- 数据结构从第一天就按多语种设计，不把输出写死在英文

## 6.2 本地后端: `M2M100`

任务 C 本地实现默认使用:

- `facebook/m2m100_418M`

理由:

- 模型体量相对可控，适合本地开发机
- 多语种能力成熟，覆盖英语、日语、中文等常见目标语种
- `Transformers` 接入简单，适合稳定工程化封装
- 适合句段级批处理，不需要额外服务

输入输出约束:

- 输入: `source_lang`、`target_lang`、句段列表、可选 glossary 预处理文本
- 输出: 每个 `segment_id` 对应一条稳定 `target_text`

工程限制:

- 不直接处理音频，只处理文本
- 不负责自由改写
- 不保证在每个语种上都达到商业级文案质量，因此需要保留人工编辑出口

## 6.3 API 后端: `SiliconFlow`

任务 C 同时支持第三方 API 翻译后端，首发选择:

- `SiliconFlow`

首发策略:

- 通过 OpenAI 兼容的 `chat/completions` 接口访问
- 默认只做“忠实翻译任务”，不用它做创作型润色
- 默认 prompt 必须强约束:
  - 忠实翻译
  - 不补充信息
  - 保留专名
  - 返回 JSON

建议首发支持的模型配置:

- `deepseek-ai/DeepSeek-V3`
- `THUDM/GLM-4.5`

说明:

- 具体可用模型名以 SiliconFlow 当前账号可访问的模型列表为准
- 代码实现要允许用户自行覆盖 `--api-model`
- API 后端主要用于质量对照、复杂句段回退和后续生产可选路径

## 6.4 密钥与配置

第三方 API 密钥 **不能写入仓库**，只能通过环境变量读取。

建议环境变量:

- `SILICONFLOW_API_KEY`
- `SILICONFLOW_BASE_URL`
- `SILICONFLOW_MODEL`

建议默认值:

- `SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1`
- `SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3`

代码要求:

- manifest 不回写明文密钥
- 日志不打印 `Authorization` 头
- 测试默认走 mock，不依赖真实密钥

## 6.5 本地机器配置目标

任务 C 首发实现要以以下机器为可运行目标:

- `MacBook M4`
- `16GB` 统一内存

实现要求:

- `M2M100` 在 `mps` 或 `cpu` 上都能跑
- 模型按需加载，不与任务 A/B/D 的大模型长期共存
- 默认小批量推理，避免在 16GB 机器上不必要的峰值内存占用
- 遇到 `mps` 不支持算子时允许回退 CPU

工程结论:

- `M4 16GB` 足够完成任务 C 首发开发和测试
- 不把更重的多模态大模型纳入任务 C 首发范围
## 6.6 为什么不把 V1 直接做成 LLM 改写器

原因:

- LLM 改写波动大，不利于可重复测试
- 很难保证段级映射稳定
- 术语、数字和专名在长文本中更容易漂移
- 如果没有非常严格的约束，很容易生成“读起来顺，但不方便回填”的结果
- 当前阶段更重要的是忠实翻译和时长风险评估，不是文案润色

结论:

- V1 先用 `M2M100` 做本地主翻译
- V1 可选 `SiliconFlow` 做 API 翻译
- V1 只保留 **保守规则化规范层**
- V1 不做自由改写
- 之后如果确实需要本地化文案润色，再新增独立可选 backend，而不是混进任务 C 首发实现

## 6.7 预留升级路线

任务 C 的实现从第一天就要预留 backend 抽象，后续可切换或并列支持:

- 其他本地 MT backend
- 其他多语种 MT backend
- 独立的后置本地化改写 backend

但这些都不进入任务 C 的首发实现。

## 7. 输入与输出

## 7.1 输入

任务 C 标准输入:

- 任务 A:
  - `segments.zh.json`
- 任务 B:
  - `speaker_profiles.json`
- 可选:
  - `speaker_matches.json`
  - `glossary.json`
  - `style_guide.json`

## 7.2 输出

建议输出 4 类产物:

1. `translation.<target_tag>.json`
2. `translation.<target_tag>.editable.json`
3. `translation.<target_tag>.srt`
4. `task-c-manifest.json`

其中 `target_tag` 例如:

- `en`
- `ja`
- `zh-Hans`

## 7.3 输出定义

### `translation.<target_tag>.json`

这是任务 C 的 **标准机器可消费输出**。

它必须保留每个 `segment_id` 的一一映射。

建议结构:

```json
{
  "job_id": "voice",
  "backend": {
    "translation_backend": "nllb-200-distilled-600M",
    "source_lang": "zho_Hans",
    "target_lang": "eng_Latn"
  },
  "segments": [
    {
      "segment_id": "seg-0001",
      "speaker_label": "SPEAKER_00",
      "speaker_id": "spk_0000",
      "start": 18.32,
      "end": 20.72,
      "duration": 2.4,
      "source_text": "奶奶 你知道哈里巴塔吗",
      "target_text": "Grandma, do you know the Burj Khalifa?",
      "context_unit_id": "unit-0001",
      "duration_budget": {
        "source_duration_sec": 2.4,
        "target_lang": "eng_Latn",
        "estimated_tts_duration_sec": 2.9,
        "duration_ratio": 1.21,
        "fit_level": "review"
      },
      "qa_flags": ["duration_may_overrun"]
    }
  ]
}
```

### `translation.<target_tag>.editable.json`

这是任务 C 的 **人工编辑友好输出**。

它与 `translation.<target_tag>.json` 不同的地方在于:

- 保留 speaker-turn 分组
- 保留上下文块
- 给人工修订留字段
- 保留时长预算和风险标签

建议结构:

```json
{
  "units": [
    {
      "unit_id": "unit-0001",
      "speaker_label": "SPEAKER_00",
      "speaker_id": "spk_0000",
      "start": 18.32,
      "end": 25.66,
      "segment_ids": ["seg-0001", "seg-0002", "seg-0003", "seg-0004"],
      "source_text": "奶奶 你知道哈里巴塔吗 哈里巴塔 是不是那个电影",
      "draft_text": "Grandma, do you know the Burj Khalifa? The Burj Khalifa? Is that from the movie?",
      "edited_text": null,
      "duration_summary": {
        "source_duration_sec": 7.34,
        "estimated_tts_duration_sec": 8.62,
        "fit_level": "review"
      },
      "status": "draft",
      "notes": []
    }
  ]
}
```

### `translation.<target_tag>.srt`

用于快速检查译文节奏和内容，不作为权威数据源。

### `task-c-manifest.json`

记录:

- 输入路径
- 后端配置
- 目标语言
- segment 数量
- glossary 应用数量
- duration 风险分布
- QA flag 分布
- 运行耗时

## 8. 核心设计

任务 C 的核心链路是:

`segments.zh.json -> speaker-aware context units -> term protection -> segment translation -> duration estimation -> QA flags -> export`

## 8.1 为什么“段级翻译 + 分组上下文”比“整段翻译”更适合当前项目

原因:

- 任务 D 需要逐句生成目标语言 TTS
- 任务 E 需要逐句对齐时间线
- 任务 B 的 speaker 信息也是句段级绑定的

所以:

- **段级翻译** 保证工程稳定性
- **分组上下文** 提升译文自然度
- **时长估计** 提前暴露后续配音风险

## 8.2 Context Unit 构造

翻译时不能只看当前句段，但也不能直接把整页文本当成一个大段。

建议构造 `context unit`:

- 按 `speaker_label` / `speaker_id` 优先分组
- 合并相邻且 gap 很小的句段
- 控制单个 unit 的总时长和总字数

初始规则建议:

- 相邻 gap `<= 0.8s`
- 同 speaker 才允许合并
- 单 unit 时长上限 `<= 12s`
- 单 unit 句段数上限 `<= 6`

说明:

- `unit` 主要用来提供上下文，不是替代 `segment`

## 8.3 术语保护与规则层

翻译层不能完全裸跑。

任务 C V1 需要先做一个轻量规则层:

- 地名词典
- 人名别名
- 品牌名
- 数字表达规则
- 不翻译术语名单

例如:

- `迪拜` -> `Dubai`
- `哈里法塔` / `哈里巴塔` -> `Burj Khalifa`
- `171万平方米` -> `1.71 million square meters`

这一步非常重要，因为当前任务 A 的中文转写中已经存在:

- 口语化
- ASR 错写
- 专名不稳定

如果不先加规则层，后面的目标语言翻译稿会明显漂。

## 8.4 翻译策略

V1 翻译过程建议分两层:

### 第一层: 原始翻译

- 本地后端用 `M2M100` 做 `source_lang -> target_lang`
- API 后端用 `SiliconFlow` 大模型执行“受约束的 JSON 翻译”
- 输入以当前句段为主
- 同时附带前后 speaker-context 作为辅助信息

### 第二层: 保守规范化

不用大模型重写整段，只做保守规范化:

- 统一标点
- 统一数字与量词表达
- 统一 glossary 命中的专名写法
- 清理明显重复的 ASR 噪声片段
- 不改变核心语义，不补写额外信息

初始规则建议:

- 专名统一到 glossary 指定写法
- 数字表达统一到目标语言规则
- 标点和空白统一
- 可疑重复 token 标成 QA，而不是擅自大改

说明:

- 这一步只做“规范化”，不是自由生成

## 8.5 API Prompt 与返回约束

为了让第三方大模型后端保持可测试、可追踪，任务 C 的 API 翻译必须使用固定约束。

请求原则:

- 每次请求只处理一个小批次句段
- 每个句段都附带 `segment_id`
- 明确给出 `source_lang` 与 `target_lang`
- 明确要求返回 JSON 数组

返回要求:

- 每条结果必须包含 `segment_id`
- 每条结果必须包含 `target_text`
- 不允许遗漏句段
- 不允许新增未请求字段影响解析

失败回退:

- JSON 解析失败时重试
- 多次失败时本批次标记失败
- 可选回退到本地 `M2M100`

## 8.6 时长预算与语言差异

翻译成不同语种后，句长和朗读时长会明显变化，这个问题不能留到任务 D 才处理。

任务 C V1 必须为每个 `segment` 和 `context unit` 输出基础时长预算。

V1 的做法不是直接合成 TTS，而是做 **语言相关的时长估计**:

- 英文优先用词数和标点停顿估计
- 日文优先用字符数和句读点估计
- 中文优先用汉字数和标点停顿估计
- 其他语种先走通用字符长度回退策略

V1 建议输出 4 类判断字段:

- `source_duration_sec`
- `estimated_tts_duration_sec`
- `duration_ratio`
- `fit_level`

其中 `fit_level` 初始建议分为:

- `fit`
- `review`
- `risky`

初始判断规则建议:

- `duration_ratio <= 1.10` -> `fit`
- `1.10 < duration_ratio <= 1.30` -> `review`
- `duration_ratio > 1.30` -> `risky`

说明:

- 不同目标语言的阈值后面可以单独调参
- 任务 C 先做风险暴露，不在这一阶段自动压缩译文

## 8.7 段级映射回填

任务 C 的关键是每个 `segment_id` 都必须有稳定的 `target_text`。

因此:

- 译文写回时以 `segment` 为主键
- `unit` 只作为上下文和编辑辅助

这样做的结果是:

- 后续任务 D 可以直接按 `segment_id` 做 TTS
- 后续任务 E 可以直接按 `segment_id` 做时间贴合

## 8.8 QA Flags

任务 C 需要主动标记“值得人工复核”的句段。

建议初始 QA flags:

- `mixed_language`
- `too_short_source`
- `duration_may_overrun`
- `duration_risky`
- `contains_number`
- `contains_protected_term`
- `low_confidence_term_resolution`
- `source_maybe_asr_error`

说明:

- 任务 C 当前没有 ASR token 级置信度，因此 `source_maybe_asr_error` 只能先用规则近似判断

## 9. 模块设计

建议新增模块:

- `src/translip/translation/runner.py`
  - 任务 C 主入口
- `src/translip/translation/backend.py`
  - 翻译后端协议
- `src/translip/translation/units.py`
  - context unit 构造
- `src/translip/translation/glossary.py`
  - 术语与保护规则
- `src/translip/translation/m2m100_backend.py`
  - `M2M100` 翻译封装
- `src/translip/translation/siliconflow_backend.py`
  - SiliconFlow API 翻译封装
- `src/translip/translation/duration.py`
  - 目标语言时长估计与风险评级
- `src/translip/translation/qa.py`
  - QA flag 生成
- `src/translip/translation/export.py`
  - JSON / SRT / manifest 导出

## 10. CLI 设计

建议首发只做一个主命令:

```bash
uv run translip translate-script \
  --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --target-lang eng_Latn \
  --backend local-m2m100 \
  --output-dir ./output-task-c \
  --glossary ./config/glossary.json
```

API 模式示例:

```bash
SILICONFLOW_API_KEY=... uv run translip translate-script \
  --segments ./output-task-a/voice/segments.zh.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --target-lang eng_Latn \
  --backend siliconflow \
  --api-model deepseek-ai/DeepSeek-V3 \
  --output-dir ./output-task-c-api
```

首发命令职责:

1. 读取任务 A/B 输出
2. 构造 context units
3. 生成 `translation.<target_tag>.json`
4. 生成 `translation.<target_tag>.editable.json`
5. 生成 `translation.<target_tag>.srt`
6. 输出 `task-c-manifest.json`

## 11. 任务 C 的实现顺序

建议按下面顺序实现:

1. 先做数据读取和 schema
2. 再做 context unit 构造
3. 再做 glossary / 术语保护
4. 再接 `M2M100`
5. 再做目标语言时长估计
6. 再接 `SiliconFlow` API backend
7. 最后做 QA flags 和导出

原因:

- 任务 C 成败首先取决于映射、翻译控制和时长标记
- 如果数据结构不稳，后面换翻译模型也没用

## 12. 测试策略

## 12.1 自动测试

必须覆盖:

- `segment_id` 映射不丢失
- context unit 分组逻辑
- glossary 替换优先级
- 多目标语言输出命名
- `M2M100` 请求参数与结果映射
- SiliconFlow API 响应解析与重试
- 时长估计规则
- QA flag 逻辑
- `translation.<target_tag>.json` / `translation.<target_tag>.editable.json` schema

## 12.2 真实素材测试

任务 C 真实测试建议直接用当前仓库已经完成的任务 A/B 产物:

- [segments.zh.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/output-task-a/voice/segments.zh.json)
- [speaker_profiles.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/output-task-b/voice/speaker_profiles.json)

测试方式分两轮:

### 第一轮: 全量跑通

目标:

- 完整视频全量生成目标语言翻译脚本

验收点:

- 所有 `segment_id` 都有 `target_text`
- 没有空译文
- speaker 映射没有丢
- 每条句段都有 `duration_budget`

### 第二轮: 人工抽查

从完整视频中抽查至少 30 条句段，重点检查:

- 地名、专名、数字
- 同 speaker 连续句段语气是否一致
- 译文是否忠实，不存在自由发挥
- 高风险时长标记是否合理

## 12.3 当前测试视频上的重点风险

基于当前任务 A 的真实结果，可以预见这些风险:

- `哈里法塔` 存在 ASR 变体，如 `哈里巴塔`
- 一些中文句段本身口语化很强
- 少量末尾片段已经出现英文混入

因此任务 C 的测试必须重点关注:

- 混合语言句段处理
- 专名纠正
- 中文数字转目标语言表达
- `zh -> ja` 等目标语言下的长度膨胀或压缩风险
- 本地 `M2M100` 与 API `SiliconFlow` 输出的一致性差异

## 12.3 首发测试矩阵

任务 C 首发至少要覆盖下面 4 组测试:

1. `M2M100 + zh -> en`
2. `M2M100 + zh -> ja`
3. `SiliconFlow + zh -> en`
4. `Task A -> Task B -> Task C` 真实样本串行验证

## 13. 验收标准

任务 C 通过的最低标准:

- 每个 `segment_id` 都有目标语言 `target_text`
- `segment` 顺序、speaker 信息、时间戳全部保留
- glossary 生效
- 翻译脚本整体可人工编辑
- 每个 `segment` 都有时长预算
- 对当前测试视频，没有大面积明显错误专名

如果出现以下情况，则任务 C 不算完成:

- 丢失 `segment_id`
- 译文为空或顺序错乱
- 同一专名多处翻法混乱
- 把翻译结果改写成明显偏离原文的自由发挥稿
- 长度风险没有被标出，导致后续配音难以预判
- 修改单条目标语言文案后无法继续供后续任务使用

## 14. 风险与升级路线

## 14.1 当前风险

- 任务 A 的 ASR 错字会直接污染任务 C
- 任务 B 的 `speaker_id` 不稳定时，会影响 speaker continuity 视图
- 不同目标语言的时长估计策略不能完全共用
- 单纯 MT backend 在部分语种下会偏书面，但当前阶段先不引入自由改写
- 第三方 API 模型更新后，输出风格可能波动
- API 限流、超时和 JSON 不稳定返回需要工程兜底

## 14.2 升级路线

任务 C 后续可按下面路线增强:

1. `M2M100` -> 更强本地 MT backend
2. 增加专名纠错词典
3. 增加按目标语言细分的时长估计器
4. 引入可选本地化润色 backend
5. 增加“同一 speaker 风格一致性”提示层

## 15. 结论

任务 C 的关键不是“上一个最强翻译模型”，而是先把下面四件事做稳:

1. 段级映射稳定
2. glossary 和专名控制稳定
3. 多语种目标语言配置稳定
4. 时长风险可前置暴露

因此，任务 C 的 V1 推荐方案是:

- **多语种段级翻译**
- **speaker-aware context units**
- **M2M100 本地翻译**
- **SiliconFlow API 可选翻译**
- **保守规范化，不做自由改写**
- **时长预算与风险标记**
- **可编辑 JSON 导出**

这条路线最适合当前仓库的工程状态，也最利于后续任务 D/E 落地。

## 16. 参考资料

- M2M100 模型页: [facebook/m2m100_418M](https://huggingface.co/facebook/m2m100_418M)
- SiliconFlow 官方文档首页: [docs.siliconflow.cn](https://docs.siliconflow.cn/)
- Hugging Face Apple Silicon: [Transformers Apple Silicon](https://huggingface.co/docs/transformers/perf_train_special)
- PyTorch MPS: [MPS backend](https://docs.pytorch.org/docs/stable/notes/mps)
