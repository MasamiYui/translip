# Translip 前端 UX/UI 评审工单（2026-06-09）

> **背景**：基于 2026-06-09 对 Translip Web 管理界面的系统性评审产出。
> **评审范围**：[frontend/src/pages](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages) 下 13 个页面 + [frontend/src/components/layout](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout) 下 3 个布局组件。
> **方法**：浏览器实际访问截图 + 源码静态分析。
> **严重程度定义**：
> - **P0**：阻塞关键功能 / 严重可访问性事故 / 严重视觉错乱，必须立刻修复。
> - **P1**：明显影响体验，需排期修复。
> - **P2**：细节优化，可纳入迭代收尾。

---

## 工单总览

| 数量 | P0 | P1 | P2 | 合计 |
|---|---|---|---|---|
| 单页工单 | 8 | 36 | 22 | **66** |
| 横向共性 | 4 | 8 | 0 | **12** |
| 战略级建议 | – | – | – | **6** |

---

## 一、P0 阻塞型工单（本周必须修）

### TICKET-P0-01 · 窄屏导航完全消失（无汉堡菜单）
- **现象**：[MainLayout.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/MainLayout.tsx#L82-L100) 中 `hidden md:block` 同时隐藏了 `Sidebar` 与 `TopNav`，**未提供任何替代触发器**，<768px 视口下用户无法跳转任何页面。
- **位置**：[MainLayout.tsx#L82-L100](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/MainLayout.tsx#L82-L100)、[Sidebar.tsx#L184-L189](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/Sidebar.tsx#L184-L189)
- **影响范围**：全站。
- **建议方案**：在 [Header.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/Header.tsx) 移动断点下增加汉堡按钮 + 抽屉式 `Sidebar`（Drawer），同时 `Sidebar` 改为 `transform: translateX(-100%)` 移动方案。
- **验收**：375px / 768px / 1280px / 1920px 四档截图均能完整导航。

---

### TICKET-P0-02 · 表格中文逐字竖排（全站表格灾难）
- **现象**：在中等宽度（≈875px）下，[TaskListPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/TaskListPage.tsx) / [DashboardPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/DashboardPage.tsx) / [AtomicJobListPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/AtomicJobListPage.tsx) / [EvaluationPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationPage.tsx) 中表格列内容（"成功"、"失败"、"中文→英语"、"31分6秒"）被中文断字规则拆成竖排单字。
- **根因**：表格单元格未设置 `whitespace: nowrap`，列宽未与内容长度对齐，且外层无 `overflow-x-auto` 兜底。
- **建议方案**：
  1. 表格行 `td` 默认 `whitespace-nowrap`，仅"名称""描述"等长文本列允许换行（`max-w-` + `line-clamp`）。
  2. 表格外包 `<div className="overflow-x-auto">`。
  3. <md 断点 `hidden md:table-cell` 隐藏次要列（ID、创建时间、耗时）。
- **验收**：以上 4 个页面在 768/1024/1440 三档宽度均无逐字竖排。

---

### TICKET-P0-03 · 批量删除串行 await + 失败中断 + 无聚合反馈
- **现象**：[TaskListPage handleBulkDelete](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/TaskListPage.tsx#L90-L105) 与 [AtomicJobListPage#L86-L92](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/AtomicJobListPage.tsx#L86-L92) 使用 `for (const id of selected) await deleteMutation.mutateAsync(id)`，一条失败即中断，已删除的不回滚，用户无错误反馈。
- **建议方案**：改为 `Promise.allSettled` 并行；最后 `toast.success("已删除 X 条，失败 Y 条（点击查看详情）")`，失败详情写入 Drawer。
- **验收**：人为构造 1 条失败 + 2 条成功，最终应看到聚合 toast、未删除项重新出现在列表、可重试。

---

### TICKET-P0-04 · 评测列表 N+1 请求
- **现象**：[EvaluationPage SummaryBadge#L200-L209](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationPage.tsx#L200-L209) 每行调用独立 `useQuery(['evaluation-summary', task.id])`，20 行 = 20 个 HTTP 请求；分页/筛选切换又会触发 20 个。
- **建议方案**：
  - **首选**：后端 `evaluationApi.list()` 直接返回 summary 字段。
  - **备选**：前端 `evaluationApi.listSummaries(ids[])` 批量接口。
- **验收**：Chrome DevTools Network 面板在加载评测列表时，仅 1-2 次请求即可填充全部 badge。

---

### TICKET-P0-05 · 新建任务提交按钮无 loading + 防双击
- **现象**：[NewTaskPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/NewTaskPage.tsx) 提交后 `createMutation.isPending` 期间按钮文案不变、未禁用，连点会产生重复任务。
- **建议方案**：`disabled={createMutation.isPending}` + `<Loader2 className="animate-spin" />` + 成功后立刻 `navigate(/tasks/:id)` 防止再次提交。
- **验收**：网速被人工 throttle 至 Slow 3G，连击 5 次按钮只能创建 1 个任务。

---

### TICKET-P0-06 · 删除作品仅 `confirm()` 无强确认
- **现象**：[WorksPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/WorksPage.tsx) 删除作品使用原生 `confirm`，但作品下挂载多个任务和角色，删除无连带提示。
- **建议方案**：使用 `<DestructiveDialog>`，列出"将影响 N 个任务、M 个角色"，并要求用户输入作品名称才能确认。
- **验收**：删除关联了任务的作品时，必须输入作品名才能点击"确认删除"。

---

### TICKET-P0-07 · 博客封面 hero 区窄屏严重错位
- **现象**：[BlogListPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/BlogListPage.tsx) 首屏 hero 文章在窄屏下封面图被截断、标题"上云配音,最贵的从来不是合成"换行混乱、副文字位置错位（实测截图）。
- **建议方案**：hero 区改为 `flex-col md:flex-row`；封面图 `aspect-ratio` 控制；标题 `text-clamp` 限制行数；移除绝对定位的子元素。
- **验收**：375 / 768 / 1024 / 1440 四档无 overflow、无文字撞图。

---

### TICKET-P0-08 · TopNav 没有溢出处理
- **现象**：[TopNav.tsx#L345-L379](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/TopNav.tsx#L345-L379) 没有任何溢出菜单，当 simpleItems 增加（当前 7 项 + 2 dropdown），1280px 以下会被压缩或溢出水平滚动。
- **建议方案**：实现"more" 溢出下拉菜单（IntersectionObserver 检测被遮挡项），把超出宽度的项收入下拉。
- **验收**：1024 / 1280 / 1440 / 1920 都能正常呈现，且无水平滚动条。

---

## 二、P1 重要工单（两周内完成）

### 通用组件类（建议先做，单独建任务）

| ID | 工单 | 关键位置 |
|---|---|---|
| TICKET-P1-01 | 实现 `<ConfirmDialog>` 替换全站 `window.confirm()` | TaskList / TaskDetail / Evaluation / AtomicJobs / Works / Tool |
| TICKET-P1-02 | 实现 `<Drawer>` 通用组件（ESC + focus trap + 移动端 bottom sheet） | TaskDetail / DubbingEditor / CharacterLibrary / EvaluationDetail |
| TICKET-P1-03 | 实现 `<EmptyState>` 通用组件，复用 [WorksPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/WorksPage.tsx) 已有的好设计 | Dashboard / TaskList / AtomicJobs / Evaluation / CharacterLibrary |
| TICKET-P1-04 | 抽公共 `<LanguageToggle>` 组件 | [Header.tsx#L70-L96](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/Header.tsx#L70-L96) + [TopNav.tsx#L404-L432](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/TopNav.tsx#L404-L432) |
| TICKET-P1-05 | Tooltip 全站迁移到 Radix（兼容触屏） | EvaluationDetail / TopNav dropdown |

### 仪表盘 [DashboardPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/DashboardPage.tsx)

- TICKET-P1-06：双 query 5s 轮询无节流，活动任务为 0 时停止轮询；用 `refetchIntervalInBackground:false`。
- TICKET-P1-07：统计卡片标签色 `#9ca3af` 对比度 2.8:1，加深至 `#4b5563`。
- TICKET-P1-08：最近任务表格无 `overflow-x-auto`，sm 断点退化为卡片列表。
- TICKET-P1-09：无任务空状态加入 `<EmptyState>` + "立即创建任务" CTA。

### 任务列表 [TaskListPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/TaskListPage.tsx)

- TICKET-P1-10：行内 checkbox 加 `aria-label={\`选择 ${task.name}\`}`；表头 `aria-label="全选"`。
- TICKET-P1-11：整行点击与 `stopPropagation` 混用导致行为不一致；改为仅任务名是 `<Link>`，去掉整行 onClick。

### 新建任务 [NewTaskPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/NewTaskPage.tsx)

- TICKET-P1-12：4 步指示器在 sm 以下隐藏文字，仅剩数字 1-4，加移动端横向滚动条。
- TICKET-P1-13：必填字段无 `*` 标识，校验失败不在字段下方提示；加 `aria-invalid` + `aria-describedby`。
- TICKET-P1-14：视频路径只接受**绝对路径文本框**，对非技术用户不友好；改为优先文件选择/拖拽 + 路径作为兜底。
- TICKET-P1-15：硬编码中文（"新任务 ${timestamp}"、各步骤标题）迁移到 [i18n/messages.ts](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/i18n/messages.ts)。

### 任务详情 [TaskDetailPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/TaskDetailPage.tsx)

- TICKET-P1-16：标签错位 BUG —— "运行执行图"标签下显示的是"31分6秒"，应该是"耗时"。
- TICKET-P1-17：文案不统一 —— 只有"当前阶段:"带冒号，其它"质量档位"、"成品目标"等都不带。
- TICKET-P1-18：导出抽屉宽度固定 `max-w-2xl`，<640px 撑屏；改 `w-full sm:max-w-2xl` + 移动端 bottom sheet。
- TICKET-P1-19：字幕颜色字段 `type="text"`，改 `<input type="color">` + hex 文本框联动。

### 配音编辑台 [DubbingEditorPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/DubbingEditorPage.tsx)

- TICKET-P1-20：顶栏 48px 内信息密度过高，分组 + 溢出菜单。
- TICKET-P1-21：布局预设按钮 `hidden xl:flex`，<1280px 完全消失；至少 lg 显示，icon-only dropdown。
- TICKET-P1-22：键盘快捷键无 `?` 帮助面板。
- TICKET-P1-23：波形组件无 loading/error 状态。

### 评测页 [EvaluationPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationPage.tsx) / [EvaluationDetailPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationDetailPage.tsx)

- TICKET-P1-24：`DropoutText` 漏读 token 用 `bg-red-100 text-red-700`，与"问题严重度红"语义冲突；改用波浪下划线或橙色 chip。
- TICKET-P1-25：进度条 fallback `animate-pulse w-1/3` 视觉像 33%；改 indeterminate 斑马动画。
- TICKET-P1-26：SegmentDrawer 无 focus trap + 初始焦点（[EvaluationDetailPage.tsx#L632-L655](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationDetailPage.tsx#L632-L655)）。
- TICKET-P1-27：`aria-label="close"` / `aria-label="clear focus"` 英文硬编码，迁 i18n（[#L288, #L636](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationDetailPage.tsx#L288)）。

### 原子工具集 [ToolListPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/ToolListPage.tsx)

- TICKET-P1-28：单列卡片在宽屏（>1024px）浪费空间；改 `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`。
- TICKET-P1-29：无搜索 / 筛选 / 收藏 / 最近使用；加顶部 search + 类别 tabs + "最近使用"区。

### 单工具页 [ToolPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/ToolPage.tsx)

- TICKET-P1-30：高级参数应折叠（普通用户只需默认值），用 `<Collapsible>` 包"高级参数"。
- TICKET-P1-31：术语（CDX23、moss-tts-nano-onnx 等）加 tooltip 解释。
- TICKET-P1-32：reset 按钮无确认；加 confirm 或撤销 toast。
- TICKET-P1-33：文件上传无进度条；接入 Dropzone + 上传速率/百分比。
- TICKET-P1-34：错误信息只 `error.message`，根据 status code 区分类别（401 提示去 Settings 配 Key）。

### 原子任务列表 [AtomicJobListPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/AtomicJobListPage.tsx)

- TICKET-P1-35：rerun / stop 无确认；停止可能丢中间结果。
- TICKET-P1-36：`refetchInterval: 3000` 始终启用；仅当 `items` 含 running/pending 时启用。

### 作品库 [WorksPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/WorksPage.tsx)

- TICKET-P1-37：卡片操作按钮 icon 13px、点击区 <24×24，不达 44×44 推荐；按钮 padding 调至 8px，icon 16px。
- TICKET-P1-38：TMDb 搜索失败无降级"仍以本地名称创建"。

### 角色库 [CharacterLibraryPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/CharacterLibraryPage.tsx)

- TICKET-P1-39：表格 `min-w-[760px]` 强制水平滚动；改 `hidden md:table-cell` 隐藏次要列，<sm 切换卡片列表。
- TICKET-P1-40：Loading 文案硬编码英文 `Loading…`，迁 `t.common.loading`。

### 全局设置 [SettingsPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/SettingsPage.tsx)

- TICKET-P1-41：系统信息底部三个图标按钮（清缓存等）无文字标签 / 无 hover 提示。
- TICKET-P1-42：缓存 13.17 GB 无视觉强调；按阈值变色 + 占比图。
- TICKET-P1-43：TMDb / HF / DeepSeek Key 是 `type="password"` 但无"眼睛"切换按钮。
- TICKET-P1-44：Key 配置后无"测试连接"按钮。
- TICKET-P1-45：Models 子页只显示名称，缺"已下载/未下载/大小/磁盘占用"。

### 布局组件

- TICKET-P1-46：[Sidebar.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/Sidebar.tsx) 折叠态下二级菜单完全不可达；折叠态点击时 popover 横向弹出子菜单。
- TICKET-P1-47：[Header.tsx#L25-L30](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/Header.tsx#L25-L30) "Ready" 绿点仅判断 `sysInfo` 是否存在；区分 isLoading / isError，error 时红色提示 + "重试"。
- TICKET-P1-48：[TopNav.tsx#L438-L439](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/components/layout/TopNav.tsx#L438-L439) 切换布局按钮 `aria-label` 始终为 `layoutModeLeft`，不随状态变化。

---

## 三、P2 优化型工单（迭代收尾）

| ID | 工单 | 关键位置 |
|---|---|---|
| TICKET-P2-01 | DashboardPage 卡片整块可点击，缺 hover 提示与 `role="link"` | [DashboardPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/DashboardPage.tsx) |
| TICKET-P2-02 | NewTaskPage 拆分 1551 行巨大组件，`defaultConfig` 抽到 `lib/taskDefaults.ts` | [NewTaskPage.tsx](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/NewTaskPage.tsx) |
| TICKET-P2-03 | NewTaskPage 字段条件渲染加 `<Collapsible>` 过渡 | 同上 |
| TICKET-P2-04 | TaskDetail 长任务无 ETA / 心跳，参考 [EvaluationDetailPage.tsx#L167-L197](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/EvaluationDetailPage.tsx#L167-L197) |
| TICKET-P2-05 | DubbingEditor 问题队列筛选/排序未持久化（应写入 `useSearchParams`） |
| TICKET-P2-06 | `formatTime` 长视频自动 `HH:MM:SS.s`，统一各处 |
| TICKET-P2-07 | Settings sticky 保存浮条遮挡内容，主容器 `pb-20` |
| TICKET-P2-08 | Settings AdvancedDefaults 无"恢复默认"按钮 |
| TICKET-P2-09 | ToolListPage Hero 区过大，挤压工具网格 |
| TICKET-P2-10 | ToolListPage 卡片加"快速运行"按钮 |
| TICKET-P2-11 | ToolPage 932 行 switch 拆分到 `tools/<toolId>/Controls.tsx` |
| TICKET-P2-12 | ToolPage 结果未持久化，通过 jobId 写入 URL search param |
| TICKET-P2-13 | WorksPage 网格响应式 `grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5` |
| TICKET-P2-14 | WorksPage 筛选写入 `useSearchParams` |
| TICKET-P2-15 | CharacterLibrary 侧边作品筛选无清空入口 |
| TICKET-P2-16 | CharacterLibrary 头像加失败回退（Avatar 组件 + 首字头像） |
| TICKET-P2-17 | EvaluationPage SearchInput icon 13px → 14-16px，输入区 padding 上调 |
| TICKET-P2-18 | EvaluationPage 空状态加 CTA（"清除筛选" / "新建任务"） |
| TICKET-P2-19 | EvaluationDetail 跑分中加 `beforeunload` 提示 |
| TICKET-P2-20 | EvaluationDetail 视频/音频键盘快捷键扩展（← → j/k/l） |
| TICKET-P2-21 | AtomicJobList ProgressBar 与百分比文本重复，合并到 ProgressBar 内置 label |
| TICKET-P2-22 | AtomicJobList 工具下拉换成 Combobox（已有 NewTaskPage 模式）|
| TICKET-P2-23 | Sidebar accordion `grid-rows-[0fr]` → `[1fr]` 在 Safari 旧版抖动，加 max-height 兜底 |
| TICKET-P2-24 | Sidebar logo 接近 Google 4 色，替换为 Translip 品牌色 |
| TICKET-P2-25 | Header backdrop-blur 低配设备开销大，加 `@supports` 降级 |

---

## 四、横向共性工单

| ID | 工单 | 涉及页面数 | 严重 |
|---|---|---|---|
| TICKET-CROSS-01 | **窄屏没有汉堡菜单 → 移动端完全无导航** | 全站 | P0 |
| TICKET-CROSS-02 | **表格列在中等宽度下中文逐字竖排** | 5+ | P0 |
| TICKET-CROSS-03 | **批量操作串行 await，失败即中断且无聚合反馈** | TaskList / AtomicJobs | P0 |
| TICKET-CROSS-04 | **TopNav 无溢出菜单** | TopNav | P0 |
| TICKET-CROSS-05 | 破坏性操作使用原生 `confirm()` | 6+ | P1 |
| TICKET-CROSS-06 | 抽屉/模态缺 ESC + focus trap + 移动端 bottom sheet | 4+ | P1 |
| TICKET-CROSS-07 | 表格普遍缺 `overflow-x-auto` + 列优先级 + 响应式折叠 | 5+ | P1 |
| TICKET-CROSS-08 | 中/英文硬编码绕过 i18n | 4+ | P1 |
| TICKET-CROSS-09 | 复选框 / 图标按钮普遍缺 `aria-label` | 3+ | P1 |
| TICKET-CROSS-10 | 列表轮询 3-5s 固定，不区分前台/后台/有无活动任务 | Dashboard / AtomicJobs / EvaluationDetail | P1 |
| TICKET-CROSS-11 | 浅色文本对比度未达 WCAG AA 4.5:1 | Dashboard / Evaluation | P1 |
| TICKET-CROSS-12 | Tooltip 仅 hover/focus 触发，触屏不可用 | EvaluationDetail / TopNav | P1 |

---

## 五、战略级建议（非工单，长期方向）

| ID | 主题 | 描述 |
|---|---|---|
| STRATEGY-01 | **双路径产品形态** | 给"普通创作者"和"工程师"准备两条路径：一键模式（视频 + 目标语言 + 质量）vs 专家模式（露出全部参数）。 |
| STRATEGY-02 | **空状态体验全站化** | 把 [WorksPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/WorksPage.tsx) 的好空状态做成 `<EmptyState>`，应用到所有列表页。 |
| STRATEGY-03 | **配音编辑台作为核心差异化重点打磨** | 加 `?` 快捷键速查 + 新手 onboarding tour + 显眼入口 + 常见问题快速修复。 |
| STRATEGY-04 | **任务阶段可视化进度** | 当前只有 0-100%，应增加：阶段时间轴 / ETA / 子步骤反馈（"正在合成第 23/156 段"）。 |
| STRATEGY-05 | **失败反馈闭环** | 任务失败页面应推荐"查看日志 / 从某阶段重跑 / 反馈 GitHub"；Key 校验失败提供"去设置页配置 →"。 |
| STRATEGY-06 | **i18n 与品牌一致性** | 全站清查硬编码文案；抽公共组件库；替换 Google 风格 logo。 |

---

## 六、落地排期建议

| 节奏 | 工单组 | 内容 |
|---|---|---|
| 🔥 **本周（P0 阻塞型）** | TICKET-P0-01 ~ 08 + CROSS-01~04 | 汉堡菜单、表格响应式、批量删除 allSettled、N+1、提交防双击、删除强确认、博客 hero 响应式、TopNav 溢出 |
| ⚡ **两周内（P1 体验）** | TICKET-P1-01 ~ 05 通用组件优先 + 各页面 P1 | 统一 ConfirmDialog/Drawer/EmptyState/LanguageToggle/Tooltip；i18n 清查；a11y 大检查；设置页测试连接 + Key 显示切换；单工具页折叠高级参数 |
| 🎯 **一个月内（P2 + 战略）** | TICKET-P2-* + STRATEGY-* | 拆分巨型组件、改造 Tooltip、Pagination URL 化、双路径模式、阶段可视化、onboarding tour |

---

## 七、整体评价

| 维度 | 评分 | 简评 |
|---|---|---|
| 功能广度 | ★★★★★ | 端到端 + 原子工具 + 编辑台 + 评测 + 资产库。 |
| 工程深度 | ★★★★★ | DAG 编排、缓存感知、多后端、子进程隔离、博客式技术文档。 |
| 视觉设计 | ★★★★☆ | 整体克制、留白合理、配色统一，[WorksPage](file:///Users/yinyijun/OpenSourceProjects/translip/frontend/src/pages/WorksPage.tsx) 空状态等单点优秀。 |
| 信息架构 | ★★★☆☆ | 侧栏分组清晰，但页面间一致性不够（同样表格在 5 个页面有 5 种实现）。 |
| 响应式 | ★★☆☆☆ | 桌面端 OK，但 ≤1024px 严重退化（导航消失、表格竖排、抽屉撑屏）。 |
| 可访问性 | ★★☆☆☆ | 缺 aria-label、focus trap、对比度问题、Tooltip 触屏不可用。 |
| 错误处理 | ★★★☆☆ | 有提示，但破坏性操作用原生 confirm、错误信息泛化。 |
| 用户引导 | ★★☆☆☆ | 无 onboarding tour、术语无 tooltip、空状态多数缺失。 |

**结论**：Translip 是一个"做得很好的工程项目"，但还不是一个"打磨完成的产品"。把 P0/P1 工单修完，再做战略级打磨，就能把现有的强工程力转化为可推荐给非工程用户的产品力。

---

> 工单编号约定：`TICKET-<等级>-<序号>`。建议在团队 issue tracker（GitHub Issues / 飞书 / Linear）按本文件结构批量创建。
