# 任务 E 技术设计: 多说话人时间贴合与混音

- 项目: `translip`
- 文档状态: Draft v1
- 创建日期: 2026-04-13
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/speaker-aware-dubbing-task-breakdown.md)
- 前置依赖:
  - [technical-design.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/technical-design.md)
  - [task-a-speaker-attributed-transcription.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-a-speaker-attributed-transcription.md)
  - [task-c-dubbing-script-generation.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-c-dubbing-script-generation.md)
  - [task-d-single-speaker-voice-cloning.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-d-single-speaker-voice-cloning.md)
  - [task-d-test-report.md](/Users/masamiyui/OpenSoureProjects/Forks/translip/docs/task-d-test-report.md)

## 1. 目标

任务 E 的目标不是继续提升单句 TTS 质量，而是把前面已经产出的结构化结果真正拼成“可听、可审查、可继续交付”的目标语言音轨。

它要解决的是 4 件事:

1. 多个 speaker 的目标语言片段，如何回填到统一时间轴
2. 当生成音频比原句更长或更短时，如何做可接受的时间贴合
3. 如何把目标语言人声与背景声重新混在一起
4. 如何导出可以人工复核和继续返修的交付物

任务 E 的首发目标应该是:

- 输入阶段 1 的 `background`
- 输入任务 A 的时间轴
- 输入任务 C 的翻译脚本
- 输入任务 D 的单句目标语言音频
- 输出一条 **目标语言 dub voice** 和一条 **带背景的 preview mix**

这里要特别强调:

- 任务 E 首发仍然是 **音频交付优先**
- 不在这一阶段做 lip-sync
- 不在这一阶段做镜头级表演优化
- 不在这一阶段做视频画面重编码作为核心目标

## 2. 范围与非目标

### 2.1 任务范围

任务 E 负责:

- 读取阶段 1 的 `background`
- 读取任务 A 的原始时间轴句段
- 读取任务 C 的翻译句段和时长预算
- 读取任务 D 为一个或多个 speaker 生成的 `segment wav`
- 把这些 segment 回填到统一 timeline
- 做基础的 duration fit
- 做 speaker 间的重叠处理
- 输出:
  - 干净的目标语言人声音轨
  - 带背景的预混音轨
  - 可复核的混音报告
  - 可返修的 timeline manifest

### 2.2 非目标

任务 E 当前不负责:

- 自动重译文案
- 自动重做任务 D 的失败句
- 视频镜头级对口型
- 角色表演重写
- 多轨 DAW 级精修混音
- 影院级响度母带

## 3. 与前置任务的关系

任务 E 直接消费前面 4 个任务的产物。

### 3.1 来自阶段 1

- `voice`
- `background`
- 源文件总时长

其中任务 E 主要消费 `background`。

### 3.2 来自任务 A

- `segment_id`
- `speaker_label`
- `start`
- `end`
- `duration`

任务 E 的 timeline anchor 以任务 A 的时间轴为准。

### 3.3 来自任务 C

- `target_text`
- `duration_budget`
- `qa_flags`

任务 E 不重新决定“该说什么”，只根据任务 C 的文本和时长预算做排布。

### 3.4 来自任务 D

- `segment wav`
- `generated_duration_sec`
- `speaker similarity`
- `text_similarity`
- `overall_status`

任务 E 不应该无条件使用所有任务 D 结果，而是要带着质量门槛去选择。

## 4. 当前现实约束

这一节必须基于当前仓库现状来定，而不是假设任务 D 已经完美。

截至 **2026-04-14**:

- 任务 D 已经能稳定生成 segment 级目标语言音频
- 任务 D 的代表性短句样本可到 `review`
- 但当前 `Qwen3-TTS` 开发后端仍然会出现:
  - 句首串词
  - 时长偏长
  - 专名词偶发读错

因此任务 E 的设计不能建立在“每个 segment 都完美可用”的假设上。

任务 E 首发必须支持:

1. **失败段不中断整条时间线**
   `Task D overall_status=failed` 的句段只要音频存在，也允许先进入时间线
2. **带缺口的可听预览**
   真正无法放入的段，仍允许保留静音缺口
3. **混音报告可解释**
   必须明确标出哪些段被放入时间线、哪些段被跳过、为什么跳过

## 5. 设计原则

任务 E 需要遵守这 8 个原则:

1. **时间轴以任务 A 为锚点**
   不重新发明新的主 timeline
2. **segment 映射不能丢**
   每个混入的音频都必须能追溯到 `segment_id`
3. **优先保证听感连续，再追求强行塞满**
   对明显不合适的段，不要硬拼
4. **混音必须可回放、可复算**
   不能只导出最终 wav，而没有中间清单
5. **放入、跳过和回退必须显式记录**
   不能静默丢段
6. **背景混音首发以保守为主**
   先做低风险 preview mix，不做激进效果
7. **算法与参数要可调**
   因为不同视频密度差异很大
8. **任务 E 首发优先音频，不优先视频容器**
   先把声音排好，再谈视频封装

## 6. 核心结论

任务 E 首发不应该做成“自动把所有问题都修平”的智能黑盒，而应该做成:

- 一个 **timeline assembler**
- 一个 **duration fit controller**
- 一个 **preview mixer**
- 一个 **quality-aware exporter**

也就是:

`Task D segments -> fit -> place -> overlap resolve -> render dub voice -> mix with background -> export`

这是目前最稳的路线，因为:

- 当前任务 D 仍然会产生 `review` 或 `failed`
- 时间贴合和混音必须知道段级质量
- 任务 E 的首要目标是交付“可审听的版本”，不是掩盖上游问题

## 7. 首发交付物

任务 E 首发建议输出 5 类产物:

1. `dub_voice.<target_tag>.wav`
   纯目标语言人声音轨
2. `preview_mix.<target_tag>.wav`
   目标语言人声 + background 的预混音轨
3. `timeline.<target_tag>.json`
   最终放入时间线的 segment 排布结果
4. `mix_report.<target_tag>.json`
   跳过、回退、重叠、时长调整等决策报告
5. `task-e-manifest.json`
   任务 E 的执行摘要

可选产物:

- `preview_mix.<target_tag>.mp3`
- `preview_video.<target_tag>.mp4`

其中 `preview_video` 建议放在任务 E 的次级目标，不作为首发必做项。

根据当前确认，任务 E 首发只做 **音频输出**，不在这一阶段实现 `preview_video.mp4`。

## 8. 输入数据设计

任务 E 首发最合理的输入不是“某个 speaker 的单独目录”，而是一个跨 speaker 的聚合输入。

建议输入结构至少包括:

- `background_path`
- `segments.zh.json`
- `translation.<target_tag>.json`
- 一个或多个 `speaker_segments.<target_tag>.json`
- 一个或多个任务 D `segments/` 目录

为了后续可扩展，任务 E 在内部应构造统一的 `timeline_item`:

```json
{
  "segment_id": "seg-0007",
  "speaker_id": "spk_0001",
  "target_lang": "en",
  "anchor_start": 12.34,
  "anchor_end": 14.14,
  "source_duration_sec": 1.8,
  "generated_duration_sec": 2.443,
  "target_text": "Go to Dubai.",
  "audio_path": ".../seg-0008.wav",
  "task_d_status": "review",
  "speaker_similarity": 0.4758,
  "text_similarity": 1.0,
  "fit_strategy": null,
  "placement_start": null,
  "placement_end": null,
  "mix_status": "pending"
}
```

任务 E 的后续全部逻辑都围绕这个结构展开。

## 9. 模块拆分

任务 E 首发建议拆成 6 个模块。

### 9.1 Candidate Loader

职责:

- 从任务 A/C/D 产物构造统一 `timeline_item`
- 检查音频文件是否存在
- 对多 speaker 结果做聚合

### 9.2 Segment Gate

职责:

- 决定哪些任务 D 结果可直接进入 timeline
- 决定哪些结果标记为 `review`
- 决定哪些结果必须跳过

首发建议的保守规则:

- `overall_status=passed/review` 才允许进入 timeline
- `overall_status=failed` 默认不进

这条规则在任务 E 首发中建议固定，不作为公开 CLI 配置项暴露。

### 9.3 Duration Fit Planner

职责:

- 根据 `source_duration_sec`、`generated_duration_sec`、`duration_budget`
  计算时间贴合方式

首发建议只支持 4 种策略:

1. `direct`
   - 生成时长足够接近原时长
   - 直接放入
2. `compress`
   - 轻度超长
   - 通过保守加速压回窗口
3. `pad`
   - 生成偏短
   - 尾部补静音或保留原空隙
4. `skip`
   - 明显不可用
   - 直接跳过

### 9.4 Overlap Resolver

职责:

- 处理两个 segment 在同一时间窗的重叠
- 尤其处理任务 A 原始对话中的交叉说话

首发建议遵循保守顺序:

1. 优先保留时间锚点更早的段
2. 如果后一段是 `passed` 而前一段只是 `review`，允许后一段覆盖冲突尾部
3. 若二者都无法无损放下，则保留质量更高者，另一段标记 `truncated` 或 `skipped_overlap`

### 9.5 Audio Renderer

职责:

- 在统一采样率下把所有时间片段渲染成单条 `dub_voice`
- 处理首尾淡入淡出
- 保证不爆音

首发建议:

- 统一 `24kHz` 或 `48kHz`
- 内部 float mixing
- 对每段加极短 fade in/out，避免 click

### 9.6 Preview Mixer

职责:

- 将 `dub_voice` 与 `background` 做保守混音
- 输出可审听 preview

首发建议:

- 不做复杂 sidechain
- 只做简单背景衰减和总线限幅
- 先保证对白能听清

## 10. 时间贴合策略

任务 E 的难点不是“能不能放进去”，而是“放进去以后是否还像正常对白”。

### 10.1 时间贴合的判定输入

每个 `timeline_item` 至少要用到:

- `anchor_start`
- `anchor_end`
- `source_duration_sec`
- `generated_duration_sec`
- `duration_budget.estimated_tts_duration_sec`
- `task_d_status`

### 10.2 首发推荐阈值

建议首发先做保守阈值:

- `0.85 <= ratio <= 1.20`
  - `direct`
- `1.20 < ratio <= 1.45`
  - `compress`
- `0.60 <= ratio < 0.85`
  - `pad`
- 其他
  - `skip` 或 `review_required`

这里的 `ratio` 指:

`generated_duration_sec / source_duration_sec`

### 10.3 配置化时间贴合策略

任务 E 文档建议把时间贴合设计成两层配置:

1. `fit_policy`
   - `conservative`
   - `high_quality`
2. `fit_backend`
   - `atempo`
   - `rubberband`

建议默认值:

- `fit_policy=conservative`
- `fit_backend=atempo`

首发默认目标是:

- 先用最稳、最可复现的链路完成核心功能
- 同时保留后续升级更高质量 time-stretch 的参数位

### 10.4 `compress` 方式

#### 默认策略: `ffmpeg atempo`

首发建议不要上相位声码器复杂链路，而是先做:

- 轻度 `ffmpeg atempo`
- 上限建议不超过 `1.15x`

原因:

- 当前任务 D 已经倾向偏长
- 任务 E 主要是在“小幅压缩”，不是做极限重定时
- `atempo` 简单、稳、依赖少、可复现

#### 可配置升级策略: `rubberband`

任务 E 从设计上建议兼容 `rubberband`，但不把它作为首发默认。

原因:

- `FFmpeg` 官方提供 `rubberband` filter
- `Rubber Band Library` 是成熟的高质量 time-stretch / pitch-shift 开源实现
- `librosa` 官方文档直接说明其 `phase_vocoder` 更偏教学/参考实现，并建议高质量场景优先使用 `Rubber Band`

因此任务 E 的建议路线是:

- **默认**
  - `atempo`
- **升级**
  - `rubberband`

推荐使用边界:

- `compress ratio <= 1.15`
  - 默认 `atempo`
- `compress ratio > 1.15`
  - 未来可切 `rubberband`

### 10.5 `pad` 方式

对偏短音频，首发建议:

- 保持原音频不变
- 尾部补静音到 placement window

不要在任务 E 首发做:

- 自动补语气词
- 自动拉长尾音

因为这些已经越界到 TTS 表演控制。

## 11. 多说话人重叠处理

多说话人视频里，任务 A 的原时间线可能存在:

- 插话
- 重叠说话
- 背景对白

任务 E 首发不应该假设每一段都严格不重叠。

建议规则:

1. 同一 speaker 内部
   - 允许后一段覆盖前一段的尾部极小重叠
   - 超过阈值则前后都标记 `timeline_conflict`

2. 不同 speaker 之间
   - 若两个段同时争抢同一窗口，优先质量更高者
   - 被牺牲的段进入 `skipped_overlap`

3. 所有冲突都写入 `mix_report`

首发不要做:

- 双 speaker 同时叠加的复杂 spatial mix

因为这会把“时间放置问题”升级成“混音艺术问题”。

## 12. 背景混音策略

任务 E 首发的背景混音原则是:

- **对白清晰优先**
- **背景完整保留次之**

### 12.1 首发推荐链路

建议链路:

`dub_voice -> normalize -> background attenuate -> sum -> limiter -> export`

### 12.2 背景处理建议

首发建议:

- background 整体降低 `6dB` 到 `12dB`
- 当 `dub_voice` 出现时，可选进一步降低 `2dB` 到 `4dB`

但这里的自动 ducking 首发不一定要做成连续包络控制。

更稳的方式是:

- 先按 segment window 做离散衰减

### 12.3 人声处理建议

首发建议:

- 不做重压缩
- 只做峰值保护
- 避免把 TTS 本身的瑕疵进一步放大

### 12.4 配置化混音策略

任务 E 文档建议把混音配置拆成:

1. `mix_profile`
   - `preview`
   - `enhanced`
2. `ducking_mode`
   - `static`
   - `sidechain`

建议默认值:

- `mix_profile=preview`
- `ducking_mode=static`

### 12.5 默认 preview mix

首发默认混音策略建议是:

- background 固定降低 `8dB`
- 活跃对白窗口额外降低 `3dB`
- 人声总线只做峰值保护
- 优先输出 `wav`

这是任务 E 首发默认，因为它:

- 依赖少
- 行为可预测
- 容易测试

### 12.6 可配置升级 mix

后续建议预留增强链路:

- `ffmpeg sidechaincompress`
- `ffmpeg loudnorm`
- 可选 `EBU R128` 风格目标响度

因此任务 E 的混音建议路线是:

- **默认**
  - `preview + static`
- **升级**
  - `enhanced + sidechain`

## 13. 建议技术选型

任务 E 首发建议尽量复用当前仓库已经稳定的依赖。

### 13.1 必选

- `numpy`
- `soundfile`
- `ffmpeg`

### 13.2 建议

- `ffmpeg` 负责:
  - `atempo`
  - `rubberband`
  - `sidechaincompress`
  - `loudnorm`
  - resample
  - format conversion
- Python 渲染层负责:
  - timeline placement
  - overlap bookkeeping
  - report generation

### 13.3 技术调研后的推荐方案

基于开源项目、官方文档和经典论文，任务 E 最合理的技术方案不是押单一算法，而是做成:

- **默认稳妥链路**
- **可配置升级链路**

#### A. 时间贴合

默认链路:

- `ffmpeg atempo`

升级链路:

- `ffmpeg rubberband`
- 或底层 `Rubber Band Library`

调研结论:

- `FFmpeg` 官方 `atempo` 适合轻量、稳定、低依赖的速度调整
- `FFmpeg` 官方 `rubberband` 允许通过 `librubberband` 做更高质量时间伸缩
- `Rubber Band` 官方文档和技术说明明确面向高质量 time-stretch / pitch-shift
- `librosa` 官方文档明确指出 `phase_vocoder` 更偏教学参考，并直接建议高质量场景使用 `Rubber Band`
- `WSOLA` 经典论文给出了 waveform similarity 路线在语音 time-scale modification 上的理论基础

最终建议:

- **首发默认**
  - `atempo`
- **预留增强**
  - `rubberband`
- **不作为默认**
  - 纯 `phase vocoder`

#### B. 背景混音

默认链路:

- `static attenuation + segment-window ducking + limiter`

升级链路:

- `sidechaincompress + loudnorm`

调研结论:

- `FFmpeg` 官方提供 `sidechaincompress`
- `FFmpeg` 官方提供 `loudnorm`
- `EBU R128` 适合作为后续更一致的响度目标

最终建议:

- **首发默认**
  - `preview` 静态混音链路
- **预留增强**
  - `enhanced` sidechain + loudnorm

#### C. 为什么首发不直接上更重的音频栈

当前不建议任务 E 首发直接引入更重的混音库或复杂时频修复库，原因是:

- 当前任务 D 的核心问题仍然是段级质量波动
- 任务 E 首发的主要风险是 timeline、fit 和 gate
- 先做透明、稳、可测的链路更重要

### 13.4 推荐配置矩阵

| 场景 | fit_policy | fit_backend | mix_profile | ducking_mode |
| --- | --- | --- | --- | --- |
| 首发默认 | `conservative` | `atempo` | `preview` | `static` |
| 质量对比 | `high_quality` | `rubberband` | `preview` | `static` |
| 后续增强 | `high_quality` | `rubberband` | `enhanced` | `sidechain` |

### 13.5 首发不建议新增重依赖

当前不建议一开始就引入:

- 完整 DAW 型混音库
- 重型时频相位修复库
- 复杂自动化 sidechain 引擎

原因很简单:

- 任务 E 首发的重点是稳定、透明、可测
- 不是把音频工程复杂度一次性拉满

## 14. CLI 草案

建议新增命令:

```bash
uv run translip render-dub \
  --background ./stage1/output/background.mp3 \
  --segments ./task-a/voice/segments.zh.json \
  --translation ./task-c/voice/translation.en.json \
  --task-d-report ./task-d/voice/spk_0001/speaker_segments.en.json \
  --output-dir ./output-task-e \
  --target-lang en
```

后续可扩展为:

- 多个 `--task-d-report`
- 自动扫描一个 `task-d-root`

首发 CLI 参数建议:

- `--background`
- `--segments`
- `--translation`
- `--task-d-report`
- `--output-dir`
- `--target-lang`
- `--max-compress-ratio`
- `--background-gain-db`
- `--preview-format`
- `--fit-policy`
- `--fit-backend`
- `--mix-profile`
- `--ducking-mode`

## 15. 验收标准

任务 E 的验收必须可测，而不是只靠“听起来差不多”。

### 15.1 完成定义

- 能读取任务 D 结果并构建 timeline
- 能输出 `dub_voice` 和 `preview_mix`
- 能生成 `mix_report` 和 `manifest`
- 遇到失败段时不会整任务崩溃

### 15.2 核心验收标准

1. 输出音轨总时长与源视频总时长一致或在极小误差内
2. 每个放入时间线的段都能追溯到 `segment_id`
3. 所有跳过段都在报告中可见
4. 不出现明显爆音和大面积削波
5. 代表性样本上，目标语言对白可被正常听清

### 15.3 测试方式

单元测试:

- timeline item 构造测试
- fit strategy 判定测试
- overlap resolver 测试
- mix report schema 测试

集成测试:

- 单 speaker 样本 1 个
- 双 speaker 样本 1 个
- 带 background 的真实视频样本 1 个

端到端验收:

- 使用 `test_video` 中的真实视频
- 从阶段 1 一直跑到任务 E
- 输出完整 preview mix

## 16. 首发实现顺序

建议任务 E 按下面顺序做:

1. 先做 timeline loader 和 report schema
2. 再做 duration fit planner
3. 再做单 speaker audio render
4. 再做多 speaker overlap resolver
5. 最后做 background preview mix

这样做的好处是:

- 每一步都能独立测
- 出问题时定位清楚
- 不会一开始就被混音细节淹没

## 17. 当前建议结论

任务 E 首发建议明确收敛成:

- **音频优先**
- **短句可用优先**
- **timeline 可解释优先**
- **preview mix 优先**

不建议任务 E 首发追求:

- 视频成片级交付
- 完全自动修平所有时长问题
- 把任务 D 的质量缺陷全部在任务 E 隐藏掉

当前最合理的产品节奏是:

1. 先让任务 E 把“可用的任务 D 结果”稳稳放进时间线
2. 先交付稳定 preview mix
3. 再继续回头提升任务 D 后端质量
4. 最后再做任务 F 的整链路工程封装

## 18. 已确认决策

进入任务 E 实现前，当前已经明确这 4 条:

1. 首发只做 **音频输出**
2. `Task D overall_status=failed` 的段默认 **坚持跳过**
3. 时间贴合支持 **配置兼容两种策略**
   - 默认 `atempo`
   - 预留 `rubberband`
4. 背景混音支持 **配置兼容两种策略**
   - 默认 `preview/static`
   - 预留 `enhanced/sidechain`

## 19. 参考资料

- FFmpeg Filters Documentation
  [https://ffmpeg.org/ffmpeg-filters.html](https://ffmpeg.org/ffmpeg-filters.html)
- Rubber Band Library Documentation
  [https://www.breakfastquay.com/rubberband/documentation.html](https://www.breakfastquay.com/rubberband/documentation.html)
- Rubber Band Technical Notes
  [https://www.breakfastquay.com/rubberband/technical.html](https://www.breakfastquay.com/rubberband/technical.html)
- librosa `phase_vocoder`
  [https://librosa.org/doc/main/generated/librosa.phase_vocoder.html](https://librosa.org/doc/main/generated/librosa.phase_vocoder.html)
- Verhelst, Roelands, `WSOLA`
  [https://dblp.org/rec/conf/icassp/VerhelstR93](https://dblp.org/rec/conf/icassp/VerhelstR93)
  公开 PDF:
  [https://sps.ewi.tudelft.nl/Education/courses/ee4c03/assignments/audio_lpc/roelands93icassp.pdf](https://sps.ewi.tudelft.nl/Education/courses/ee4c03/assignments/audio_lpc/roelands93icassp.pdf)
- EBU R128
  [https://tech.ebu.ch/files/live/sites/tech/files/shared/r/r128.pdf](https://tech.ebu.ch/files/live/sites/tech/files/shared/r/r128.pdf)
