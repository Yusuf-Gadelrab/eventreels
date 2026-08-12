# EventReels

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-d4af37)](https://www.python.org/)
[![Local-first](https://img.shields.io/badge/local--first-no%20API%20keys-d4af37)](#how-it-works)
[![Status](https://img.shields.io/badge/status-alpha-8c742a)](#status)

EventReels is a local video-automation pipeline that turns raw event footage into a finished 9:16 highlight reel, using ffmpeg scene-change detection and audio-energy analysis to pick and order the best moments. It's built for people who film everything and edit nothing — club officers, event hosts, and anyone who wants an Instagram/TikTok-ready recap without opening a timeline.

Everything runs on your own machine with `ffmpeg` and Python. There's no cloud upload step and no API keys to configure.

**Your night, already edited.**

## Quickstart

Prerequisites: [`ffmpeg`](https://ffmpeg.org/) on your `PATH`, Python 3.11+, and [`uv`](https://docs.astral.sh/uv/) — `uv run` installs everything else automatically into an isolated environment.

```bash
git clone https://github.com/Yusuf-Gadelrab/eventreels.git
cd eventreels
```

**Command line** (`reelsmith`):
```bash
cd reelsmith
uv run reelsmith party.mov -o reel.mp4 --duration 30 --title "RUSH WEEK"
uv run reelsmith party.mov -o reel.mp4 --duration 30 --music bed.mp3
uv run reelsmith party.mov -o reel.mp4 --duration 30 --beat-sync --captions
```

**Web studio** (drag-and-drop UI at `http://127.0.0.1:8910`):
```bash
cd web
./run.sh
```
Drag footage in, watch the four-stage pipeline work, preview the reel in a phone frame, download.

## How it works

`reelsmith` is the editing engine (a `uv`-managed Python package); `web` is a FastAPI studio UI built on top of it. Both drive the same pipeline:

1. **Watch** — ffmpeg scene-change detection scores every frame to find visual cuts and motion bursts.
2. **Listen** — per-half-second RMS loudness analysis reads crowd noise and music drops as an audio-energy signal.
3. **Pick** — footage is split into 1.5–6s segments between scene cuts, each segment scored on loudness and motion, then greedy-selected to hit the target reel length and re-sorted chronologically so the reel tells the night in order.
4. **Cut** — selected segments are cover-cropped to 1080×1920 @30fps, rendered H.264/AAC with per-clip fades, and loudness-normalized to **-14 LUFS** (the Instagram/TikTok/YouTube integrated-loudness target).

Optional layers on top of the core pipeline: beat-syncing cut points to a music bed or the source audio's own beat grid (`--beat-sync`), burned-in captions from local speech transcription via `faster-whisper` (`--captions`, no cloud call), and four pacing templates — Rush, Game Day, Formal, Hackathon — that change segment length and title styling.

`reelsmith` has real Python dependencies (`opencv-python`, `librosa`, `mediapipe`, `faster-whisper`), managed by `uv` — it is **not** a zero-dependency script. What it doesn't have is a cloud dependency: every dependency installs and runs locally, nothing leaves your machine, and no API key is ever required.

## Status

This is a personal, actively-evolving project with no hosted deployment and no users yet — treat it as alpha, not a finished product. The CLI (`reelsmith`) and its test suite are the more mature half; the FastAPI web studio (Huey/SQLite job queue, a reel library, shareable `/r/{id}` watch pages) is newer and rougher around the edges. Expect sharp corners.

```bash
cd reelsmith && uv run pytest -q      # or: python3 -m unittest discover -s tests
cd web && uv run pytest tests/
```
The suite generates synthetic quiet→loud→quiet footage and asserts the pipeline picks the loud window and renders a valid vertical reel. Whisper transcription integration tests are optional, gated behind `REELSMITH_SLOW_TESTS=1`.

## What's new (June 2026)
- **Reel Library:** persistent storage of your finished reels in SQLite.
- **Shareable watch pages:** watch, unfurl, and share your finished reels via `/r/{id}`.
- **Thumbnail library:** studio UI now has a library strip for quick access to your history.
- **Templates:** Rush, Game, Formal, and Hackathon pacing/title presets.
- **Captioning:** automatic local transcription and caption burning.

## License

There is no OSI open-source license on this repository. Source is public for portfolio and evaluation purposes only — no permission is granted to copy, modify, or redistribute this code. See [`reelsmith/README.md`](reelsmith/README.md) for the exact terms. All rights reserved, © 2026 Yusuf Gadelrab.

## More from this author

- [DIRA](https://github.com/Yusuf-Gadelrab/dira) — zero-dependency security scanner for startup codebases
- [EcoImpact](https://github.com/Yusuf-Gadelrab/ecoimpact) — local-first litter map + cleanup impact meter
- [EdgeLog](https://github.com/Yusuf-Gadelrab/edgelog) — trade journal analyzer

## About the author

Built by **Yusuf Gadelrab** — computer science student at San José State University (BS Computer Science, expected May 2028), and a co-author on the poster "Exploring Bilingual Coding for Inclusive Computer Science Learning" at the ACM SIGCSE Technical Symposium 2026 ([DOI 10.1145/3770761.3777339](https://doi.org/10.1145/3770761.3777339)).

- Project page: <https://yusuf-gadelrab.github.io/eventreels.html>
- Portfolio: <https://yusuf-gadelrab.github.io/>
- About / FAQ: <https://yusuf-gadelrab.github.io/about.html>
- Guides: <https://yusuf-gadelrab.github.io/guides.html>
- Contact: yusuf.gadelrab06@gmail.com
