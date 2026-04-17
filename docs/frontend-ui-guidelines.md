# Frontend UI Guidelines

本文档是 translip 前端界面的设计规范，**AI 在生成或修改 UI 代码之前必须先阅读本文档**。

---

## 核心原则：反 Card Soup

### 什么是 Card Soup（禁止）

Card Soup 是指将页面内每一个逻辑小节都套上独立的圆角方块容器（`rounded-2xl border shadow`），导致页面看起来像一堆叠在一起的名片。

**典型错误模式：**

```tsx
// ❌ 错误：每块内容都是独立卡片
<div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
  <div className="text-sm font-semibold">导出状态</div>
  ...
</div>
<div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
  <div className="text-sm font-semibold">最近导出结果</div>
  ...
</div>
<div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
  <div className="text-sm font-semibold">运行控制</div>
  ...
</div>
```

**问题：**
- 视觉噪音多，每个块都在竞争注意力
- 内容之间的层级关系被弱化
- 页面整体纵向高度膨胀
- 风格上显得"拼凑感"重

---

## 正确的布局方式

### 1. 大容器 + 内部分隔线

页面的区块结构通过**已有的大容器**划分，容器内部用 `border-b` / `border-r` / `border-t` 等分隔线区分内容段，而不是为每段内容都新建一个方块。

```tsx
// ✅ 正确：一个大区块，内部用分隔线区分内容
<div className="border-b border-slate-100 px-7 py-6">
  {/* 主标题区 */}
  <div className="mb-5 ...">导出区</div>

  {/* 主行动区：横向两列，中间用 border-r 分隔 */}
  <div className="grid lg:grid-cols-[1fr_1fr]">
    <div className="lg:border-r lg:pr-8">
      {/* 导出状态 */}
    </div>
    <div className="lg:pl-8">
      {/* 最近导出结果 */}
    </div>
  </div>

  {/* 次要区：用 border-t 分隔 */}
  <div className="mt-6 border-t border-slate-100 pt-6 grid lg:grid-cols-[1fr_auto]">
    {/* 素材清单 */}
    <div>...</div>
    {/* 运行控制：用 border-l 与左侧分隔 */}
    <div className="lg:border-l lg:pl-8">...</div>
  </div>
</div>
```

### 2. 什么时候允许用卡片

卡片（`rounded-xl border`）只在以下情况使用：
- **可点击的选项卡**：如导出版本选择（用户需要知道"这是一个可选的东西"）
- **内嵌的状态反馈**：如 blocker 警告（用左边框 `border-l-2 border-amber-400` 而非整个方块）
- **独立的弹层/抽屉内部**：Drawer 里空间独立，内部可以有适度的小卡片分节

### 3. 可选的卡片使用边框而非 shadow

```tsx
// ✅ 选中态用颜色区分
<button className="rounded-xl border border-blue-500 bg-blue-50">已选</button>
<button className="rounded-xl border border-slate-200 hover:border-slate-300">未选</button>

// ❌ 不要给静态展示容器加 shadow-sm —— 增加视觉重量但没有信息价值
<div className="rounded-2xl border shadow-sm">...</div>
```

---

## 信息层级规则

### 标签文字

用最小化的方式展示标签，不要用"标签 + 值"各自放一行的方式撑高度：

```tsx
// ✅ 内联展示：标签与值同行
<span className="text-xs text-slate-500">
  推荐版本：<span className="font-medium text-slate-700">{value}</span>
</span>

// ❌ 独立方块展示：QuickInfoChip 风格的 rounded-full border 标签堆叠
<div className="rounded-full border border-slate-200 px-3 py-1.5 text-xs">
  <span>标签：</span><span>值</span>
</div>
```

### 标题等级

| 用途 | 样式 |
|------|------|
| 页面区块名（导出区、运行控制等） | `text-[11px] font-semibold uppercase tracking-widest text-slate-400` |
| 区块内小节标题 | `text-xs font-semibold text-slate-500` |
| 主内容标题（任务名等） | `text-2xl font-semibold text-slate-900` |

---

## 列表和状态行

### 素材清单

素材清单等状态性列表优先用 **2列网格** 而非单列，减少纵向占用：

```tsx
<div className="grid grid-cols-1 gap-y-0 sm:grid-cols-2">
  {rows.map(row => <AssetStatusRow key={row.title} {...row} />)}
</div>
```

每行用 `py-2.5` 上下间距，不加横线 `divide-y`（视觉上更轻）。

### 状态标记

状态 Badge（就绪/缺失等）用 `rounded-full border` 的 pill 形式，**仅用在需要快速扫视状态的列表场景**，不要用作"信息标签"。

---

## 操作按钮规则

### 主操作

```tsx
// 主要操作（导出、提交）：实色背景
<button className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
```

### 次要操作

```tsx
// 次要操作（重跑、停止）：边框按钮，统一用 border-slate-200
<button className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
```

### 危险操作

```tsx
// 危险操作（删除）：文字用红色，边框与其他次要按钮一致，hover 才变红底
// 不要默认就用 bg-rose-50 border-rose-200 —— 视觉上过于强调
<button className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-rose-600 hover:bg-rose-50">
```

### 按钮排列

- 多个操作按钮在控制区（运行控制）竖向排列，避免在小宽度下横向换行
- 在主操作区（如导出成品按钮）保持单行，只有一个主操作

---

## 链接和下载行

```tsx
// ✅ 轻量下载行：无背景无边框，hover 改变文字颜色即可
<a className="flex items-center justify-between gap-4 py-2 text-sm text-slate-700 hover:text-slate-900">
  <div>
    <div className="font-medium">{label}</div>
    <div className="text-xs text-slate-400">{path}</div>
  </div>
  <Download size={14} className="shrink-0 text-slate-400" />
</a>

// ❌ 不要给下载行加 rounded-xl border —— 这是列表项，不是按钮
<a className="flex ... rounded-xl border border-slate-200 px-4 py-3 hover:bg-slate-50">
```

---

## 告警和 Blocker 信息

```tsx
// ✅ 左侧竖线 + 淡色背景，轻量告警
<div className="border-l-2 border-amber-400 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">

// ❌ 完整圆角边框方块，视觉太重
<div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
```

Blocker 内的修复操作用**文字链接风格**（下划线 hover），而非独立按钮：

```tsx
<button className="text-xs font-medium text-amber-700 underline-offset-2 hover:underline">
  修复操作
</button>
```

---

## Drawer（抽屉）内部规则

Drawer 是独立的面板，内部可以使用适度的节块分组，但 **DrawerSection** 组件本身也应去掉 `rounded-2xl border shadow-sm`，改用上边框分隔：

```tsx
// ✅ 简洁分节
<section className="space-y-4 border-t border-slate-100 pt-5 first:border-t-0 first:pt-0">
  <div className="text-sm font-semibold text-slate-900">{title}</div>
  {children}
</section>

// ❌ Card soup 在 Drawer 里也不对
<section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
```

---

## 检查清单（AI 生成 UI 前自检）

在生成或修改 UI 之前，对照以下问题：

- [ ] 新增内容是否被包在独立的 `rounded-xl border shadow` 方块里？→ 应该用分隔线代替
- [ ] 是否有多个同级方块堆叠？→ 合并为一个大容器，用 `border-t` / `border-r` 分隔
- [ ] 标签+值是否分两行展示？→ 考虑是否可以内联
- [ ] 按钮颜色是否只有危险操作才用彩色背景？→ 普通次要按钮统一用 `border-slate-200`
- [ ] 列表项是否有独立方块边框？→ 用 `py-2.5` 间距 + 轻分隔线代替