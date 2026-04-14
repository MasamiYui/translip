# 任务 D 技术设计: 单模型 Qwen3-TTS 声音克隆与目标语言合成

- 项目: `translip`
- 文档状态: Draft v2
- 创建日期: 2026-04-14
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/speaker-aware-dubbing-task-breakdown.md)
- 前置依赖:
  - [task-b-speaker-registry-and-retrieval.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-b-speaker-registry-and-retrieval.md)
  - [task-c-dubbing-script-generation.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-c-dubbing-script-generation.md)
  - [task-e-timeline-fitting-and-mixing.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-e-timeline-fitting-and-mixing.md)

## 1. 文档目的

这份文档定义 `Task D` 的下一版实现方向:

- 不再同时推进多个 TTS / VC 后端
- 不再把工程复杂度建立在“多模型并行比较”上
- 先只选一个主模型，把单 speaker 英文配音链路做稳

当前结论:

- `Task D v2` 只选 `Qwen3-TTS-12Hz-0.6B-Base`
- 首发只做 `中文 -> 英文`
- 继续保留任务 B / C / E 的现有数据结构
- 但 `Task D` 的核心合成后端从当前 `F5-TTS` 迁移到 `Qwen3-TTS`

这是一份**替代设计文档**。

当前仓库里的 `Task D v1` 已经用 `F5-TTS` 跑通过工程链路，但全量测试表明它在当前场景下的主要短板是:

- 时长失配多
- 英文句段失败率高
- 最终可进入 `Task E` 的句段比例偏低

因此，`Task D v2` 的目标不是再叠更多后端，而是先换一个更适合当前任务形态的单模型方案。

## 2. 单模型决策

### 2.1 最终选型

`Task D v2` 主模型:

- `Qwen3-TTS-12Hz-0.6B-Base`

### 2.2 为什么只选这一个

当前项目的真实约束是:

- 开发机是 `MacBook M4 16GB`
- 任务链路已经有 `Task A/B/C/E`
- `Task D` 需要严格保留 `segment_id -> audio` 映射
- 当前最痛的问题是英文配音的**时长可用性**，不是纯粹的音色克隆演示

基于这些约束，我建议先只选 `Qwen3-TTS-12Hz-0.6B-Base`，原因是:

1. 官方直接支持基于 `ref_audio + ref_text` 的 voice clone，这与我们当前的 `speaker profile + reference clip + target_text` 结构天然匹配。
2. 官方模型覆盖 `中文 / 英文 / 日语` 等多语种，但 `Task D v2` 首发只用英文，范围可控。
3. `0.6B` 体量更适合作为本地首发方案，不会像更大的服务端模型那样一开始就把开发链路拖重。
4. 项目目标是“先完成稳定配音”，不是“先做模型对比平台”。

### 2.3 为什么不继续把 F5-TTS 当主方案

`Task D v1` 的全量测试结果已经说明:

- `Task D` 评估总计 `171` 条句段
- `passed = 5`
- `review = 31`
- `failed = 135`

其中最大问题不是 speaker similarity，而是 duration:

- `duration failed = 121`
- `speaker failed = 14`
- `intelligibility failed = 48`

也就是说，当前主问题是:

- 句子说得太长
- 进入 `Task E` 时大量句段被过滤

所以继续围绕 `F5-TTS` 叠更多参数和更多旁路，不是当前最优解。

### 2.4 为什么这一步不选 OpenVoice V2

`OpenVoice V2` 很强，但它更适合作为:

- 未来的音色增强层
- 或 future voice conversion 层

而不是现在唯一的主 TTS 引擎。

当前阶段先把一个完整的 `text -> english speech -> quality gate -> task-e` 路线做稳，更重要。

## 3. 任务目标

`Task D v2` 的目标是:

- 输入某个 `speaker_id`
- 读取任务 B 给出的参考音频与 transcript
- 读取任务 C 给出的英文句段
- 逐句生成英文配音
- 对每句做自动质量评估
- 输出可直接进入 `Task E` 的句段音频和报告

这一步仍然不是最终成品配音。

它只证明一件事:

- 对某个说话人，系统能否稳定地产出**可以继续进入时间线回填**的英文句段音频

## 4. 范围与非目标

### 4.1 范围

`Task D v2` 负责:

- 单 speaker 的参考音频选择
- 参考音频文本对齐
- 按 `segment` 逐句英文合成
- 逐句质量评估
- 生成 `report / manifest / demo audio`

### 4.2 非目标

`Task D v2` 不负责:

- 多 speaker 拼接
- 时间线回填
- 与背景混音
- lip-sync
- 自由改写脚本
- 多候选重采样
- 多模型投票

这里故意不做这些，是为了控制工程复杂度。

## 5. 设计原则

`Task D v2` 必须遵守这 6 条原则:

1. **只保留一个主模型**
   不在本轮实现里并行维护多个主后端。
2. **逐 segment 合成**
   每条输出必须稳定映射回 `segment_id`。
3. **参考音频选择可解释**
   不能随机挑 clip。
4. **质量门控先于时间线回填**
   不合格的句段直接在 `Task D` 拦掉。
5. **保留现有工程边界**
   不重做任务 B / C / E 的数据协议。
6. **先做英文**
   当前只做 `zh -> en`，不同时扩展日语。

## 6. 输入与输出

### 6.1 输入

来自任务 B:

- `speaker_profiles.json`
- `reference_clips/`

来自任务 C:

- `translation.en.json`

来自任务请求:

- `speaker_id`
- 可选 `segment_ids`

### 6.2 输出

`Task D v2` 继续保留现有输出形态:

- `segments/<segment_id>.wav`
- `speaker_segments.en.json`
- `speaker_demo.en.wav`
- `task-d-manifest.json`

其中 `speaker_segments.en.json` 仍然是任务 E 的直接输入之一。

## 7. 参考音频策略

### 7.1 选择原则

默认只从任务 B 的 `reference_clips` 中选，不额外自由搜索。

排序规则:

1. 单 speaker、无重叠说话
2. `8s - 12s` 优先
3. transcript 完整且可信
4. 音量稳定
5. 噪声、笑声、喊叫、明显情绪化片段降权

### 7.2 为什么要控制在短时

这里不追求“信息尽量多”，而追求“条件尽量稳定”。

原因是:

- `Task D` 现在要做的是逐句英文合成
- 参考音频过长，往往会引入更多风格漂移和非语义噪声
- 当前的评估逻辑更需要一个稳定 timbre anchor，而不是长篇上下文

### 7.3 参考音频文本

`Qwen3-TTS` 需要:

- `ref_audio`
- `ref_text`

因此任务 B 产出的 reference clip transcript 必须继续保留，不能丢。

如果任务 B 当前 transcript 不够稳，则 `Task D v2` 可以增加一个很轻的 reference transcript 修正步骤，但这一步只服务于 reference，不重跑完整任务 A。

## 8. 文本喂给模型的方式

### 8.1 基本原则

每个 `segment_id` 独立进行一次 TTS。

不做:

- 大段文本合成后再拆分
- 自动长文本 chunk 后再倒推 segment

原因:

- `Task E` 依赖稳定的句段边界
- 一旦在 `Task D` 丢失 segment 映射，后面时间线会变复杂

### 8.2 任务内数据结构

建议保留当前等价结构:

- `segment_id`
- `speaker_id`
- `target_lang`
- `target_text`
- `source_duration_sec`
- `duration_budget`
- `qa_flags`

Qwen3-TTS 实际收到的最小输入是:

- `ref_audio`
- `ref_text`
- `target_text`

### 8.3 对时长的态度

`Task D` 不负责最后一跳的时间线贴合，但必须在这一阶段就把风险分出来。

所以:

- `Task C` 的 `duration_budget` 继续保留
- `Task D` 生成后继续计算 `duration_ratio`
- `Task E` 再决定 `direct / compress / pad / skip`

这三层分工不变。

## 9. 质量评估

`Task D v2` 继续保留三类指标，不因为换模型就改评估原则。

### 9.1 speaker similarity

继续复用当前仓库里的 speaker embedding 评估链路:

- `SpeechBrain ECAPA`

原因:

- 任务 B 已经在用同一 embedding 空间
- 这样评估口径一致

### 9.2 intelligibility

继续保留 backread ASR:

- 对生成音频重新 ASR
- 计算与 `target_text` 的文本相似度

### 9.3 duration

继续保留:

- `generated_duration_sec`
- `source_duration_sec`
- `duration_ratio`

### 9.4 overall_status 判定

当前规则继续沿用:

- 任一项 `failed` -> `overall_status = failed`
- 否则只要有 `review` -> `overall_status = review`
- 三项都 `passed` -> `overall_status = passed`

这个规则现在已经和任务 E 对接好了，不建议同时重写。

## 10. CLI 与模块设计

这一版不需要重做整个命令面。

建议保留当前 `synthesize-speaker` 入口，但把底层后端替换成 Qwen3-TTS。

### 10.1 建议保留的模块边界

- `reference.py`
  - 负责参考音频选择与准备
- `runner.py`
  - 负责单 speaker 整体调度
- `metrics.py`
  - 负责质量评估
- `export.py`
  - 负责 report / manifest / demo 输出

### 10.2 需要替换的模块

- 当前 `f5tts_backend.py`

替换为:

- `qwen_tts_backend.py`

这一步不要求保留多 backend 抽象，只需要保证 `runner.py` 不直接耦合具体实现细节。

## 11. 运行环境建议

首发目标环境:

- `MacBook M4 16GB`
- `Python 3.11`
- `uv`

当前建议的本地运行策略:

- 一次只处理一个 speaker
- 不并发加载多个大模型
- 优先复用 reference prompt

这里的核心目标不是极限吞吐，而是:

- 先得到稳定、可复现的句段级英文配音结果

## 12. 测试与验收

### 12.1 单元测试

至少覆盖:

- reference 选择排序
- `segment_id` 映射完整性
- report 统计逻辑
- overall_status 判定
- manifest 结构

### 12.2 集成测试

至少覆盖:

1. 单 speaker smoke test
   - 选 3 到 5 条句段
   - 检查音频是否生成
   - 检查 report 是否完整

2. 单 speaker full test
   - 对一个 speaker 的全部句段跑完
   - 观察 `passed / review / failed`

3. 全链路 test
   - 用 `test_video` 的视频从 `Stage 1 -> Task E` 全量重跑
   - 观察最终 `placed_count / skipped_count`

### 12.3 验收标准

`Task D v2` 验收不要求一步到位完美，但至少要满足:

1. 全链路可稳定跑通，不出现卡死或大量人工中断
2. `Task D` 的 `overall_status` 结果明显优于当前 `F5-TTS` 版本
3. `Task E` 的 `placed_count` 明显高于当前全量结果 `33`
4. 失败主因仍然可解释，不能变成“看不懂为什么失败”

## 13. 风险与边界

### 13.1 主要风险

- 英文文本本身比中文更长，时长问题不会因为换模型而完全消失
- reference transcript 质量会直接影响克隆质量
- Apple Silicon 本地推理速度仍可能有限

### 13.2 明确不做的事情

这一版先不做:

- 多候选采样
- 多模型 fallback
- OpenVoice 音色增强
- 在线 API 辅助修音

这些都属于下一阶段优化项，不进入 `Task D v2` 首发范围。

## 14. 实施建议

如果你确认这份设计，建议实现顺序是:

1. 替换 `Task D` 主后端为 `Qwen3-TTS`
2. 先跑单 speaker smoke test
3. 再跑 `test_video` 的全量 Task D
4. 最后再跑完整 `Stage 1 -> Task E`

这样可以尽量快速验证:

- 句段级英文配音是否比当前版本更可用
- `Task E` 的最终可放入时间线比例是否明显改善

## 15. 参考资料

- Qwen3-TTS 官方仓库:
  [https://github.com/QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- Qwen3-TTS 技术报告:
  [https://arxiv.org/abs/2601.15621](https://arxiv.org/abs/2601.15621)
- Apple Silicon 本地推理参考:
  [https://github.com/Blaizzy/mlx-audio](https://github.com/Blaizzy/mlx-audio)
- OpenVoice 官方仓库:
  [https://github.com/myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice)
- Seed-VC 官方仓库:
  [https://github.com/Plachtaa/seed-vc](https://github.com/Plachtaa/seed-vc)

其中:

- `Qwen3-TTS` 是本设计的唯一主模型参考
- `OpenVoice` 和 `Seed-VC` 只作为后续方向参考，不进入本轮首发实现
