# Task D Qwen Clone With Stable English Fallback Design

- Project: `translip`
- Status: Draft
- Date: 2026-04-16
- Scope: `Task D` speaker-aware dubbing, `Task E` timeline render integration

## 1. Goal

Stabilize the English dubbing pipeline while continuing to use Qwen models.

The system should prioritize sentence completeness and predictable output over strict per-speaker cloning fidelity. A sentence should only be dropped when there is no usable Qwen output after all configured generation strategies are exhausted. In the normal case, every translated segment should leave `Task D` with one selected audio candidate that is safe to send into `Task E`.

## 2. Problem Statement

The current `Task D` implementation uses `Qwen3-TTS-12Hz-0.6B-Base` in a single-pass voice clone flow:

1. Select one reference clip for a speaker.
2. Build one voice clone prompt.
3. Generate one audio segment.
4. Evaluate it after generation.
5. Persist the result even when the output is near-silent or obviously unusable.

This design fails for cross-lingual dubbing because:

- the generation path is unstable and can produce near-silent audio for the same input;
- one selected reference clip is reused for all segments of a speaker;
- generation quality failures do not trigger candidate retries;
- `Task E` can still place failed `Task D` outputs on the timeline;
- reruns can reuse bad outputs from a shared `output_root`.

The result is that subtitles and translations exist, but final dubbed audio is missing many sentences in practice.

## 3. Product Decision

The accepted product behavior is:

- Continue using Qwen models.
- Keep voice cloning as the preferred path.
- If repeated cloning attempts for a segment fail, do not drop the sentence.
- Instead, synthesize the segment with a stable built-in English male Qwen voice.
- The selected fallback speaker is `Aiden`.

This is an intentional quality hierarchy:

1. Cloned speaker voice
2. Stable English fallback voice
3. No audio

The system should strongly prefer `1`, accept `2`, and avoid `3`.

## 4. Model Strategy

### 4.1 Primary model

- Model: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`
- Role: per-segment cross-lingual voice clone

### 4.2 Fallback model

- Model: `Qwen/Qwen3-TTS-0.6B-CustomVoice`
- Speaker: `Aiden`
- Role: stable English male fallback when all clone attempts fail

### 4.3 Non-goals

This design does not:

- introduce a non-Qwen fallback model;
- guarantee perfect speaker identity preservation for every segment;
- redesign translation quality or timeline fitting policy;
- add user-facing controls for fallback speaker selection in this iteration.

## 5. Success Criteria

The new system is successful when:

- near-silent clone outputs are rejected before selection;
- each segment can try multiple Qwen clone candidates before failing;
- failed clone segments can still produce usable fallback English speech;
- `Task E` receives only selected usable outputs;
- reports clearly show whether a segment used clone or fallback mode;
- rerunning from `task-d` recomputes `Task D` and downstream stages instead of silently reusing known-bad artifacts.

## 6. Architecture Overview

`Task D` becomes a candidate-selection stage instead of a single-shot generator.

For each segment:

1. Build an ordered list of clone attempts.
2. Generate one candidate at a time.
3. Run hard acceptance checks immediately.
4. If a candidate passes, select it and stop trying.
5. If all clone candidates fail, run the English fallback voice.
6. If fallback passes, select it.
7. Only if fallback also fails should the segment be marked as unresolved.

`Task E` should consume only the selected outputs from `Task D`, not every attempted output.

## 7. Generation Modes

Each `Task D` segment attempt belongs to one generation mode:

- `clone_ref_primary`
- `clone_ref_secondary`
- `clone_ref_tertiary`
- `clone_xvector_only`
- `clone_conservative`
- `fallback_custom_voice`

The first acceptable candidate becomes the `selected` output for the segment.

## 8. Clone Attempt Policy

### 8.1 Reference selection

Reference clips remain sourced from `Task B`, but `Task D` should no longer treat one speaker-level reference as globally fixed.

For each speaker:

- load ranked reference candidates from `speaker_profiles.json`;
- keep the top `N` usable clips, where `N=3` in the initial implementation;
- reuse preprocessed reference packages across segments.

### 8.2 Attempt order

For each segment, the ordered clone attempts are:

1. top-ranked reference clip in current normal clone mode;
2. second-ranked reference clip in current normal clone mode, if available;
3. third-ranked reference clip in current normal clone mode, if available;
4. top-ranked reference clip with `x_vector_only_mode=True`;
5. top-ranked reference clip with a conservative generation preset.

If all fail, move to fallback.

### 8.3 Conservative preset

The conservative clone preset exists to reduce unstable outputs from the default Qwen generation path.

Initial preset:

- explicit generation kwargs instead of relying on Qwen package defaults;
- set `do_sample=False`;
- set `subtalker_dosample=False`;
- set `top_k=1` and `subtalker_top_k=1`;
- keep `top_p=1.0` and `subtalker_top_p=1.0`;
- keep `repetition_penalty=1.05`;
- still bounded by the existing token-duration budget logic.

## 9. Hard Acceptance Gates

Every generated candidate must pass hard gates before it can be selected.

### 9.1 Audio presence gate

Reject a candidate if it is effectively silent.

Initial rule:

- compute peak and RMS on the generated waveform;
- reject if peak is below a configured silence threshold;
- reject if RMS is below a configured silence threshold.

This gate exists because near-silent outputs currently look like successful generations to the pipeline.

### 9.2 Backread gate

Reject a candidate if ASR backread is empty or nearly empty for non-trivial text.

### 9.3 Intelligibility gate

Reject a candidate if backread text similarity is below the required threshold.

### 9.4 Duration gate

Reject a candidate if duration falls outside a stricter range than the current review-level status allows.

### 9.5 Fallback gate

Fallback candidates still need to pass silence, backread, intelligibility, and duration gates.

Fallback is a last-resort voice choice, not a bypass around unusable audio.

## 10. Reporting Model

`Task D` reports must distinguish between attempts and the selected result.

### 10.1 Per-attempt fields

Each attempt record should include:

- `segment_id`
- `attempt_index`
- `generation_mode`
- `reference_path` or `fallback_speaker`
- `backend_model`
- `audio_path`
- `peak_db`
- `rms_db`
- `backread_text`
- `text_similarity`
- `speaker_similarity` when applicable
- `duration_ratio`
- `rejection_reasons`
- `accepted`

### 10.2 Per-segment selected fields

Each selected segment result should include:

- `segment_id`
- `selected_audio_path`
- `selected_generation_mode`
- `selected_reference_path` or `fallback_speaker`
- `clone_attempt_count`
- `used_fallback`
- `overall_status`

### 10.3 Stage summary

The stage manifest should summarize:

- total segments;
- clone-selected count;
- fallback-selected count;
- unresolved count;
- silence rejection count;
- backread rejection count;
- duration rejection count.

## 11. Task E Integration

`Task E` should stop treating all existing `Task D` audio files as equally eligible.

It should only load the selected outputs from `Task D`.

Required behavior:

- selected clone outputs are eligible;
- selected fallback outputs are eligible;
- rejected attempts are ignored completely;
- unresolved segments are skipped with explicit reason `skipped_unresolved_task_d`.

This change removes the current behavior where failed clone outputs can still be mixed if an audio file exists.

## 12. Rerun Semantics

Reruns from `task-d` or later must not silently reuse the same bad `Task D` artifacts in a shared output directory.

Required behavior:

- rerunning from `task-d` must invalidate `task-d`, `task-e`, and `task-g`;
- cached upstream stages may still be reused;
- selected outputs and manifests for `task-d` must be regenerated;
- the UI should continue to show the rerun task lineage, but the data consumed by downstream stages must reflect the new `Task D` run.

## 13. Configuration Additions

The following configuration should be added to the pipeline request or normalized task config:

- `task_d_max_reference_candidates`
- `task_d_enable_xvector_only_retry`
- `task_d_enable_custom_voice_fallback`
- `task_d_fallback_speaker`
- `task_d_silence_peak_db_threshold`
- `task_d_silence_rms_db_threshold`
- `task_d_min_text_similarity`
- `task_d_max_duration_ratio`
- `task_d_min_duration_ratio`

Initial defaults should favor the new accepted product decision:

- fallback enabled;
- fallback speaker `Aiden`;
- strict silence rejection enabled.

## 14. Testing Strategy

### 14.1 Unit tests

Add tests for:

- silence detection on generated waveforms;
- candidate retry ordering;
- reference fallback after failed candidate;
- selection of fallback custom voice after clone failures;
- selected-output-only behavior for `Task E`.

### 14.2 Integration-style tests

Add synthetic tests where:

- clone candidate 1 is silent;
- clone candidate 2 has empty backread;
- fallback candidate succeeds;
- `Task E` mixes the fallback output and does not mix rejected clone attempts.

### 14.3 Regression coverage

Add a regression test representing the observed real-world failure mode:

- translated segments exist;
- `Task D` first attempts produce silent or failed clone outputs;
- final selected output remains non-empty because fallback succeeds.

## 15. Rollout Plan

Implementation should be staged:

1. Add hard silence and acceptance gates.
2. Add per-segment multi-attempt clone selection.
3. Add `CustomVoice` fallback with `Aiden`.
4. Change `Task E` to consume selected outputs only.
5. Fix rerun invalidation for `task-d` and downstream stages.

This order reduces risk and gives immediate quality wins even before fallback is fully wired.

## 16. Risks

### 16.1 Voice consistency risk

Fallback segments will not match the original speaker identity.

This is accepted by product decision and should be visible in reports.

### 16.2 Runtime cost

Multiple clone attempts per segment increase `Task D` runtime.

This is acceptable because stability and completeness are the priority.

### 16.3 Reporting complexity

Attempt-level tracking adds more JSON structure and test surface.

This is necessary because the current report format cannot explain why a segment ended up missing or downgraded.

## 17. Recommendation

Proceed with a Qwen-only two-tier design:

- clone first with `Qwen3-TTS Base`;
- fallback to `Qwen3-TTS CustomVoice` speaker `Aiden`;
- treat `Task D` as a candidate selector with hard acceptance gates;
- make `Task E` consume only selected usable outputs.

This is the smallest architecture change that directly solves the current production problem of missing sentences while respecting the decision to continue using Qwen.
