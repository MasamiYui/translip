# Task/Delivery Config Separation Design

## Summary

Split the current task configuration model into two explicit concepts:

- `pipeline_config`: how the pipeline runs
- `delivery_config`: how final subtitle preview and final video export behave

The backend will store both domains separately inside the existing task JSON payload and expose them as separate API fields.
The task creation flow will only edit pipeline concerns.
The task detail page will own delivery composition and subtitle styling.

## Current Problem

The current implementation mixes pipeline execution fields and delivery composition fields in the same `config` object.

This creates four concrete issues:

1. The new task page edits subtitle composition and style fields even though users have no rendered output to tune yet.
2. The task detail page keeps a second set of local subtitle state instead of reading from persisted task values.
3. The delivery compose endpoint writes delivery choices back into the same `config` object used to rebuild pipeline requests.
4. Task rerun copies the full `config`, so a temporary export tweak can silently affect later reruns.

## Goals

- Make task creation responsible only for pipeline execution inputs.
- Make task detail delivery composition responsible only for delivery/export inputs.
- Keep the current database schema unchanged.
- Preserve backward compatibility for existing tasks stored with the legacy flat config shape.
- Keep current task list and dashboard behavior working with minimal UI churn.

## Non-Goals

- Adding a database migration or new SQL columns in this change.
- Reworking task list visuals.
- Redesigning the whole delivery composer interaction.
- Removing support for existing flat config tasks already stored locally.

## Chosen Design

### Storage Shape

Persist task config in canonical nested form inside the existing JSON column:

```json
{
  "pipeline": {
    "template": "asr-dub-basic",
    "run_from_stage": "stage1",
    "run_to_stage": "task-g",
    "video_source": "original",
    "audio_source": "both",
    "subtitle_source": "asr"
  },
  "delivery": {
    "subtitle_mode": "none",
    "subtitle_render_source": "ocr",
    "subtitle_font": "Noto Sans",
    "subtitle_font_size": 0,
    "subtitle_color": "#FFFFFF",
    "subtitle_outline_color": "#000000",
    "subtitle_outline_width": 2.0,
    "subtitle_position": "bottom",
    "subtitle_margin_v": 0,
    "subtitle_bold": false,
    "bilingual_chinese_position": "bottom",
    "bilingual_english_position": "top",
    "export_preview": true,
    "export_dub": true
  }
}
```

### Backward Compatibility

If stored config is flat legacy data, normalize it into:

- pipeline fields copied into `pipeline`
- delivery fields copied into `delivery`

All existing code paths will consume the normalized split structure.

### API Shape

Task read responses will expose:

- `config`: pipeline config only, kept for current frontend compatibility
- `delivery_config`: explicit delivery config for detail-page composer

Task creation will continue accepting `config` as pipeline config.
The backend will generate default `delivery_config` automatically.

### UI Responsibilities

#### New Task Page

Keep only pipeline concerns:

- template
- subtitle extraction/input policy for earlier stages
- video source
- audio source
- run range
- model/backend/cache controls

Remove delivery-only controls:

- subtitle mode
- subtitle render source for export
- subtitle font, size, color, outline, position, margin, bold
- bilingual subtitle placement

Add copy that delivery/subtitle styling is configured after the pipeline has produced artifacts.

#### Task Detail Page

Initialize composer state from persisted `delivery_config`.
Preview and compose actions use the same source of truth.
Saving/exporting updates `delivery_config` only, not `config`.

## Backend Changes

### Normalization Helpers

Add helpers in `src/translip/server/task_config.py` to:

- classify pipeline vs delivery keys
- build default delivery config
- normalize legacy flat config into canonical nested shape
- expose pipeline and delivery slices independently

### Pipeline Request Construction

`_build_pipeline_request()` will read:

- execution fields from normalized pipeline config
- subtitle/export fields from normalized delivery config

This keeps automatic `task-g` execution working without leaking delivery state back into pipeline config.

### Delivery Route Persistence

`/delivery-compose` will write only the normalized delivery section.
It will not mutate the normalized pipeline section.

### Rerun Behavior

Rerun will copy both normalized sections forward, but only `run_from_stage` changes in pipeline config.
This keeps explicit delivery preferences while removing accidental coupling to pipeline-only settings.

## Frontend Changes

### Types

Add a `delivery_config` field to task reads and keep `Task.config` as pipeline config.

### New Task Page

Refactor local state so step 2 no longer displays delivery subtitle styling controls.
The page summary remains focused on template, run range, delivery policy, and core backend choices.

### Task Detail Page

Replace hard-coded local delivery defaults with state hydration from `task.delivery_config`.
Composer actions should continue to support local edits, preview generation, and final export.

## Testing

- Python tests for normalization and request construction across legacy and canonical storage shapes.
- Python tests for delivery route persistence to ensure pipeline config is unchanged.
- Frontend tests to verify the new task page no longer shows delivery-only controls.
- Frontend tests to verify the task detail page hydrates composer controls from `delivery_config`.
- End-to-end validation with `test_video`.
- Browser validation with Playwright against the running app.

## Risks

- Existing code may still read raw stored config directly and bypass normalization.
- Legacy tasks may expose edge cases if a field exists in both old and new locations.
- Frontend tests that rely on select ordering may need updates because fields are removed.

## Success Criteria

- New tasks are created without any delivery-only subtitle style fields in the creation UI.
- Task detail composer reads and persists `delivery_config`.
- Delivery compose no longer mutates pipeline config.
- Rerun uses normalized split config successfully.
- Existing legacy tasks still open and export correctly after normalization.
