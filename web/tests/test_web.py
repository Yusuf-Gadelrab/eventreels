import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURE = Path(__file__).parent / "fixture.mp4"
CLICK = Path(__file__).parent / "click_120bpm.wav"


def make_fixture() -> None:
    if FIXTURE.exists():
        return
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=duration=20:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
        "-af", "volume='if(between(t,8,14),2.0,0.02)':eval=frame",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(FIXTURE),
    ], check=True, capture_output=True)


def make_click_track() -> None:
    if CLICK.exists():
        return
    expr = r"aevalsrc=if(lt(mod(t\,0.5)\,0.03)\,sin(6283.1853*t)\,0):d=10:s=44100"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", expr,
        "-c:a", "pcm_s16le", str(CLICK),
    ], check=True, capture_output=True)


def test_upload_to_reel_flow(tmp_path):
    make_fixture()
    c = TestClient(main.app)

    r = c.post("/api/jobs", files=[("files", ("party.mp4", FIXTURE.read_bytes(), "video/mp4"))],
               data={"duration": "8", "title": "TEST NIGHT", "captions": "false"})
    assert r.status_code == 201
    job_id = r.json()["id"]

    for _ in range(120):
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(1)
    assert j["status"] == "done", j.get("error")
    assert j["pct"] == 100
    assert j["moments"], "no moments reported"

    v = c.get(f"/api/jobs/{job_id}/video")
    assert v.status_code == 200
    assert v.headers["content-type"] == "video/mp4"
    assert len(v.content) > 50_000

    assert c.delete(f"/api/jobs/{job_id}").json() == {"ok": True}
    assert c.get(f"/api/jobs/{job_id}").status_code == 404


def test_rejects_non_video():
    c = TestClient(main.app)
    r = c.post("/api/jobs", files=[("files", ("notes.txt", b"hello", "text/plain"))],
               data={"duration": "30"})
    assert r.status_code == 422


def test_multiclip_job():
    make_fixture()
    c = TestClient(main.app)
    data = FIXTURE.read_bytes()
    r = c.post("/api/jobs", files=[("files", ("a.mp4", data, "video/mp4")),
                                   ("files", ("b.mp4", data, "video/mp4"))],
               data={"duration": "8"})
    assert r.status_code == 201
    job_id = r.json()["id"]
    j = {}
    for _ in range(180):
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(1)
    assert j["status"] == "done", j.get("error")
    assert j["clips"] == 2
    assert {m["clip"] for m in j["moments"]} <= {1, 2}
    c.delete(f"/api/jobs/{job_id}")


def test_music_bed_job():
    make_fixture()
    make_click_track()
    c = TestClient(main.app)
    r = c.post(
        "/api/jobs",
        files=[
            ("files", ("party.mp4", FIXTURE.read_bytes(), "video/mp4")),
            ("music", ("bed.wav", CLICK.read_bytes(), "audio/wav")),
        ],
        data={"duration": "8", "captions": "false"},
    )
    assert r.status_code == 201
    job_id = r.json()["id"]
    j = {}
    for _ in range(120):
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(1)
    assert j["status"] == "done", j.get("error")
    assert Path(main.jobs[job_id]["reel"]).exists()
    c.delete(f"/api/jobs/{job_id}")


def test_waitlist(tmp_path):
    main.WAITLIST = tmp_path / "wl.json"
    c = TestClient(main.app)
    assert c.post("/api/waitlist", json={"email": "nope"}).status_code == 422
    r = c.post("/api/waitlist", json={"email": "Yusuf@SJSU.edu"})
    assert r.status_code == 201 and r.json()["count"] == 1
    r = c.post("/api/waitlist", json={"email": "yusuf@sjsu.edu"})
    assert r.json()["count"] == 1  # deduped case-insensitively
    assert c.get("/landing").status_code == 200
