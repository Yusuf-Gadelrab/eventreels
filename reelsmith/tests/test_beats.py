import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reelsmith import analyze, beats, select  # noqa: E402
from reelsmith.cli import make_reel  # noqa: E402

FIXTURE = Path(__file__).parent / "fixture.mp4"
CLICK = Path(__file__).parent / "click_120bpm.wav"
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


def make_click_track() -> None:
    if CLICK.exists():
        return
    expr = r"aevalsrc=if(lt(mod(t\,0.5)\,0.03)\,sin(6283.1853*t)\,0):d=20:s=44100"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", expr,
        "-c:a", "pcm_s16le", str(CLICK),
    ], check=True, capture_output=True)


class TestBeats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        make_fixture()
        make_click_track()

    def test_detects_click_track_beats(self):
        detected = beats.detect_beats(str(CLICK))
        self.assertGreaterEqual(len(detected), 34)
        self.assertLessEqual(len(detected), 42)
        spacings = [b - a for a, b in zip(detected, detected[1:])]
        mean_spacing = sum(spacings) / len(spacings)
        self.assertAlmostEqual(mean_spacing, 0.5, delta=0.05)

    def test_snap_segments_to_beats(self):
        moved = select.snap_segments_to_beats(
            [select.Segment(3.50, 4.95)], [5.0]
        )
        self.assertEqual(moved[0].end, 5.0)

        too_short = select.snap_segments_to_beats(
            [select.Segment(4.20, 5.20)], [4.50]
        )
        self.assertEqual(too_short[0].start, 4.20)
        self.assertEqual(too_short[0].dur, 1.0)

    def test_full_pipeline_with_music_bed(self):
        out = FIXTURE.parent / "out_music.mp4"
        make_reel(str(FIXTURE), str(out), target=10.0, music=str(CLICK), verbose=False)
        self.assertTrue(out.exists())
        self.assertLessEqual(abs(analyze.duration_of(str(out)) - 10.0), 1.5)
        out.unlink()


if __name__ == "__main__":
    unittest.main()
