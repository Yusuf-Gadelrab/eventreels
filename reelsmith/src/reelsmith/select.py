"""Turn analysis into an edit decision list: which moments make the reel."""

from dataclasses import dataclass

from .analyze import EnergyWindow
from .template import TemplateConfig


@dataclass
class Segment:
    start: float
    end: float
    score: float = 0.0
    src: int = 0  # index into the source-clip list

    @property
    def dur(self) -> float:
        return self.end - self.start


def build_segments(duration: float, scene_cuts: list[float], tpl: TemplateConfig | None = None) -> list[Segment]:
    """Candidate segments between scene cuts; uniform slicing when footage has no cuts."""
    if tpl is None:
        tpl = TemplateConfig()
    bounds = [0.0] + [c for c in scene_cuts if 0 < c < duration] + [duration]
    segs: list[Segment] = []
    for a, b in zip(bounds, bounds[1:]):
        length = b - a
        if length < tpl.min_seg:
            continue
        n = max(1, int(length // tpl.max_seg) + (1 if length % tpl.max_seg >= tpl.min_seg else 0))
        step = length / n
        for i in range(n):
            s, e = a + i * step, min(a + (i + 1) * step, b)
            if e - s >= tpl.min_seg:
                segs.append(Segment(round(s, 2), round(e, 2)))
    return segs


AUDIO_WEIGHT = 0.7
MOTION_WEIGHT = 0.3


def _normalized(segs: list[Segment], windows: list[EnergyWindow]) -> list[float]:
    """Mean window value per segment, normalized 0..1 across the footage."""
    if not windows:
        return [0.5] * len(segs)
    lo = min(w.rms_db for w in windows)
    hi = max(w.rms_db for w in windows)
    span = (hi - lo) or 1.0
    out = []
    for s in segs:
        inside = [w.rms_db for w in windows if s.start <= w.t < s.end]
        mean = sum(inside) / len(inside) if inside else lo
        out.append((mean - lo) / span)
    return out


def score_segments(segs: list[Segment], energy: list[EnergyWindow],
                   motion: list[EnergyWindow] | None = None) -> list[Segment]:
    """Loudness finds the crowd; motion finds the action when the camera never cuts."""
    audio = _normalized(segs, energy)
    if motion:
        visual = _normalized(segs, motion)
        for s, a, v in zip(segs, audio, visual):
            s.score = AUDIO_WEIGHT * a + MOTION_WEIGHT * v
    else:
        for s, a in zip(segs, audio):
            s.score = a
    return segs


def score_multi(segs: list[Segment], energy_by_src: dict[int, list[EnergyWindow]],
                motion_by_src: dict[int, list[EnergyWindow]]) -> list[Segment]:
    """Cross-clip scoring: normalize loudness/motion over ALL clips so a loud clip's moments
    outrank a quiet clip's, instead of each clip grading itself on a curve."""
    def globally(windows_by_src: dict[int, list[EnergyWindow]], weight: float) -> None:
        all_vals = [w.rms_db for ws in windows_by_src.values() for w in ws]
        if not all_vals:
            for s in segs:
                s.score += weight * 0.5
            return
        lo, hi = min(all_vals), max(all_vals)
        span = (hi - lo) or 1.0
        for s in segs:
            inside = [w.rms_db for w in windows_by_src.get(s.src, []) if s.start <= w.t < s.end]
            mean = sum(inside) / len(inside) if inside else lo
            s.score += weight * (mean - lo) / span

    for s in segs:
        s.score = 0.0
    globally(energy_by_src, AUDIO_WEIGHT)
    globally(motion_by_src, MOTION_WEIGHT)
    return segs


def pick(segs: list[Segment], target: float, tpl: TemplateConfig | None = None) -> list[Segment]:
    """Greedy best-first up to target length, then clip-then-time order so the reel tells the story in order."""
    if tpl is None:
        tpl = TemplateConfig()
    chosen: list[Segment] = []
    total = 0.0
    for s in sorted(segs, key=lambda s: s.score, reverse=True):
        if total + s.dur > target + tpl.min_seg:
            continue
        chosen.append(s)
        total += s.dur
        if total >= target:
            break
    return sorted(chosen, key=lambda s: (s.src, s.start))


def _nearest_beat(t: float, beats: list[float], max_shift: float) -> float | None:
    if not beats:
        return None
    beat = min(beats, key=lambda b: abs(b - t))
    return beat if abs(beat - t) <= max_shift else None


def _clone_segments(segments: list[Segment]) -> list[Segment]:
    return [Segment(s.start, s.end, s.score, s.src) for s in segments]


def snap_segments_to_beats(segments: list[Segment], beats: list[float],
                           max_shift: float = 0.35) -> list[Segment]:
    """Move source-time segment boundaries onto nearby beats when it stays valid.

    This is used for source-audio beat sync, where beat timestamps share the same
    timeline as each segment's start/end. Boundaries are left alone if snapping
    would make a segment shorter than 1.0s or overlap an adjacent selected
    segment from the same source clip.
    """
    if not beats:
        return _clone_segments(segments)

    snapped = _clone_segments(segments)
    min_dur = 1.0
    beats = sorted(float(b) for b in beats)

    for i, seg in enumerate(snapped):
        prev_seg = snapped[i - 1] if i > 0 and snapped[i - 1].src == seg.src else None
        next_seg = snapped[i + 1] if i + 1 < len(snapped) and snapped[i + 1].src == seg.src else None

        start = _nearest_beat(seg.start, beats, max_shift)
        if start is not None:
            valid_prev = prev_seg is None or start >= prev_seg.end
            if valid_prev and seg.end - start >= min_dur:
                seg.start = round(start, 2)

        end = _nearest_beat(seg.end, beats, max_shift)
        if end is not None:
            valid_next = next_seg is None or end <= next_seg.start
            if valid_next and end - seg.start >= min_dur:
                seg.end = round(end, 2)

    return snapped


def snap_segments_to_timeline_beats(segments: list[Segment], beats: list[float],
                                    max_shift: float = 0.35) -> list[Segment]:
    """Adjust segment durations so reel cut points land on music-bed beats.

    Music-bed beats are in reel time, not source-clip time. For each selected
    segment, shift its source end by the delta needed to place the cumulative
    reel boundary on a nearby beat. The source start stays fixed so content does
    not jump backward into a previous selected moment.
    """
    if not beats:
        return _clone_segments(segments)

    snapped = _clone_segments(segments)
    beats = sorted(float(b) for b in beats)
    min_dur = 1.0
    reel_t = 0.0

    for i, seg in enumerate(snapped):
        cut_t = reel_t + seg.dur
        beat = _nearest_beat(cut_t, beats, max_shift)
        if beat is not None:
            delta = beat - cut_t
            new_end = seg.end + delta
            next_seg = (
                snapped[i + 1]
                if i + 1 < len(snapped) and snapped[i + 1].src == seg.src
                else None
            )
            valid_next = next_seg is None or new_end <= next_seg.start
            if valid_next and new_end - seg.start >= min_dur:
                seg.end = round(new_end, 2)
        reel_t += seg.dur

    return snapped
