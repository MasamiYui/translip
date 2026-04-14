# Frontend Chinese/English Internationalization Design

## Summary

Add first-class Chinese and English support to the React frontend under `frontend/`.
The UI will default to Simplified Chinese on first visit, expose a visible language switcher in the header, and persist the user's choice in `localStorage` so the selected language survives reloads and future visits.

The implementation will use a lightweight in-repo internationalization layer based on React context and typed message dictionaries instead of adding a third-party i18n framework.

## Context

The current frontend is a Vite + React 19 application with all user-facing strings inlined directly inside page components and shared UI components.
Text is currently a mix of Chinese and English:

- Navigation labels are Chinese while part of the product branding is English.
- Shared status and stage labels are hard-coded in utility modules.
- Relative time, date/time, and duration formatting are tied to Chinese output.
- Dialog and empty-state text are inlined in page components.

This structure makes it easy to miss strings and creates a high risk of partial localization if language support is added ad hoc.

## Goals

- Support both Simplified Chinese and English across the existing frontend.
- Default to Chinese for first-time visitors.
- Provide a visible language switcher inside the page header.
- Persist the selected language in `localStorage`.
- Update all current static UI text, status labels, stage labels, placeholders, empty states, and confirmation text when language changes.
- Ensure formatted time and date strings follow the active UI language.
- Keep the solution small and maintainable for the current scale of the app.

## Non-Goals

- Adding route-based locale prefixes such as `/zh` or `/en`.
- Detecting browser language for initial language selection.
- Localizing backend-provided freeform error messages.
- Translating artifact file names, task names, or user-entered data.
- Introducing a full ICU/message-format system for pluralization beyond the current UI needs.
- Adding additional languages beyond Chinese and English in this change.

## Chosen Approach

Use a lightweight app-local i18n layer built from:

- A message dictionary module containing `zh-CN` and `en-US` message trees.
- An `I18nProvider` mounted near the app root.
- A `useI18n()` hook for components to access:
  - the current locale
  - the resolved messages
  - a `setLocale()` action
  - helper translation/formatting functions
- Locale-aware formatting helpers for relative time, date/time, and durations.

This approach is preferred over `react-i18next` because the current app is small, all strings are local, and there is no SSR, route-based locale handling, or translation pipeline that justifies the added dependency and runtime complexity.

## User Experience

### Initial State

- First visit defaults to Simplified Chinese.
- The app writes the selected locale to `localStorage` only after initialization or when the user switches languages.
- The document language attribute is set to `zh-CN` or `en-US` to reflect the active locale.

### Language Switcher

- The header will contain a compact toggle control with options for `中文` and `EN`.
- Switching language updates visible UI text immediately without navigation or page reload.
- The control stays available on every page because it lives in the shared header.

### Localization Scope

The following UI content must switch with the locale:

- Sidebar branding subtitle and navigation labels.
- Header connection and readiness text.
- Dashboard headings, stat labels, table headers, empty states, and CTA text.
- Task list headings, filters, search placeholder, table headers, bulk-action text, delete button titles, pagination text, and loading/empty states.
- New task wizard step labels, field labels, hints, placeholders, checkbox labels, section titles, and error notices.
- Task detail page section titles, action labels, stage details, manifest controls, artifact labels, and progress labels.
- Settings page headings, labels, system/model status labels, and about copy.
- Shared status badge labels.
- Shared pipeline stage labels and cached/pending marker text.
- Utility-formatted relative time, date/time, and duration output.
- `window.confirm(...)` messages and other inline prompts.

## Architecture

### File Layout

Add a dedicated i18n area under `frontend/src/i18n/`:

- `messages.ts`
  - Locale type definitions.
  - Chinese and English message dictionaries.
  - Shared message typing inferred from the default dictionary.
- `I18nProvider.tsx`
  - Locale state ownership.
  - `localStorage` hydration and persistence.
  - `document.documentElement.lang` synchronization.
  - Stable translation and formatter helpers.
- `useI18n.ts`
  - Hook wrapper around the provider context.

Potentially move or split formatting helpers so locale-aware formatting lives beside the i18n layer instead of remaining in `frontend/src/lib/utils.ts`.

### Provider Placement

Mount `I18nProvider` near the root in `frontend/src/App.tsx`, wrapping the router and current layout tree so all pages and shared components can access the locale.

### Message Access Pattern

Components will not reference raw dictionary objects directly.
They will call `useI18n()` and read namespaced messages, for example:

- `t.nav.dashboard`
- `t.dashboard.empty.title`
- `t.status.running`

The goal is not a string-key resolver like `t("dashboard.empty.title")`.
For this codebase, typed nested objects are simpler, safer, and easier to refactor.

## Dictionary Structure

Use a nested message tree organized by UI area instead of a flat string table.

Top-level groups should include:

- `common`
- `nav`
- `header`
- `dashboard`
- `tasks`
- `newTask`
- `taskDetail`
- `settings`
- `status`
- `stages`
- `languages`
- `format`

This keeps text co-located conceptually and reduces accidental reuse of ambiguous generic labels.

## Formatting Strategy

### Relative Time

Replace the current hard-coded Chinese relative-time helper with a locale-aware formatter:

- Chinese examples:
  - `刚刚`
  - `3分钟前`
  - `昨天`
- English examples:
  - `just now`
  - `3 minutes ago`
  - `yesterday`

For older dates, use locale-specific `toLocaleDateString(...)` output based on the active locale.

### Date and Time

Replace hard-coded `zh-CN` formatting in `formatDateTime(...)` with active-locale formatting.

### Duration

Duration output will also be localized:

- Chinese examples:
  - `1小时 5分 3秒`
  - `5分 8秒`
- English examples:
  - `1h 5m 3s`
  - `5m 8s`

The implementation does not need natural-language long-form English like `1 hour 5 minutes`.
Compact output is sufficient and matches the dashboard/control-panel style.

## Shared Constants Migration

The following existing constants will stop owning display text:

- `STAGE_LABELS`
- `LANG_LABELS`
- `STATUS_CONFIG.label`

Instead:

- stage display labels come from i18n messages
- language display labels come from i18n messages
- status badge labels come from i18n messages

If utility modules still need canonical stage order or language codes, those values should remain as non-localized identifiers.

## Component-Level Changes

### Layout

- `Header.tsx`
  - Add the language switcher.
  - Localize connection/readiness text.
- `Sidebar.tsx`
  - Localize navigation labels and branding subtitle.

### Shared Components

- `StatusBadge.tsx`
  - Keep color/status mapping local.
  - Replace embedded display labels with locale-aware labels from the provider.
- `PipelineGraph.tsx`
  - Replace cached/pending text markers and stage display labels with locale-aware strings.

### Pages

- `DashboardPage.tsx`
  - Localize cards, section headers, table headers, empty state, and CTA labels.
- `TaskListPage.tsx`
  - Localize filters, search placeholder, loading states, delete prompts, table headers, and pagination summary.
- `NewTaskPage.tsx`
  - Localize step titles, field labels, section titles, hints, option labels where they are user-facing, and error banners.
  - Keep technical backend identifiers such as `qwen3tts` or `local-m2m100` unchanged where they are product/backend names.
- `TaskDetailPage.tsx`
  - Localize overview, stage detail labels, action buttons, confirmation dialogs, and artifact/manifest labels.
- `SettingsPage.tsx`
  - Localize section titles, info labels, model availability labels, and about copy where appropriate.

## State and Persistence

### Storage Key

Persist the locale under a dedicated key, for example:

- `translip.locale`

This avoids collisions with future stored preferences.

### Initialization Rules

- If `localStorage` contains a supported locale, use it.
- Otherwise default to `zh-CN`.
- Unsupported or malformed stored values fall back to `zh-CN`.

## Error Handling

- Missing `localStorage` access should fail safely and leave the app on the default locale.
- Missing message keys should be treated as a development error; the implementation should favor typed dictionary completeness so missing keys are caught at compile time rather than at runtime.
- Backend error strings returned by the API will be displayed as-is until a separate backend localization strategy exists.

## Testing Strategy

The frontend currently has no dedicated test setup for this behavior.
Add a minimal test harness with Vitest for the i18n core only.

### Required Tests

- Provider defaults to Chinese when no stored locale exists.
- Provider restores English when `localStorage` contains the English locale.
- Switching locale updates persisted storage.
- Relative time formatter returns Chinese output under `zh-CN`.
- Relative time formatter returns English output under `en-US`.
- Status/stage label lookup resolves localized labels for both locales.

### Verification Outside Automated Tests

Manual verification should confirm:

- language switcher is visible in the header
- language selection persists after reload
- every current page switches cleanly between Chinese and English
- no obvious untranslated strings remain in shared UI
- no layout regressions occur due to longer English labels

## Rollout Notes

This change is intentionally additive and low-risk.
It does not alter routes, backend contracts, or task execution logic.
The main implementation risk is incomplete text extraction, so the work should prioritize exhaustive coverage of current UI strings and centralization of formatting helpers.

## Implementation Outline

1. Add the i18n provider, locale storage, and message dictionaries.
2. Move shared display labels and formatting helpers to locale-aware versions.
3. Add the header language switcher.
4. Replace hard-coded strings across shared components and pages.
5. Add minimal Vitest coverage for i18n state and formatter behavior.
6. Run frontend tests, lint, and build to verify the integration.
