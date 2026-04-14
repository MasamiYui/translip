# 任务 G 技术设计: 最终视频合成与交付封装

- 项目: `video-voice-separate`
- 文档状态: Draft v1
- 创建日期: 2026-04-14
- 对应任务: [speaker-aware-dubbing-task-breakdown.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/speaker-aware-dubbing-task-breakdown.md)
- 前置依赖:
  - [task-e-timeline-fitting-and-mixing.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-e-timeline-fitting-and-mixing.md)
  - [task-f-pipeline-and-engineering-orchestration.md](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/task-f-pipeline-and-engineering-orchestration.md)

## 1. 目标

任务 G 的目标是把已经在 Task E 生成完成的目标语言音频产物，重新封装回原视频，形成真正可交付的最终视频文件。

这一层不再新增 ASR、翻译、TTS 或混音算法，而是解决“如何把前面已经做出来的内容稳定地交付出去”。

任务 G 首发需要解决 5 件事:

1. 消费 Task F / Task E 的标准产物，而不是重新跑音频阶段
2. 保留原视频画面，替换或附加新的音轨
3. 输出一组命名稳定、结构稳定的最终交付文件
4. 把导出参数、音轨策略、时长处理策略做成明确可配置项
5. 生成最终交付层的 manifest / report，便于回溯和验收

## 2. 为什么单独拆成任务 G

这一步不建议塞回 Task E，也不建议继续混在 Task F 里。

原因是:

- Task E 的职责是音频层:
  - 时间线装配
  - 时长贴合
  - preview mix
  - dub voice
- Task F 的职责是工程编排层:
  - 阶段调度
  - 缓存
  - resume
  - pipeline status
- 最终视频导出属于交付层:
  - 选择什么音轨
  - 用什么编码参数
  - 怎么处理时长边界
  - 交付哪些文件

所以拆成单独的 Task G，边界最清楚:

- `E`: 产出最终音频资产
- `F`: 编排并记录整条流水线
- `G`: 把音频资产封装成最终视频交付物

## 3. 任务范围

任务 G 首发负责:

- 读取原始输入视频
- 读取 Task E 的 `preview_mix` 和 `dub_voice`
- 导出至少一份最终 `mp4`
- 生成交付目录
- 生成 `delivery-manifest.json`
- 生成 `delivery-report.json`

任务 G 首发不负责:

- 重跑 Task A-E
- 修改 Task E 时间线
- 做最终字幕翻译优化
- 复杂多音轨播放器体验
- Web UI
- 封面、元数据、缩略图生成

## 4. 用户视角目标

当用户执行任务 G 时，预期是:

- 输入: 原视频 + 已跑完的 Task F / Task E 目录
- 输出: 可以直接播放、直接发给别人审看、后续可继续人工精修的视频文件

最小交付物建议是:

1. `final_preview.<target_tag>.mp4`
   原视频画面 + `preview_mix`
2. `final_dub.<target_tag>.mp4`
   原视频画面 + `dub_voice`
3. `delivery-manifest.json`
4. `delivery-report.json`

其中:

- `final_preview` 是默认主交付物，最接近“实际观看效果”
- `final_dub` 更适合质检、返修和音频问题定位

## 5. 输入与输出

## 5.1 输入

任务 G 至少需要这些输入:

- `input_video_path`
- `task_e_manifest_path`
- `preview_mix_path`
- `dub_voice_path`

可选输入:

- `timeline_path`
- `mix_report_path`
- 可选字幕文件

## 5.2 输出

任务 G 首发输出:

- `final_preview.<target_tag>.mp4`
- `final_dub.<target_tag>.mp4`
- `delivery-manifest.json`
- `delivery-report.json`

建议目录:

```text
<output-root>/
  final-preview/
    final_preview.en.mp4
  final-dub/
    final_dub.en.mp4
  delivery-manifest.json
  delivery-report.json
```

如果由 Task F 直接串接调用，建议目录放在:

```text
<pipeline-output-root>/
  task-g/
    delivery/
      final_preview.en.mp4
      final_dub.en.mp4
      delivery-manifest.json
      delivery-report.json
```

## 6. 技术选型

任务 G 首发建议只选一条稳定路线:

- 视频封装后端: `ffmpeg`

原因:

- 仓库前面阶段已经深度依赖 `ffmpeg`
- 本地可用性最好
- 直接支持音视频 mux
- 直接支持 `copy` 视频流与音轨重编码
- 工程复杂度最低

不建议首发引入:

- MoviePy
- PyAV 全量重写封装
- 自定义视频编辑框架

因为任务 G 的核心并不是做非线性剪辑，而是稳定交付。

## 7. 核心方案

## 7.1 首发导出模式

任务 G 首发建议支持 2 种导出模式:

1. `preview`
   使用 `preview_mix`
2. `dub`
   使用 `dub_voice`

默认导出两份:

- `final_preview`
- `final_dub`

这样做的好处是:

- `preview` 可直接审看
- `dub` 可快速判断问题是 TTS 本身还是背景混音问题

## 7.2 视频处理策略

首发建议默认:

- **尽量 copy 原视频流**
- **只重编码目标音轨**

推荐默认策略:

- `video_codec = copy`
- `audio_codec = aac`
- `container = mp4`

原因:

- 最快
- 最稳定
- 减少画质损失
- 对本地机器最友好

如果输入视频的容器或编码导致 `copy` 不兼容，再回退到视频重编码。

## 7.3 音轨处理策略

首发建议只做“替换主音轨”的稳定路径，不先做复杂多音轨策略。

也就是:

- 输出视频只有一条最终音轨
- 这条音轨来自 `preview_mix` 或 `dub_voice`

未来再扩展:

- 保留原音轨作为第二音轨
- 同时写入原音轨与目标音轨
- 写入多语言音轨

但首发不做，避免交付行为过早复杂化。

## 7.4 时长边界策略

这是任务 G 必须明确的点。

由于当前 Task E 已经允许:

- `overflow_unfitted`
- `underflow_unfitted`

所以音频时长未必总能完美贴合原视频。

任务 G 首发建议默认策略:

- `end_policy = trim_audio_to_video`

也就是:

- 以原视频时长为准
- 如果目标音轨比视频长，导出时截断多余音频
- 如果目标音轨比视频短，视频保持原长，后部静音

原因:

- 交付物必须稳定可播
- 不应为了保留超长音频去自动延长视频画面
- 延长视频结尾属于后续增强，不是首发核心功能

未来可扩展:

- `end_policy = pad_video`
- `end_policy = keep_longest`

但首发先不做。

## 8. 推荐 FFmpeg 路线

## 8.1 Preview 视频

逻辑:

- 输入原视频
- 输入 `preview_mix`
- 保留原视频流
- 替换音轨
- 输出 `final_preview.en.mp4`

## 8.2 Dub 视频

逻辑:

- 输入原视频
- 输入 `dub_voice`
- 保留原视频流
- 替换音轨
- 输出 `final_dub.en.mp4`

## 8.3 默认封装规则

首发建议:

- `-map 0:v:0`
- `-map 1:a:0`
- `-c:v copy`
- `-c:a aac`
- `-shortest`
- 显式 `-movflags +faststart`

其中:

- `-shortest` 可以和默认 `trim_audio_to_video` 语义保持一致
- `+faststart` 让交付视频更适合网络分发和预览

## 9. 公开配置设计

任务 G 建议公开这些高价值参数。

## 9.1 输入配置

- `--input-video`
- `--pipeline-root`
- `--task-e-dir`
- `--output-dir`

说明:

- `pipeline-root` 和 `task-e-dir` 至少需要其一
- 如果给了 `pipeline-root`，任务 G 自动定位 Task E 产物

## 9.2 导出选择配置

- `--export-preview`
- `--export-dub`
- `--target-lang`

默认:

- 两者都导出

## 9.3 编码配置

- `--container`
- `--video-codec`
- `--audio-codec`
- `--audio-bitrate`

默认:

- `container=mp4`
- `video-codec=copy`
- `audio-codec=aac`

## 9.4 时长策略配置

- `--end-policy`

首发只公开这些枚举值:

- `trim_audio_to_video` 默认
- `keep_longest` 预留

其中:

- `keep_longest` 可以先只作为占位枚举，不一定首发实现

## 9.5 质量与调试配置

- `--overwrite`
- `--keep-temp`
- `--write-status`

如果后续由 Task F 串联调用:

- 这些配置也可以被纳入总 pipeline config

## 10. CLI 与接口建议

建议新增一个独立 CLI:

```bash
uv run video-voice-separate export-video \
  --input-video ./test_video/example.mp4 \
  --pipeline-root ./output-pipeline \
  --output-dir ./output-delivery \
  --target-lang en \
  --export-preview \
  --export-dub
```

建议的 Python 接口:

```python
export_delivery(request: ExportVideoRequest) -> ExportVideoResult
```

请求对象建议包括:

- 视频输入路径
- Task E 产物路径
- 导出模式
- 编码策略
- 结束策略

返回对象建议包括:

- preview 导出路径
- dub 导出路径
- delivery manifest/report 路径
- 导出统计

## 11. 数据结构建议

## 11.1 delivery-manifest.json

建议包含:

- 输入视频信息
- 使用的 Task E 产物路径
- 导出配置
- 最终输出路径
- 时间戳
- 状态
- 错误信息

## 11.2 delivery-report.json

建议包含:

- 导出模式
- 目标语言
- 输出文件大小
- 视频时长
- 音轨时长
- 是否发生裁剪
- 使用的 end policy
- 编码方式

## 12. 关键实现细节

## 12.1 不重新跑 Task E

任务 G 必须是纯消费层，不允许因为缺文件就偷偷重跑 Task E。

如果输入缺失:

- 直接报错
- 错误写入 `delivery-manifest.json`

这样边界才清楚。

## 12.2 输入校验

任务 G 首发必须校验:

- 原视频存在
- Task E manifest 存在
- `preview_mix` 存在
- `dub_voice` 存在
- 目标语言标签和文件名一致

## 12.3 输出命名稳定

任务 G 不能临时拼各种不稳定名字。

建议固定:

- `final_preview.<target_tag>.mp4`
- `final_dub.<target_tag>.mp4`

## 12.4 失败可回溯

如果 `ffmpeg` 导出失败:

- 必须保留 stderr
- 写入 `delivery-manifest.json`
- 尽量写入 `delivery-report.json`

## 13. 验收标准

任务 G 完成后，应满足这些标准:

1. 给定一个已完成 Task E 的 pipeline 目录，能稳定导出 `mp4`
2. 输出视频可以在系统播放器正常播放
3. 默认情况下画面保持原视频
4. 默认情况下音轨为目标音轨，不混入错误音轨
5. 输出命名与目录结构稳定
6. 导出失败时有清晰错误信息和 manifest

## 14. 测试策略

## 14.1 单元测试

- 请求对象归一化
- Task E 路径自动解析
- 输出命名规则
- manifest/report schema
- end policy 决策逻辑

## 14.2 集成测试

使用已有 `test_video/我在迪拜等你.mp4` 和 Task F 产物做真实验证。

至少验证:

1. `final_preview.en.mp4` 导出成功
2. `final_dub.en.mp4` 导出成功
3. 视频时长可探测
4. 音轨存在
5. manifest/report 正常生成

## 14.3 回归测试

在完成 Task G 后，需要重新跑:

- `uv run pytest -q`
- 基于 `test_video` 的 A -> G 全链路验证

## 15. 风险与取舍

任务 G 首发的主要风险不是“封装做不出来”，而是交付语义需要提前收敛。

当前要明确接受的取舍:

- 默认只导出单音轨视频，不做多音轨
- 默认以原视频时长为准，不自动延长画面
- 默认优先 `preview_mix` 和 `dub_voice` 两份视频，而不是一次性做所有变体
- 默认先追求稳定交付，不追求复杂字幕轨和高级封装

## 16. 实现顺序建议

任务 G 建议按这个顺序实现:

1. 定义 `ExportVideoRequest` / `ExportVideoResult`
2. 实现 Task E 产物路径解析
3. 实现 `ffmpeg` preview 导出
4. 实现 `ffmpeg` dub 导出
5. 写 `delivery-manifest.json` / `delivery-report.json`
6. 接入 CLI `export-video`
7. 用 `test_video` 跑真实验证
8. 最后决定是否让 Task F 在后续串接 Task G

## 17. 当前建议结论

任务 G 首发建议做成:

- 一个独立导出命令
- 一个稳定的 `ffmpeg` 封装层
- 两份最终视频:
  - `final_preview`
  - `final_dub`
- 一套交付 manifest/report

这是当前最小、最稳、最适合继续推进的方案。
