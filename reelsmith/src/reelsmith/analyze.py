"""Footage analysis via ffmpeg/ffprobe — no Python media deps."""

import json
import re
import subprocess
from dataclasses import dataclass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def duration_of(path: str) -> float:
    p = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", path,
    ])
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {p.stderr.strip()}")
    return float(json.loads(p.stdout)["format"]["duration"])


def video_size(path: str) -> tuple[int, int]:
    p = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", path,
    ])
    s = json.loads(p.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def detect_scene_cuts(path: str, threshold: float = 0.3) -> list[float]:
    """Timestamps where the visual content changes sharply (cuts, camera moves)."""
    p = _run([
        "ffmpeg", "-hide_banner", "-i", path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ])
    cuts = [float(m) for m in re.findall(r"pts_time:\s*([0-9.]+)", p.stderr)]
    return sorted(set(round(c, 2) for c in cuts))


@dataclass
class EnergyWindow:
    t: float        # window start, seconds
    rms_db: float   # mean RMS loudness, dBFS (higher = louder)


def motion_energy(path: str, window: float = 0.5) -> list[EnergyWindow]:
    """Per-window visual motion via mean luma frame-difference (signalstats YDIF).
    Catches action in continuous handheld footage where scene detection finds no cuts."""
    p = _run([
        "ffmpeg", "-hide_banner", "-i", path,
        "-vf", "signalstats,metadata=mode=print:key=lavfi.signalstats.YDIF:file=-",
        "-f", "null", "-",
    ])
    buckets: dict[int, list[float]] = {}
    t = None
    for line in p.stdout.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"lavfi\.signalstats\.YDIF=([0-9.]+)", line)
        if m and t is not None:
            buckets.setdefault(int(t / window), []).append(float(m.group(1)))
            t = None
    return [EnergyWindow(t=i * window, rms_db=sum(v) / len(v))
            for i, v in sorted(buckets.items())]


def audio_energy(path: str, window: float = 0.5, normalize: bool = False) -> list[EnergyWindow]:
    """Per-window audio loudness. Loud crowd/music ≈ highlight signal.
    If normalize=True, pre-normalizes per-clip loudness so one loud clip can't dominate selection.
    Formula: normalized_dB = raw_dB - clip_mean_dB."""
    p = _run([
        "ffmpeg", "-hide_banner", "-i", path,
        "-af",
        f"aresample=44100,asetnsamples={int(44100 * window)},"
        "astats=metadata=1:reset=1,"
        "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
        "-f", "null", "-",
    ])
    windows: list[EnergyWindow] = []
    t = None
    for line in p.stdout.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        m = re.search(r"lavfi\.astats\.Overall\.RMS_level=(-?[0-9.]+|-inf)", line)
        if m and t is not None:
            val = -90.0 if m.group(1) == "-inf" else float(m.group(1))
            windows.append(EnergyWindow(t=t, rms_db=val))
            t = None
            
    if normalize and windows:
        mean_db = sum(w.rms_db for w in windows) / len(windows)
        for w in windows:
            w.rms_db -= mean_db
            
    return windows
