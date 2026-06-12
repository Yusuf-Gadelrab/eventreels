# reelsmith — the EventReels editing brain

Raw event footage in → finished 9:16 highlight reel out. Local-first: ffmpeg + Python,
zero API keys, Python deps managed by `uv`.

## How it decides what makes the cut
1. **Scene detection** — ffmpeg scene-change scoring finds visual moments (cuts, motion bursts).
2. **Audio energy** — per-half-second RMS loudness; crowd noise and music drops = highlights.
3. **Selection** — segments between scene cuts (1.5–6s each) scored by normalized loudness,
   greedy-picked to the target length, then re-sorted chronologically.
4. **Beat sync** — optional music-bed beats snap reel cut points; source audio can also drive
   beat snapping with `--beat-sync`.
5. **Render** — cover-crop to 1080×1920 @30fps, H.264/AAC, optional 2.5s title overlay,
   optional burned-in captions, and optional ducked music bed.

## Usage
```bash
uv run reelsmith party.mov -o reel.mp4 --duration 30 --title "RUSH WEEK"
uv run reelsmith party.mov -o reel.mp4 --duration 30 --music bed.mp3
uv run reelsmith party.mov -o reel.mp4 --duration 30 --beat-sync --captions
# or with no install at all:
PYTHONPATH=src python3 -m reelsmith.cli party.mov -o reel.mp4
```

## Tests
```bash
uv run pytest -q
```
Generates synthetic footage (quiet→loud→quiet) and asserts the pipeline picks the loud window
and renders a valid vertical reel. Whisper transcription integration is optional and gated behind
`REELSMITH_SLOW_TESTS=1`.

## License
© 2026 Yusuf Gadelrab. All rights reserved. Source is public for portfolio and evaluation
purposes only: no license is granted to copy, modify, or redistribute this code.
