"""Local speech captioning and source-time to reel-time remapping."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .select import Segment

logger = logging.getLogger(__name__)

Caption = dict[str, float | int | str]


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def chunk_words(words: list[Any], max_words: int = 5, max_duration: float = 2.2,
                segment_start: float | None = None,
                segment_end: float | None = None) -> list[Caption]:
    """Group word-timestamp rows into short caption chunks."""
    chunks: list[Caption] = []
    current: list[str] = []
    start: float | None = None
    end: float | None = None

    def flush() -> None:
        nonlocal current, start, end
        if not current or start is None or end is None:
            current, start, end = [], None, None
            return
        s = max(start, segment_start) if segment_start is not None else start
        e = min(end, segment_end) if segment_end is not None else end
        if e > s:
            chunks.append({"start": round(s, 2), "end": round(e, 2),
                           "text": " ".join(current)})
        current, start, end = [], None, None

    for word in words:
        text = str(_field(word, "word", "")).strip()
        if not text:
            continue
        w_start = float(_field(word, "start", 0.0))
        w_end = float(_field(word, "end", w_start))
        next_start = w_start if start is None else start
        would_run_long = current and (w_end - next_start > max_duration)
        would_overflow = current and len(current) >= max_words
        if would_run_long or would_overflow:
            flush()
        if start is None:
            start = w_start
        end = w_end
        current.append(text)

    flush()
    return chunks


def transcribe_segments(video_path: str, segments: list[Segment]) -> list[Caption]:
    """Transcribe selected source-time segments using faster-whisper when available.

    Any import, model-download, or transcription failure degrades to no captions
    so rendering can still complete locally.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - environment-dependent fallback
        logger.warning("captions unavailable: could not import faster-whisper (%s)", exc)
        return []

    if not segments:
        return []

    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
    except Exception as exc:  # pragma: no cover - model download/cache dependent
        logger.warning("captions unavailable: could not load Whisper base model (%s)", exc)
        return []

    captions: list[Caption] = []
    with tempfile.TemporaryDirectory(prefix="reelsmith-captions-") as tmp:
        tmpdir = Path(tmp)
        for i, seg in enumerate(segments):
            wav = tmpdir / f"seg{i:03d}.wav"
            p = subprocess.run([
                "ffmpeg", "-hide_banner", "-y",
                "-ss", f"{seg.start:.2f}", "-t", f"{seg.dur:.2f}",
                "-i", video_path,
                "-vn", "-ac", "1", "-ar", "16000", "-f", "wav",
                str(wav),
            ], capture_output=True, text=True)
            if p.returncode != 0:
                logger.warning("caption audio extraction failed for %.2f-%.2f: %s",
                               seg.start, seg.end, p.stderr[-500:])
                continue
            try:
                transcript, _ = model.transcribe(str(wav), word_timestamps=True,
                                                 vad_filter=True)
                words: list[dict[str, float | str]] = []
                for item in transcript:
                    for word in item.words or []:
                        words.append({
                            "start": seg.start + float(word.start),
                            "end": seg.start + float(word.end),
                            "word": str(word.word).strip(),
                        })
                captions.extend(chunk_words(words, segment_start=seg.start,
                                            segment_end=seg.end))
            except Exception as exc:  # pragma: no cover - model/runtime dependent
                logger.warning("caption transcription failed for %.2f-%.2f: %s",
                               seg.start, seg.end, exc)
    return captions


def remap_captions_to_reel(captions: list[Caption],
                           segments: list[Segment]) -> list[Caption]:
    """Map source-time captions into the concatenated reel timeline."""
    remapped: list[Caption] = []
    reel_offset = 0.0
    for seg in segments:
        for cap in captions:
            cap_src = int(cap.get("src", 0))
            if cap_src != seg.src:
                continue
            start = float(cap["start"])
            end = float(cap["end"])
            overlap_start = max(start, seg.start)
            overlap_end = min(end, seg.end)
            if overlap_end <= overlap_start:
                continue
            remapped.append({
                "start": round(reel_offset + (overlap_start - seg.start), 2),
                "end": round(reel_offset + (overlap_end - seg.start), 2),
                "text": str(cap["text"]),
            })
        reel_offset += seg.dur
    return sorted(remapped, key=lambda c: (float(c["start"]), float(c["end"])))
