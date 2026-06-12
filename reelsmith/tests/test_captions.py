import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reelsmith import captions, select  # noqa: E402

FIXTURE = Path(__file__).parent / "fixture.mp4"


def make_fixture() -> None:
    if FIXTURE.exists():
        return
    subprocess.run([
        "ffmpeg", "-hide_banner", "-y",
        "-f", "lavfi", "-i", "testsrc2=duration=20:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        str(FIXTURE),
    ], check=True, capture_output=True)


class TestCaptions(unittest.TestCase):
    def test_chunk_words_caps_words_and_duration(self):
        words = [
            {"start": i * 0.4, "end": i * 0.4 + 0.32, "word": f"w{i}"}
            for i in range(9)
        ]
        chunks = captions.chunk_words(words)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(str(chunk["text"]).split()), 5)
            self.assertLessEqual(float(chunk["end"]) - float(chunk["start"]), 2.2)

    def test_remap_captions_to_reel(self):
        segments = [
            select.Segment(10.0, 12.0, src=0),
            select.Segment(20.0, 23.0, src=0),
        ]
        source_caps = [
            {"start": 10.5, "end": 11.5, "text": "first"},
            {"start": 21.0, "end": 22.0, "text": "second"},
        ]
        remapped = captions.remap_captions_to_reel(source_caps, segments)
        self.assertEqual(remapped, [
            {"start": 0.5, "end": 1.5, "text": "first"},
            {"start": 3.0, "end": 4.0, "text": "second"},
        ])

    @unittest.skipUnless(os.getenv("REELSMITH_SLOW_TESTS") == "1",
                         "requires Whisper model download/cache")
    def test_transcribe_segments_optional_integration(self):
        make_fixture()
        rows = captions.transcribe_segments(str(FIXTURE), [select.Segment(0.0, 3.0)])
        self.assertIsInstance(rows, list)


if __name__ == "__main__":
    unittest.main()
