import unittest
from pathlib import Path
import tempfile
import subprocess
from reelsmith.crop import get_subject_cx

class TestCrop(unittest.TestCase):
    def test_get_subject_cx_no_face(self):
        """Test that get_subject_cx returns 0.5 when no faces are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_vid = Path(tmpdir) / "testsrc.mp4"
            # Create a 2s video with a test pattern (no faces)
            subprocess.run([
                "ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=30",
                "-c:v", "libx264", str(test_vid)
            ], capture_output=True)
            
            cx = get_subject_cx(str(test_vid), 0.0, 2.0)
            self.assertEqual(cx, 0.5)

if __name__ == "__main__":
    unittest.main()
