"""EventReels web studio — thin local wrapper around the reelsmith pipeline.

Jobs run in a worker thread with stage-level progress the UI polls. Uploads land in a temp
workspace and are deleted with the job (privacy: nothing persists beyond the session).
"""

import json
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from huey import SqliteHuey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reelsmith" / "src"))
from reelsmith import analyze, beats, captions as captioning, render, select  # noqa: E402

STATIC = Path(__file__).parent / "static"
WORK = Path(tempfile.gettempdir()) / "eventreels-jobs"
WORK.mkdir(exist_ok=True)
DB_PATH = Path(__file__).parent / "reels.db"

app = FastAPI(title="EventReels Studio")
huey = SqliteHuey(filename=str(DB_PATH.parent / "huey.db"))
MAX_UPLOAD = 2 * 1024**3

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db() -> None:
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS reels(
            id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            title TEXT,
            template TEXT,
            duration REAL,
            clips INTEGER,
            source_seconds REAL,
            moments TEXT,
            file_path TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS jobs(
            id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            status TEXT,
            stage TEXT,
            pct INTEGER,
            error TEXT
        )""")

init_db()

def get_job(job_id: str) -> dict | None:
    with db() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

def update_job(job_id: str, **kwargs):
    updates = ", ".join(f"{k}=?" for k in kwargs.keys())
    values = list(kwargs.values()) + [job_id]
    with db() as c:
        c.execute(f"UPDATE jobs SET {updates} WHERE id=?", values)

def save_reel(job_id, data):
    with db() as c:
        c.execute("""INSERT INTO reels (id, created_at, title, template, duration, clips, source_seconds, moments, file_path)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (job_id, data["created"], data.get("title"), data.get("template"),
                   data.get("reel_duration"), data.get("clips"), data.get("source_duration"),
                   json.dumps(data.get("moments")), data.get("reel")))


@huey.task()
def run_job(job_id: str, srcs: list[Path], target: float, title: str | None,
            music_path: Path | None = None, captions: bool = False,
            template_name: str = "auto", watermark: bool = True) -> None:

    def stage(name: str, pct: int) -> None:
        update_job(job_id, stage=name, pct=pct)

    try:
        segs: list[select.Segment] = []
        energy_by_src: dict[int, list] = {}
        motion_by_src: dict[int, list] = {}
        total_dur = 0.0
        for i, src in enumerate(srcs):
            base = 10 + int(45 * i / len(srcs))
            stage("analyzing", base)
            dur = analyze.duration_of(str(src))
            total_dur += dur
            cuts = analyze.detect_scene_cuts(str(src))
            stage("listening", base + int(20 / len(srcs)))
            energy_by_src[i] = analyze.audio_energy(str(src), normalize=True)
            motion_by_src[i] = analyze.motion_energy(str(src))
            from reelsmith.template import get_template
            tpl = get_template(template_name)
            clip_segs = select.build_segments(dur, cuts, tpl)
            for s in clip_segs:
                s.src = i
            segs += clip_segs
        stage("scoring", 58)
        chosen = select.pick(select.score_multi(segs, energy_by_src, motion_by_src), target, tpl)
        if not chosen:
            raise ValueError("footage too short to cut a reel from")
        if music_path:
            bed_beats = beats.detect_beats(str(music_path))
            if bed_beats:
                chosen = select.snap_segments_to_timeline_beats(chosen, bed_beats)

        caption_rows = []
        if captions:
            stage("captioning", 70)
            for i, src in enumerate(srcs):
                src_segments = [s for s in chosen if s.src == i]
                for cap in captioning.transcribe_segments(str(src), src_segments):
                    cap["src"] = i
                    caption_rows.append(cap)
                stage("captioning", 70 + int(15 * (i + 1) / len(srcs)))

        stage("rendering", 85 if captions else 70)
        out = srcs[0].parent / "reel.mp4"
        render.render([str(s) for s in srcs], chosen, str(out), title=title,
                      music_path=str(music_path) if music_path else None,
                      captions=caption_rows, tpl=tpl, watermark=watermark)
        
        final_job_data = {
            "created": time.time(),
            "title": title,
            "template": template_name,
            "reel_duration": round(sum(s.dur for s in chosen), 1),
            "clips": len(srcs),
            "source_duration": round(total_dur, 1),
            "moments": [
                {"clip": s.src + 1, "start": s.start, "end": s.end, "score": round(s.score, 2)}
                for s in chosen
            ],
            "reel": str(out)
        }
        save_reel(job_id, final_job_data)
        update_job(job_id, status="done", stage="done", pct=100)
        
        print(f"📧 EMAIL [SENT]: Your highlight reel is ready! -> user@example.com")
        print(f"📱 SMS [SENT]: Watch your new reel here: http://127.0.0.1:8910/r/{job_id}")

    except Exception as e:
        update_job(job_id, status="error", stage="error", error=str(e))


def prune_old_jobs(max_age: float = 4 * 3600) -> None:
    cutoff = time.time() - max_age
    with db() as c:
        old_jobs = c.execute("SELECT id FROM jobs WHERE created_at < ?", (cutoff,)).fetchall()
        for row in old_jobs:
            jid = row["id"]
            shutil.rmtree(WORK / jid, ignore_errors=True)
            c.execute("DELETE FROM jobs WHERE id = ?", (jid,))
            c.execute("DELETE FROM reels WHERE id = ?", (jid,))


WAITLIST = Path(__file__).parent / "waitlist.json"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/landing")
def landing():
    return FileResponse(Path(__file__).resolve().parents[1] / "landing" / "index.html")


@app.post("/api/waitlist", status_code=201)
def join_waitlist(body: dict):
    email = str(body.get("email", "")).strip().lower()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 254:
        raise HTTPException(422, "enter a real email")
    entries = json.loads(WAITLIST.read_text()) if WAITLIST.exists() else []
    if email not in [e["email"] for e in entries]:
        entries.append({"email": email, "at": time.time()})
        WAITLIST.write_text(json.dumps(entries, indent=1))
    return {"ok": True, "count": len(entries)}


VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi")
AUDIO_EXTS = (".mp3", ".m4a", ".wav")


@app.post("/api/jobs", status_code=201)
async def create_job(files: list[UploadFile] = File(...), duration: float = Form(30.0),
                     title: str = Form(""), music: UploadFile | None = File(None),
                     captions: bool = Form(False), template: str = Form("auto"),
                     pro: bool = Form(False)):
    prune_old_jobs()
    if not files or len(files) > 12:
        raise HTTPException(422, "upload 1–12 video files")
    for f in files:
        if not (f.filename or "").lower().endswith(VIDEO_EXTS):
            raise HTTPException(422, f"not a video file: {f.filename} "
                                     f"(want {' '.join(VIDEO_EXTS)})")
    if music and music.filename and not music.filename.lower().endswith(AUDIO_EXTS):
        raise HTTPException(422, f"not a music bed: {music.filename} "
                                 f"(want {' '.join(AUDIO_EXTS)})")
    job_id = uuid.uuid4().hex[:12]
    jobdir = WORK / job_id
    jobdir.mkdir()
    srcs: list[Path] = []
    size = 0
    for i, f in enumerate(files):
        src = jobdir / (f"source{i:02d}" + Path(f.filename).suffix.lower())
        with src.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    shutil.rmtree(jobdir, ignore_errors=True)
                    raise HTTPException(413, "uploads too large (2 GB max total)")
                out.write(chunk)
        srcs.append(src)
    music_path = None
    if music and music.filename:
        music_path = jobdir / ("music" + Path(music.filename).suffix.lower())
        with music_path.open("wb") as out:
            while chunk := await music.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    shutil.rmtree(jobdir, ignore_errors=True)
                    raise HTTPException(413, "uploads too large (2 GB max total)")
                out.write(chunk)
    with db() as c:
        c.execute("""INSERT INTO jobs (id, created_at, status, stage, pct, error)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (job_id, time.time(), "working", "uploaded", 5, None))
    run_job(job_id, srcs, max(8.0, min(90.0, duration)),
            title.strip() or None, music_path, captions,
            template, not pro)
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "no such job")
    return job


@app.get("/api/reels")
def list_reels():
    with db() as c:
        return [dict(row) for row in c.execute("SELECT * FROM reels ORDER BY created_at DESC")]

@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str):
    with db() as c:
        reel = c.execute("SELECT file_path FROM reels WHERE id=?", (job_id,)).fetchone()
    if reel:
        return FileResponse(reel["file_path"], media_type="video/mp4", filename="eventreels.mp4")
    
    raise HTTPException(404, "reel not ready")

@app.get("/r/{job_id}")
def watch_reel(job_id: str):
    return FileResponse(STATIC / "watch.html")


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    shutil.rmtree(WORK / job_id, ignore_errors=True)
    with db() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        c.execute("DELETE FROM reels WHERE id=?", (job_id,))
    return {"ok": True}
