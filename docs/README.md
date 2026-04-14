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

## 分任务设计

| 任务 | 设计文档 | 说明 |
| --- | --- | --- |
| Task A | [task-a-speaker-attributed-transcription.md](./task-a-speaker-attributed-transcription.md) | 说话人归因转写 |
| Task B | [task-b-speaker-registry-and-retrieval.md](./task-b-speaker-registry-and-retrieval.md) | 说话人建档与检索 |
| Task C | [task-c-dubbing-script-generation.md](./task-c-dubbing-script-generation.md) | 面向配音的翻译脚本生成 |
| Task D | [task-d-single-speaker-voice-cloning.md](./task-d-single-speaker-voice-cloning.md) | 单说话人声音克隆与合成 |
| Task E | [task-e-timeline-fitting-and-mixing.md](./task-e-timeline-fitting-and-mixing.md) | 时间轴拟合与混音 |
| Task F | [task-f-pipeline-and-engineering-orchestration.md](./task-f-pipeline-and-engineering-orchestration.md) | 编排、缓存与状态跟踪 |
| Task G | [task-g-final-video-delivery.md](./task-g-final-video-delivery.md) | 最终视频交付与导出 |

## 测试与验证报告

| 任务 | 测试报告 | 说明 |
| --- | --- | --- |
| Task A | [task-a-test-report.md](./task-a-test-report.md) | 转写链路验证 |
| Task B | [task-b-test-report.md](./task-b-test-report.md) | 声纹建档与匹配验证 |
| Task C | [task-c-test-report.md](./task-c-test-report.md) | 本地和 API 翻译后端验证 |
| Task D | [task-d-test-report.md](./task-d-test-report.md) | Qwen3-TTS 合成验证 |
| Task E | [task-e-test-report.md](./task-e-test-report.md) | 时间贴合与混音验证 |
| Task F | [task-f-test-report.md](./task-f-test-report.md) | 编排、缓存和状态验证 |
| Task G | [task-g-test-report.md](./task-g-test-report.md) | 视频交付验证 |

说明：

- 大部分设计文档为中文
- `task-e-test-report.md`、`task-f-test-report.md`、`task-g-test-report.md` 当前为英文验证记录

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
