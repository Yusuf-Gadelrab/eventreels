"""End-to-end test on synthetic footage: a quiet→LOUD→quiet soundtrack over moving video.
The pipeline must produce a valid 1080x1920 reel and prefer the loud window (8–14s)."""

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reelsmith import analyze, select  # noqa: E402
from reelsmith.cli import make_reel  # noqa: E402

FIXTURE = Path(__file__).parent / "fixture.mp4"
DURATION = 20


def make_fixture() -> None:
    if FIXTURE.exists():
        return
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", f"testsrc2=duration={DURATION}:size=640x360:rate=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={DURATION}",
        "-af", "volume='if(between(t,8,14),2.0,0.02)':eval=frame",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        str(FIXTURE),
    ], check=True, capture_output=True)


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        make_fixture()

    def test_selection_prefers_loud_window(self):
        dur = analyze.duration_of(str(FIXTURE))
        cuts = analyze.detect_scene_cuts(str(FIXTURE))
        energy = analyze.audio_energy(str(FIXTURE))
        self.assertGreater(len(energy), 10)
        segs = select.score_segments(select.build_segments(dur, cuts), energy)
        chosen = select.pick(segs, target=6.0)
        self.assertTrue(chosen, "picked no segments")
        loud_overlap = sum(
            max(0.0, min(s.end, 14.0) - max(s.start, 8.0)) for s in chosen
        )
        total = sum(s.dur for s in chosen)
        self.assertGreater(loud_overlap / total, 0.5,
                           f"loud-window overlap only {loud_overlap:.1f}s of {total:.1f}s")

    def test_motion_scoring_prefers_action(self):
        """Flat audio, static first half, moving second half — motion must drive selection."""
        fixture = FIXTURE.parent / "fixture_motion.mp4"
        if not fixture.exists():
            subprocess.run([
                "ffmpeg", "-hide_banner", "-y",
                "-f", "lavfi", "-i", "color=c=gray:duration=10:size=640x360:rate=30",
                "-f", "lavfi", "-i", "testsrc2=duration=10:size=640x360:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
                "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                "-map", "[v]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(fixture),
            ], check=True, capture_output=True)
        dur = analyze.duration_of(str(fixture))
        motion = analyze.motion_energy(str(fixture))
        self.assertGreater(len(motion), 10)
        energy = analyze.audio_energy(str(fixture))
        segs = select.score_segments(select.build_segments(dur, []), energy, motion)
        chosen = select.pick(segs, target=6.0)
        action_overlap = sum(max(0.0, min(s.end, 20.0) - max(s.start, 10.0)) for s in chosen)
        total = sum(s.dur for s in chosen)
        self.assertGreater(action_overlap / total, 0.5,
                           f"action-half overlap only {action_overlap:.1f}s of {total:.1f}s")

    def test_multiclip_prefers_loud_clip(self):
        """Two clips, one quiet one loud — cross-clip normalization must favor the loud clip."""
        quiet = FIXTURE.parent / "fixture_quiet.mp4"
        loud = FIXTURE.parent / "fixture_loud.mp4"
        for path, vol in ((quiet, "0.02"), (loud, "2.0")):
            if path.exists():
                continue
            subprocess.run([
                "ffmpeg", "-hide_banner", "-y",
                "-f", "lavfi", "-i", "testsrc2=duration=12:size=640x360:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
                "-af", f"volume={vol}",
                "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(path),
            ], check=True, capture_output=True)
        out = FIXTURE.parent / "out_multi.mp4"
        make_reel([str(quiet), str(loud)], str(out), target=6.0, verbose=False)
        self.assertTrue(out.exists())
        self.assertEqual(analyze.video_size(str(out)), (1080, 1920))
        out.unlink()
        # selection itself must come ≥80% from the loud clip (src=1)
        segs, e, m = [], {}, {}
        for i, p in enumerate((quiet, loud)):
            dur = analyze.duration_of(str(p))
            e[i] = analyze.audio_energy(str(p))
            m[i] = analyze.motion_energy(str(p))
            cs = select.build_segments(dur, [])
            for s in cs:
                s.src = i
            segs += cs
        chosen = select.pick(select.score_multi(segs, e, m), target=6.0)
        loud_time = sum(s.dur for s in chosen if s.src == 1)
        total = sum(s.dur for s in chosen)
        self.assertGreater(loud_time / total, 0.8,
                           f"only {loud_time:.1f}s of {total:.1f}s came from the loud clip")

    def test_end_to_end_render(self):
        out = FIXTURE.parent / "out_reel.mp4"
        make_reel(str(FIXTURE), str(out), target=8.0, title="TEST NIGHT", verbose=False)
        self.assertTrue(out.exists())
        w, h = analyze.video_size(str(out))
        self.assertEqual((w, h), (1080, 1920))
        d = analyze.duration_of(str(out))
        self.assertGreaterEqual(d, 3.0)
        self.assertLessEqual(d, 12.0)
        out.unlink()

    def test_multiclip_normalization(self):
        """With normalization ON, quiet clip still gets >=1 segment in the reel."""
        quiet = FIXTURE.parent / "fixture_quiet.mp4"
        loud = FIXTURE.parent / "fixture_loud.mp4"
        for path, vol in ((quiet, "0.02"), (loud, "2.0")):
            if path.exists(): continue
            subprocess.run([
                "ffmpeg", "-hide_banner", "-y",
                "-f", "lavfi", "-i", "testsrc2=duration=12:size=640x360:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
                "-af", f"volume={vol}",
                "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(path),
            ], check=True, capture_output=True)
            
        segs, e, m = [], {}, {}
        for i, p in enumerate((quiet, loud)):
            dur = analyze.duration_of(str(p))
            e[i] = analyze.audio_energy(str(p), normalize=True)
            m[i] = analyze.motion_energy(str(p))
            cs = select.build_segments(dur, [])
            for s in cs: s.src = i
            segs += cs
        chosen = select.pick(select.score_multi(segs, e, m), target=10.0)
        quiet_segs = [s for s in chosen if s.src == 0]
        self.assertGreaterEqual(len(quiet_segs), 1, "Quiet clip should have >=1 segment when normalized")

    def test_templates_vary_selection(self):
        """rush and formal templates should produce different edit decisions."""
        dur = analyze.duration_of(str(FIXTURE))
        energy = analyze.audio_energy(str(FIXTURE))
        
        from reelsmith.template import get_template
        tpl_rush = get_template("rush")
        segs_rush = select.score_segments(select.build_segments(dur, [], tpl_rush), energy)
        chosen_rush = select.pick(segs_rush, target=10.0, tpl=tpl_rush)
        
        tpl_formal = get_template("formal")
        segs_formal = select.score_segments(select.build_segments(dur, [], tpl_formal), energy)
        chosen_formal = select.pick(segs_formal, target=10.0, tpl=tpl_formal)
        
        self.assertNotEqual([s.dur for s in chosen_rush], [s.dur for s in chosen_formal],
                            "rush and formal should pick different segment durations/pacing")
if __name__ == "__main__":
    unittest.main()
