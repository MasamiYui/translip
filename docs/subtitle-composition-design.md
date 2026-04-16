# 字幕成品交付增强设计

## 目标

在现有 Task G 最终交付层上补齐字幕成品能力：

- 仅中文：保留原始中文硬字幕
- 仅英文：擦除中文后压入英文字幕
- 中英双语：保留中文并压入英文字幕
- 支持字幕样式自动推荐 + 手动指定
- 支持生成可直接播放的视频预览片段

## 为什么放在 Task G

这个功能最适合继续放在 Task G，而不是新建独立 compose 命令：

1. Task G 本身就是“最终成品交付层”
2. 字幕模式本质上是最终导出策略，不是上游 ASR/TTS 算法阶段
3. 现在 `ExportVideoRequest` / `delivery_policy` 已经具备扩展点
4. 用户最终要控制的是“导出什么成品”，而不是“单独跑一个字幕处理器”

所以建议：

- **正式成品出口**：继续增强 `translip export-video` / pipeline 的 `task-g`
- **调样式工具**：新增 `translip preview-subtitles`

## 当前代码落点

### 交付层
- `src/translip/delivery/runner.py`
- `src/translip/delivery/export.py`

### pipeline 串接层
- `src/translip/orchestration/runner.py`
- `src/translip/orchestration/request.py`

### 现有字幕来源
- OCR 原中文字幕：`src/translip/orchestration/ocr_bridge.py`
  - `ocr-detect/ocr_subtitles.source.srt`
- OCR 翻译英文字幕：`src/translip/subtitles/runner.py`
  - `ocr-translate/ocr_subtitles.<lang>.srt`
- ASR 翻译英文字幕：`src/translip/translation/export.py`
  - `task-c/translation.<lang>.srt`

### 擦字幕能力
- `src/translip/orchestration/erase_bridge.py`
  - 输出 `subtitle-erase/clean_video.mp4`

## 成品模式

### 1. chinese_only
- 视频：原视频
- 中文字幕：保留硬字幕
- 英文字幕：无
- 音轨：preview 或 dub

### 2. english_only
- 视频：`clean_video.mp4`
- 中文字幕：已擦除
- 英文字幕：烧录英文字幕
- 音轨：preview 或 dub

### 3. bilingual
- 视频：原视频
- 中文字幕：保留硬字幕
- 英文字幕：额外烧录英文字幕
- 默认英文放顶部，避免和底部中文打架

### 4. none
- 保持当前行为，仅做音视频 mux

## 样式系统

### 自动推荐
按分辨率推荐：

| 高度 | 字号 | 边距 | 描边 |
|---|---:|---:|---:|
| <= 720 | 20 | 20 | 1.5 |
| <= 1080 | 28 | 30 | 2.0 |
| <= 2160 | 36 | 40 | 2.5 |
| > 2160 | 42 | 50 | 3.0 |

默认字体：
- CJK: `Noto Sans CJK SC`
- Latin: `Noto Sans`

### 手动覆盖
支持指定：
- 字体
- 字号
- 颜色
- 描边颜色
- 描边宽度
- 位置 top/bottom
- 垂直边距
- bold

## 预览能力

新增 `preview-subtitles`：
- 输入视频 + 字幕 + 样式
- 自动截取第一条字幕附近 10 秒片段
- 烧录后输出短 mp4
- 方便直接播放确认视觉效果

## 技术方案

### 字幕中间格式
使用 ASS 作为烧录前中间格式：
- SRT 易读但样式能力弱
- ASS 可以稳定表达字体、位置、描边、双样式双语

### 核心模块
- `src/translip/subtitles/burn.py`
  - `recommend_style`
  - `srt_to_ass`
  - `merge_bilingual_ass`
  - `first_subtitle_time`

- `src/translip/subtitles/preview.py`
  - `preview_subtitle`

### ffmpeg 增强
- `probe_video_resolution`
- `burn_subtitle_and_mux`
- `burn_subtitle_preview`

## CLI 设计

### export-video 新参数
- `--subtitle-mode none|chinese_only|english_only|bilingual`
- `--subtitle-source ocr|asr`
- `--subtitle-font`
- `--subtitle-font-size`
- `--subtitle-color`
- `--subtitle-outline-color`
- `--subtitle-outline-width`
- `--subtitle-position`
- `--subtitle-margin-v`
- `--subtitle-bold`
- `--bilingual-chinese-position`
- `--bilingual-english-position`

### preview-subtitles
示例：

```bash
uv run translip preview-subtitles \
  --input-video ./test_video/example.mp4 \
  --subtitle ./output-pipeline/ocr-translate/ocr_subtitles.en.srt \
  --font-family "Arial" \
  --font-size 28 \
  --position bottom
```

## 后续建议

当前先把功能收敛在“字幕烧录到成品视频”。
后续若你要把这块做顺，还可以继续演进：

1. 前端做一个成品导出面板
2. 预览页面支持切换 OCR/ASR 字幕来源
3. 双语模式支持更细粒度模板（英文上方、英文下三分之一、居中等）
4. 允许输出外挂字幕版（不烧录，只附 `.srt/.ass`）
5. 增加样式 preset（短视频、横屏视频、会议录屏）

## 我对产品结构的建议

我建议最终把“最终产物”明确拆成三层心智：

1. **音频产物层**（Task E）
   - dub voice
   - preview mix

2. **字幕产物层**（OCR / ASR / 翻译）
   - 中文源字幕
   - 英文字幕
   - 样式 preset / ASS 中间文件

3. **成品交付层**（Task G）
   - 输出模式
   - 选择视频源 original/clean
   - 选择音轨 preview/dub
   - 选择字幕模式 none/chinese_only/english_only/bilingual
   - 选择字幕来源 ocr/asr

这样以后即使功能继续变复杂，也不会乱到一起。
