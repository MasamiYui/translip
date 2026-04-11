# video-voice-separate

Separate `voice` and `background` audio from local video or audio files.

## Quick Start

```bash
uv sync
uv run video-voice-separate run \
  --input ./test_video/example.mp4 \
  --mode auto \
  --quality balanced \
  --output-dir ./output
```

Download the built-in `CDX23` dialogue checkpoints ahead of time if you plan to use
`--mode dialogue` often:

```bash
uv run video-voice-separate download-models --backend cdx23 --quality balanced
```

Run the dialogue backend explicitly:

```bash
uv run video-voice-separate run \
  --input ./test_video/example.mp4 \
  --mode dialogue \
  --quality balanced \
  --output-dir ./output-dialogue \
  --keep-intermediate
```

## Commands

- `video-voice-separate run`: separate a file into `voice` and `background`
- `video-voice-separate probe`: inspect input media metadata
- `video-voice-separate download-models`: download backend checkpoints into cache

See [docs/technical-design.md](docs/technical-design.md) for the system design.
