# 文档索引

`docs/` 目录保存项目的总体方案、任务设计和验证报告。第一次阅读这个仓库，建议先按下面的顺序看。

## 推荐阅读顺序

1. [../README.md](../README.md)
   仓库总览、安装方式、快速开始和常用命令
2. [speaker-aware-dubbing-plan.md](./speaker-aware-dubbing-plan.md)
   项目的整体目标、技术选型和阶段性路线
3. [speaker-aware-dubbing-task-breakdown.md](./speaker-aware-dubbing-task-breakdown.md)
   从 Task A 到 Task G 的任务拆解与里程碑定义
4. [technical-design.md](./technical-design.md)
   Stage 1 音频分离系统设计
5. [frontend-management-system-design.md](./frontend-management-system-design.md)
   Web 管理界面的产品和工程设计

## 总体设计

| 文档 | 说明 |
| --- | --- |
| [technical-design.md](./technical-design.md) | Stage 1 音频分离设计，包含模型选型、接口和目录约定 |
| [speaker-aware-dubbing-plan.md](./speaker-aware-dubbing-plan.md) | 多说话人、多语种配音系统的总体规划 |
| [speaker-aware-dubbing-task-breakdown.md](./speaker-aware-dubbing-task-breakdown.md) | 全链路任务拆解、验收标准和实施顺序 |
| [frontend-management-system-design.md](./frontend-management-system-design.md) | FastAPI + React 管理界面的设计方案 |
| [project-optimization-analysis.md](./project-optimization-analysis.md) | 从工程实现与用户体验两个维度梳理项目优化方向 |

## 分任务设计

| 任务 | 设计文档 | 说明 |
| --- | --- | --- |
| transcription | [speaker-attributed-transcription.md](./speaker-attributed-transcription.md) | 说话人归因转写 |
| speaker-registry | [speaker-registry-and-retrieval.md](./speaker-registry-and-retrieval.md) | 说话人建档与检索 |
| translation | [dubbing-script-generation.md](./dubbing-script-generation.md) | 面向配音的翻译脚本生成 |
| synthesis | [single-speaker-voice-cloning.md](./single-speaker-voice-cloning.md) | 单说话人声音克隆与合成 |
| render | [timeline-fitting-and-mixing.md](./timeline-fitting-and-mixing.md) | 时间轴拟合与混音 |
| orchestration | [pipeline-and-engineering-orchestration.md](./pipeline-and-engineering-orchestration.md) | 编排、缓存与状态跟踪 |
| delivery | [final-video-delivery.md](./final-video-delivery.md) | 最终视频交付与导出 |

## 测试与验证报告

| 任务 | 测试报告 | 说明 |
| --- | --- | --- |
| transcription | [transcription-test-report.md](./transcription-test-report.md) | 转写链路验证 |
| speaker-registry | [speaker-registry-test-report.md](./speaker-registry-test-report.md) | 声纹建档与匹配验证 |
| translation | [translation-test-report.md](./translation-test-report.md) | 本地和 API 翻译后端验证 |
| synthesis | [synthesis-test-report.md](./synthesis-test-report.md) | Qwen3-TTS 合成验证 |
| render | [render-test-report.md](./render-test-report.md) | 时间贴合与混音验证 |
| orchestration | [orchestration-test-report.md](./orchestration-test-report.md) | 编排、缓存和状态验证 |
| delivery | [delivery-test-report.md](./delivery-test-report.md) | 视频交付验证 |

说明：

- 大部分设计文档为中文
- `render-test-report.md`、`orchestration-test-report.md`、`delivery-test-report.md` 当前为英文验证记录

## 辅助资源

| 文件 | 说明 |
| --- | --- |
| [../config/glossary.example.json](../config/glossary.example.json) | 术语表样例，可用于 Task C 保护专有名词 |
| [../scripts/run_task_a_to_c.py](../scripts/run_task_a_to_c.py) | 从 Stage 1 跑到 Task C 的演示脚本 |
| [../scripts/run_task_a_to_d.py](../scripts/run_task_a_to_d.py) | 从 Stage 1 跑到 Task D 的演示脚本 |
| [../scripts/run_task_a_to_e.py](../scripts/run_task_a_to_e.py) | 从 Stage 1 跑到 Task E 的演示脚本 |

## 如何使用这些文档

- 想快速了解项目：先看 [../README.md](../README.md)
- 想看总体方向：看 [speaker-aware-dubbing-plan.md](./speaker-aware-dubbing-plan.md)
- 想落地某个阶段：直接跳到对应的 Task 设计文档
- 想确认当前实现状态：结合对应的 test report 一起看
