# EventReels 🎞️

**Your night, already edited.** Drop in raw event footage, get back a finished 9:16 highlight
reel. No timeline, no editor, no skill needed.

## How it works
The pipeline watches and listens to your footage, then cuts the reel the way an editor would:

1. **Watch** — scene-change detection finds the visual moments (ffmpeg, frame-level scoring)
2. **Listen** — per-half-second loudness analysis finds the crowd energy and music drops
3. **Pick** — moments are scored and greedy-selected to your target length, then re-ordered
   chronologically so the reel tells the night in order
4. **Cut** — 1080×1920 @30fps, cover-crop, per-clip fades, loudness-normalized to **-14 LUFS**
   (the Instagram/TikTok/YouTube standard)

100% local. Zero API keys. Zero Python dependencies — just `ffmpeg`.

## The studio
```bash
cd web && ./run.sh        # → http://127.0.0.1:8910
```
Drag footage in, watch the four-stage pipeline work, preview the reel in a phone frame, download.

## The CLI
```bash
cd reelsmith
uv run reelsmith party.mov -o reel.mp4 --duration 30 --title "RUSH WEEK"
uv run reelsmith party.mov -o reel.mp4 --duration 30 --music bed.mp3
uv run reelsmith party.mov -o reel.mp4 --duration 30 --beat-sync --captions
```

## Tests
```bash
cd reelsmith && python3 -m unittest discover -s tests
cd web && uv run pytest tests/
```
The suite generates synthetic quiet→loud→quiet footage and proves the pipeline picks the loud
window and renders a valid vertical reel.



## What's new (June 2026)
- **Reel Library:** Persistent storage of your finished reels in SQLite.
- **Shareable Watch Pages:** Watch, unfurl, and share your finished reels via /r/{id}.
- **Thumbnail Library:** Studio UI now features a library strip for quick access to your history.
- **Improved templates:** Rush, Game, Formal, and Hackathon templates added.
- **Captioning:** Automatic transcription and caption burning.
