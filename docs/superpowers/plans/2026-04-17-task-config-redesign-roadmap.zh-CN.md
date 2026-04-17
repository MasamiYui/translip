# 任务配置体验重构：研发路线图与工作拆解

- 项目: `translip`
- 文档状态: Draft v1
- 创建日期: 2026-04-17
- 关联文档:
  - [任务配置体验重构：从“参数配置”转向“结果驱动”的产品与交互方案](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-17-task-config-product-ux-redesign.zh-CN.md)
  - [任务配置体验重构：页面级内容与参数规格](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-17-task-config-page-level-spec.zh-CN.md)
  - [任务配置体验重构：前端实现清单与视觉约束](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-17-task-config-frontend-implementation-spec.zh-CN.md)
  - [任务配置体验重构：交互状态与文案规格](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-17-task-config-interaction-states-copy-spec.zh-CN.md)

---

## 1. 目标

这份路线图不是产品说明，而是把前面几份设计文档落成一个可执行的研发方案。

核心目标有三个：

1. 让这次重构可以按阶段推进，而不是大爆炸改造
2. 明确哪些工作需要前后端配合，哪些可以前端先做
3. 让最终交付结果既符合新的信息架构，又完全保持现有后台风格

---

## 2. 改造范围

## 2.1 前端范围

涉及页面：

- `/`
- `/tasks`
- `/tasks/new`
- `/tasks/:id`
- `/settings`

涉及模块：

- 新建任务页的意图化重构
- 任务详情页的状态中心重构
- 导出向导抽屉
- Dashboard / 列表的信息增强
- 设置页的默认值与预设管理
- i18n 文案结构重组

## 2.2 后端范围

涉及读模型和接口：

- `TaskRead`
- 任务列表返回结构
- 任务详情返回结构
- 导出相关接口
- 可导出状态与素材摘要
- 预设与默认值管理

## 2.3 非目标

本轮不做：

- 新视觉体系
- 登录与权限系统
- 多用户配置隔离
- 与这次任务无关的 pipeline 核心算法改造

---

## 3. 基本实施原则

## 3.1 页面结构重构优先，视觉风格稳定优先

顺序上要优先解决：

- 用户决策顺序
- 页面职责边界
- 参数归位

而不是先折腾样式。

## 3.2 读模型先于 UI 细节

如果任务详情没有：

- `output_intent`
- `export_readiness`
- `asset_summary`
- `last_export_summary`

前端就会被迫在页面里做很多不稳定推断。

所以本轮要尽量先补读模型，再补 UI。

## 3.3 先让流程顺，再让能力全

优先级顺序：

1. 新建任务顺
2. 详情页判断顺
3. 导出向导顺
4. 默认值与 preset 顺

## 3.4 保持现有风格是验收项，不是建议项

验收时必须检查：

- 背景
- 卡片
- 按钮
- 边框
- 色彩
- 排版

不能出现“结构对了，但像另一个产品”的结果。

---

## 4. 建议里程碑

建议拆成 5 个里程碑。

## M0：数据与读模型准备

## M1：新建任务页意图化改造

## M2：任务详情页状态中心改造

## M3：导出向导与交付配置收拢

## M4：设置页默认值 / 预设 / Dashboard / 列表收尾

每个里程碑都应该能独立验收，避免跨太多页面一起炸。

---

## 5. M0：数据与读模型准备

## 5.1 目标

为前端新界面提供更稳定的读模型，减少页面内硬推断。

## 5.2 后端新增建议

建议在任务读模型中补齐以下字段：

### 任务级用户语义字段

- `output_intent`
- `quality_preset`

### 导出就绪状态

- `export_readiness.status`
- `export_readiness.recommended_profile`
- `export_readiness.blockers[]`
- `export_readiness.actions[]`

### 素材摘要

- `asset_summary.video.original`
- `asset_summary.video.clean`
- `asset_summary.audio.preview`
- `asset_summary.audio.dub`
- `asset_summary.subtitles.ocr_translated`
- `asset_summary.subtitles.asr_translated`

### 最近导出摘要

- `last_export_summary.profile`
- `last_export_summary.created_at`
- `last_export_summary.files[]`
- `last_export_summary.config_summary`

## 5.3 前端类型工作

涉及文件：

- [frontend/src/types/index.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/types/index.ts)
- [frontend/src/api/tasks.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/api/tasks.ts)

建议新增：

- `TaskOutputIntent`
- `TaskQualityPreset`
- `TaskExportProfile`
- `TaskAssetSummary`
- `TaskExportReadiness`
- `TaskExportBlocker`
- `TaskLastExportSummary`

## 5.4 验收标准

- 任务详情返回结构里不再只有 `config + delivery_config`
- 前端不需要仅靠 artifact 路径名猜所有状态

---

## 6. M1：新建任务页意图化改造

## 6.1 目标

把新建页从“技术配置大表单”改成“按用户决策顺序组织”的页面。

## 6.2 页面目标

用户需要在新建页完成的决策只有：

1. 输入什么视频
2. 要什么结果
3. 用什么质量档位
4. 是否需要高级控制

## 6.3 具体任务拆解

### Task 1：调整步骤名称与顺序

目标：

- 将步骤改为“素材与语言 / 成品目标 / 质量与设置 / 确认创建”

涉及文件：

- [frontend/src/pages/NewTaskPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/NewTaskPage.tsx)
- [frontend/src/i18n/messages.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/i18n/messages.ts)

### Task 2：新增 `output_intent` 卡片选择

目标：

- 用结果卡片替换模板下拉作为主要入口

建议新增组件：

- `components/task/IntentCardGroup.tsx`

### Task 3：新增右侧实时摘要卡

目标：

- 摘要从“最后一步确认”改为“全程实时解释”

建议新增组件：

- `components/task/TaskSummaryCard.tsx`

### Task 4：将高级设置拆层

目标：

- 默认只显示必要项
- “更多设置”收纳通用高级参数
- “开发者设置”收纳模板、阶段、链路控制

建议新增组件：

- `components/task/AdvancedSettingsAccordion.tsx`

### Task 5：彻底移除导出期字段

目标：

- 新建页不再出现任何字幕样式字段
- 不再出现 Delivery Composer 相关心智

## 6.4 依赖关系

前端可先行，哪怕后端暂时还没有 `output_intent`，也可以先在前端内部映射。

但最终还是要依赖 M0 补齐正式字段。

## 6.5 测试要求

### 单测 / 组件测试

- 卡片选择切换后摘要正确变化
- 开发者设置默认关闭
- 导出期字段不再出现

### Playwright

- 新建页默认流程可以创建任务
- 新建页高级设置可展开
- 新建页不会出现字体、颜色、描边等字段

---

## 7. M2：任务详情页状态中心改造

## 7.1 目标

把任务详情页改成：

- 状态中心
- 素材中心
- 推荐动作中心

而不是“进度 + 大块导出表单”。

## 7.2 具体任务拆解

### Task 1：引入导出就绪摘要

目标：

- 在标题区或顶部卡中显示：
  - 当前是否可导出
  - 推荐动作
  - 当前阻塞原因

建议新增组件：

- `components/task/ExportReadinessCard.tsx`

### Task 2：新增素材状态视图

目标：

- 从用户视角展示音频、字幕、视频、成品状态

建议新增组件：

- `components/task/AssetStatusGrid.tsx`

### Task 3：新增问题与建议区块

目标：

- 把“缺什么素材”和“下一步该做什么”显式化

建议新增组件：

- `components/task/RecommendationPanel.tsx`

### Task 4：把现有 Delivery Composer 从正文移除

目标：

- 正文不再默认展示完整导出表单
- 改为“导出成品”入口卡 + 最近导出摘要

建议新增组件：

- `components/task/RecentExportCard.tsx`

### Task 5：将技术细节折叠处理

目标：

- 保留技术能力
- 不让技术细节抢占主视图

建议新增组件：

- `components/task/TechnicalDetailsAccordion.tsx`

## 7.3 依赖关系

强依赖 M0 的读模型增强。

如果 M0 未完成，前端可以短期根据 artifact 推断素材状态，但建议仅作临时方案。

## 7.4 测试要求

### 单测 / 组件测试

- 各种 `export_readiness` 状态渲染正确
- 不同 blocker 会显示不同 CTA
- 无导出记录时 RecentExportCard 正确显示空状态

### Playwright

- 已完成且可导出任务显示 `导出成品`
- 已完成但受阻任务显示 `补齐缺失素材`
- 失败任务显示 `从此阶段重跑`

---

## 8. M3：导出向导与交付配置收拢

## 8.1 目标

建立导出成品的唯一入口，把所有交付参数收拢到抽屉中。

## 8.2 具体任务拆解

### Task 1：新增导出抽屉骨架

建议新增：

- `components/task/export/TaskExportWizard.tsx`

功能：

- 打开 / 关闭
- 初始化任务交付配置
- 管理向导内局部草稿状态

### Task 2：导出版本选择

建议新增：

- `components/task/export/ExportProfileCardGroup.tsx`

功能：

- 展示导出版本卡
- 根据 `output_intent` 自动推荐默认值

### Task 3：素材来源选择

建议新增：

- `components/task/export/ExportSourceSelector.tsx`

功能：

- 视频来源
- 音轨来源
- 英文字幕来源
- 缺失资源禁用提示

### Task 4：样式 preset 与高级微调

建议新增：

- `components/task/export/SubtitleStylePresetPicker.tsx`
- `components/task/export/SubtitleAdvancedEditor.tsx`

功能：

- 预设卡片
- 高级字段折叠
- 颜色 / 字体 / 位置等微调

### Task 5：预览与导出面板

建议新增：

- `components/task/export/ExportPreviewPanel.tsx`

功能：

- 预览生成
- 预览视频展示
- 导出结果展示
- 失败与重试提示

## 8.3 API 配套建议

现有接口：

- `/api/tasks/{id}/subtitle-preview`
- `/api/tasks/{id}/delivery-compose`

建议后续补充：

- 返回更清晰的导出摘要
- 返回最近导出记录
- 返回导出版本推荐

## 8.4 测试要求

### 单测 / 组件测试

- 导出版本切换后素材推荐变化正确
- 缺失素材时选项禁用与文案正确
- 样式 preset 切换会更新默认样式

### Playwright

- 打开导出向导
- 生成 10 秒预览
- 导出最终成品
- 导出完成后详情页正确刷新

---

## 9. M4：设置页、Dashboard、任务列表收尾

## 9.1 目标

补齐系统层默认值、业务 preset 和全局任务运营视角。

## 9.2 Dashboard 任务

### Task 1：新增待导出统计

### Task 2：活跃任务卡增加结果类型与推荐动作

### Task 3：排序按“最需要处理”优先

## 9.3 任务列表任务

### Task 1：新增结果类型列

### Task 2：新增导出状态列

### Task 3：新增 `output_intent` 与导出状态筛选

### Task 4：新增 `复制为新任务`

## 9.4 设置页任务

### Task 1：拆成 4 个模块或 Tab

- 默认偏好
- 常用方案
- 系统环境
- 开发者选项

### Task 2：补全默认值表单

### Task 3：补业务 preset 与导出 preset 管理

### Task 4：补开发者选项

## 9.5 测试要求

### 单测 / 组件测试

- 设置页默认值表单保存逻辑
- 预设列表与删除
- Dashboard 状态统计渲染

### Playwright

- 修改默认偏好后，新建任务默认值同步变化
- 任务列表筛选正确工作

---

## 10. 组件级拆解建议

## 10.1 新增组件清单

### 通用 / 任务域

- `IntentCardGroup`
- `TaskSummaryCard`
- `AdvancedSettingsAccordion`
- `TaskIntentBadge`
- `TaskActionHint`
- `AssetStatusGrid`
- `ExportReadinessCard`
- `RecommendationPanel`
- `RecentExportCard`
- `TechnicalDetailsAccordion`

### 导出域

- `TaskExportWizard`
- `ExportProfileCardGroup`
- `ExportSourceSelector`
- `SubtitleStylePresetPicker`
- `SubtitleAdvancedEditor`
- `ExportPreviewPanel`

### 设置域

- `SettingsTabs`
- `DefaultPreferencesForm`
- `PresetManager`
- `DeveloperOptionsForm`

## 10.2 组件优先级

优先级从高到低：

1. `IntentCardGroup`
2. `TaskSummaryCard`
3. `ExportReadinessCard`
4. `TaskExportWizard`
5. `AssetStatusGrid`
6. `RecommendationPanel`
7. `SettingsTabs` 及其下属组件

---

## 11. 文件级改动清单

## 11.1 前端主要文件

高优先级改动：

- [frontend/src/pages/NewTaskPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/NewTaskPage.tsx)
- [frontend/src/pages/TaskDetailPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/TaskDetailPage.tsx)
- [frontend/src/pages/TaskListPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/TaskListPage.tsx)
- [frontend/src/pages/DashboardPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/DashboardPage.tsx)
- [frontend/src/pages/SettingsPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/SettingsPage.tsx)
- [frontend/src/types/index.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/types/index.ts)
- [frontend/src/api/tasks.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/api/tasks.ts)
- [frontend/src/i18n/messages.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/i18n/messages.ts)

## 11.2 后端主要文件

高优先级改动：

- [src/translip/server/schemas.py](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/src/translip/server/schemas.py)
- `src/translip/server/routes/tasks.py`
- `src/translip/server/routes/delivery.py`
- `src/translip/server/task_config.py`
- `src/translip/server/task_manager.py`

---

## 12. 建议提交顺序

为了降低风险，建议提交拆成至少 6 次。

## Commit 1：读模型与类型准备

- 后端 schema 补字段
- 前端 types / api 补字段

## Commit 2：新建任务页信息结构改造

- `output_intent`
- 摘要卡
- 高级设置分层

## Commit 3：任务详情页状态中心改造

- 导出就绪状态
- 素材状态
- 问题与建议

## Commit 4：导出向导接入

- 抽屉
- 预览
- 导出流程

## Commit 5：Dashboard / 列表 / 设置页收尾

- 任务运营信息
- 默认偏好
- 预设

## Commit 6：文案与测试收口

- i18n 文案
- 测试补齐
- 样式回归检查

---

## 13. 测试与验证计划

## 13.1 前端单测 / 组件测试

重点测试：

- 新建任务摘要逻辑
- 导出就绪状态渲染
- 导出版本推荐
- 导出抽屉内状态切换
- 设置页默认值回填

## 13.2 端到端测试

建议使用现有 Playwright 链路覆盖：

### Case 1：快速默认创建任务

- 进入新建页
- 选择默认结果类型
- 创建任务
- 跳转到详情页

### Case 2：任务完成后导出

- 打开任务详情
- 进入导出向导
- 生成预览
- 导出成品

### Case 3：缺失素材阻塞

- 打开缺少干净视频的任务
- 验证详情页显示 `补齐缺失素材`
- 验证导出向导中英文字幕版被阻塞或给出替代建议

### Case 4：设置默认值生效

- 修改默认目标语言与结果类型
- 返回新建页
- 验证默认值变化

## 13.3 视觉回归检查

人工检查项：

- 页面背景是否仍是当前后台风格
- 卡片边框与圆角是否统一
- 新增组件是否“像原生后台的一部分”
- 是否出现突兀的新视觉模式

---

## 14. 风险与对策

## 风险 1：前端提前写死过多推导逻辑

问题：

- 后端后续补模型时容易冲突

对策：

- 前端的临时推导写在单独 mapper 中，不散落在页面里

## 风险 2：详情页仍然承担过多职责

问题：

- 容易又把导出向导做回一大块正文表单

对策：

- 明确要求交付配置只存在于抽屉

## 风险 3：风格漂移

问题：

- 新组件写着写着就偏离当前后台

对策：

- PR 评审时单独检查视觉约束文档
- 复用现有卡片和按钮模式

## 风险 4：文案和状态逻辑不同步

问题：

- UI 看起来清楚，但状态文案仍然技术化

对策：

- 按交互状态文档逐项对照
- 把状态和 CTA 文案集中在 i18n 层

---

## 15. 完成定义

以下条件同时满足时，这次改造才算真正完成：

1. 新建任务页不再要求用户在创建时思考导出样式
2. 任务详情页能明确回答“现在有什么、缺什么、下一步做什么”
3. 所有导出参数都收拢到导出向导
4. 设置页承担系统默认值和常用方案管理
5. Dashboard 和列表页能体现“待导出”和“受阻”视角
6. 视觉风格与现有后台保持一致
7. Playwright 能完整验证新建、详情、导出、默认值四条主路径

---

## 16. 最终建议

如果要降低风险、提高推进效率，最好的执行方式是：

1. 先补读模型
2. 再做新建页
3. 再做详情页与导出向导
4. 最后做设置页、Dashboard 和列表页

不要一开始就把所有页面一起改，也不要先从“颜色和风格”下手。

这次真正需要被重构的，是用户决策顺序和页面职责，而不是视觉语言本身。
