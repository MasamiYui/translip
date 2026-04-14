# Task E Test Report

Date: 2026-04-14

## Scope

Task E assembles Task D segment-level synthesis outputs back onto the original
background timeline and exports:

- `dub_voice.<target_tag>.wav`
- `preview_mix.<target_tag>.wav`
- `timeline.<target_tag>.json`
- `mix_report.<target_tag>.json`
- `task-e-manifest.json`

This validation round is based on the new `Qwen3-TTS` Task D pipeline and the
updated stage-isolated A→E demo script.

## Automated Tests

Command:

```bash
uv run pytest -q
```

Result:

- `35 passed`

Task E related coverage includes:

- CLI parsing for `render-dub`
- failed Task D segment passthrough behavior when audio exists
- overlap resolution
- fit strategies: `direct`, `compress`, `pad`
- preview mix export

## Real Render Validation

### Command

```bash
reports=()
for path in $(find tmp/e2e-task-a-to-e-qwen-full/task-d/voice -name 'speaker_segments.en.json' | sort); do
  reports+=(--task-d-report "$path")
done
/Users/masamiyui/.local/bin/uv run translip render-dub \
  --background ./tmp/e2e-task-a-to-e-qwen-full/stage1/我在迪拜等你/background.mp3 \
  --segments ./tmp/e2e-task-a-to-e-qwen-full/task-a/voice/segments.zh.json \
  --translation ./tmp/e2e-task-a-to-e-qwen-full/task-c/voice/translation.en.json \
  --output-dir ./tmp/task-e-noskip \
  --target-lang en \
  --fit-policy high_quality \
  --fit-backend atempo \
  --mix-profile preview \
  --ducking-mode static \
  --max-compress-ratio 1.7 \
  "${reports[@]}"
```

### Final Artifacts

- [dub_voice.en.wav](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/task-e-noskip/voice/dub_voice.en.wav)
- [preview_mix.en.wav](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/task-e-noskip/voice/preview_mix.en.wav)
- [timeline.en.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/task-e-noskip/voice/timeline.en.json)
- [mix_report.en.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/task-e-noskip/voice/mix_report.en.json)
- [task-e-manifest.json](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/task-e-noskip/voice/task-e-manifest.json)

### Observed Result

Task E completed successfully.

- `placed_count = 90`
- `skipped_count = 78`
- fit strategies:
  - `direct = 17`
  - `compress = 32`
  - `pad = 7`
  - `overflow_unfitted = 27`
  - `underflow_unfitted = 7`
- skipped reasons:
  - `skipped_overlap = 78`
- total timeline duration:
  - `534.593s`

Task E consumed Task D reports from 6 speakers:

- [spk_0000](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0000/speaker_segments.en.json)
- [spk_0001](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0001/speaker_segments.en.json)
- [spk_0002](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0002/speaker_segments.en.json)
- [spk_0003](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0003/speaker_segments.en.json)
- [spk_0004](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0004/speaker_segments.en.json)
- [spk_0007](/Users/masamiyui/OpenSoureProjects/Forks/translip/tmp/e2e-task-a-to-e-qwen-full/task-d/voice/spk_0007/speaker_segments.en.json)

Representative placed segments in the final timeline include:

- `seg-0004` from `spk_0000`
- `seg-0007` and `seg-0009` from `spk_0001`
- `seg-0012`, `seg-0013`, `seg-0018` from `spk_0003`

## What Changed In This Round

Compared with the previous development-only Task E run:

- the upstream Task D backend is now `Qwen3-TTS`
- the failed Task D segments are no longer filtered out before fit and overlap handling
- overlong and undersized segments are also kept instead of being dropped at fit time
- the placed segment count improved from `38` to `90`
- the remaining skips are now entirely overlap-driven in this validation run

## Remaining Limits

- Task E now places many more segments, but that also increases overlap pressure
- current overlap resolution will still drop later conflicting segments when a
  stronger candidate already occupies the same time window
- the biggest upstream bottleneck remains duration mismatch on short lines
- current mix is still a preview mix, not final-grade mastering
- because Task D is local and conservative, some English lines still sound longer than the source timing window allows

## Conclusion

Task E is now validated on a full real-video run with the migrated
`Qwen3-TTS` Task D pipeline. The end-to-end local workflow from stage 1 through
Task E completes successfully on `MacBook M4 16GB`, and the current remaining
gap is quality/yield optimization rather than pipeline breakage.
