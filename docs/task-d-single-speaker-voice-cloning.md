# 任务 D 技术设计: 目标语言单说话人声音克隆与合成

- 项目: `video-voice-separate`
- 文档状态: Implemented v1
- 创建日期: 2026-04-12
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/speaker-aware-dubbing-task-breakdown.md)
- 前置依赖:
  - [task-b-speaker-registry-and-retrieval.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-b-speaker-registry-and-retrieval.md)
  - [task-c-dubbing-script-generation.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-c-dubbing-script-generation.md)
  - [task-c-test-report.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-c-test-report.md)

## 1. 目标

当前仓库已经完成本设计的首发实现:

- 已接入 `F5-TTS` 开发后端
- 已预留 `OpenVoice V2` backend 抽象
- 已提供 `synthesize-speaker` CLI
- 已提供 Task D report / manifest / demo 音频输出
- 已补充真实测试报告: [task-d-test-report.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-d-test-report.md)

任务 D 的目标不是直接生成整条多说话人配音成品，而是先证明一件事:

- 给定一个 speaker 的参考音频
- 给定这个 speaker 的目标语言文本
- 系统能稳定产出音色接近、内容可懂、可继续进入任务 E 的单 speaker 音频片段

这一步要回答四个问题:

1. 参考音频怎么选，才能让声音克隆尽量稳定
2. 目标语言文本怎么喂给 TTS，才能保留 segment 级映射
3. 生成结果怎么自动评估，尤其能不能通过“声纹”方式对比
4. 当前本地机器上，先用哪条后端路线最稳

## 2. 范围与非目标

### 2.1 任务范围

任务 D 负责:

- 读取任务 B 的 `speaker_profiles.json`
- 读取任务 C 的 `translation.<target_tag>.json`
- 针对单个 `speaker_id` 选择参考音频
- 为该 speaker 的目标语言句段生成单条或多条语音
- 导出逐句音频片段
- 导出单 speaker demo 音频
- 计算基础自动评估指标
- 生成任务 D manifest

### 2.2 非目标

任务 D 当前不负责:

- 多 speaker 拼接
- 回填原始全局时间线
- 与 background 混音
- 自动压缩时长到精确对齐
- 视频 lip-sync
- 多 speaker 对话连贯性优化

## 3. 与任务 B/C 的关系

任务 D 直接消费任务 B 和任务 C 的结构化产物。

任务 B 提供:

- `speaker_id`
- `speaker_profiles.json`
- `reference_clips[].path`
- `reference_clips[].text`
- `reference_clips[].duration`

任务 C 提供:

- `segment_id`
- `speaker_id`
- `target_text`
- `duration_budget`
- `qa_flags`

因此任务 D 的本质不是重新理解内容，而是把:

- `speaker reference`
- `segment target_text`

转换成:

- `segment audio`
- `segment quality report`

## 4. 设计原则

任务 D 的设计必须满足这 7 个原则:

1. **单 speaker 先做通**
   不在这一阶段处理多人拼接
2. **segment 映射不能丢**
   每个输出音频都必须能映射回 `segment_id`
3. **参考音频选择要可解释**
   不能随机拿一段音频做克隆
4. **后端必须可替换**
   当前机器可跑的开发后端和未来生产导向后端要分离
5. **自动评估必须先落地**
   至少要有 speaker similarity、可懂度和时长三类指标
6. **失败段可重跑**
   不能一个段失败就必须整 speaker 全量重跑
7. **先忠实合成，再谈表演控制**
   当前阶段不引入复杂情绪控制和风格重写

## 5. 核心结论

截至 **2026-04-12**，任务 D 的最合理路线不是一开始就押一个“理论最强”的模型，而是拆成两层:

- **开发默认后端**: `F5-TTS`
- **生产导向后端**: `OpenVoice V2`

原因:

- 当前开发机是 `MacBook M4 16GB`
- 任务 D 首要目标是先在本地稳定跑通单 speaker
- `F5-TTS` 官方 README 直接给出了 Apple Silicon 安装路径和 CLI 推理方式
- `F5-TTS` 官方公开的基础多语模型主线目前是 `zh & en`，更多语言依赖社区共享 checkpoint
- 但 `F5-TTS` README 同时明确写了预训练模型权重受 `CC-BY-NC` 约束，不适合作为生产默认
- `OpenVoice V2` 官方 README 明确写了原生支持英语、西班牙语、法语、中文、日语、韩语，且 V1/V2 都是 `MIT` 许可，适合后续商用导向
- 但 `OpenVoice` 官方使用文档把 Linux 作为开发者主路径，当前在本机上直接作为首发实现风险更高

因此:

- **任务 D 首发实现建议先做 `F5-TTS`**
- **从第一天就预留 `OpenVoice V2` backend 抽象**
- **一旦单 speaker 能力成立，再补 `OpenVoice V2`**

这和任务 C 的策略一致:

- 先让当前机器稳定可跑
- 再补更强或更适合生产的后端

这里还要补一个语言范围上的现实约束:

- 如果任务 D 首发只验证 `中文 -> 英文`，`F5-TTS` 更适合作为本机开发默认
- 如果任务 D 首发就要求 `中文 -> 日文` 也稳定可用，那么 `OpenVoice V2` 的优先级会明显上升
- 若继续选择 `F5-TTS` 路线，则日语更适合作为后续通过社区 checkpoint 单独评估的实验分支

基于论文和官方仓库，本轮调研还得到 3 个直接影响实现的结论:

1. **参考音频必须控制在短时、干净、带精确 transcript 的范围内**
   F5-TTS 官方推理文档明确建议 `reference audio <12s`，并在结尾保留约 `1s` 静音；同时它要求提供参考音频的文本内容 `ref_text`，如果不提供就会触发额外 ASR。
2. **任务 D 为了保住 `segment_id`，不能把长段文本直接交给 TTS 自动 chunk**
   F5-TTS 官方推理文档明确写了单次生成当前按总长 `30s` 处理，并会对长文本自动 chunk。这个机制对交互式试听有用，但对我们的任务 D 不利，因为它会破坏稳定的 segment 边界。
3. **可以，而且应该，用“声纹 / speaker embedding”做音色一致性比对，但不能只看这一项**
   F5-TTS 官方评测流程里明确包含 `SIM` 指标，同时也保留 `WER` 和 `UTMOS`。ByteDance 的 `seed-tts-eval` 也把 `speaker similarity (SIM)` 和 `WER` 作为零样本 TTS 的核心客观指标。这意味着任务 D 不应只靠人工试听，也不应只看单一声纹分数，而应同时看音色相似度、内容正确性和时长可用性。

## 6. 后端选型

## 6.1 开发默认后端: `F5-TTS`

建议首发实现:

- `F5-TTS`

理由:

- 官方仓库明确支持 Apple Silicon 的 PyTorch 安装路径
- 支持 CLI 推理
- 推理接口天然适合任务 D 所需的:
  - `ref_audio`
  - `ref_text`
  - `gen_text`
- 我们已经在任务 B 中保存了参考 clip 和对应 transcript，能直接复用
- 我们已经在任务 C 中有 `target_text`，天然适合按 segment 合成

适合任务 D 的地方:

- 可快速验证单 speaker 克隆是否成立
- 支持逐句生成
- 易于构建本地自动化测试
- 对 `zh/en` 首发验证更贴近官方基础模型路径

风险:

- 预训练模型权重不是生产默认可用许可
- 多语种跨语言稳定性需要实测，不应在文档里预设“必然很好”
- 如果首发目标语言包含日语，需额外引入社区 checkpoint 或调整后端

## 6.2 生产导向后端: `OpenVoice V2`

建议作为任务 D 第二后端:

- `OpenVoice V2`

理由:

- 官方 README 明确写了:
  - 更好的音质
  - 原生多语种支持
  - 英语、西班牙语、法语、中文、日语、韩语
  - `MIT` 许可，可商业使用
- 官方 README 同时强调其零样本跨语种声音克隆能力

适合任务 D 的地方:

- 更契合“目标语言单 speaker 克隆”的产品目标
- 商业风险明显低于 `F5-TTS` 预训练权重
- 对 `en/zh/ja` 这种多目标语言路线更自然

风险:

- 官方开发者文档以 Linux 安装路径为主
- 需要额外安装 `MeloTTS`
- 当前本机首发实现不如 `F5-TTS` 稳

## 6.3 当前不建议作为任务 D 首发

当前不建议直接作为任务 D 首发默认:

- `CosyVoice`

原因:

- 当前仓库和本机环境更适合先落轻量、可替换的单 speaker 路线
- `CosyVoice` 生态更重，更适合后续在 Linux/GPU 条件更稳定时单独评估

## 6.4 参考音频怎么选，才能让声音克隆更稳定

这个问题本轮调研后，建议直接定成 **“短时、单 speaker、精确 transcript、可解释排序”** 策略。

### 直接来自官方资料的约束

`F5-TTS` 官方推理文档给了几个非常关键的约束:

- 单次生成目前按总长 `30s` 处理，长参考音频会被裁到约 `12s`
- 官方明确建议 `reference audio <12s`
- 官方明确建议结尾保留约 `1s` 静音
- 官方 CLI 显式要求 `ref_audio + ref_text + gen_text`
- 如果不提供 `ref_text`，会触发额外 ASR

`OpenVoice` 的论文和官方使用文档则说明:

- 它只需要一段 **short audio clip**
- 参考音频可以是 **任意语言**
- 可以把这个音色迁移到多种目标语言

### 任务 D 的工程建议

基于这些来源，我的建议是:

1. 默认只从任务 B 的 `reference_clips` 中选
2. 优先选 **8s - 12s** 的 clip
3. 必须是单 speaker、无重叠说话
4. 必须能拿到对应 transcript，且直接复用任务 B 里保存的 `text`
5. 预处理时给 reference clip 尾部补约 `1s` 静音
6. 避免过强情绪、笑声、喊叫、现场噪声很重的 clip

其中第 6 条是我根据零样本 voice cloning 的常见失败模式做的 **工程推断**，不是上面官方文档的直接原句。

### 参考音频不是越长越好

对任务 D，这里更重要的不是“信息越多越好”，而是“条件越稳定越好”。

原因:

- `F5-TTS` 官方会把过长 reference clip 裁到约 `12s`
- 长音频更容易混入情绪变化、语速漂移、环境噪声和错误 transcript
- 对零样本克隆来说，reference 既是音色条件，也是韵律条件来源之一，脏条件会直接带进生成结果

因此任务 D 的默认立场应该是:

- **宁可选更短但更干净的参考音频，也不要选更长但更杂的参考音频**

### 建议的 reference 选择流程

建议把参考音频选择做成固定 3 步，而不是一次性拍脑袋挑片段:

1. **过滤**
   只保留单 speaker、带 transcript、时长在 `5s - 15s` 之间的候选
2. **打分**
   对候选片段按时长、文本完整度、能量稳定性、噪声风险做排序
3. **定稿**
   选择 `top-1` 作为主 reference，同时保留 `top-2` 作为失败重跑回退

### 建议的 reference 打分规则

任务 D V1 不需要上复杂学习排序，规则打分就够了。

建议得分由 4 项组成:

1. **时长分**
   最优区间 `8s - 12s`
2. **文本分**
   不是极短句，不是只有感叹词，不是大量口头禅
3. **稳定分**
   `rms` 合理，不明显过轻，不明显爆音
4. **风险扣分**
   有笑声、喊叫、明显噪声、强混响、截断词尾时扣分

一个简单可执行的默认策略可以是:

- `duration_score`: `8s - 12s` 最高，`5s - 8s` 和 `12s - 15s` 次之，其余淘汰
- `text_score`: 字数或词数过少则降级
- `rms_score`: 过低降级，过高且疑似削波也降级
- `risk_penalty`: 命中明显风险标签则直接降档

这里的时长上限、静音尾部、`ref_text` 要求直接来自 F5 官方推理说明；其余评分项是我基于项目现状给出的工程策略。

### 为什么不建议让 TTS 后端自己转写 reference

`F5-TTS` 官方已经写了:

- 不提供 `ref_text` 时，会额外做 ASR

对我们这个项目，这不是最优路径，因为:

- 任务 B 已经保存了参考 clip 的 `text`
- 再做一遍 ASR 会增加内存和耗时
- reference_text 一旦漂移，speaker 条件和文本条件会一起变脏

因此任务 D 的结论很明确:

- **reference_text 直接复用任务 B 的结果，不在任务 D 重做 ASR**
- **任务 D 输入给 backend 的 reference，不只是音频文件，还应是 `audio + text + duration + quality metadata` 的完整 reference package**

## 6.5 目标语言文本怎么喂给 TTS，才能保留 segment 级映射

这一点本轮调研后，我的建议也比较明确:

- **V1 一律按 segment 逐条喂给 TTS**
- **不把整段长文本直接交给后端自动 chunk**

### 直接来自官方资料的依据

`F5-TTS` 官方推理文档明确写了:

- 单次生成按总长 `30s` 处理
- 更长文本会自动 chunk
- 标点和空格会影响停顿与 chunk 边界
- 英文句末标点后应保留空格，否则不会被识别成正常断句

### 对任务 D 的直接影响

这意味着如果我们把整 speaker 的长文本一次性送给后端:

- 生成边界会由模型自己的 chunk 逻辑决定
- 输出和原始 `segment_id` 的映射会变弱
- 任务 E 后续很难按原时间线拼回去

因此任务 D 推荐方案是:

1. 先按 `speaker_id` 过滤句段
2. 对每个 `segment_id` 单独发起一次 TTS
3. 每次调用只传该 segment 的 `target_text`
4. 生成完成后，把 wav 与 `segment_id` 一一绑定

### 任务 D 建议的 TTS 输入单元

为了让 segment 级映射后面不丢，我建议任务 D 内部明确引入一个 `tts_segment` 结构，而不是只传裸字符串。

建议至少包含:

- `segment_id`
- `speaker_id`
- `target_lang`
- `target_text`
- `source_duration_sec`
- `duration_budget_sec`
- `qa_flags`

这样做的原因:

- 任务 D 当前只生成单 speaker，但后面任务 E 还要拼回原时间线
- 只传文本会丢掉“这句话本来有多长”“这句话是否高风险”这些后续关键控制信息
- 后续如果引入时长压缩、停顿控制、重跑策略，也不需要推翻当前输入结构

### 文本预处理建议

根据 F5-TTS 官方推理说明，任务 D 在送入 TTS 前至少要做这几步:

1. 统一标点
2. 为英文句末标点补空格
3. 规范数字写法
4. 保留任务 C 已经校正过的 glossary 专名
5. 删除明显不该朗读的控制字符

这里第 2、3 点和 F5 的官方推理说明直接相关；第 4、5 点是结合我们当前任务 C 输出结构做的工程延伸。

### 关于目标语言时长问题

这是任务 D 必须提前面对的问题，不能等到任务 E 再发现。

因为:

- 中文转英文、中文转日文后，句长变化不稳定
- 即使同一句文本，不同 TTS 后端、不同 reference、不同停顿也会产生不同语音时长
- 如果任务 D 不保留 segment 级真实时长，任务 E 就只能盲拼

因此我的建议是:

1. 任务 C 继续负责给出 `duration_budget`
2. 任务 D 必须记录每个 segment 的 `generated_duration_sec`
3. 任务 D 先只做风险标记，不在首发就自动重写译文
4. 真正的自动压时长，放到任务 E 或任务 D v2 再做

换句话说:

- **任务 D 首发要先做到“测出来”，不是马上“修到完美”**

### 是否可以按 context unit 而不是 segment 喂

可以，但我不建议把它作为 V1 默认。

更稳的做法是:

- **正式产物**: 逐 `segment` 合成
- **试听 demo**: 可以按 `context unit` 或若干 segment 拼接额外生成

这属于我的 **工程建议**，不是官方仓库的直接表述。

## 6.6 是否可以通过“声纹”方式对比生成结果

可以，而且我认为这是任务 D 必须要做的。

### 依据

`F5-TTS` 官方评测文档明确给了 3 类客观评估入口:

- `WER`
- `SIM`
- `UTMOS`

其中 `SIM` 就是音色一致性方向的客观评测。

### 任务 D 的实现建议

当前仓库已经有任务 B 用过的:

- `speechbrain-ecapa`

因此任务 D 的 V1 最合理路线是:

1. 用 reference clip 提 speaker embedding
2. 用生成音频提 speaker embedding
3. 算 cosine similarity
4. 按区间打标:
   - `passed`
   - `review`
   - `failed`

### 但不能只看声纹分数

这里需要强调一点:

- **speaker similarity 高，不代表文本一定读对**
- **speaker similarity 高，也不代表时长一定能用**

因此“能不能通过声纹对比”这个问题，答案是:

- **可以**
- **应该做**
- **但只能作为三项联合验收的一项**

更稳的联合判断应该是:

1. `speaker similarity`
2. `ASR back-read / text fidelity`
3. `duration_ratio`

只有三项一起看，才能回答:

- 像不像这个人
- 说得对不对
- 后面拼不拼得回去

### 为什么我建议先复用现有 ECAPA

原因很简单:

- 任务 B 已经在用同一 embedding 空间
- 工程上复用最快
- 对“是不是还是这个人”这个问题已经足够有用

### 后续评测升级路线

如果后面任务 D 进入更严格的评测阶段，我建议把评测拆成两层:

1. **工程验收层**
   先复用 `speechbrain-ecapa`，因为它已经在仓库里落地
2. **论文对齐层**
   再补 `seed-tts-eval` 这一类更接近社区通用口径的评测链路

`seed-tts-eval` 官方 README 明确写了:

- 客观评测采用 `WER` 和 `SIM`
- `SIM` 通过 speaker embedding 的 cosine similarity 计算
- 其公开脚本使用的是 speaker verification 微调后的 `WavLM-large`

所以任务 D 的稳妥路线应当是:

- **V1: 先复用现有 ECAPA，做工程可验收**
- **V2: 再补更对齐零样本 TTS 社区基准的 `WavLM-large SIM`**

### 后续是否要和 F5 官方评测对齐

建议后续增加，但不必阻塞任务 D 首发。

更完整的后续路线是:

1. V1 先复用当前仓库的 `speechbrain-ecapa`
2. V2 再增加与 F5 官方评测更接近的 `SIM` 路径
3. 与 `WER / intelligibility`、`duration ratio` 组合起来做综合判断

这里第 2 步是我的 **工程推断**，不是 F5 文档直接要求我们必须这么做。

## 7. 本地机器策略

目标机器:

- `MacBook M4`
- `16GB` 统一内存

工程策略:

- 任务 D 首发默认使用 `F5-TTS`
- 每次只加载一个大模型
- 与任务 A/B/C 的大模型分阶段运行，不做长驻并存
- 生成时先按 speaker 小批量跑，不全量并发

工程结论:

- 当前机器适合先做 `F5-TTS` 单 speaker 验证
- 不适合在任务 D 首发就同时背负多后端和多人拼接复杂度

## 8. 输入与输出

## 8.1 输入

任务 D 标准输入:

- 任务 B:
  - `speaker_profiles.json`
- 任务 C:
  - `translation.<target_tag>.json`
- 额外参数:
  - `speaker_id`
  - `backend`
  - 可选 `reference_clip_path`
  - 可选 `segment_ids`

## 8.2 输出

建议输出:

1. `speaker_demo.<target_tag>.wav`
2. `segments/<segment_id>.wav`
3. `speaker_segments.<target_tag>.json`
4. `task-d-manifest.json`

## 8.3 输出定义

### `speaker_segments.<target_tag>.json`

这是任务 D 的标准机器输出。

建议结构:

```json
{
  "speaker_id": "spk_0000",
  "backend": {
    "tts_backend": "f5tts",
    "model": "F5TTS_v1_Base",
    "device": "mps",
    "target_lang": "en"
  },
  "reference": {
    "path": ".../clip_0001.wav",
    "text": "我给你三十天的时间",
    "duration": 10.4,
    "selection_reason": "top1 duration/text/rms balanced"
  },
  "segments": [
    {
      "segment_id": "seg-0001",
      "target_text": "Do you know Burj Khalifa?",
      "source_duration_sec": 2.6,
      "generated_duration_sec": 2.1,
      "duration_ratio": 0.808,
      "speaker_similarity": 0.79,
      "intelligibility_status": "review",
      "audio_path": ".../segments/seg-0001.wav"
    }
  ]
}
```

### `task-d-manifest.json`

记录:

- 输入文件
- speaker_id
- 目标语言
- 参考音频来源
- 使用后端
- 句段数量
- 成功/失败数量
- 自动评估分布
- 总耗时

## 9. 参考音频策略

任务 D 成败很大程度上取决于参考音频选得好不好。

当前项目已经在任务 B 中保存了:

- `reference_clips[].path`
- `reference_clips[].text`
- `reference_clips[].duration`
- `reference_clips[].rms`

因此任务 D V1 不需要重新做参考音频挖掘，只需要做 **可解释选择策略**。

建议默认选择规则:

1. 优先选时长在 `8s - 12s` 的 clip
2. 优先选文本长度适中、不是极短句的 clip
3. 优先选 `rms` 合理、不是太轻的 clip
4. 如果多个候选都合格，优先选时长更稳定、文本更完整的 clip
5. 至少保留一个 `fallback reference`

调整建议:

- 如果参考 clip 超过 `12s`，预处理时先裁到合适长度，而不是完全依赖后端自动裁剪

说明:

- `F5-TTS` 需要 `ref_audio + ref_text`
- 任务 B 已经保存了参考 clip 的 `text`
- 因此不需要再为 reference 音频额外做 ASR

## 10. 合成策略

任务 D V1 建议采用:

- **单 speaker**
- **逐 segment 合成**
- **逐 segment 评估**
- **再额外导出一个试听 demo**

这样做的原因:

- 后续任务 E 需要 segment 级拼接
- 如果只导出一条长音频，不利于定位失败句段
- 如果某几个 segment 失败，可以局部重跑

建议流程:

`speaker_profiles.json + translation.<target_tag>.json -> select reference clip -> filter one speaker segments -> synthesize each segment -> measure generated duration -> compute quality metrics -> export`

任务 D 内部建议显式保留这条映射:

`segment_id -> target_text -> generated_wav -> metrics`

补充说明:

- 逐 segment 合成是为了保住 `segment_id`
- 不依赖 TTS 后端自动 chunk 来决定最终边界
- 如果要生成连续试听 demo，应在 segment 级产物生成完之后再额外拼接

## 11. 自动评估策略

任务 D 不能只靠人工试听。

建议至少落 3 类自动评估:

### 11.1 音色相似度

使用当前仓库已经存在的 speaker embedding 能力:

- `speechbrain-ecapa`

做法:

- 用参考 clip 提 embedding
- 用生成音频提 embedding
- 计算 cosine similarity

目的:

- 先判断“像不像这个 speaker”
- 这一步本质上就是你说的“通过声纹方式对比”

### 11.2 可懂度 / 文本忠实度

使用现有 ASR 能力做轻量回读:

- 对生成音频再做一次 ASR
- 与任务 C 的 `target_text` 做归一化比对

V1 不必上严格 WER 基准，但至少要有:

- `passed`
- `review`
- `failed`

三档判断

目的:

- 先判断“说出来的内容是否接近目标文本”

### 11.3 时长偏差

任务 C 已经给了估计时长，任务 D 要补上真实生成时长。

计算:

- `generated_duration_sec / source_duration_sec`

目的:

- 先判断“这段音频是否明显超时”

说明:

- 任务 D 不负责压时长
- 但必须为任务 E 提供真实时长数据

### 11.4 评估结论

任务 D 的 V1 不建议只看一个指标。

最合理的判断方式是三项联合:

1. `speaker similarity`
2. `ASR 回读一致性`
3. `generated_duration / source_duration`

其中:

- 第一项回答“像不像这个人”
- 第二项回答“说的对不对”
- 第三项回答“后续能不能拼回时间线”

### 11.5 建议的自动验收矩阵

任务 D V1 可以先用三档制，不必伪装成特别精细的绝对评分。

建议:

- `passed`
  - speaker similarity 达标
  - ASR 回读无明显偏离
  - duration ratio 在可接受区间
- `review`
  - 三项里有一项接近边界，或 target_text 本身为高风险句
- `failed`
  - 明显不像原 speaker，或文本明显读错，或时长明显超预算

这里的阈值在实现前不必提前写死，因为:

- 不同目标语言的分布会变
- 不同 backend 的分布会变
- 跨语种 speaker verification 的分数本来就可能整体偏移

但文档层面应该先定一个原则:

- **任务 D 的最终判定使用联合规则，不使用单一声纹阈值一票通过**

## 12. 模块设计

建议新增模块:

- `src/video_voice_separate/dubbing/runner.py`
  - 任务 D 主入口
- `src/video_voice_separate/dubbing/backend.py`
  - TTS backend 协议
- `src/video_voice_separate/dubbing/reference.py`
  - 参考 clip 选择
- `src/video_voice_separate/dubbing/f5tts_backend.py`
  - `F5-TTS` 封装
- `src/video_voice_separate/dubbing/openvoice_backend.py`
  - `OpenVoice V2` 封装
- `src/video_voice_separate/dubbing/metrics.py`
  - speaker similarity / intelligibility / duration
- `src/video_voice_separate/dubbing/export.py`
  - JSON / wav / manifest 导出

## 13. CLI 设计

建议首发命令:

```bash
uv run video-voice-separate synthesize-speaker \
  --translation ./output-task-c/voice/translation.en.json \
  --profiles ./output-task-b/voice/speaker_profiles.json \
  --speaker-id spk_0000 \
  --backend f5tts \
  --output-dir ./output-task-d
```

说明:

- 首发只处理单 speaker
- `speaker_id` 必填
- `target_lang` 从 translation 文件中解析

## 14. 实现顺序

建议按下面顺序实现:

1. 先做输入 schema 和单 speaker 过滤
2. 再做参考 clip 选择
3. 先接 `F5-TTS`
4. 再做导出结构
5. 再做自动评估
6. 最后预留 `OpenVoice V2` backend

原因:

- 当前机器上先跑通 `F5-TTS` 才能建立任务 D 基线
- 如果一开始直接做多后端，很容易把问题混在一起

## 15. 测试策略

## 15.1 自动测试

必须覆盖:

- 参考 clip 选择逻辑
- 单 speaker segment 过滤逻辑
- 输出 JSON schema
- duration 统计逻辑
- speaker similarity 计算逻辑
- CLI 参数解析

## 15.2 真实样本测试

直接使用当前仓库已有真实产物:

- 任务 B:
  - `speaker_profiles.json`
- 任务 C:
  - `translation.en.json`

建议先做两轮:

### 第一轮: smoke test

目标:

- 选一个 `speaker_id`
- 只跑 `3 - 5` 条句段

验收点:

- 能成功输出 wav
- 没有全静音
- manifest 和 segment report 结构正确

### 第二轮: 单 speaker 全量测试

目标:

- 选当前测试视频里句段最多的 speaker
- 跑其全部英文句段

验收点:

- 逐句产物齐全
- speaker similarity 没有大面积崩掉
- intelligibility 没有大面积失败
- demo 音频可试听

## 16. 验收标准

任务 D 通过的最低标准:

- 能针对一个 `speaker_id` 成功生成多条目标语言音频
- 每条输出都保留 `segment_id`
- 有可解释的参考音频来源
- 有基础自动评估输出
- 当前测试视频上能产出可试听 demo

如果出现以下情况，则任务 D 不算完成:

- 不能稳定输出 wav
- 多条句段里音色明显随机漂移
- 生成文本大面积听不清或偏离目标文本
- 输出没有真实时长数据
- 后续任务 E 无法消费其产物

## 17. 风险

当前任务 D 的主要风险:

1. 任务 A 的 ASR 错字会污染 reference_text
2. 任务 C 的 target_text 若过长，会直接拉高 TTS 超时风险
3. `F5-TTS` 预训练权重的许可不能直接作为生产默认
4. `OpenVoice V2` 在当前本机环境上的工程稳定性需要实测
5. 跨语种 speaker verification 的分数分布可能和同语种场景不同，阈值需要真实样本校准

## 18. 结论

任务 D 最重要的不是一开始就做成“完整配音”，而是先把这四件事做稳:

1. 单 speaker 能稳定选到合适 reference
2. 单 speaker 能逐句生成目标语言音频
3. 生成结果有基础自动评估
4. 输出结构能直接交给任务 E

因此，任务 D 的推荐首发方案是:

- **单 speaker**
- **逐 segment 合成**
- **`F5-TTS` 作为开发默认后端**
- **`OpenVoice V2` 作为生产导向后端预留**
- **自动评估先落地**

这条路线最适合当前仓库状态，也最适合你现在这台机器。

## 19. 当前讨论后建议先拍板的事项

为了后面写代码不返工，我建议先把下面 4 件事确认掉:

1. **任务 D 首发 backend**
   我的建议仍然是 `F5-TTS` 先落开发实现，`OpenVoice V2` 先保留接口
2. **任务 D 首发目标语言范围**
   如果先做 `中文 -> 英文`，我建议继续 `F5-TTS`；如果要求首发同时覆盖 `日语`，就要重新评估 `OpenVoice V2` 的优先级
3. **reference 选择策略**
   我的建议是固定成 `top-1 + fallback top-2`，而不是每次手工指定
4. **segment 级合成边界**
   我的建议是正式产物严格逐 `segment`，试听 demo 另行拼接
5. **自动验收口径**
   我的建议是 `speaker similarity + ASR back-read + duration ratio` 联合判定，不把声纹单独当最终裁决

## 20. 参考资料

- F5-TTS 官方仓库: [SWivid/F5-TTS](https://github.com/SWivid/F5-TTS)
- F5-TTS 论文: [arXiv:2410.06885](https://arxiv.org/abs/2410.06885)
- OpenVoice 官方仓库: [myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice)
- OpenVoice 使用文档: [docs/USAGE.md](https://github.com/myshell-ai/OpenVoice/blob/main/docs/USAGE.md)
- OpenVoice 论文: [arXiv:2312.01479](https://arxiv.org/abs/2312.01479)
- SpeechBrain ECAPA-TDNN 模型卡: [speechbrain/spkrec-ecapa-voxceleb](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
- seed-tts-eval 官方仓库: [BytedanceSpeech/seed-tts-eval](https://github.com/BytedanceSpeech/seed-tts-eval)
- CosyVoice 官方仓库: [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice)
