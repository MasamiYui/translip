# Goal-First Delivery Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make task creation goal-first and make export default to that goal, while preserving the existing frontend visual language.

**Architecture:** Keep `output_intent` as the only primary decision in the new-task flow. Reframe the export drawer around a recommended default derived from `output_intent`, and expose alternative export variants as an optional override. Implement this as targeted UI changes in `NewTaskPage.tsx` and `TaskDetailPage.tsx`, backed by focused page tests.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, existing task presentation helpers.

---

### Task 1: Lock the intended behavior with page tests

**Files:**
- Modify: `frontend/src/pages/__tests__/NewTaskPage.test.tsx`
- Modify: `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`

- [ ] **Step 1: Write a failing NewTaskPage expectation for goal-first system explanation**

```tsx
expect(screen.getByText('系统将自动启用')).toBeInTheDocument()
expect(screen.getByText('OCR 字幕链路')).toBeInTheDocument()
expect(screen.getByText('配音合成')).toBeInTheDocument()
expect(screen.getByText('该处理链路由成品目标自动生成')).toBeInTheDocument()
```

- [ ] **Step 2: Run the targeted NewTaskPage test and confirm it fails for missing UI**

Run: `npm test -- frontend/src/pages/__tests__/NewTaskPage.test.tsx`
Expected: FAIL because the new explanatory labels and helper copy are not rendered yet.

- [ ] **Step 3: Write failing TaskDetailPage expectations for default-export-first drawer**

```tsx
expect(await screen.findByText('1. 默认导出')).toBeInTheDocument()
expect(screen.getByText('将导出为')).toBeInTheDocument()
expect(screen.getByRole('button', { name: '切换其他版本' })).toBeInTheDocument()
expect(screen.queryByText('1. 选择导出版本')).not.toBeInTheDocument()
```

- [ ] **Step 4: Run the targeted TaskDetailPage delivery test and confirm it fails for the old drawer structure**

Run: `npm test -- frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
Expected: FAIL because the page still renders the old “选择导出版本” step and no optional override trigger.

### Task 2: Implement the goal-first explanation in the new-task flow

**Files:**
- Modify: `frontend/src/pages/NewTaskPage.tsx`

- [ ] **Step 1: Add intent-derived capability metadata next to the existing intent card configuration**

```tsx
function getIntentCapabilitySummary(intent: TaskOutputIntent, locale: string) {
  return {
    heading: locale === 'zh-CN' ? '系统将自动启用' : 'Auto-enabled capabilities',
    capabilities: ['OCR 字幕链路', '配音合成', '字幕擦除'],
    helper: locale === 'zh-CN'
      ? '该处理链路由成品目标自动生成'
      : 'This workflow is generated from the selected goal.',
  }
}
```

- [ ] **Step 2: Render a style-matched explanatory panel under the selected goal**

```tsx
<section className="rounded-[20px] border border-slate-200/80 bg-white/80 p-4">
  <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
    系统将自动启用
  </div>
  <div className="mt-3 flex flex-wrap gap-2">
    {capabilities.map(item => (
      <span key={item} className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 shadow-sm ring-1 ring-slate-200">
        {item}
      </span>
    ))}
  </div>
  <div className="mt-3 text-sm text-slate-500">该处理链路由成品目标自动生成</div>
</section>
```

- [ ] **Step 3: Update the workflow preview copy so it reads as system output, not a second decision**

```tsx
title={locale === 'zh-CN' ? '系统处理链路' : 'Workflow Preview'}
```

- [ ] **Step 4: Run the NewTaskPage test again and confirm it passes**

Run: `npm test -- frontend/src/pages/__tests__/NewTaskPage.test.tsx`
Expected: PASS

### Task 3: Reframe the export drawer around a default export with optional override

**Files:**
- Modify: `frontend/src/pages/TaskDetailPage.tsx`

- [ ] **Step 1: Add UI state for showing or hiding alternate export versions**

```tsx
const [showProfileOverrides, setShowProfileOverrides] = useState(false)
```

- [ ] **Step 2: Replace the first drawer section with a default-export summary card**

```tsx
<DrawerSection title="1. 默认导出">
  <div className="rounded-xl border border-blue-100 bg-blue-50/70 p-4">
    <div className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-500">将导出为</div>
    <div className="mt-2 text-lg font-semibold text-slate-900">{getExportProfileLabel(exportProfile, locale)}</div>
    <div className="mt-2 text-sm text-slate-600">
      来自成品目标：{getOutputIntentLabel(task.output_intent, locale)}
    </div>
  </div>
</DrawerSection>
```

- [ ] **Step 3: Render the current version cards behind an optional “切换其他版本” action**

```tsx
<button
  type="button"
  onClick={() => setShowProfileOverrides(prev => !prev)}
  className="text-sm font-medium text-blue-600 hover:text-blue-700"
>
  {showProfileOverrides ? '收起其他版本' : '切换其他版本'}
</button>
```

- [ ] **Step 4: Keep existing profile-card styling when overrides are expanded**

```tsx
{showProfileOverrides && (
  <div className="grid gap-3 md:grid-cols-2">
    {profiles.map(profile => (
      <button className={selected ? 'border-blue-500 bg-blue-50 shadow-sm' : 'border-slate-200 bg-white'} />
    ))}
  </div>
)}
```

- [ ] **Step 5: Renumber the remaining drawer sections without changing their core controls**

```tsx
<DrawerSection title="2. 确认素材来源" />
<DrawerSection title="3. 选择字幕样式" />
<DrawerSection title="4. 预览并导出" />
```

- [ ] **Step 6: Run the TaskDetailPage delivery test and confirm it passes**

Run: `npm test -- frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
Expected: PASS

### Task 4: Final verification

**Files:**
- Modify: `frontend/src/pages/NewTaskPage.tsx`
- Modify: `frontend/src/pages/TaskDetailPage.tsx`
- Modify: `frontend/src/pages/__tests__/NewTaskPage.test.tsx`
- Modify: `frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`

- [ ] **Step 1: Run the full targeted frontend verification**

Run: `npm test -- frontend/src/pages/__tests__/NewTaskPage.test.tsx frontend/src/pages/__tests__/TaskDetailPage.delivery.test.tsx`
Expected: PASS with all touched page tests green.

- [ ] **Step 2: Review the changed UI copy for consistency with the approved design**

Checklist:
- New-task Step 2 still centers on 成品目标
- Workflow copy reads as automatic system behavior
- Export drawer defaults to the intent-derived export
- Alternate versions are optional, not mandatory

- [ ] **Step 3: Prepare the final summary with verification evidence**

Report:
- Which files changed
- Which tests were run
- Whether any residual risk remains
