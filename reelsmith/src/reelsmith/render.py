"""Render the chosen segments into a 9:16 vertical reel with ffmpeg."""

import subprocess
import tempfile
from pathlib import Path

from .captions import Caption, remap_captions_to_reel
from .crop import get_subject_cx
from .select import Segment
from .template import TemplateConfig

W, H = 1080, 1920


def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{p.stderr[-2000:]}")


def _has_filter(name: str) -> bool:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return f" {name} " in p.stdout


def _has_drawtext() -> bool:
    return _has_filter("drawtext")


def _has_subtitles() -> bool:
    return _has_filter("subtitles")


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = int(t % 60)
    centis = int(round((t - int(t)) * 100))
    if centis == 100:
        seconds += 1
        centis = 0
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _ass_text(text: str) -> str:
    words = text.replace("{", "").replace("}", "").replace("\\", "").split()
    if len(words) > 3:
        mid = (len(words) + 1) // 2
        return " ".join(words[:mid]) + r"\N" + " ".join(words[mid:])
    return " ".join(words)


def _write_ass(path: Path, captions: list[Caption], segments: list[Segment]) -> int:
    events = remap_captions_to_reel(captions, segments)
    if not events:
        return 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ReelCaption,Arial,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,5,0,2,80,80,422,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cap in events:
        lines.append(
            "Dialogue: 0,"
            f"{_ass_time(float(cap['start']))},"
            f"{_ass_time(float(cap['end']))},"
            "ReelCaption,,0,0,0,,"
            f"{_ass_text(str(cap['text']))}\n"
        )
    path.write_text("".join(lines))
    return len(events)


def _video_filter(title: str | None, ass_path: Path | None, tpl: TemplateConfig | None = None, watermark: bool = False) -> str | None:
    if tpl is None:
        tpl = TemplateConfig()
    filters: list[str] = []
    if ass_path is not None:
        filters.append(f"subtitles='{_filter_path(ass_path)}'")
    if title:
        safe = title.replace("\\", "").replace("'", "’").replace(":", "\\:")
        filters.append(
            f"drawtext=text='{safe}':fontsize={tpl.title.font_size}:fontcolor=white:"
            f"borderw=6:bordercolor=black:x=(w-text_w)/2:y={tpl.title.y_expr}:"
            f"enable='lt(t,{tpl.title.duration})'"
        )
    if watermark:
        filters.append(
            f"drawtext=text='EventReels':fontsize=36:fontcolor=white@0.6:"
            f"x=w-text_w-30:y=h-text_h-30:shadowcolor=black@0.4:shadowx=2:shadowy=2"
        )
    return ",".join(filters) if filters else None


def _music_audio_filter(total_duration: float) -> str:
    fade_dur = min(1.5, max(0.0, total_duration))
    fade_start = max(0.0, total_duration - fade_dur)
    return (
        "[0:a]volume=-18dB[orig];"
        f"[1:a]atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st={fade_start:.3f}:d={fade_dur:.3f}[bed];"
        "[orig][bed]amix=inputs=2:duration=first:dropout_transition=0,"
        "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
    )


def render(source: str | list[str], segments: list[Segment], out: str,
           title: str | None = None, music_path: str | None = None,
           captions: list[Caption] | None = None,
           tpl: TemplateConfig | None = None,
           watermark: bool = False) -> str:
    if tpl is None:
        tpl = TemplateConfig()
    sources = [source] if isinstance(source, str) else source
    if not segments:
        raise ValueError("no segments selected — nothing to render")
    FADE = tpl.fade
    with tempfile.TemporaryDirectory(prefix="reelsmith-") as tmp:
        tmpdir = Path(tmp)
        clips = []
        for i, seg in enumerate(segments):
            clip = tmpdir / f"clip{i:03d}.mp4"
            fades = (
                f",fade=t=in:st=0:d={FADE},fade=t=out:st={max(0.0, seg.dur - FADE):.2f}:d={FADE}"
                if seg.dur > 3 * FADE else ""
            )
            cx = get_subject_cx(sources[seg.src], seg.start, seg.dur)
            crop_filter = f"crop={W}:{H}:max(0\\,min(in_w-{W}\\,in_w*{cx:.3f}-{W}/2)):(in_h-{H})/2"
            vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,{crop_filter},setsar=1,fps=30,format=yuv420p" + fades
            
            _run([
                "ffmpeg", "-hide_banner", "-y",
                "-ss", f"{seg.start:.2f}", "-t", f"{seg.dur:.2f}", "-i", sources[seg.src],
                "-vf", vf,
                "-af", f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, seg.dur - FADE):.2f}:d={FADE}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                str(clip),
            ])
            clips.append(clip)

        concat_list = tmpdir / "list.txt"
        concat_list.write_text("".join(f"file '{c}'\n" for c in clips))

        if title and not _has_drawtext():
            print("warn: this ffmpeg build lacks drawtext — skipping title card "
                  "(brew ffmpeg with freetype enables it)", flush=True)
            title = None
        ass_path = None
        if captions:
            if _has_subtitles():
                candidate = tmpdir / "captions.ass"
                if _write_ass(candidate, captions, segments):
                    ass_path = candidate
            else:
                print("warn: this ffmpeg build lacks subtitles/libass — skipping captions "
                      "(brew ffmpeg with libass enables it)", flush=True)
        vf = _video_filter(title, ass_path, tpl, watermark)

        cmd = ["ffmpeg", "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list)]
        if music_path:
            total_duration = sum(s.dur for s in segments)
            cmd += ["-stream_loop", "-1", "-i", music_path]
            filters = [_music_audio_filter(total_duration)]
            if vf:
                filters.insert(0, f"[0:v]{vf}[vout]")
            cmd += ["-filter_complex", ";".join(filters)]
            if vf:
                cmd += ["-map", "[vout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
            else:
                cmd += ["-map", "0:v:0", "-c:v", "copy"]
            cmd += ["-map", "[aout]", "-c:a", "aac", "-ar", "44100"]
        else:
            if vf:
                cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]
            else:
                cmd += ["-c:v", "copy"]
            cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-ar", "44100"]
        cmd.append(out)
        _run(cmd)
    return out

def render_title_card(text: str, output_path: str):
    # Uses ffmpeg filter_complex to render centered text
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=3",
        "-vf", f"drawtext=text='{text}':fontsize=100:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", output_path
    ], check=True)
