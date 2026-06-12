import argparse
import sys

from . import analyze, beats, captions as captioning, render, select, template


def make_reel(source: str | list[str], out: str, target: float = 30.0,
              title: str | None = None, verbose: bool = True,
              music: str | None = None, beat_sync: bool = False,
              captions: bool = False, tpl_name: str | None = None,
              watermark: bool = False) -> str:
    tpl = template.get_template(tpl_name)
    def log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    sources = [source] if isinstance(source, str) else source
    segs: list[select.Segment] = []
    energy_by_src: dict[int, list] = {}
    motion_by_src: dict[int, list] = {}
    for i, src in enumerate(sources):
        dur = analyze.duration_of(src)
        cuts = analyze.detect_scene_cuts(src)
        energy_by_src[i] = analyze.audio_energy(src, normalize=True)
        motion_by_src[i] = analyze.motion_energy(src)
        clip_segs = select.build_segments(dur, cuts, tpl)
        for s in clip_segs:
            s.src = i
        segs += clip_segs
        log(f"• clip {i + 1}/{len(sources)}: {dur:.1f}s, {len(cuts)} cuts, "
            f"{len(energy_by_src[i])} audio + {len(motion_by_src[i])} motion windows")

    segs = select.score_multi(segs, energy_by_src, motion_by_src)
    chosen = select.pick(segs, target, tpl)
    if music:
        bed_beats = beats.detect_beats(music)
        if bed_beats:
            chosen = select.snap_segments_to_timeline_beats(chosen, bed_beats)
            log(f"• beat-sync: snapped cuts to {len(bed_beats)} music-bed beats")
        else:
            log("• beat-sync: no music-bed beats detected; keeping selected cuts")
    elif beat_sync:
        snapped: list[select.Segment] = []
        beat_total = 0
        for i, src in enumerate(sources):
            src_beats = beats.detect_beats(src)
            beat_total += len(src_beats)
            src_segments = [s for s in chosen if s.src == i]
            snapped.extend(select.snap_segments_to_beats(src_segments, src_beats))
        if beat_total:
            chosen = sorted(snapped, key=lambda s: (s.src, s.start))
            log(f"• beat-sync: snapped cuts to {beat_total} source-audio beats")
        else:
            log("• beat-sync: no source-audio beats detected; keeping selected cuts")

    total = sum(s.dur for s in chosen)
    log(f"• selected {len(chosen)} moments ({total:.1f}s of {target:.0f}s target)")
    for s in chosen:
        log(f"    clip{s.src + 1} {s.start:7.2f}–{s.end:7.2f}  score={s.score:.2f}")

    caption_rows = []
    if captions:
        log("• captioning selected speech moments")
        for i, src in enumerate(sources):
            src_segments = [s for s in chosen if s.src == i]
            for cap in captioning.transcribe_segments(src, src_segments):
                cap["src"] = i
                caption_rows.append(cap)
        log(f"• captions: {len(caption_rows)} chunks")

    render.render(sources, chosen, out, title=title, music_path=music,
                  captions=caption_rows, tpl=tpl, watermark=watermark)
    log(f"✓ reel written: {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(prog="reelsmith",
                                 description="Raw event footage in, vertical highlight reel out.")
    ap.add_argument("source", nargs="+", help="input video file(s) — pass several clips from the same event")
    ap.add_argument("-o", "--out", default="reel.mp4")
    ap.add_argument("-d", "--duration", type=float, default=30.0, help="target reel length, seconds")
    ap.add_argument("-t", "--title", default=None, help="title card text (first 2.5s)")
    ap.add_argument("--music", default=None, help="optional music bed (mp3/m4a/wav)")
    ap.add_argument("--beat-sync", action="store_true",
                    help="snap cuts to beats detected from source audio when no music bed is set")
    ap.add_argument("--captions", action="store_true",
                    help="transcribe selected speech locally and burn short captions")
    ap.add_argument("-q", "--quiet", action="store_true")
    ap.add_argument("--template", choices=list(template.TEMPLATES.keys()), default="auto",
                    help="event preset changing pacing and title style")
    ap.add_argument("--watermark", action="store_true", help="burn a watermark onto the reel")
    args = ap.parse_args()
    try:
        make_reel(args.source, args.out, args.duration, args.title, verbose=not args.quiet,
                  music=args.music, beat_sync=args.beat_sync, captions=args.captions,
                  tpl_name=args.template, watermark=args.watermark)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
