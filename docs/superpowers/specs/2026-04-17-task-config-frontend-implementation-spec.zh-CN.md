# 任务配置体验重构：前端实现清单与视觉约束

- 项目: `translip`
- 文档状态: Draft v1
- 创建日期: 2026-04-17
- 关联文档:
  - [任务配置体验重构：从“参数配置”转向“结果驱动”的产品与交互方案](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-17-task-config-product-ux-redesign.zh-CN.md)
  - [任务配置体验重构：页面级内容与参数规格](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/docs/superpowers/specs/2026-04-17-task-config-page-level-spec.zh-CN.md)

---

## 1. 这份文档解决什么问题

前两份文档已经把产品方向和页面级职责讲清楚了，这一份文档进一步回答：

1. 前端应该按什么顺序改
2. 每个页面具体改哪些模块
3. 哪些组件可以复用，哪些组件需要新建
4. 最重要的一点：**如何在重构信息架构的同时，完全保持当前后台的视觉风格**

这份文档是给前端实现和评审用的，重点是“怎么落”，不是再讨论“要不要改”。

---

## 2. 视觉约束：必须完全沿用现有后台风格

这部分是硬约束，不是建议。

## 2.1 总原则

本次重构允许：

- 重组页面信息结构
- 调整模块顺序
- 替换字段入口
- 新增抽屉 / 弹层 / Tab / 卡片模块

本次重构不允许：

- 更换整体视觉语言
- 引入与当前后台明显不一致的设计风格
- 为了“更高级”而使用新的配色体系或夸张装饰
- 做成营销页、作品集页、品牌展示页的视觉风格

一句话：

> 这是一次信息架构重构，不是一次视觉改版。

## 2.2 当前视觉语言必须保持的基线

根据现有 `MainLayout`、`Sidebar`、`Header`、`TaskListPage`、`DashboardPage`、`TaskDetailPage` 等组件，当前后台的视觉基线很明确：

### 布局基线

- 主背景：`bg-slate-50`
- 顶部栏：白底 + `border-slate-200`
- 左侧栏：`bg-slate-900`
- 页面容器：居中、`max-w-*`、外部留白 `p-6`
- 内容组织：卡片式分区，不是大面积无边界布局

### 表面层级

- 一级表面：白色卡片 `bg-white`
- 卡片边框：`border-slate-200`
- 轻阴影：`shadow-sm`
- 圆角主规格：`rounded-xl`
- 次级圆角：`rounded-lg` / `rounded-md`

### 主色与状态色

- 主色：蓝色链路，优先 `blue-600 / blue-500 / blue-50`
- 中性色：`slate-*`
- 成功态：`emerald-*`
- 警告态：`amber-*`
- 失败态：`red-*` 或 `rose-*`

### 字体与信息密度

- 字体继续使用现有项目默认栈
- 不引入新的品牌字体
- 标题层级保持当前管理后台风格：
  - 页面标题：`text-2xl`
  - 卡片标题：`text-base` 或 `text-sm font-semibold`
  - 辅助标签：`text-xs uppercase tracking-widest text-slate-400`

### 动效基线

- 仅保留现有级别的轻交互反馈：
  - hover 背景色变化
  - 进度条过渡
  - 状态点闪烁
  - 展开/收起轻动画
- 不引入大面积 motion 或夸张动画

## 2.3 明确禁止的视觉变化

以下内容全部禁止：

- 大面积渐变背景替换当前后台背景
- 高饱和撞色面板
- 大号插画式 hero 区
- 玻璃拟态、毛玻璃大面积叠层
- 强品牌风 landing page 视觉
- 紫色偏置、黑金风、赛博风等明显另类方向
- 与现有边框、圆角、阴影体系不一致的强风格组件

## 2.4 允许的小范围视觉增强

在不改变风格前提下，只允许做这些增强：

- 更清晰的卡片分组
- 更好的 CTA 层级
- 更清楚的空状态
- 更清楚的阻塞提示
- 更统一的 Badge / 状态块 / 摘要卡

这些增强必须看起来像“现有系统自然长出来的”，而不是“换了一个设计师”。

---

## 3. 组件复用策略

## 3.1 现有组件必须优先复用

优先复用：

- `PageContainer`
- `Sidebar`
- `Header`
- `StatusBadge`
- `ProgressBar`
- `PipelineGraph`

以及现有页面中已经形成的表现模式：

- 白卡片 + 灰边框 + 轻阴影
- 顶部标题栏 + 右侧主按钮
- 表格型列表
- 二级说明文案使用 `text-slate-400/500`

## 3.2 建议新增的组件

建议新增，但视觉上必须继承现有风格：

- `IntentCardGroup`
- `TaskSummaryCard`
- `RecommendationPanel`
- `AssetStatusGrid`
- `ExportReadinessCard`
- `ExportWizardDrawer`
- `ExportProfileCardGroup`
- `SubtitleStylePresetPicker`
- `TechnicalDetailsAccordion`

这些新组件的样式基础应继续使用：

- `bg-white`
- `border border-slate-200`
- `rounded-xl`
- `shadow-sm`
- `text-slate-*`
- `bg-blue-50 / bg-emerald-50 / bg-amber-50` 作为轻提示底色

## 3.3 不建议新引入的 UI 风格组件

本轮不建议为了这次改版额外引入新的视觉组件体系，比如：

- 完整新的 design system
- 与当前样式差异明显的炫酷分段导航
- 花哨的步骤条组件

如果要做步骤条，也要做成当前后台的简洁版本，而不是引入完全不同的 UI 语言。

---

## 4. 路由级实现范围

本轮主要涉及这些页面或模块：

- `/`
- `/tasks`
- `/tasks/new`
- `/tasks/:id`
- `/settings`

以及新增：

- `TaskExportWizard` 抽屉 / 弹层模块

---

## 5. Dashboard 实现清单

## 5.1 改造目标

Dashboard 继续保持“管理后台首页”的样子，不做视觉重构，只补足更有行动意义的信息。

## 5.2 保留现有结构

保留：

- 顶部标题 + 新建任务按钮
- 统计卡片
- Active tasks 区块
- Recent completed 区块
- 空状态版式

## 5.3 需要新增的内容

### 新增统计项

在当前统计卡片中新增：

- 待导出任务数

可选：

- 导出受阻任务数

### Active tasks 区块新增信息

当前活跃任务卡片中增加：

- 结果类型标签
- 导出状态标签
- 当前推荐动作

例如：

- `双语审片版`
- `待导出`
- `下一步：导出成品`

### 新增“待处理任务”排序

Dashboard 中的任务排序调整为：

1. 失败且可恢复
2. 已完成待导出
3. 运行中
4. pending

## 5.4 实现边界

Dashboard 不新增配置入口。

不允许：

- 在首页直接改任务配置
- 在首页展开导出表单

## 5.5 受影响文件

主要文件：

- [DashboardPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/DashboardPage.tsx)

可能新增的小组件：

- `components/task/TaskActionHint.tsx`
- `components/task/TaskIntentBadge.tsx`

---

## 6. 任务列表页实现清单

## 6.1 改造目标

任务列表页继续保持“表格管理页”风格，只增强信息和筛选，不改成卡片流或别的风格。

## 6.2 保留现有结构

保留：

- 顶部标题 + 主按钮
- 顶部筛选栏
- 白底表格
- 分页
- 行 hover 与删除动作

## 6.3 需要新增的列

建议新增：

- 结果类型
- 当前阶段
- 导出状态

列顺序建议：

1. 选择框
2. 任务名称
3. 结果类型
4. 状态
5. 进度
6. 语言方向
7. 当前阶段
8. 导出状态
9. 创建时间
10. 操作

## 6.4 需要新增的筛选

新增：

- `output_intent` 筛选
- `export_status` 筛选

保持现有按钮组 / 搜索框风格，不要换成新的重型筛选器 UI。

## 6.5 行内动作增强

增加条件性快捷动作：

- 可导出任务：显示 `导出`
- 失败任务：显示 `重跑`
- 所有任务：保留 `删除`

这些动作仍然维持当前小型文字按钮或 icon 按钮风格。

## 6.6 实现边界

不允许：

- 在列表中直接出现复杂展开行
- 在列表中嵌入导出配置面板

## 6.7 受影响文件

主要文件：

- [TaskListPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/TaskListPage.tsx)

---

## 7. 新建任务页实现清单

## 7.1 核心改造目标

把当前“按技术阶段堆表单”的页面，改成“按用户决策顺序组织”的页面。

但视觉上仍然保持：

- 白卡片分区
- 浅灰边框
- 轻量说明块
- 右侧摘要卡

## 7.2 新建页结构重排

建议改成以下结构：

1. 页面标题
2. 顶部步骤条
3. 左侧主内容列
4. 右侧固定摘要列

### 左侧主内容列模块

- 模块 A：素材与语言
- 模块 B：成品目标
- 模块 C：质量与高级控制

### 右侧摘要列模块

- 本次任务摘要
- 系统推荐说明
- 风险提示
- 主 CTA

## 7.3 现有组件可直接保留的部分

可保留：

- 步骤条整体表现形式
- `Field / Select / TextInput / Checkbox / SectionCard / ConfirmRow`
- 媒体探测交互

但它们的使用方式要变。

## 7.4 需要删除或迁出的内容

从新建页彻底移出：

- 所有字幕样式字段
- 任何导出期样式控制
- 任何“预览字幕”型参数

这些必须不再出现在 `NewTaskPage` 里。

## 7.5 需要新增的模块

### `IntentCardGroup`

用于展示 4 个成品目标卡片：

- 英文配音成片
- 中英双语审片版
- 英文字幕版
- 快速验证版

要求：

- 外观沿用当前卡片体系
- 选中态使用 `border-blue-500 bg-blue-50`
- 非选中态保持 `bg-white border-slate-200`

### `TaskSummaryCard`

右侧摘要卡，复用当前确认页风格，但改为实时更新，而不是只在最后一步展示。

### `AdvancedSettingsAccordion`

承载：

- 更多设置
- 开发者设置

手风琴样式必须简洁，延续当前后台折叠区的风格，不要花哨。

## 7.6 参数分组落地

### 默认可见

- `name`
- `input_path`
- `source_lang`
- `target_lang`
- `output_intent`
- `quality_preset`

### 更多设置

- `translation_backend`
- `tts_backend`
- `device`
- `use_cache`
- `keep_intermediate`
- `save_as_preset`
- `preset_name`

### 开发者设置

- `template`
- `run_from_stage`
- `run_to_stage`
- `subtitle_source`
- `video_source`
- `audio_source`
- `separation_mode`
- `separation_quality`
- `asr_model`
- `condense_mode`
- `fit_policy`
- `mix_profile`
- `background_gain_db`

## 7.7 视觉实现要求

### 摘要卡

摘要卡不允许做成彩色大面板。

建议：

- `bg-white`
- `border border-slate-200`
- `rounded-xl`
- `shadow-sm`

风险提示行可以用：

- `bg-amber-50 border-amber-200 text-amber-700`

### 成品目标卡片

允许增强选中反馈，但不能做成产品官网式大 Banner。

推荐：

- 图标 + 标题 + 一行说明 + 2-3 个 badge
- 高度统一
- 不使用大面积渐变

## 7.8 受影响文件

主要文件：

- [NewTaskPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/NewTaskPage.tsx)

建议新增组件：

- `components/task/IntentCardGroup.tsx`
- `components/task/TaskSummaryCard.tsx`
- `components/task/AdvancedSettingsAccordion.tsx`

---

## 8. 任务详情页实现清单

## 8.1 核心改造目标

当前详情页最大的问题不是不好看，而是信息目标混在一起。

这次要做的是把它重构成：

- 任务状态中心
- 素材状态中心
- 动作入口中心

而不是“进度图 + 大块导出编辑区”的拼接页。

## 8.2 保留现有视觉骨架

保留：

- 顶部返回链接
- 外层大卡片容器
- 标题区
- 进度区
- 工作流图区
- 底部操作区

## 8.3 需要重构的区块

### 当前 Delivery Composer 区块

建议从正文中间移除，不再默认展示完整表单。

替换为：

- `ExportReadinessCard`
- `RecentExportCard`
- `OpenExportWizardButton`

### 新增“问题与建议”区块

展示：

- 阻塞问题
- 系统建议
- 快捷动作

UI 形式建议：

- 仍然使用白底卡片
- 每条建议是一个轻提示行或小卡片
- 颜色只用轻提示底色，不做夸张警报样式

## 8.4 推荐的新详情页结构

1. 顶部任务摘要
2. 当前推荐动作卡
3. 素材状态卡
4. 工作流图区
5. 问题与建议卡
6. 最近导出结果卡
7. 技术细节与运行操作

## 8.5 需要新增的只读摘要

### 任务摘要中增加

- `output_intent` 人话标签
- 导出状态
- 可导出标识

### 素材状态中增加

- 原视频可用性
- 干净视频可用性
- preview 音轨可用性
- dub 音轨可用性
- OCR 字幕可用性
- ASR 字幕可用性

## 8.6 需要新增的组件

建议新增：

- `ExportReadinessCard`
- `AssetStatusGrid`
- `RecommendationPanel`
- `RecentExportCard`
- `TechnicalDetailsAccordion`

### `AssetStatusGrid`

建议表现方式：

- 两列或四列小卡片
- 卡片高度一致
- 状态图标 + 状态文字 + 文件入口

风格必须延续当前白卡、浅边框体系。

## 8.7 重跑和删除区

保留现有按钮风格，不改成全新操作条。

仅增强：

- `复制为新任务`
- `补齐缺失素材`

## 8.8 技术细节区

建议新增折叠区承载：

- `pipeline_config`
- 模板
- 阶段范围
- 各阶段细节
- artifact 路径

默认折叠，不应成为主视图。

## 8.9 受影响文件

主要文件：

- [TaskDetailPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/TaskDetailPage.tsx)

建议新增组件：

- `components/task/ExportReadinessCard.tsx`
- `components/task/AssetStatusGrid.tsx`
- `components/task/RecommendationPanel.tsx`
- `components/task/RecentExportCard.tsx`
- `components/task/TechnicalDetailsAccordion.tsx`

---

## 9. 导出向导实现清单

## 9.1 组件形态

建议采用：

- 右侧抽屉

不建议：

- 跳转独立页面
- 中间正文常驻大表单

原因：

- 与详情页关系更自然
- 不打断用户上下文
- 能保留“看状态 -> 导出”的流畅路径

## 9.2 抽屉视觉约束

抽屉必须继续使用现有后台视觉语言：

- 白底
- 灰色边线
- 清晰标题区
- 分段卡片
- 轻量按钮层级

不要做成营销式 wizard，也不要引入夸张进度引导动效。

## 9.3 抽屉结构

建议分成 4 段，不一定非要强制逐页跳转，也可以是单页分段式：

1. 导出版本
2. 素材来源
3. 字幕样式
4. 预览与导出

如果做单页分段式，仍然要保证顺序固定。

## 9.4 需要新增的组件

- `TaskExportWizard`
- `ExportProfileCardGroup`
- `ExportSourceSelector`
- `SubtitleStylePresetPicker`
- `SubtitleAdvancedEditor`
- `ExportPreviewPanel`

## 9.5 Step 1：导出版本

用卡片单选，不用原始枚举下拉。

选中态依旧使用现有蓝色轻高亮。

推荐卡片信息：

- 标题
- 简述
- 画面/音轨/字幕偏好摘要
- 是否推荐

## 9.6 Step 2：素材来源

保持表单简洁，不做复杂自由组合器。

建议每类资源使用现有输入风格：

- 标签
- 单选按钮组 / select
- 说明文案
- 禁用态说明

禁用态视觉必须延续现有系统风格：

- `text-slate-400`
- `bg-slate-50`
- `border-slate-200`

不要用大面积警报色。

## 9.7 Step 3：字幕样式

### 第一层

样式 preset 卡片。

### 第二层

高级微调区域，默认收起。

高级微调输入控件仍沿用当前输入体系：

- 输入框
- 下拉
- 开关
- 颜色选择器

注意：

- 颜色选择器视觉也要朴素
- 不要引入花哨色盘组件

## 9.8 Step 4：预览与导出

### 预览区域

使用现有视频播放器卡片风格：

- 白卡片容器
- 黑色视频区域
- 底部文件列表

### 导出按钮区

保持现有 CTA 层级：

- 主按钮蓝 / 绿色轻强调
- 次按钮白底灰边

不需要做特别复杂的底部工具栏。

## 9.9 受影响文件

建议新增：

- `components/task/export/TaskExportWizard.tsx`
- `components/task/export/ExportProfileCardGroup.tsx`
- `components/task/export/ExportSourceSelector.tsx`
- `components/task/export/SubtitleStylePresetPicker.tsx`
- `components/task/export/SubtitleAdvancedEditor.tsx`
- `components/task/export/ExportPreviewPanel.tsx`

并改动：

- [TaskDetailPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/TaskDetailPage.tsx)

---

## 10. 设置页实现清单

## 10.1 核心改造目标

设置页继续保持“简单系统设置页”的风格，但扩展为真正的默认值管理页。

## 10.2 视觉约束

不引入新的花哨 Tab 组件，建议仍然用：

- 顶部简洁分段按钮
- 或左侧二级导航

整体仍然是白底卡片分区。

## 10.3 推荐结构

1. 默认偏好
2. 常用方案
3. 系统环境
4. 开发者选项

## 10.4 默认偏好模块

新增可编辑项：

- 默认语言对
- 默认结果类型
- 默认质量档位
- 默认翻译后端
- 默认 TTS 后端
- 默认设备
- 默认缓存行为
- 默认预览时长
- 默认字幕样式 preset

## 10.5 常用方案模块

管理两类 preset：

- 新建任务 preset
- 导出 preset

注意：这里的列表和编辑器都必须沿用后台朴素管理风格，不做视觉展示卡墙。

## 10.6 开发者选项模块

只保留几个开关：

- 是否启用开发者模式
- 是否默认显示技术细节
- 是否默认展开导出高级微调

## 10.7 受影响文件

主要文件：

- [SettingsPage.tsx](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/pages/SettingsPage.tsx)

建议新增组件：

- `components/settings/SettingsTabs.tsx`
- `components/settings/DefaultPreferencesForm.tsx`
- `components/settings/PresetManager.tsx`
- `components/settings/DeveloperOptionsForm.tsx`

---

## 11. 类型与状态实现建议

## 11.1 前端类型层建议新增

建议在 [index.ts](/Users/masamiyui/OpenSoureProjects/Forks/video-voice-separate/frontend/src/types/index.ts) 中新增或补齐：

- `output_intent`
- `quality_preset`
- `export_profile`
- `subtitle_style_preset`
- `export_readiness`
- `export_blockers`
- `asset_summary`
- `last_export_summary`

## 11.2 不建议前端自己拼复杂业务语义

前端可以做轻映射，但不要把所有推荐逻辑都写死在页面组件里。

建议后端或接口层尽量返回：

- 推荐导出版本
- 当前导出就绪状态
- 当前缺失素材
- 建议动作

这样页面更稳，也更容易保持一致。

## 11.3 页面状态管理建议

### 新建页

局部 state + React Query 即可，不需要引入新的复杂状态管理。

### 详情页

任务详情查询结果 + 导出状态派生数据。

### 导出向导

使用独立局部 state 管理交付配置草稿，提交时再调用导出接口。

不要把导出向导草稿塞回详情页主 state，避免页面越来越乱。

---

## 12. API 与数据配合建议

## 12.1 为了支撑新 UI，建议后端补齐的读模型

任务详情读取建议新增或补齐：

- `output_intent`
- `quality_preset`
- `export_readiness.status`
- `export_readiness.recommended_profile`
- `export_readiness.blockers[]`
- `asset_summary`
- `last_export_summary`

## 12.2 前端短期兼容策略

如果后端暂时还没补全，前端可以短期做派生：

- 从 `config` 推断 `output_intent`
- 从 artifacts 推断 `asset_summary`
- 从 `delivery_config` 推断最近导出摘要

但这应该只是过渡方案。

---

## 13. 验收标准

## 13.1 结构层验收

- 新建任务页不再出现导出样式参数
- 详情页不再默认展示完整 Delivery Composer 大表单
- 导出配置集中到导出向导
- 设置页承担全局默认值

## 13.2 视觉层验收

- 页面整体仍然明显属于当前同一后台系统
- 主背景、卡片、边框、主色、按钮层级保持一致
- 没有引入突兀的新视觉风格
- 新组件放进现有页面中不会显得“像外来的”

## 13.3 使用层验收

- 用户在新建页能先理解“我要什么结果”
- 用户在详情页能一眼看懂“现在缺什么”
- 用户在导出向导能顺着“版本 -> 来源 -> 样式 -> 预览”完成操作

---

## 14. 推荐开发顺序

## Phase 1：信息结构先落地

1. 新建页重排
2. 详情页移除内嵌导出大表单
3. 新增导出向导骨架

## Phase 2：补状态与摘要

1. Dashboard 增加待处理视角
2. 任务列表补结果类型和导出状态
3. 详情页补素材状态、阻塞状态、推荐动作

## Phase 3：补默认值和预设

1. 设置页扩展默认偏好
2. 加入业务 preset 与导出 preset
3. 补开发者选项

---

## 15. 最终结论

这轮前端改造最重要的边界有两个：

1. **结构要重做**
2. **风格不要乱动**

前者解决“为什么难用”，后者解决“为什么不能做得像另一个产品”。

真正正确的落地方式应该是：

- 用现有后台的卡片、边框、色彩、标题层级、按钮层级
- 承载新的信息架构
- 让用户觉得“产品更清楚了”
- 而不是让用户觉得“整个前端像换了一套设计”
